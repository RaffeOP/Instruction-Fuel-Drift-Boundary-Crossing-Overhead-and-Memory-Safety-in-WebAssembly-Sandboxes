//! RQ2 extension: compound linear-memory sequences and concurrent pooling-allocator tenants.
//!
//! Compound regime. Each trial runs a seeded random sequence of operations on one instance:
//! memory.grow (including requests past the declared maximum), i32 loads and stores near the
//! current end and at high addresses, and memory.fill / memory.copy ranges that straddle the
//! end. A host-side shadow copy of linear memory gives the specified result of every step.
//! A step conforms when it traps exactly when the specification requires, returns the specified
//! value, and leaves memory and its size as specified; bulk operators that trap must write
//! nothing. The trial conforms when every step conforms and the final memory equals the shadow.
//!
//! Pooling regime. Threads repeatedly instantiate tenants on a pooling allocator with fewer
//! slots than the tenants they try to hold. Each successful tenant grows its memory, checks that
//! every byte it can see is zero (a reused slot must not expose a previous tenant's data),
//! writes a tenant-specific pattern, and verifies the pattern before it is dropped. An
//! instantiation refused for lack of slots must fail with an error, not a crash.
//!
//! Usage: boundary_stress --out-compound C.csv --out-pooling P.csv [--trials N] [--steps N]

use std::env;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::sync::{Arc, Mutex};
use std::thread;

use wasmtime::{Config, Engine, Instance, InstanceAllocationStrategy, Memory, Module, PoolingAllocationConfig, Store, TypedFunc};

const PAGE: u64 = 65536;
const MAX_PAGES: u64 = 1024;
const GUEST: &str = r#"(module
  (memory (export "memory") 1 1024)
  (func (export "grow") (param i32) (result i32) (memory.grow (local.get 0)))
  (func (export "store") (param i32 i32) (i32.store (local.get 0) (local.get 1)))
  (func (export "load") (param i32) (result i32) (i32.load (local.get 0)))
  (func (export "fill") (param i32 i32 i32) (memory.fill (local.get 0) (local.get 1) (local.get 2)))
  (func (export "copy") (param i32 i32 i32) (memory.copy (local.get 0) (local.get 1) (local.get 2))))"#;
const POOL_SLOTS: u32 = 64;
const POOL_THREADS: usize = 8;
const TENANTS_HELD_PER_THREAD: usize = 16;
const POOL_ATTEMPTS_PER_THREAD: usize = 200;
const HIGH_ADDRESSES: [u32; 4] = [0xFFFF_FFFC, 0xFFFF_FFFF, 0x8000_0000, 0x7FFF_FFFE];

struct Rng(u64);

impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        self.0
    }
    fn below(&mut self, n: u64) -> u64 {
        self.next() % n
    }
}

struct ConfigSpec {
    name: &'static str,
    guard: Option<u64>,
    signals: bool,
    growth_reservation: Option<u64>,
    pooling: bool,
}

const CONFIGS: [ConfigSpec; 7] = [
    ConfigSpec { name: "default_2gib_guard", guard: None, signals: true, growth_reservation: None, pooling: false },
    ConfigSpec { name: "reduced_64kib_guard", guard: Some(65536), signals: true, growth_reservation: None, pooling: false },
    ConfigSpec { name: "zero_guard", guard: Some(0), signals: true, growth_reservation: None, pooling: false },
    ConfigSpec { name: "zero_guard_explicit_checks", guard: Some(0), signals: false, growth_reservation: None, pooling: false },
    ConfigSpec { name: "no_growth_reservation", guard: None, signals: true, growth_reservation: Some(0), pooling: false },
    ConfigSpec { name: "zero_guard_no_growth_reservation", guard: Some(0), signals: true, growth_reservation: Some(0), pooling: false },
    ConfigSpec { name: "pooling_allocator", guard: None, signals: true, growth_reservation: None, pooling: true },
];

fn pooling_config() -> PoolingAllocationConfig {
    let mut pool = PoolingAllocationConfig::new();
    pool.total_memories(POOL_SLOTS);
    pool.total_core_instances(POOL_SLOTS);
    pool.total_tables(POOL_SLOTS);
    pool.max_memory_size((MAX_PAGES * PAGE) as usize);
    pool
}

fn engine_for(spec: &ConfigSpec) -> Engine {
    let mut config = Config::new();
    if let Some(guard) = spec.guard {
        config.memory_guard_size(guard);
    }
    config.signals_based_traps(spec.signals);
    if let Some(bytes) = spec.growth_reservation {
        config.memory_reservation_for_growth(bytes);
    }
    if spec.pooling {
        config.allocation_strategy(InstanceAllocationStrategy::Pooling(pooling_config()));
    }
    Engine::new(&config).expect("engine")
}

struct Guest {
    store: Store<()>,
    memory: Memory,
    grow: TypedFunc<i32, i32>,
    store_fn: TypedFunc<(i32, i32), ()>,
    load: TypedFunc<i32, i32>,
    fill: TypedFunc<(i32, i32, i32), ()>,
    copy: TypedFunc<(i32, i32, i32), ()>,
}

fn instantiate(engine: &Engine, module: &Module) -> wasmtime::Result<Guest> {
    let mut store = Store::new(engine, ());
    let instance = Instance::new(&mut store, module, &[])?;
    Ok(Guest {
        memory: instance.get_memory(&mut store, "memory").expect("memory"),
        grow: instance.get_typed_func(&mut store, "grow")?,
        store_fn: instance.get_typed_func(&mut store, "store")?,
        load: instance.get_typed_func(&mut store, "load")?,
        fill: instance.get_typed_func(&mut store, "fill")?,
        copy: instance.get_typed_func(&mut store, "copy")?,
        store,
    })
}

/// An address near the current end of memory, or a high address, or an in-bounds address.
fn pick_address(rng: &mut Rng, size: u64) -> u32 {
    match rng.below(4) {
        0 => HIGH_ADDRESSES[rng.below(4) as usize],
        1 => rng.below(size.max(1)) as u32,
        _ => (size as i64 + rng.below(17) as i64 - 8).clamp(0, u32::MAX as i64) as u32,
    }
}

fn in_bounds(address: u32, length: u64, size: u64) -> bool {
    address as u64 + length <= size
}

/// Runs one compound step. Returns the operation, whether it conformed, and whether the
/// specification required a trap (or, for grow, a failure result). Updates the shadow.
fn compound_step(guest: &mut Guest, shadow: &mut Vec<u8>, rng: &mut Rng) -> (&'static str, bool, bool) {
    let size = shadow.len() as u64;
    match rng.below(5) {
        0 => {
            let delta = if rng.below(4) == 0 { 200 + rng.below(1000) } else { rng.below(9) };
            let result = guest.grow.call(&mut guest.store, delta as i32).expect("grow never traps");
            let pages = size / PAGE;
            let allowed = pages + delta <= MAX_PAGES;
            if allowed {
                shadow.resize(((pages + delta) * PAGE) as usize, 0);
            }
            let expected = if allowed { pages as i32 } else { -1 };
            ("grow", result == expected, !allowed)
        }
        1 => {
            let address = pick_address(rng, size);
            let value = rng.next() as i32;
            let trapped = guest.store_fn.call(&mut guest.store, (address as i32, value)).is_err();
            let legal = in_bounds(address, 4, size);
            if legal && !trapped {
                shadow[address as usize..address as usize + 4].copy_from_slice(&value.to_le_bytes());
            }
            ("store", trapped != legal, !legal)
        }
        2 => {
            let address = pick_address(rng, size);
            let outcome = guest.load.call(&mut guest.store, address as i32);
            let legal = in_bounds(address, 4, size);
            let ok = match outcome {
                Ok(value) => legal && value.to_le_bytes() == shadow[address as usize..address as usize + 4],
                Err(_) => !legal,
            };
            ("load", ok, !legal)
        }
        3 => {
            let address = pick_address(rng, size);
            let length = rng.below(257);
            let byte = rng.below(256) as u8;
            let trapped = guest.fill.call(&mut guest.store, (address as i32, byte as i32, length as i32)).is_err();
            let legal = in_bounds(address, length, size);
            if legal && !trapped {
                shadow[address as usize..(address as u64 + length) as usize].fill(byte);
            }
            ("fill", trapped != legal, !legal)
        }
        _ => {
            let destination = pick_address(rng, size);
            let source = rng.below(size) as u32;
            let length = rng.below(257);
            let trapped = guest.copy.call(&mut guest.store, (destination as i32, source as i32, length as i32)).is_err();
            let legal = in_bounds(destination, length, size) && in_bounds(source, length, size);
            if legal && !trapped {
                shadow.copy_within(source as usize..(source as u64 + length) as usize, destination as usize);
            }
            ("copy", trapped != legal, !legal)
        }
    }
}

fn compound(trials: u32, steps: u32, out: &mut impl Write) {
    writeln!(out, "config,trial,steps,step_failures,first_failure,traps_expected,final_memory_equal,conforms").unwrap();
    for spec in &CONFIGS {
        let engine = engine_for(spec);
        let module = Module::new(&engine, GUEST).expect("module");
        for trial in 0..trials {
            let mut rng = Rng(0x9E37_79B9_7F4A_7C15 ^ (trial as u64 + 1) * 0x2545_F491_4F6C_DD1D);
            let mut guest = instantiate(&engine, &module).expect("instantiate");
            let mut shadow = vec![0u8; PAGE as usize];
            let mut failures = 0;
            let mut first_failure = "";
            let mut traps_expected = 0;
            for _ in 0..steps {
                let (kind, ok, must_fail) = compound_step(&mut guest, &mut shadow, &mut rng);
                let size_ok = guest.memory.data_size(&guest.store) == shadow.len();
                traps_expected += u32::from(must_fail);
                if !(ok && size_ok) {
                    failures += 1;
                    if first_failure.is_empty() {
                        first_failure = kind;
                    }
                }
            }
            let equal = guest.memory.data(&guest.store) == shadow.as_slice();
            let conforms = failures == 0 && equal;
            writeln!(out, "{},{trial},{steps},{failures},{first_failure},{traps_expected},{equal},{conforms}", spec.name).unwrap();
        }
        eprintln!("compound {} done", spec.name);
    }
}

#[derive(Default)]
struct PoolCounts {
    attempts: u64,
    admitted: u64,
    refused_cleanly: u64,
    dirty_slot: u64,
    pattern_lost: u64,
    other_errors: u64,
}

fn tenant_lifecycle(guest: &mut Guest, rng: &mut Rng, tag: u8, counts: &mut PoolCounts) {
    let pages = 1 + rng.below(16);
    guest.grow.call(&mut guest.store, (pages - 1) as i32).expect("grow");
    if guest.memory.data(&guest.store).iter().any(|&b| b != 0) {
        counts.dirty_slot += 1;
    }
    let size = guest.memory.data_size(&guest.store) as i32;
    guest.fill.call(&mut guest.store, (0, tag as i32, size)).expect("fill");
}

fn verify_and_drop(guest: Guest, tag: u8, counts: &mut PoolCounts) {
    if guest.memory.data(&guest.store).iter().any(|&b| b != tag) {
        counts.pattern_lost += 1;
    }
}

fn pooling(out: &mut impl Write) {
    let spec = &CONFIGS[6];
    let engine = engine_for(spec);
    let module = Module::new(&engine, GUEST).expect("module");
    let totals = Arc::new(Mutex::new(PoolCounts::default()));
    let workers: Vec<_> = (0..POOL_THREADS)
        .map(|worker| {
            let (engine, module, totals) = (engine.clone(), module.clone(), totals.clone());
            thread::spawn(move || {
                let mut rng = Rng(0xD1B5_4A32_D192_ED03 ^ (worker as u64 + 7) * 0x9E37_79B9);
                let mut counts = PoolCounts::default();
                let mut held: Vec<(Guest, u8)> = Vec::new();
                for attempt in 0..POOL_ATTEMPTS_PER_THREAD {
                    counts.attempts += 1;
                    let tag = (1 + (worker * 31 + attempt) % 254) as u8;
                    match instantiate(&engine, &module) {
                        Ok(mut guest) => {
                            counts.admitted += 1;
                            tenant_lifecycle(&mut guest, &mut rng, tag, &mut counts);
                            held.push((guest, tag));
                        }
                        Err(error) => {
                            let text = format!("{error:?}");
                            if text.contains("maximum concurrent") || text.contains("limit") || text.contains("pool") {
                                counts.refused_cleanly += 1;
                            } else {
                                counts.other_errors += 1;
                                eprintln!("unexpected instantiation error: {text}");
                            }
                        }
                    }
                    if held.len() >= TENANTS_HELD_PER_THREAD || (rng.below(3) == 0 && !held.is_empty()) {
                        let index = rng.below(held.len() as u64) as usize;
                        let (guest, tag) = held.swap_remove(index);
                        verify_and_drop(guest, tag, &mut counts);
                    }
                }
                for (guest, tag) in held {
                    verify_and_drop(guest, tag, &mut counts);
                }
                let mut total = totals.lock().unwrap();
                total.attempts += counts.attempts;
                total.admitted += counts.admitted;
                total.refused_cleanly += counts.refused_cleanly;
                total.dirty_slot += counts.dirty_slot;
                total.pattern_lost += counts.pattern_lost;
                total.other_errors += counts.other_errors;
            })
        })
        .collect();
    for worker in workers {
        worker.join().expect("worker panicked");
    }
    let c = totals.lock().unwrap();
    writeln!(out, "threads,slots,attempts,admitted,refused_cleanly,dirty_slot,pattern_lost,other_errors").unwrap();
    writeln!(out, "{POOL_THREADS},{POOL_SLOTS},{},{},{},{},{},{}", c.attempts, c.admitted, c.refused_cleanly,
             c.dirty_slot, c.pattern_lost, c.other_errors).unwrap();
    eprintln!("pooling: {} attempts, {} admitted, {} refused, {} dirty, {} lost, {} other",
              c.attempts, c.admitted, c.refused_cleanly, c.dirty_slot, c.pattern_lost, c.other_errors);
}

fn main() {
    let mut compound_out = None;
    let mut pooling_out = None;
    let mut trials = 600u32;
    let mut steps = 40u32;
    let mut args = env::args().skip(1);
    while let Some(flag) = args.next() {
        let value = args.next().expect("value");
        match flag.as_str() {
            "--out-compound" => compound_out = Some(value),
            "--out-pooling" => pooling_out = Some(value),
            "--trials" => trials = value.parse().expect("trials"),
            "--steps" => steps = value.parse().expect("steps"),
            other => panic!("unknown flag {other}"),
        }
    }
    let mut compound_file = BufWriter::new(File::create(compound_out.expect("--out-compound")).expect("create"));
    compound(trials, steps, &mut compound_file);
    let mut pooling_file = BufWriter::new(File::create(pooling_out.expect("--out-pooling")).expect("create"));
    pooling(&mut pooling_file);
}
