//! Wasmtime timing with configurable PMU counters (kperf, root required) and a per-replicate
//! load log. Each replicate records fuel, thread CPU and wall time, the 1-minute load average
//! sampled immediately before the call, and the per-thread deltas of the events in EVENTS.
//!
//! The timed thread requests QOS_CLASS_USER_INTERACTIVE so the scheduler prefers performance
//! cores. macOS offers no hard core pinning; the effective clock (cycles per CPU ns) recorded
//! for every replicate identifies replicates that ran on an efficiency core.
//!
//! Usage: sudo pmu_bench --plan PLAN.csv --out OUT.csv [--backend cranelift|winch]
//!        [--replicates N] [--warmup N] [--load-gate L] [--only KEY_SUBSTRING] [--pmu 0|1]
//!        [--flat-bulk 0|1]   (zero the per-byte bulk-memory fuel costs)

#[path = "../plan.rs"]
mod plan;

use std::env;
use std::ffi::CString;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::os::raw::{c_char, c_double, c_int};
use std::path::{Path, PathBuf};
use std::thread;
use std::time::{Duration, Instant};

use wasmtime::{
    Config, Engine, ExternType, Func, Linker, Module, OperatorCost, Store, Strategy, Val, ValType, VariableOperatorCost,
};

const FUEL_BUDGET: u64 = 1 << 62;
const QOS_CLASS_USER_INTERACTIVE: u32 = 0x21;
const LOAD_POLL: Duration = Duration::from_secs(5);
const MAX_GATE_WAIT: Duration = Duration::from_secs(600);
const EVENTS: [&str; 8] = [
    "FIXED_CYCLES",
    "FIXED_INSTRUCTIONS",
    "L1D_CACHE_MISS_LD_NONSPEC",
    "BRANCH_MISPRED_NONSPEC",
    "L1D_TLB_MISS_NONSPEC",
    "LDST_UNIT_WAITING_OLD_L1D_CACHE_MISS",
    "L2_TLB_MISS_DATA",
    "MAP_STALL_DISPATCH",
];
const CSV_HEADER: &str = "runtime,opt_level,kernel,group,replicate,reps,fuel,cpu_ns,wall_ns,load1,\
cycles,instructions,l1d_miss_ld,branch_mispred,l1d_tlb_miss,l1d_miss_wait_cycles,l2_tlb_miss,\
map_stall_dispatch";

extern "C" {
    fn kc_init(names: *const *const c_char, count: usize) -> c_int;
    fn kc_read(out: *mut u64) -> c_int;
    fn kc_shutdown();
    fn getloadavg(loads: *mut c_double, count: c_int) -> c_int;
    fn pthread_set_qos_class_self_np(qos: u32, relative_priority: c_int) -> c_int;
}

struct Options {
    plan: PathBuf,
    out: PathBuf,
    backend: String,
    replicates: u32,
    warmup: u32,
    load_gate: f64,
    only: Option<String>,
    use_pmu: bool,
    flat_bulk: bool,
}

fn parse_options() -> Result<Options, String> {
    let mut options = Options {
        plan: PathBuf::new(),
        out: PathBuf::new(),
        backend: "cranelift".to_string(),
        replicates: 30,
        warmup: 2,
        load_gate: 2.0,
        only: None,
        use_pmu: true,
        flat_bulk: false,
    };
    let mut args = env::args().skip(1);
    while let Some(flag) = args.next() {
        let value = args.next().ok_or_else(|| format!("missing value for {flag}"))?;
        match flag.as_str() {
            "--plan" => options.plan = PathBuf::from(value),
            "--out" => options.out = PathBuf::from(value),
            "--backend" => options.backend = value,
            "--replicates" => options.replicates = value.parse().map_err(|e| format!("{e}"))?,
            "--warmup" => options.warmup = value.parse().map_err(|e| format!("{e}"))?,
            "--load-gate" => options.load_gate = value.parse().map_err(|e| format!("{e}"))?,
            "--only" => options.only = Some(value),
            "--pmu" => options.use_pmu = value != "0",
            "--flat-bulk" => options.flat_bulk = value != "0",
            other => return Err(format!("unknown flag {other}")),
        }
    }
    if options.plan.as_os_str().is_empty() || options.out.as_os_str().is_empty() {
        return Err("--plan and --out are required".to_string());
    }
    Ok(options)
}

fn thread_cpu_ns() -> u64 {
    let mut spec = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    // SAFETY: clock_gettime writes into the provided timespec.
    let status = unsafe { libc::clock_gettime(libc::CLOCK_THREAD_CPUTIME_ID, &mut spec) };
    assert_eq!(status, 0, "clock_gettime failed");
    spec.tv_sec as u64 * 1_000_000_000 + spec.tv_nsec as u64
}

fn load1() -> f64 {
    let mut loads = [0.0f64; 3];
    // SAFETY: the buffer holds three doubles.
    let count = unsafe { getloadavg(loads.as_mut_ptr(), 3) };
    if count < 1 {
        f64::NAN
    } else {
        loads[0]
    }
}

/// Waits until the 1-minute load is at or below the gate. Returns the waited time.
fn wait_for_quiet(gate: f64) -> Duration {
    let started = Instant::now();
    while load1() > gate && started.elapsed() < MAX_GATE_WAIT {
        thread::sleep(LOAD_POLL);
    }
    started.elapsed()
}

fn read_counters(use_pmu: bool) -> [u64; EVENTS.len()] {
    let mut values = [0u64; EVENTS.len()];
    if !use_pmu {
        return values;
    }
    // SAFETY: values has room for every configured event.
    let status = unsafe { kc_read(values.as_mut_ptr()) };
    assert_eq!(status, 0, "kc_read failed");
    values
}

fn init_counters() -> Result<(), String> {
    let names: Vec<CString> = EVENTS.iter().map(|name| CString::new(*name).expect("event name")).collect();
    let pointers: Vec<*const c_char> = names.iter().map(|name| name.as_ptr()).collect();
    // SAFETY: pointers reference NUL-terminated strings that outlive the call.
    let status = unsafe { kc_init(pointers.as_ptr(), pointers.len()) };
    if status == 0 {
        Ok(())
    } else {
        Err("kperf counter setup failed; run with sudo".to_string())
    }
}

fn zero_value(ty: &ValType) -> Val {
    match ty {
        ValType::I32 => Val::I32(0),
        ValType::I64 => Val::I64(0),
        ValType::F32 => Val::F32(0),
        ValType::F64 => Val::F64(0),
        other => panic!("no zero value for {other:?}"),
    }
}

/// Satisfies every import with a no-op; the timed path never reaches them.
fn stub_linker(store: &mut Store<()>, engine: &Engine, module: &Module) -> Result<Linker<()>, String> {
    let mut linker = Linker::new(engine);
    for import in module.imports() {
        let ExternType::Func(func_type) = import.ty() else {
            return Err(format!("non-function import {}.{}", import.module(), import.name()));
        };
        let results: Vec<ValType> = func_type.results().collect();
        let stub = Func::new(&mut *store, func_type.clone(), move |_caller, _params, out| {
            for (slot, ty) in out.iter_mut().zip(results.iter()) {
                *slot = zero_value(ty);
            }
            Ok(())
        });
        linker
            .define(&mut *store, import.module(), import.name(), stub)
            .map_err(|e| format!("define import: {e}"))?;
    }
    Ok(linker)
}

fn run_cell(engine: &Engine, cell: &plan::Cell, options: &Options, out: &mut impl Write) -> Result<(), String> {
    let module = Module::from_file(engine, Path::new(&cell.path)).map_err(|e| format!("{}: {e}", cell.key))?;
    let mut store = Store::new(engine, ());
    store.set_fuel(FUEL_BUDGET).map_err(|e| format!("{e}"))?;
    let linker = stub_linker(&mut store, engine, &module)?;
    let instance = linker.instantiate(&mut store, &module).map_err(|e| format!("instantiate: {e}"))?;
    let run = instance.get_typed_func::<i32, i64>(&mut store, "run").map_err(|e| format!("run: {e}"))?;
    for _ in 0..options.warmup {
        store.set_fuel(FUEL_BUDGET).map_err(|e| format!("{e}"))?;
        run.call(&mut store, cell.reps as i32).map_err(|e| format!("warmup trap: {e}"))?;
    }
    let runtime = if options.flat_bulk { format!("wasmtime-{}-flatbulk", options.backend) } else { format!("wasmtime-{}", options.backend) };
    for replicate in 0..options.replicates {
        store.set_fuel(FUEL_BUDGET).map_err(|e| format!("{e}"))?;
        let load = load1();
        let wall = Instant::now();
        let cpu_start = thread_cpu_ns();
        let pmu_start = read_counters(options.use_pmu);
        run.call(&mut store, cell.reps as i32).map_err(|e| format!("timed trap: {e}"))?;
        let pmu_end = read_counters(options.use_pmu);
        let cpu_ns = thread_cpu_ns() - cpu_start;
        let wall_ns = wall.elapsed().as_nanos() as u64;
        let fuel = FUEL_BUDGET - store.get_fuel().map_err(|e| format!("{e}"))?;
        let deltas: Vec<String> = pmu_end
            .iter()
            .zip(pmu_start.iter())
            .map(|(end, start)| end.wrapping_sub(*start).to_string())
            .collect();
        writeln!(
            out,
            "{runtime},{},{},{},{replicate},{},{fuel},{cpu_ns},{wall_ns},{load:.2},{}",
            cell.opt_level, cell.key, cell.group, cell.reps, deltas.join(",")
        )
        .map_err(|e| format!("write: {e}"))?;
    }
    Ok(())
}

/// Fuel table with every per-byte, per-element, and per-page cost set to zero, so bulk
/// operators cost only their flat per-operator charge (the accounting Winch applies).
fn flat_bulk_costs() -> OperatorCost {
    let mut cost = OperatorCost::new();
    cost.variable = VariableOperatorCost {
        memory_copy_per_byte: 0,
        memory_fill_per_byte: 0,
        memory_init_per_byte: 0,
        memory_grow_per_page: 0,
        table_copy_per_element: 0,
        table_fill_per_element: 0,
        table_init_per_element: 0,
        table_grow_per_element: 0,
        array_copy_per_element: 0,
        array_fill_per_element: 0,
        array_new_data_per_element: 0,
        array_init_data_per_element: 0,
        array_new_elem_per_element: 0,
        array_init_elem_per_element: 0,
        array_new_default_per_element: 0,
        array_new_per_element: 0,
    };
    cost
}

fn build_engine(backend: &str, flat_bulk: bool) -> Result<Engine, String> {
    let strategy = match backend {
        "cranelift" => Strategy::Cranelift,
        "winch" => Strategy::Winch,
        other => return Err(format!("unsupported backend {other}")),
    };
    let mut config = Config::new();
    config.strategy(strategy);
    config.consume_fuel(true);
    if flat_bulk {
        config.operator_cost(flat_bulk_costs());
    }
    Engine::new(&config).map_err(|e| format!("engine: {e}"))
}

fn run_all(options: &Options) -> Result<(), String> {
    let cells = plan::load(&options.plan)?;
    let engine = build_engine(&options.backend, options.flat_bulk)?;
    if options.use_pmu {
        init_counters()?;
    }
    let file = File::create(&options.out).map_err(|e| format!("{}: {e}", options.out.display()))?;
    let mut out = BufWriter::new(file);
    writeln!(out, "{CSV_HEADER}").map_err(|e| format!("write: {e}"))?;
    for cell in &cells {
        if let Some(filter) = &options.only {
            if !cell.key.contains(filter.as_str()) {
                continue;
            }
        }
        let waited = wait_for_quiet(options.load_gate);
        run_cell(&engine, cell, options, &mut out)?;
        out.flush().map_err(|e| format!("flush: {e}"))?;
        eprintln!("done {} {} (gate wait {:.0}s, load {:.2})", cell.opt_level, cell.key, waited.as_secs_f64(), load1());
    }
    Ok(())
}

fn main() {
    // SAFETY: sets the QoS class of the calling thread only.
    unsafe { pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0) };
    let result = parse_options().and_then(|options| run_all(&options));
    // SAFETY: releases the counters configured by kc_init; safe to call if setup failed.
    unsafe { kc_shutdown() };
    if let Err(message) = result {
        eprintln!("error: {message}");
        std::process::exit(1);
    }
}
