//! RQ3 host-call boundary benchmark with a Rust embedder.
//!
//! The guest (kernels/c_src/host_boundary.c) calls the import `env.host_consume(ptr, len)`
//! `calls` times. The host copies the payload out of linear memory and validates it as UTF-8.
//! The native baseline performs the same copy and validation on a host buffer without the
//! boundary. A third side, `null`, calls the import with length zero and does no work in the
//! host, which measures the guest-to-host transition directly instead of as a fitted intercept.
//!
//! Samples run in a seeded random order of (side, size, replicate). Each row records the
//! per-call thread CPU time and the 1-minute load sampled before it.
//!
//! Usage: host_bench --module host_boundary.wasm --out OUT.csv [--replicates N]

use std::env;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::os::raw::{c_double, c_int};
use std::path::PathBuf;

use wasmtime::{Caller, Engine, Extern, Instance, Linker, Module, Store, TypedFunc};

const SIZES: [usize; 10] = [64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216];
const TARGET_BYTES_PER_SAMPLE: usize = 200_000_000;
const MIN_CALLS: usize = 4;
const MAX_CALLS: usize = 20_000;
const NULL_CALLS: usize = 200_000;
const SEED: u64 = 20261022;

extern "C" {
    fn getloadavg(loads: *mut c_double, count: c_int) -> c_int;
}

fn load1() -> f64 {
    let mut loads = [0.0f64; 3];
    // SAFETY: buffer holds three doubles.
    unsafe { getloadavg(loads.as_mut_ptr(), 3) };
    loads[0]
}

fn thread_cpu_ns() -> u64 {
    let mut spec = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    // SAFETY: clock_gettime writes into the provided timespec.
    let status = unsafe { libc::clock_gettime(libc::CLOCK_THREAD_CPUTIME_ID, &mut spec) };
    assert_eq!(status, 0);
    spec.tv_sec as u64 * 1_000_000_000 + spec.tv_nsec as u64
}

fn calls_for(size: usize) -> usize {
    (TARGET_BYTES_PER_SAMPLE / size).clamp(MIN_CALLS, MAX_CALLS)
}

/// Copies and validates a payload; returns 1 when it is valid UTF-8.
fn consume(bytes: &[u8]) -> i32 {
    let owned = bytes.to_vec();
    i32::from(std::str::from_utf8(std::hint::black_box(&owned)).is_ok())
}

fn host_consume(mut caller: Caller<'_, ()>, pointer: i32, length: i32) -> i32 {
    if length == 0 {
        return 1;
    }
    let Some(Extern::Memory(memory)) = caller.get_export("memory") else {
        return 0;
    };
    let start = pointer as usize;
    let data = memory.data(&caller);
    consume(&data[start..start + length as usize])
}

struct Guest {
    store: Store<()>,
    run: TypedFunc<(i32, i32), i32>,
}

fn instantiate(path: &PathBuf) -> Guest {
    let engine = Engine::default();
    let module = Module::from_file(&engine, path).expect("module");
    let mut linker = Linker::new(&engine);
    linker.func_wrap("env", "host_consume", host_consume).expect("link");
    let mut store = Store::new(&engine, ());
    let instance: Instance = linker.instantiate(&mut store, &module).expect("instantiate");
    let fill = instance.get_typed_func::<i32, ()>(&mut store, "fill").expect("fill");
    fill.call(&mut store, SIZES[SIZES.len() - 1] as i32).expect("fill call");
    let run = instance.get_typed_func::<(i32, i32), i32>(&mut store, "run").expect("run");
    Guest { store, run }
}

fn shuffled_plan(replicates: usize) -> Vec<(&'static str, usize, usize)> {
    let mut plan = Vec::new();
    for replicate in 0..replicates {
        plan.push(("null", 0, replicate));
        for size in SIZES {
            plan.push(("wasm", size, replicate));
            plan.push(("native", size, replicate));
        }
    }
    let mut state = SEED;
    for i in (1..plan.len()).rev() {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        plan.swap(i, (state % (i as u64 + 1)) as usize);
    }
    plan
}

fn main() {
    let mut module = None;
    let mut out = None;
    let mut replicates = 200usize;
    let mut args = env::args().skip(1);
    while let Some(flag) = args.next() {
        let value = args.next().expect("flag value");
        match flag.as_str() {
            "--module" => module = Some(PathBuf::from(value)),
            "--out" => out = Some(PathBuf::from(value)),
            "--replicates" => replicates = value.parse().expect("replicates"),
            other => panic!("unknown flag {other}"),
        }
    }
    let mut guest = instantiate(&module.expect("--module"));
    let native_payload: Vec<u8> = (0..SIZES[SIZES.len() - 1]).map(|i| b'A' + (i % 26) as u8).collect();
    let mut writer = BufWriter::new(File::create(out.expect("--out")).expect("create"));
    writeln!(writer, "side,payload_bytes,replicate,calls,per_call_ns,loadavg_1m").unwrap();
    for _ in 0..3 {
        guest.run.call(&mut guest.store, (1000, 64)).expect("warmup");
    }
    for (side, size, replicate) in shuffled_plan(replicates) {
        let load = load1();
        let calls = if side == "null" { NULL_CALLS } else { calls_for(size) };
        let start = thread_cpu_ns();
        let accepted = match side {
            "native" => (0..calls).map(|_| consume(&native_payload[..size])).sum::<i32>(),
            _ => guest.run.call(&mut guest.store, (calls as i32, size as i32)).expect("run"),
        };
        let elapsed = thread_cpu_ns() - start;
        assert_eq!(accepted as usize, calls, "every call must validate");
        writeln!(writer, "{side},{size},{replicate},{calls},{:.2},{load:.2}", elapsed as f64 / calls as f64).unwrap();
    }
}
