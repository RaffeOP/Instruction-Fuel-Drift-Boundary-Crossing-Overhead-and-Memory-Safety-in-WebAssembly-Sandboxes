//! Wasmer runs with the official deterministic metering middleware (one fuel unit per
//! WebAssembly operator). Records fuel consumed by each run(reps) call alongside on-CPU time.

use std::fs::{self, File};
use std::io::{BufRead, BufReader, Write};
use std::path::Path;
use std::sync::Arc;
use std::time::Instant;

#[path = "../hwcount.rs"]
mod hwcount;

use wasmer::sys::{Cranelift, EngineBuilder, LLVM, Singlepass};
use wasmer::{Extern, Function, FunctionType, Imports, Instance, Module, Store, Type, TypedFunction, Value};
use wasmer_middlewares::metering::{get_remaining_points, set_remaining_points, MeteringPoints};
use wasmer_middlewares::Metering;

const FUEL_BUDGET: u64 = 1 << 60;
const WARMUP: u32 = 2;

fn thread_cpu_ns() -> u64 {
    let mut spec = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    unsafe { libc::clock_gettime(libc::CLOCK_THREAD_CPUTIME_ID, &mut spec) };
    spec.tv_sec as u64 * 1_000_000_000 + spec.tv_nsec as u64
}

fn zero(ty: &Type) -> Value {
    match ty {
        Type::I64 => Value::I64(0),
        Type::F32 => Value::F32(0.0),
        Type::F64 => Value::F64(0.0),
        _ => Value::I32(0),
    }
}

fn stubs(store: &mut Store, module: &Module) -> Imports {
    let mut imports = Imports::new();
    for import in module.imports() {
        if let wasmer::ExternType::Function(ft) = import.ty() {
            let results: Vec<Type> = ft.results().to_vec();
            let ty = FunctionType::new(ft.params().to_vec(), results.clone());
            let f = Function::new(&mut *store, ty, move |_args: &[Value]| {
                Ok(results.iter().map(zero).collect::<Vec<_>>())
            });
            imports.define(import.module(), import.name(), Extern::from(f));
        }
    }
    imports
}

fn metered_store(backend: &str) -> Store {
    let metering = Arc::new(Metering::new(FUEL_BUDGET, |_op: &wasmer::wasmparser::Operator| 1u64));
    let engine = match backend {
        "singlepass" => {
            let mut c = Singlepass::default();
            wasmer::sys::CompilerConfig::push_middleware(&mut c, metering);
            EngineBuilder::new(c).engine()
        }
        "cranelift" => {
            let mut c = Cranelift::default();
            wasmer::sys::CompilerConfig::push_middleware(&mut c, metering);
            EngineBuilder::new(c).engine()
        }
        "llvm" => {
            let mut c = LLVM::default();
            wasmer::sys::CompilerConfig::push_middleware(&mut c, metering);
            EngineBuilder::new(c).engine()
        }
        other => panic!("unknown backend {other}"),
    };
    Store::new(engine)
}

/// One timed replicate: fuel, CPU and wall time, and hardware counters for a single run(reps) call.
struct Replicate {
    fuel: u64,
    cpu: u64,
    wall: u64,
    cycles: u64,
    instructions: u64,
}

fn timed_replicate(store: &mut Store, instance: &Instance, run: &TypedFunction<i32, i64>, reps: i32) -> Replicate {
    set_remaining_points(store, instance, FUEL_BUDGET);
    let cpu0 = thread_cpu_ns();
    let hw0 = hwcount::read();
    let wall0 = Instant::now();
    run.call(store, reps).expect("timed");
    let wall = wall0.elapsed().as_nanos() as u64;
    let cpu = thread_cpu_ns() - cpu0;
    let hw1 = hwcount::read();
    let fuel = match get_remaining_points(store, instance) {
        MeteringPoints::Remaining(rem) => FUEL_BUDGET - rem,
        MeteringPoints::Exhausted => panic!("metering budget exhausted"),
    };
    Replicate { fuel, cpu, wall, cycles: hw1.cycles - hw0.cycles, instructions: hw1.instructions - hw0.instructions }
}

/// Times one plan row: compiles the module, checks its checksum, warms up, and writes the replicates.
fn run_cell(backend: &str, runtime: &str, row: &[&str], replicates: u32, writer: &mut impl Write) {
    let (kernel, group, opt, path, reps) = (row[0], row[1], row[2], row[3], row[4]);
    let bytes = fs::read(path).expect("module");
    let mut store = metered_store(backend);
    let module = Module::new(&store, &bytes).expect("compile");
    let imports = stubs(&mut store, &module);
    let instance = Instance::new(&mut store, &module, &imports).expect("instantiate");
    set_remaining_points(&mut store, &instance, FUEL_BUDGET);
    let run = instance.exports.get_typed_function::<i32, i64>(&store, "run").expect("run");
    let check = instance.exports.get_typed_function::<(), i64>(&store, "check").expect("check");
    let checksum = check.call(&mut store).expect("check call");
    set_remaining_points(&mut store, &instance, FUEL_BUDGET);
    let r: i32 = reps.parse().unwrap();
    for _ in 0..WARMUP {
        set_remaining_points(&mut store, &instance, FUEL_BUDGET);
        run.call(&mut store, r).expect("warmup");
    }
    for replicate in 0..replicates {
        let m = timed_replicate(&mut store, &instance, &run, r);
        writeln!(writer, "{runtime},{opt},{kernel},{group},{replicate},{reps},{},{},{},{checksum},{},{}",
                 m.fuel, m.cpu, m.wall, m.cycles, m.instructions).unwrap();
    }
    writer.flush().unwrap();
    eprintln!("done {backend} {opt} {kernel}");
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let get = |flag: &str| args.iter().position(|a| a == flag).map(|i| args[i + 1].clone()).expect(flag);
    let backend = get("--backend");
    let plan = get("--plan");
    let out = get("--out");
    let replicates: u32 = get("--replicates").parse().unwrap();
    let runtime = format!("wasmer-{backend}-metered");
    let reader = BufReader::new(File::open(&plan).expect("plan"));
    if let Some(parent) = Path::new(&out).parent() { fs::create_dir_all(parent).unwrap(); }
    let mut writer = File::create(&out).expect("out");
    writeln!(writer, "runtime,opt_level,kernel,group,replicate,reps,fuel,cpu_ns,wall_ns,checksum,cycles,instructions").unwrap();
    for line in reader.lines().skip(1) {
        let line = line.unwrap();
        let row: Vec<&str> = line.split(',').collect();
        run_cell(&backend, &runtime, &row, replicates, &mut writer);
    }
}
