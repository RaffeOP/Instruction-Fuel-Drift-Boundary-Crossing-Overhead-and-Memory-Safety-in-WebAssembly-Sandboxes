//! Wasmer runner for one compiler backend (Singlepass or Cranelift).
//! Function imports are satisfied by no-op stubs; the timed path never calls them.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::Path;

use wasmer::sys::{Cranelift, EngineBuilder, Singlepass, LLVM};
use wasmer::{Extern, Function, FunctionType, Imports, Instance, Module, Store, Type, Value};

use crate::plan::Cell;
use crate::timing::Stopwatch;
use crate::Options;

const CSV_HEADER: &str = "runtime,opt_level,kernel,group,replicate,reps,fuel,cpu_ns,wall_ns,checksum,cycles,instructions";

fn zero_value(ty: &Type) -> Result<Value, String> {
    match ty {
        Type::I32 => Ok(Value::I32(0)),
        Type::I64 => Ok(Value::I64(0)),
        Type::F32 => Ok(Value::F32(0.0)),
        Type::F64 => Ok(Value::F64(0.0)),
        other => Err(format!("no zero value for import result type {other:?}")),
    }
}

fn stub_imports(store: &mut Store, module: &Module) -> Result<Imports, String> {
    let mut imports = Imports::new();
    for import in module.imports() {
        let wasmer::ExternType::Function(function_type) = import.ty() else {
            return Err(format!("unsupported non-function import {}.{}", import.module(), import.name()));
        };
        let params: Vec<Type> = function_type.params().to_vec();
        let results: Vec<Type> = function_type.results().to_vec();
        let ty = FunctionType::new(params, results.clone());
        let stub = Function::new(&mut *store, ty, move |_args: &[Value]| {
            let mut out = Vec::new();
            for result in &results {
                out.push(zero_value(result).expect("stub result type"));
            }
            Ok(out)
        });
        imports.define(import.module(), import.name(), Extern::from(stub));
    }
    Ok(imports)
}

fn make_store(backend: &str) -> Result<Store, String> {
    let engine = match backend {
        "singlepass" => EngineBuilder::new(Singlepass::default()).engine(),
        "cranelift" => EngineBuilder::new(Cranelift::default()).engine(),
        "llvm" => EngineBuilder::new(LLVM::default()).engine(),
        other => return Err(format!("unsupported wasmer backend {other}")),
    };
    Ok(Store::new(engine))
}

fn run_cell(backend: &str, cell: &Cell, options: &Options, writer: &mut impl Write) -> Result<(), String> {
    let mut store = make_store(backend)?;
    let bytes = fs::read(Path::new(&cell.path)).map_err(|e| format!("{}: {e}", cell.key))?;
    let module = Module::new(&store, &bytes).map_err(|e| format!("{} compile: {e}", cell.key))?;
    let imports = stub_imports(&mut store, &module)?;
    let instance = Instance::new(&mut store, &module, &imports).map_err(|e| format!("{} instantiate: {e}", cell.key))?;
    let run = instance
        .exports
        .get_typed_function::<i32, i64>(&store, "run")
        .map_err(|e| format!("{}: run export: {e}", cell.key))?;
    let check = instance
        .exports
        .get_typed_function::<(), i64>(&store, "check")
        .map_err(|e| format!("{}: check export: {e}", cell.key))?;
    let checksum = check.call(&mut store).map_err(|e| format!("{}: check trap: {e}", cell.key))?;
    for _ in 0..options.warmup {
        run.call(&mut store, cell.reps as i32).map_err(|e| format!("{}: warmup trap: {e}", cell.key))?;
    }
    for replicate in 0..options.replicates {
        let watch = Stopwatch::start();
        run.call(&mut store, cell.reps as i32).map_err(|e| format!("{}: timed trap: {e}", cell.key))?;
        let measured = watch.stop();
        writeln!(
            writer,
            "{},{},{},{},{replicate},{},,{},{},{checksum},{},{}",
            options.runtime, cell.opt_level, cell.key, cell.group, cell.reps,
            measured.cpu_ns, measured.wall_ns, measured.cycles, measured.instructions
        )
        .map_err(|e| format!("write: {e}"))?;
    }
    Ok(())
}

pub fn run(cells: &[Cell], options: &Options, backend: &str) -> Result<(), String> {
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
        run_cell(backend, cell, options, &mut file)?;
        file.flush().map_err(|e| format!("flush: {e}"))?;
        eprintln!("done {} {} {}", options.runtime, cell.opt_level, cell.key);
    }
    Ok(())
}
