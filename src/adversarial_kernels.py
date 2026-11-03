#!/usr/bin/env python3
"""
Generates the adversarial kernel family used to search for the worst-case cost per fuel unit.

The benchmark corpus measures amplification over benign kernels. This generator instead
targets operators that Wasmtime charges one fuel unit for but that can take many cycles:
dependent loads that miss in cache and TLB, long-latency integer and floating-point
arithmetic, unpredictable direct branches, and unpredictable indirect calls. Bulk-memory
operators are included as a control because Wasmtime 50 charges them per byte.

Every module is plain WAT, imports nothing, and exports run(reps) -> i64 and check() -> i64,
the same interface as the corpus. One-time setup (building a pointer cycle) runs on the
first call, which the harness spends in warm-up, so it is excluded from timed replicates.

Writes kernels/adversarial/<name>.wat and data/adversarial_plan_uncalibrated.csv.
"""

import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "kernels" / "adversarial"
PLAN_PATH = PROJECT_ROOT / "data" / "adversarial_plan_uncalibrated.csv"
PROBE_PLAN_PATH = PROJECT_ROOT / "data" / "quota_probe_plan.csv"
PREEMPTION_PROBE_BYTES = 1 << 28  # one 256 MiB memory.copy: the longest single operator we test

WASM_PAGE = 65536
CHASE_LOADS_PER_REP = 1 << 16
ALU_OPS_PER_REP = 1 << 16
BULK_OPS_PER_REP = 64
CACHE_LINE = 128
OS_PAGE = 16384
CHASE_WORKING_SETS = [1 << k for k in range(14, 31, 2)]  # 16 KiB .. 1 GiB
BULK_LENGTHS = [64, 4096, 1 << 18, 1 << 22]
INDIRECT_TARGETS = [2, 64]
CHASE_UNROLLS = [4, 16, 64]

XORSHIFT = """
  (func $rand (result i32)
    (global.set $seed (i32.xor (global.get $seed) (i32.shl (global.get $seed) (i32.const 13))))
    (global.set $seed (i32.xor (global.get $seed) (i32.shr_u (global.get $seed) (i32.const 17))))
    (global.set $seed (i32.xor (global.get $seed) (i32.shl (global.get $seed) (i32.const 5))))
    (global.get $seed))
"""


def module(pages: int, body: str) -> str:
    return (
        "(module\n"
        f'  (memory (export "memory") {pages})\n'
        "  (global $seed (mut i32) (i32.const 2463534242))\n"
        "  (global $ready (mut i32) (i32.const 0))\n"
        "  (global $acc (mut i64) (i64.const 0))\n"
        f"{XORSHIFT}{body}\n"
        '  (func (export "check") (result i64) (global.get $acc))\n'
        ")\n"
    )


def chase(working_set: int, stride: int, unroll: int = 1) -> str:
    """Dependent loads around one random cycle (Sattolo) of slots `stride` bytes apart.

    The cursor persists across calls, so successive calls continue around the cycle
    instead of re-walking a prefix that warm-up has already brought into cache.
    With unroll > 1 each loop iteration nests `unroll` dependent loads in one expression,
    which removes the per-hop loop bookkeeping that fuel would otherwise charge.
    """
    hop = "(local.get $p)"
    for _ in range(unroll):
        hop = f"(i32.load {hop})"
    iterations = CHASE_LOADS_PER_REP // unroll
    slots = working_set // stride
    pages = max(1, working_set // WASM_PAGE)
    return module(pages, f"""
  (func $setup (local $i i32) (local $j i32) (local $t i32)
    (local.set $i (i32.const 0))
    (loop $fill
      (i32.store (i32.mul (local.get $i) (i32.const {stride})) (local.get $i))
      (local.set $i (i32.add (local.get $i) (i32.const 1)))
      (br_if $fill (i32.lt_u (local.get $i) (i32.const {slots}))))
    (local.set $i (i32.const {slots - 1}))
    (loop $shuffle
      (local.set $j (i32.rem_u (call $rand) (local.get $i)))
      (local.set $t (i32.load (i32.mul (local.get $i) (i32.const {stride}))))
      (i32.store (i32.mul (local.get $i) (i32.const {stride}))
                 (i32.load (i32.mul (local.get $j) (i32.const {stride}))))
      (i32.store (i32.mul (local.get $j) (i32.const {stride})) (local.get $t))
      (local.set $i (i32.sub (local.get $i) (i32.const 1)))
      (br_if $shuffle (i32.gt_u (local.get $i) (i32.const 0))))
    (local.set $i (i32.const 0))
    (loop $scale
      (i32.store (i32.mul (local.get $i) (i32.const {stride}))
                 (i32.mul (i32.load (i32.mul (local.get $i) (i32.const {stride}))) (i32.const {stride})))
      (local.set $i (i32.add (local.get $i) (i32.const 1)))
      (br_if $scale (i32.lt_u (local.get $i) (i32.const {slots})))))
  (global $cursor (mut i32) (i32.const 0))
  (func (export "run") (param $reps i32) (result i64) (local $p i32) (local $k i32)
    (if (i32.eqz (global.get $ready)) (then (call $setup) (global.set $ready (i32.const 1))))
    (local.set $p (global.get $cursor))
    (loop $rep
      (local.set $k (i32.const {iterations}))
      (loop $hop
        (local.set $p {hop})
        (br_if $hop (local.tee $k (i32.sub (local.get $k) (i32.const 1)))))
      (br_if $rep (local.tee $reps (i32.sub (local.get $reps) (i32.const 1)))))
    (global.set $cursor (local.get $p))
    (global.set $acc (i64.extend_i32_u (local.get $p)))
    (global.get $acc))""")


def alu_chain(kind: str) -> str:
    """A dependent chain of one long-latency operator."""
    step = {
        "i64_div": "(local.set $x (i64.div_u (i64.or (local.get $x) (i64.const 0x4000000000000000)) (local.get $y)))",
        "i64_rem": "(local.set $x (i64.add (i64.rem_u (local.get $x) (local.get $y)) (i64.const 0x7fffffffffff)))",
        "f64_div": "(local.set $f (f64.div (local.get $f) (f64.const 1.0000001)))",
        "f64_sqrt": "(local.set $f (f64.add (f64.sqrt (local.get $f)) (f64.const 2.0)))",
        "i64_mul": "(local.set $x (i64.mul (local.get $x) (local.get $y)))",
        "i64_add": "(local.set $x (i64.add (local.get $x) (local.get $y)))",
    }[kind]
    return module(1, f"""
  (func (export "run") (param $reps i32) (result i64)
    (local $k i32) (local $x i64) (local $y i64) (local $f f64)
    (local.set $x (i64.const 0x123456789abcdef))
    (local.set $y (i64.const 7))
    (local.set $f (f64.const 12345.678))
    (loop $rep
      (local.set $k (i32.const {ALU_OPS_PER_REP}))
      (loop $op
        {step}
        (br_if $op (local.tee $k (i32.sub (local.get $k) (i32.const 1)))))
      (br_if $rep (local.tee $reps (i32.sub (local.get $reps) (i32.const 1)))))
    (global.set $acc (i64.add (local.get $x) (i64.reinterpret_f64 (local.get $f))))
    (global.get $acc))""")


def random_branch() -> str:
    """One data-dependent direct branch per iteration on a pseudo-random bit."""
    return module(1, f"""
  (func (export "run") (param $reps i32) (result i64) (local $k i32) (local $a i64)
    (loop $rep
      (local.set $k (i32.const {ALU_OPS_PER_REP}))
      (loop $op
        (if (i32.and (call $rand) (i32.const 1))
          (then (local.set $a (i64.add (local.get $a) (i64.const 3))))
          (else (local.set $a (i64.sub (local.get $a) (i64.const 1)))))
        (br_if $op (local.tee $k (i32.sub (local.get $k) (i32.const 1)))))
      (br_if $rep (local.tee $reps (i32.sub (local.get $reps) (i32.const 1)))))
    (global.set $acc (local.get $a))
    (global.get $acc))""")


def indirect_calls(targets: int) -> str:
    """call_indirect through a table of `targets` functions chosen pseudo-randomly."""
    funcs = "\n".join(
        f"  (func $t{i} (param i64) (result i64) (i64.add (local.get 0) (i64.const {i + 1})))"
        for i in range(targets)
    )
    names = " ".join(f"$t{i}" for i in range(targets))
    return module(1, f"""
  (type $unary (func (param i64) (result i64)))
  (table {targets} funcref)
  (elem (i32.const 0) {names})
{funcs}
  (func (export "run") (param $reps i32) (result i64) (local $k i32) (local $a i64)
    (loop $rep
      (local.set $k (i32.const {ALU_OPS_PER_REP}))
      (loop $op
        (local.set $a (call_indirect (type $unary) (local.get $a)
                        (i32.and (call $rand) (i32.const {targets - 1}))))
        (br_if $op (local.tee $k (i32.sub (local.get $k) (i32.const 1)))))
      (br_if $rep (local.tee $reps (i32.sub (local.get $reps) (i32.const 1)))))
    (global.set $acc (local.get $a))
    (global.get $acc))""")


def bulk(kind: str, length: int, ops_per_rep: int = BULK_OPS_PER_REP) -> str:
    """memory.copy or memory.fill of `length` bytes; Wasmtime charges these per byte."""
    pages = max(1, (2 * length) // WASM_PAGE + 1)
    op = (
        f"(memory.copy (i32.const {length}) (i32.const 0) (i32.const {length}))"
        if kind == "copy"
        else f"(memory.fill (i32.const 0) (i32.wrap_i64 (local.get $a)) (i32.const {length}))"
    )
    return module(pages, f"""
  (func (export "run") (param $reps i32) (result i64) (local $k i32) (local $a i64)
    (loop $rep
      (local.set $k (i32.const {ops_per_rep}))
      (loop $op
        {op}
        (local.set $a (i64.add (local.get $a) (i64.load (i32.const 8))))
        (br_if $op (local.tee $k (i32.sub (local.get $k) (i32.const 1)))))
      (br_if $rep (local.tee $reps (i32.sub (local.get $reps) (i32.const 1)))))
    (global.set $acc (local.get $a))
    (global.get $acc))""")


def size_label(n: int) -> str:
    for unit, scale in (("G", 1 << 30), ("M", 1 << 20), ("K", 1 << 10)):
        if n >= scale:
            return f"{n // scale}{unit}"
    return str(n)


def family() -> list:
    kernels = []
    for stride in (CACHE_LINE, OS_PAGE):
        for ws in CHASE_WORKING_SETS:
            if ws // stride >= 16:
                kernels.append((f"adv_chase_s{stride}_{size_label(ws)}", "chase", chase(ws, stride)))
    for unroll in CHASE_UNROLLS:
        for ws in (1 << 14, 1 << 30):
            label = f"adv_chase_s{CACHE_LINE}_{size_label(ws)}_u{unroll}"
            kernels.append((label, "chase", chase(ws, CACHE_LINE, unroll)))
    for kind in ("i64_add", "i64_mul", "i64_div", "i64_rem", "f64_div", "f64_sqrt"):
        kernels.append((f"adv_alu_{kind}", "alu", alu_chain(kind)))
    kernels.append(("adv_branch_random", "branch", random_branch()))
    for targets in INDIRECT_TARGETS:
        kernels.append((f"adv_indirect_{targets}", "indirect", indirect_calls(targets)))
    for kind in ("copy", "fill"):
        for length in BULK_LENGTHS:
            kernels.append((f"adv_bulk_{kind}_{size_label(length)}", "bulk", bulk(kind, length)))
    return kernels


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, group, text in family():
        path = OUT_DIR / f"{name}.wat"
        path.write_text(text)
        rows.append({"kernel": name, "group": f"adv_{group}", "opt_level": "wat", "path": str(path), "reps": 1})
    with PLAN_PATH.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["kernel", "group", "opt_level", "path", "reps"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} kernels to {OUT_DIR}")
    write_preemption_probe()


def write_preemption_probe() -> None:
    """A kernel whose loop body is one 256 MiB copy, to measure how long a single bulk operator
    delays an epoch interrupt. It is used only by the quota experiment, not by the search."""
    name = f"adv_bulk_copy_{size_label(PREEMPTION_PROBE_BYTES)}_single"
    path = OUT_DIR / f"{name}.wat"
    path.write_text(bulk("copy", PREEMPTION_PROBE_BYTES, ops_per_rep=1))
    with PROBE_PLAN_PATH.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["kernel", "group", "opt_level", "path", "reps"])
        writer.writerow([name, "adv_bulk", "wat", str(path), 1])


if __name__ == "__main__":
    main()
