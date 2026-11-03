//! Benchmark runner specifically for Wasmtime (Cranelift and Winch) with fuel metering.
//! Independent of Wasmer or LLVM, compiling cleanly for native ARM64 and x86_64 (Rosetta 2).

use std::env;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;

use wasmtime::{Config, Engine, ExternType, Func, Linker, Module, Store, Strategy, Val, ValType};

#[path = "../hwcount.rs"]
mod hwcount;
#[path = "../plan.rs"]
mod plan;
#[path = "../timing.rs"]
mod timing;

use plan::Cell;
use timing::Stopwatch;

const FUEL_BUDGET: u64 = 1 << 62;
const CSV_HEADER: &str = "runtime,opt_level,kernel,group,replicate,reps,fuel,cpu_ns,wall_ns,checksum,cycles,instructions";

fn zero_value(ty: &ValType) -> Result<Val, String> {
    match ty {
        ValType::I32 => Ok(Val::I32(0)),
        ValType::I64 => Ok(Val::I64(0)),
        ValType::F32 => Ok(Val::F32(0)),
        ValType::F64 => Ok(Val::F64(0)),
        other => Err(format!("no zero value for import result type {other:?}")),
    }
}

fn link_stub_imports(store: &mut Store<()>, engine: &Engine, module: &Module) -> Result<Linker<()>, String> {
    let mut linker = Linker::new(engine);
    for import in module.imports() {
        let ExternType::Func(func_type) = import.ty() else {
            return Err(format!("unsupported non-function import {}.{}", import.module(), import.name()));
        };
        let results: Vec<ValType> = func_type.results().collect();
        let stub = Func::new(&mut *store, func_type.clone(), move |_caller, _params, out| {
            for (slot, ty) in out.iter_mut().zip(results.iter()) {
                *slot = zero_value(ty).expect("stub result type");
            }
            Ok(())
        });
        linker
            .define(&mut *store, import.module(), import.name(), stub)
            .map_err(|e| format!("define {}.{}: {e}", import.module(), import.name()))?;
    }
    Ok(linker)
}

fn build_engine(strategy: Strategy) -> Result<Engine, String> {
    let mut config = Config::new();
    config.strategy(strategy);
    config.consume_fuel(true);
    Engine::new(&config).map_err(|e| format!("engine: {e}"))
}

struct Options {
    runtime: String,
    plan: PathBuf,
    out: PathBuf,
    replicates: u32,
    warmup: u32,
}

fn parse_options() -> Result<Options, String> {
    let mut args = env::args().skip(1);
    let mut runtime = None;
    let mut plan = None;
    let mut out = None;
    let mut replicates = 30;
    let mut warmup = 2;
    while let Some(flag) = args.next() {
        let value = args.next().ok_or_else(|| format!("missing value for {flag}"))?;
        match flag.as_str() {
            "--runtime" => runtime = Some(value),
            "--plan" => plan = Some(PathBuf::from(value)),
            "--out" => out = Some(PathBuf::from(value)),
            "--replicates" => replicates = value.parse().map_err(|e| format!("{e}"))?,
            "--warmup" => warmup = value.parse().map_err(|e| format!("{e}"))?,
            other => return Err(format!("unknown flag {other}")),
        }
    }
    Ok(Options {
        runtime: runtime.ok_or("--runtime required")?,
        plan: plan.ok_or("--plan required")?,
        out: out.ok_or("--out required")?,
        replicates,
        warmup,
    })
}

fn run_cell(
    engine: &Engine,
    cell: &Cell,
    runtime: &str,
    options: &Options,
    writer: &mut dyn Write,
) -> Result<(), String> {
    let wasm_bytes = fs::read(&cell.path).map_err(|e| format!("{}: {e}", cell.path.display()))?;
    let module = Module::new(engine, &wasm_bytes).map_err(|e| format!("compile {}: {e}", cell.path.display()))?;

    // Warmup calls
    for _ in 0..options.warmup {
        let mut store = Store::new(engine, ());
        store.set_fuel(FUEL_BUDGET).map_err(|e| format!("set fuel: {e}"))?;
        let linker = link_stub_imports(&mut store, engine, &module)?;
        let instance = linker
            .instantiate(&mut store, &module)
            .map_err(|e| format!("instantiate {}: {e}", cell.path.display()))?;
        let run_fn = instance
            .get_typed_func::<i32, i64>(&mut store, "run")
            .map_err(|e| format!("lookup run in {}: {e}", cell.path.display()))?;
        let _ = run_fn.call(&mut store, cell.reps as i32);
    }

    // Timed replicates
    for rep in 0..options.replicates {
        let mut store = Store::new(engine, ());
        store.set_fuel(FUEL_BUDGET).map_err(|e| format!("set fuel: {e}"))?;
        let linker = link_stub_imports(&mut store, engine, &module)?;
        let instance = linker
            .instantiate(&mut store, &module)
            .map_err(|e| format!("instantiate {}: {e}", cell.path.display()))?;
        let run_fn = instance
            .get_typed_func::<i32, i64>(&mut store, "run")
            .map_err(|e| format!("lookup run in {}: {e}", cell.path.display()))?;

        let timer = Stopwatch::start();
        let checksum = run_fn.call(&mut store, cell.reps as i32).map_err(|e| format!("call {}: {e}", cell.path.display()))?;
        let measured = timer.stop();

        let fuel_remaining = store.get_fuel().map_err(|e| format!("get fuel: {e}"))?;
        let fuel_used = FUEL_BUDGET.saturating_sub(fuel_remaining);

        writeln!(
            writer,
            "{},{},{},{},{},{},{},{},{},{},{},{}",
            runtime,
            cell.opt_level,
            cell.key,
            cell.group,
            rep,
            cell.reps,
            fuel_used,
            measured.cpu_ns,
            measured.wall_ns,
            checksum,
            measured.cycles,
            measured.instructions,
        )
        .map_err(|e| format!("write row: {e}"))?;
    }
    Ok(())
}

fn main() {
    let options = match parse_options() {
        Ok(opt) => opt,
        Err(msg) => {
            eprintln!("error: {msg}");
            std::process::exit(2);
        }
    };
    let strategy = match options.runtime.as_str() {
        "wasmtime-cranelift" => Strategy::Cranelift,
        "wasmtime-winch" => Strategy::Winch,
        other => {
            eprintln!("error: unsupported runtime {other}; expected wasmtime-cranelift or wasmtime-winch");
            std::process::exit(2);
        }
    };
    let engine = build_engine(strategy).expect("build engine");
    let cells = plan::load(&options.plan).expect("load plan");

    if let Some(parent) = options.out.parent() {
        fs::create_dir_all(parent).expect("create out dir");
    }
    let mut file = OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .open(&options.out)
        .expect("open out file");
    writeln!(file, "{CSV_HEADER}").expect("write header");

    for cell in &cells {
        if let Err(e) = run_cell(&engine, cell, &options.runtime, &options, &mut file) {
            eprintln!("error in cell {}_{}: {e}", cell.key, cell.opt_level);
        }
    }
}
