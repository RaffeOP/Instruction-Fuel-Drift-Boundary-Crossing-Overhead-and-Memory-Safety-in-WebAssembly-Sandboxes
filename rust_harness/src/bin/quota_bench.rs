//! DualGate: a CPU-time quota for Wasmtime guests built from fuel and epoch interruption.
//!
//! Policies, each enforcing a CPU budget B on one call of `run(i32::MAX)`:
//!   fuel  - fuel budget B / psi_ref, the conversion a fuel-only platform would use;
//!   time  - a timer thread advances the engine epoch every tick; at each epoch deadline the
//!           guest thread reads its own CPU time and interrupts once it reaches B;
//!   dual  - both limits; the call stops at whichever fires first.
//! A safety cap (epoch callback at CAP x B CPU time) stops fuel-only runs that would otherwise
//! run for minutes; such runs are recorded as censored.
//!
//! Modes:
//!   --mode enforce   one row per (cell, policy, replicate): CPU at stop, stop reason, fuel used
//!   --mode overhead  per cell, mean CPU of run(reps) with fuel only and with fuel plus epoch
//!                    interruption (callback always continues), to price the epoch checks
//!
//! Usage: quota_bench --mode enforce|overhead --plan PLAN.csv --out OUT.csv [--backend cranelift|winch]
//!        [--budget-ms 20] [--tick-us 1000] [--psi-ref NS_PER_FUEL] [--replicates N] [--cap 50]

#[path = "../plan.rs"]
mod plan;

use std::env;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU8, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

use wasmtime::{Config, Engine, ExternType, Func, Linker, Module, Store, Strategy, Trap, UpdateDeadline, Val, ValType};

const UNLIMITED_FUEL: u64 = 1 << 62;
const STOP_NONE: u8 = 0;
const STOP_TIME: u8 = 1;
const STOP_CAP: u8 = 2;
const QOS_CLASS_USER_INTERACTIVE: u32 = 0x21;

extern "C" {
    fn pthread_set_qos_class_self_np(qos: u32, relative_priority: i32) -> i32;
}

struct Options {
    mode: String,
    plan: PathBuf,
    out: PathBuf,
    backend: String,
    budget_ns: u64,
    tick: Duration,
    psi_ref: f64,
    replicates: u32,
    cap: u64,
}

fn parse() -> Options {
    let mut options = Options {
        mode: String::new(),
        plan: PathBuf::new(),
        out: PathBuf::new(),
        backend: "cranelift".into(),
        budget_ns: 20_000_000,
        tick: Duration::from_micros(1000),
        psi_ref: 0.0365,
        replicates: 5,
        cap: 50,
    };
    let mut args = env::args().skip(1);
    while let Some(flag) = args.next() {
        let value = args.next().expect("flag value");
        match flag.as_str() {
            "--mode" => options.mode = value,
            "--plan" => options.plan = PathBuf::from(value),
            "--out" => options.out = PathBuf::from(value),
            "--backend" => options.backend = value,
            "--budget-ms" => options.budget_ns = value.parse::<u64>().expect("budget") * 1_000_000,
            "--tick-us" => options.tick = Duration::from_micros(value.parse().expect("tick")),
            "--psi-ref" => options.psi_ref = value.parse().expect("psi"),
            "--replicates" => options.replicates = value.parse().expect("replicates"),
            "--cap" => options.cap = value.parse().expect("cap"),
            other => panic!("unknown flag {other}"),
        }
    }
    options
}

fn thread_cpu_ns() -> u64 {
    let mut spec = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    // SAFETY: clock_gettime writes into the provided timespec.
    let status = unsafe { libc::clock_gettime(libc::CLOCK_THREAD_CPUTIME_ID, &mut spec) };
    assert_eq!(status, 0);
    spec.tv_sec as u64 * 1_000_000_000 + spec.tv_nsec as u64
}

fn build_engine(backend: &str, epochs: bool) -> Engine {
    let mut config = Config::new();
    config.strategy(if backend == "winch" { Strategy::Winch } else { Strategy::Cranelift });
    config.consume_fuel(true);
    config.epoch_interruption(epochs);
    Engine::new(&config).expect("engine")
}

fn zero_value(ty: &ValType) -> Val {
    match ty {
        ValType::I32 => Val::I32(0),
        ValType::I64 => Val::I64(0),
        ValType::F32 => Val::F32(0),
        ValType::F64 => Val::F64(0),
        other => panic!("no zero for {other:?}"),
    }
}

fn instantiate(engine: &Engine, path: &Path) -> (Store<()>, wasmtime::TypedFunc<i32, i64>) {
    let module = Module::from_file(engine, path).expect("module");
    let mut store = Store::new(engine, ());
    store.set_fuel(UNLIMITED_FUEL).expect("fuel");
    store.set_epoch_deadline(u64::MAX / 2);
    let mut linker = Linker::new(engine);
    for import in module.imports() {
        let ExternType::Func(ty) = import.ty() else { panic!("non-function import") };
        let results: Vec<ValType> = ty.results().collect();
        let stub = Func::new(&mut store, ty.clone(), move |_, _, out| {
            for (slot, t) in out.iter_mut().zip(results.iter()) {
                *slot = zero_value(t);
            }
            Ok(())
        });
        linker.define(&mut store, import.module(), import.name(), stub).expect("define");
    }
    let instance = linker.instantiate(&mut store, &module).expect("instantiate");
    let run = instance.get_typed_func::<i32, i64>(&mut store, "run").expect("run export");
    (store, run)
}

/// Starts a thread that advances the engine epoch every tick until `stop` is set.
fn start_ticker(engine: &Engine, tick: Duration, stop: Arc<AtomicBool>) -> thread::JoinHandle<()> {
    let engine = engine.clone();
    thread::spawn(move || {
        while !stop.load(Ordering::Relaxed) {
            thread::sleep(tick);
            engine.increment_epoch();
        }
    })
}

/// Installs a callback that interrupts once the guest thread's CPU reaches `limit_ns`.
fn arm_cpu_gate(store: &mut Store<()>, limit_ns: u64, reason: u8, flag: Arc<AtomicU8>) {
    let start = thread_cpu_ns();
    store.epoch_deadline_callback(move |_| {
        if thread_cpu_ns() - start >= limit_ns {
            flag.store(reason, Ordering::Relaxed);
            Ok(UpdateDeadline::Interrupt)
        } else {
            Ok(UpdateDeadline::Continue(1))
        }
    });
    store.set_epoch_deadline(1);
}

fn enforce_once(engine: &Engine, cell: &plan::Cell, policy: &str, options: &Options) -> (u64, &'static str, u64) {
    let (mut store, run) = instantiate(engine, &cell.path);
    run.call(&mut store, 1).expect("warm-up call");
    let flag = Arc::new(AtomicU8::new(STOP_NONE));
    let fuel_budget = (options.budget_ns as f64 / options.psi_ref) as u64;
    let granted = if policy == "time" { UNLIMITED_FUEL } else { fuel_budget };
    store.set_fuel(granted).expect("fuel");
    let (limit, reason) = if policy == "fuel" { (options.cap * options.budget_ns, STOP_CAP) } else { (options.budget_ns, STOP_TIME) };
    arm_cpu_gate(&mut store, limit, reason, flag.clone());
    let start = thread_cpu_ns();
    let outcome = run.call(&mut store, i32::MAX);
    let cpu = thread_cpu_ns() - start;
    let used = granted - store.get_fuel().expect("fuel");
    let stop = match outcome {
        Ok(_) => "completed",
        Err(error) => match (error.downcast_ref::<Trap>(), flag.load(Ordering::Relaxed)) {
            (Some(Trap::OutOfFuel), _) => "fuel",
            (_, STOP_TIME) => "time",
            (_, STOP_CAP) => "cap",
            _ => "other",
        },
    };
    (cpu, stop, used)
}

fn enforce(options: &Options, cells: &[plan::Cell], out: &mut impl Write) {
    let engine = build_engine(&options.backend, true);
    let stop = Arc::new(AtomicBool::new(false));
    let ticker = start_ticker(&engine, options.tick, stop.clone());
    writeln!(out, "backend,kernel,opt_level,group,policy,replicate,budget_ns,tick_us,cpu_ns,overshoot,stop,fuel_used").unwrap();
    for cell in cells {
        for policy in ["fuel", "time", "dual"] {
            for replicate in 0..options.replicates {
                let (cpu, reason, used) = enforce_once(&engine, cell, policy, options);
                let overshoot = cpu as f64 / options.budget_ns as f64 - 1.0;
                // The fuel counter is not synchronized when an epoch interrupt unwinds the call,
                // so fuel is reported only for calls that stopped on fuel or completed.
                let fuel_text = if reason == "fuel" || reason == "completed" { used.to_string() } else { String::new() };
                writeln!(out, "{},{},{},{},{policy},{replicate},{},{},{cpu},{overshoot:.5},{reason},{fuel_text}",
                         options.backend, cell.key, cell.opt_level, cell.group, options.budget_ns,
                         options.tick.as_micros()).unwrap();
            }
        }
        out.flush().unwrap();
        eprintln!("enforced {} {}", cell.opt_level, cell.key);
    }
    stop.store(true, Ordering::Relaxed);
    ticker.join().unwrap();
}

fn timed_mean(engine: &Engine, cell: &plan::Cell, replicates: u32, epochs: bool) -> f64 {
    let (mut store, run) = instantiate(engine, &cell.path);
    if epochs {
        store.epoch_deadline_callback(|_| Ok(UpdateDeadline::Continue(1)));
        store.set_epoch_deadline(1);
    }
    for _ in 0..2 {
        run.call(&mut store, cell.reps as i32).expect("warm-up");
    }
    let mut total = 0u64;
    for _ in 0..replicates {
        store.set_fuel(UNLIMITED_FUEL).expect("fuel");
        let start = thread_cpu_ns();
        run.call(&mut store, cell.reps as i32).expect("run");
        total += thread_cpu_ns() - start;
    }
    total as f64 / replicates as f64
}

fn overhead(options: &Options, cells: &[plan::Cell], out: &mut impl Write) {
    let plain = build_engine(&options.backend, false);
    let gated = build_engine(&options.backend, true);
    let stop = Arc::new(AtomicBool::new(false));
    let ticker = start_ticker(&gated, options.tick, stop.clone());
    writeln!(out, "backend,kernel,opt_level,group,replicates,cpu_fuel_only_ns,cpu_fuel_epoch_ns,ratio").unwrap();
    for cell in cells {
        let base = timed_mean(&plain, cell, options.replicates, false);
        let with_epochs = timed_mean(&gated, cell, options.replicates, true);
        writeln!(out, "{},{},{},{},{},{base:.0},{with_epochs:.0},{:.5}", options.backend, cell.key, cell.opt_level,
                 cell.group, options.replicates, with_epochs / base).unwrap();
        out.flush().unwrap();
        eprintln!("overhead {} {}", cell.opt_level, cell.key);
    }
    stop.store(true, Ordering::Relaxed);
    ticker.join().unwrap();
}

fn main() {
    // SAFETY: sets the QoS class of the calling thread only.
    unsafe { pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0) };
    let options = parse();
    let cells = plan::load(&options.plan).expect("plan");
    let mut out = BufWriter::new(File::create(&options.out).expect("out"));
    match options.mode.as_str() {
        "enforce" => enforce(&options, &cells, &mut out),
        "overhead" => overhead(&options, &cells, &mut out),
        other => panic!("unknown mode {other}"),
    }
}
