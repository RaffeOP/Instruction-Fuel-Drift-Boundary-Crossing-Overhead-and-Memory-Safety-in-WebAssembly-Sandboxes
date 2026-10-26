//! Wasmtime runner for one backend strategy (Cranelift or Winch).
//! Fuel is metered on every call; the fuel consumed by run(reps) is recorded.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::Path;

use wasmtime::{Config, Engine, ExternType, Func, Linker, Module, Store, Strategy, Val, ValType};

use crate::plan::Cell;
use crate::timing::Stopwatch;
use crate::Options;

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

/// Satisfies every function import with a no-op that returns zeros. Imports are
/// WASI calls on the stdio and clock paths, which the timed run never reaches.
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

fn run_cell(
    engine: &Engine,
    cell: &Cell,
    runtime: &str,
    options: &Options,
    writer: &mut impl Write,
) -> Result<(), String> {
    let module = Module::from_file(engine, Path::new(&cell.path)).map_err(|e| format!("{}: {e}", cell.key))?;
    let mut store = Store::new(engine, ());
    store.set_fuel(FUEL_BUDGET).map_err(|e| format!("{e}"))?;
    let linker = link_stub_imports(&mut store, engine, &module)?;
    let instance = linker
        .instantiate(&mut store, &module)
        .map_err(|e| format!("instantiate {}: {e}", cell.key))?;
    let run = instance
        .get_typed_func::<i32, i64>(&mut store, "run")
        .map_err(|e| format!("{}: run export: {e}", cell.key))?;
    let check = instance
        .get_typed_func::<(), i64>(&mut store, "check")
        .map_err(|e| format!("{}: check export: {e}", cell.key))?;
    let checksum = check.call(&mut store, ()).map_err(|e| format!("{}: check trap: {e}", cell.key))?;
    for _ in 0..options.warmup {
        store.set_fuel(FUEL_BUDGET).map_err(|e| format!("{e}"))?;
        run.call(&mut store, cell.reps as i32).map_err(|e| format!("{}: warmup trap: {e}", cell.key))?;
    }
    for replicate in 0..options.replicates {
        store.set_fuel(FUEL_BUDGET).map_err(|e| format!("{e}"))?;
        let watch = Stopwatch::start();
        run.call(&mut store, cell.reps as i32).map_err(|e| format!("{}: timed trap: {e}", cell.key))?;
        let measured = watch.stop();
        let fuel = FUEL_BUDGET - store.get_fuel().map_err(|e| format!("{e}"))?;
        writeln!(
            writer,
            "{runtime},{},{},{},{replicate},{},{fuel},{},{},{checksum},{},{}",
            cell.opt_level, cell.key, cell.group, cell.reps,
            measured.cpu_ns, measured.wall_ns, measured.cycles, measured.instructions
        )
        .map_err(|e| format!("write: {e}"))?;
    }
    Ok(())
}

pub fn run(cells: &[Cell], options: &Options, strategy: Strategy) -> Result<(), String> {
    let engine = build_engine(strategy)?;
    if let Some(parent) = options.out.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("mkdir: {e}"))?;
    }
    let mut file = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&options.out)
        .map_err(|e| format!("open {}: {e}", options.out.display()))?;
    writeln!(file, "{CSV_HEADER}").map_err(|e| format!("write: {e}"))?;
    for cell in cells {
        run_cell(&engine, cell, &options.runtime, options, &mut file)?;
        file.flush().map_err(|e| format!("flush: {e}"))?;
        eprintln!("done {} {} {}", options.runtime, cell.opt_level, cell.key);
    }
    Ok(())
}
