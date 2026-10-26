//! WASI Preview 1 versus Preview 2 write-cost benchmark.
//! Runs the same guest program as a Preview 1 core module and as a Preview 2 component, on one
//! Wasmtime engine, with stdout inherited (run the binary with stdout redirected to /dev/null).
//! Each measurement is one full invocation (instantiation + program). Per-write cost is
//! (T(writes) - T(0)) / writes, which removes instantiation and startup.

use std::fs::File;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::Instant;

use wasmtime::component::{Component, Linker as ComponentLinker};
use wasmtime::{Config, Engine, Linker, Module, Store};
use wasmtime_wasi::p1::WasiP1Ctx;
use wasmtime_wasi::{ResourceTable, WasiCtx, WasiCtxView, WasiView};

const WRITE_BUDGET_BYTES: u64 = 200_000_000;
const MIN_WRITES: u64 = 10;
const MAX_WRITES: u64 = 20_000;

struct P2State {
    ctx: WasiCtx,
    table: ResourceTable,
}

impl WasiView for P2State {
    fn ctx(&mut self) -> WasiCtxView<'_> {
        WasiCtxView { ctx: &mut self.ctx, table: &mut self.table }
    }
}

fn thread_cpu_ns() -> u64 {
    let mut spec = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    // SAFETY: clock_gettime writes into the provided timespec.
    unsafe { libc::clock_gettime(libc::CLOCK_THREAD_CPUTIME_ID, &mut spec) };
    spec.tv_sec as u64 * 1_000_000_000 + spec.tv_nsec as u64
}

fn guest_args(size: usize, writes: u64) -> Vec<String> {
    vec!["wasi_guest".to_string(), size.to_string(), writes.to_string()]
}

fn run_preview1(engine: &Engine, path: &Path, size: usize, writes: u64) -> wasmtime::Result<()> {
    let mut builder = WasiCtx::builder();
    builder.inherit_stdout().args(&guest_args(size, writes));
    let mut store = Store::new(engine, builder.build_p1());
    let mut linker: Linker<WasiP1Ctx> = Linker::new(engine);
    wasmtime_wasi::p1::add_to_linker_sync(&mut linker, |ctx| ctx)?;
    let module = Module::from_file(engine, path)?;
    let instance = linker.instantiate(&mut store, &module)?;
    let start = instance.get_typed_func::<(), ()>(&mut store, "_start")?;
    start.call(&mut store, ())
}

fn run_preview2(engine: &Engine, path: &Path, size: usize, writes: u64) -> wasmtime::Result<()> {
    let mut builder = WasiCtx::builder();
    builder.inherit_stdout().args(&guest_args(size, writes));
    let mut store = Store::new(engine, P2State { ctx: builder.build(), table: ResourceTable::new() });
    let mut linker: ComponentLinker<P2State> = ComponentLinker::new(engine);
    wasmtime_wasi::p2::add_to_linker_sync(&mut linker)?;
    let component = Component::from_file(engine, path)?;
    let command = wasmtime_wasi::p2::bindings::sync::Command::instantiate(&mut store, &component, &linker)?;
    command
        .wasi_cli_run()
        .call_run(&mut store)?
        .map_err(|()| wasmtime::format_err!("guest exited with failure"))
}

fn timed(f: impl FnOnce() -> wasmtime::Result<()>) -> (u64, u64) {
    let cpu0 = thread_cpu_ns();
    let wall0 = Instant::now();
    f().expect("guest run failed");
    (thread_cpu_ns() - cpu0, wall0.elapsed().as_nanos() as u64)
}

fn writes_for(size: usize) -> u64 {
    (WRITE_BUDGET_BYTES / size as u64).clamp(MIN_WRITES, MAX_WRITES)
}

struct Options {
    p1: PathBuf,
    p2: PathBuf,
    sizes: Vec<usize>,
    replicates: u32,
    out: PathBuf,
}

fn parse() -> Options {
    let args: Vec<String> = std::env::args().collect();
    let get = |flag: &str| args.iter().position(|a| a == flag).map(|i| args[i + 1].clone());
    Options {
        p1: PathBuf::from(get("--p1").expect("--p1")),
        p2: PathBuf::from(get("--p2").expect("--p2")),
        sizes: get("--sizes")
            .expect("--sizes")
            .split(',')
            .map(|s| s.parse().expect("size"))
            .collect(),
        replicates: get("--replicates").expect("--replicates").parse().expect("replicates"),
        out: PathBuf::from(get("--out").expect("--out")),
    }
}

fn main() {
    let options = parse();
    let mut config = Config::new();
    config.wasm_component_model(true);
    let engine = Engine::new(&config).expect("engine");

    // Plan: every (side, size, writes-mode, replicate) cell in a seeded random order.
    let mut plan: Vec<(&str, usize, bool, u32)> = Vec::new();
    for replicate in 0..options.replicates {
        for &size in &options.sizes {
            for side in ["preview1", "preview2"] {
                plan.push((side, size, true, replicate));
                plan.push((side, size, false, replicate));
            }
        }
    }
    let mut state: u64 = 20261024;
    for i in (1..plan.len()).rev() {
        state = state.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        let j = (state >> 33) as usize % (i + 1);
        plan.swap(i, j);
    }

    let mut out = File::create(&options.out).expect("out");
    writeln!(out, "side,payload_bytes,writes,mode,replicate,cpu_ns,wall_ns").unwrap();
    for (side, size, full, replicate) in plan {
        let writes = if full { writes_for(size) } else { 0 };
        let (cpu, wall) = match side {
            "preview1" => timed(|| run_preview1(&engine, &options.p1, size, writes)),
            _ => timed(|| run_preview2(&engine, &options.p2, size, writes)),
        };
        writeln!(
            out,
            "{side},{size},{writes},{},{replicate},{cpu},{wall}",
            if full { "full" } else { "baseline" }
        )
        .unwrap();
    }
    eprintln!("wrote {}", options.out.display());
}
