//! In-process timing harness for Wasmtime (Cranelift and Winch backends).
//! Reads a timing plan, instantiates each module once per cell, runs the timed
//! `run(reps)` export for the requested replicates, and writes one CSV row per call.

mod hwcount;
mod plan;
mod timing;
mod wasmer_runner;
mod wasmtime_runner;

use std::env;
use std::path::PathBuf;

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
    let mut replicates = 100;
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

fn main() {
    let options = match parse_options() {
        Ok(options) => options,
        Err(message) => {
            eprintln!("error: {message}");
            std::process::exit(2);
        }
    };
    let cells = plan::load(&options.plan).expect("read plan");
    let result = match options.runtime.as_str() {
        "wasmtime-cranelift" => wasmtime_runner::run(&cells, &options, wasmtime::Strategy::Cranelift),
        "wasmtime-winch" => wasmtime_runner::run(&cells, &options, wasmtime::Strategy::Winch),
        "wasmer-singlepass" => wasmer_runner::run(&cells, &options, "singlepass"),
        "wasmer-cranelift" => wasmer_runner::run(&cells, &options, "cranelift"),
        "wasmer-llvm" => wasmer_runner::run(&cells, &options, "llvm"),
        other => Err(format!("unsupported runtime {other}")),
    };
    if let Err(message) = result {
        eprintln!("error: {message}");
        std::process::exit(1);
    }
}
