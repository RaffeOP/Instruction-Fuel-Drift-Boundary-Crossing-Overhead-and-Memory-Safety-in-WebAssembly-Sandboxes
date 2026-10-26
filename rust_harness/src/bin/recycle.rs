//! Sandbox recycling child process for RQ4 (on-demand versus pooling allocation).
//! Creates, runs, and drops one instance per lifecycle. At every checkpoint it prints
//! a line and blocks until the parent acknowledges on stdin, so the parent can sample
//! this process's unique set size while no lifecycle is in flight.

use std::io::{self, BufRead, Write};
use std::path::{Path, PathBuf};
use std::time::Instant;

use wasmtime::{Config, Engine, InstanceAllocationStrategy, Module, PoolingAllocationConfig, Store};

const TASK_VM_INFO: i32 = 22;

/// Leading fields of Mach task_vm_info_data_t, in header order. `internal` is the private
/// anonymous memory of this task, the closest macOS analogue of unique set size.
#[repr(C)]
#[derive(Default)]
struct TaskVmInfo {
    virtual_size: u64,
    region_count: i32,
    page_size: i32,
    resident_size: u64,
    resident_size_peak: u64,
    device: u64,
    device_peak: u64,
    internal: u64,
    internal_peak: u64,
    external: u64,
    external_peak: u64,
    reusable: u64,
    reusable_peak: u64,
    purgeable_volatile_pmap: u64,
    purgeable_volatile_resident: u64,
    purgeable_volatile_virtual: u64,
    compressed: u64,
    compressed_peak: u64,
    compressed_lifetime: u64,
    phys_footprint: u64,
}

extern "C" {
    fn mach_task_self() -> u32;
    fn task_info(task: u32, flavor: i32, info: *mut i32, count: *mut u32) -> i32;
}

/// Private anonymous (internal) and physical footprint bytes of the current task, read through
/// task_info(TASK_VM_INFO). Internal pages are private anonymous pages, which are dirty by definition.
fn memory_bytes() -> (u64, u64) {
    let mut info = TaskVmInfo::default();
    let mut count = (std::mem::size_of::<TaskVmInfo>() / std::mem::size_of::<i32>()) as u32;
    // SAFETY: task_info writes at most `count` 32-bit words into `info`, which is large enough.
    let status = unsafe {
        task_info(mach_task_self(), TASK_VM_INFO, &mut info as *mut TaskVmInfo as *mut i32, &mut count)
    };
    assert_eq!(status, 0, "task_info(TASK_VM_INFO) failed");
    (info.internal, info.phys_footprint)
}

struct Options {
    pooled: bool,
    lifecycles: u32,
    checkpoint_stride: u32,
    module: PathBuf,
    latency_out: PathBuf,
    dirty_pages: i32,
}

fn parse() -> Result<Options, String> {
    let mut pooled = None;
    let mut lifecycles = None;
    let mut stride = None;
    let mut module = None;
    let mut latency_out = None;
    let mut dirty_pages = 4;
    let mut args = std::env::args().skip(1);
    while let Some(flag) = args.next() {
        let value = args.next().ok_or_else(|| format!("missing value for {flag}"))?;
        match flag.as_str() {
            "--mode" => pooled = Some(match value.as_str() {
                "on-demand" => false,
                "pooled" => true,
                other => return Err(format!("unknown mode {other}")),
            }),
            "--lifecycles" => lifecycles = Some(value.parse().map_err(|e| format!("{e}"))?),
            "--checkpoint-stride" => stride = Some(value.parse().map_err(|e| format!("{e}"))?),
            "--module" => module = Some(PathBuf::from(value)),
            "--latency-out" => latency_out = Some(PathBuf::from(value)),
            "--dirty-pages" => dirty_pages = value.parse().map_err(|e| format!("{e}"))?,
            other => return Err(format!("unknown flag {other}")),
        }
    }
    Ok(Options {
        pooled: pooled.ok_or("--mode required")?,
        lifecycles: lifecycles.ok_or("--lifecycles required")?,
        checkpoint_stride: stride.ok_or("--checkpoint-stride required")?,
        module: module.ok_or("--module required")?,
        latency_out: latency_out.ok_or("--latency-out required")?,
        dirty_pages,
    })
}

fn build_engine(pooled: bool) -> Result<Engine, String> {
    let mut config = Config::new();
    if pooled {
        let mut pool = PoolingAllocationConfig::new();
        pool.total_memories(8);
        config.allocation_strategy(InstanceAllocationStrategy::Pooling(pool));
    }
    Engine::new(&config).map_err(|e| format!("engine: {e}"))
}

/// Instantiates the module once, dirties its memory, drops it, and returns the lifecycle latency.
fn run_lifecycle(engine: &Engine, module: &Module, dirty_pages: i32) -> u64 {
    let started = Instant::now();
    let mut store = Store::new(engine, ());
    let instance = wasmtime::Instance::new(&mut store, module, &[]).expect("instantiate");
    let dirty = instance
        .get_typed_func::<i32, i32>(&mut store, "dirty")
        .expect("dirty export");
    let previous = dirty.call(&mut store, dirty_pages).expect("dirty call");
    assert!(previous >= 0, "linear-memory growth failed");
    drop(store);
    started.elapsed().as_nanos() as u64
}

/// Reports the task's memory at a checkpoint and waits for the parent's acknowledgement line.
fn checkpoint(lifecycle: u32, acknowledgements: &mut impl BufRead) {
    let (internal, footprint) = memory_bytes();
    let stdout = io::stdout();
    let mut handle = stdout.lock();
    writeln!(handle, "CHECKPOINT {lifecycle} {internal} {footprint}").expect("write checkpoint");
    handle.flush().expect("flush checkpoint");
    drop(handle);
    let mut acknowledgement = String::new();
    acknowledgements.read_line(&mut acknowledgement).expect("acknowledgement");
}

/// Writes each lifecycle latency as a little-endian u64, for the parent to read as raw bytes.
fn write_latencies(path: &Path, latencies: &[u64]) {
    let mut bytes = Vec::with_capacity(latencies.len() * 8);
    for value in latencies {
        bytes.extend_from_slice(&value.to_le_bytes());
    }
    std::fs::write(path, bytes).expect("write latencies");
}

fn main() {
    let options = match parse() {
        Ok(options) => options,
        Err(message) => {
            eprintln!("error: {message}");
            std::process::exit(2);
        }
    };
    let engine = build_engine(options.pooled).expect("engine");
    let module = Module::from_file(&engine, &options.module).expect("module");
    let mut latencies: Vec<u64> = Vec::with_capacity(options.lifecycles as usize);
    let stdin = io::stdin();
    let mut acknowledgements = stdin.lock();
    for lifecycle in 0..options.lifecycles {
        latencies.push(run_lifecycle(&engine, &module, options.dirty_pages));
        if lifecycle % options.checkpoint_stride == 0 {
            checkpoint(lifecycle, &mut acknowledgements);
        }
    }
    write_latencies(&options.latency_out, &latencies);
    println!("DONE {}", options.lifecycles);
}
