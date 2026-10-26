#!/usr/bin/env python3
"""Counts dynamically executed instructions per opcode class for every corpus cell.

Each module is disassembled with wasm2wat, and a stack-neutral counter increment is placed
before every instruction line in the function bodies. Each increment reads a mutable i64
global, adds one, and writes it back, so the operand stack is unchanged. The instrumented
text is reassembled with wat2wasm and executed once with the cell's timing reps. The counter
values after that call are the dynamic per-class counts for one timed call. The run result
must equal the uninstrumented module's result, which guards against a changed semantics.
"""
import csv
import re
import subprocess
import sys
from pathlib import Path

import wasmtime

sys.path.insert(0, str(Path(__file__).resolve().parent))
from opcode_profile import OPCODE_CLASSES, WASM2WAT, classify  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = PROJECT_ROOT / "data" / "timing_plan.csv"
OUT_PATH = PROJECT_ROOT / "data" / "dynamic_opcode_mix.csv"
WAT2WASM = "/opt/homebrew/bin/wat2wasm"
MNEMONIC = re.compile(r"^(\s*)([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)?)")
CLASS_NAMES = [name for name, _ in OPCODE_CLASSES] + ["other"]
INSTRUCTION_INDENT = "    "
GLOBAL_LINE = re.compile(r"^  \(global ")
FUNC_LINE = re.compile(r"^  \(func ")
DRIVER_PREFIX = "cnt_"


def counter_name(class_name: str) -> str:
    return f"${DRIVER_PREFIX}{class_name}"


def declarations(lines_before: list) -> list:
    decls = [f"  (global {counter_name(c)} (mut i64) (i64.const 0))" for c in CLASS_NAMES]
    exports = [f'  (export "{DRIVER_PREFIX}{c}" (global {counter_name(c)}))' for c in CLASS_NAMES]
    return decls + exports


def insertion_point(lines: list) -> int:
    last_global = max((i for i, line in enumerate(lines) if GLOBAL_LINE.match(line)), default=None)
    if last_global is not None:
        return last_global + 1
    return next(i for i, line in enumerate(lines) if FUNC_LINE.match(line))


def increment(class_name: str, indent: str) -> list:
    name = counter_name(class_name)
    return [f"{indent}global.get {name}", f"{indent}i64.const 1", f"{indent}i64.add",
            f"{indent}global.set {name}"]


def instrument(wat: str) -> str:
    lines = wat.splitlines()
    point = insertion_point(lines)
    out = []
    in_function = False
    for index, line in enumerate(lines):
        if index == point:
            out.extend(declarations(lines))
        if FUNC_LINE.match(line):
            in_function = True
        if in_function and line.startswith("  )"):
            in_function = False
        match = MNEMONIC.match(line) if in_function else None
        if match and not line.lstrip().startswith("("):
            out.extend(increment(classify(match.group(2)), match.group(1)))
        out.append(line)
    return "\n".join(out) + "\n"


def wasm_from_wat(wat: str, workdir: Path) -> bytes:
    source = workdir / "instrumented.wat"
    target = workdir / "instrumented.wasm"
    source.write_text(wat)
    subprocess.run([WAT2WASM, str(source), "-o", str(target)], check=True, capture_output=True)
    return target.read_bytes()


def stub_imports(store: wasmtime.Store, module: wasmtime.Module) -> list:
    stubs = []
    for item in module.imports:
        if not isinstance(item.type, wasmtime.FuncType):
            raise RuntimeError(f"unsupported non-function import {item.module}.{item.name}")
        results = list(item.type.results)

        def zero_call(*_args, _results=results):
            values = []
            for kind in _results:
                values.append(0.0 if kind.kind in ("f32", "f64") else 0)
            return values[0] if len(values) == 1 else (tuple(values) if values else None)

        stubs.append(wasmtime.Func(store, item.type, zero_call))
    return stubs


def run_once(module_bytes: bytes, reps: int, read_counters: bool) -> tuple:
    engine = wasmtime.Engine()
    store = wasmtime.Store(engine)
    module = wasmtime.Module(engine, module_bytes)
    instance = wasmtime.Instance(store, module, stub_imports(store, module))
    exports = instance.exports(store)
    result = exports["run"](store, reps)
    counts = None
    if read_counters:
        counts = {c: exports[f"{DRIVER_PREFIX}{c}"].value(store) for c in CLASS_NAMES}
    return result, counts


def count_cell(wasm_path: Path, reps: int, workdir: Path) -> dict:
    original_wat = subprocess.run([WASM2WAT, str(wasm_path)], capture_output=True, text=True,
                                  check=True).stdout
    original_bytes = wasm_from_wat(original_wat, workdir)
    reference, _ = run_once(original_bytes, reps, read_counters=False)
    instrumented_bytes = wasm_from_wat(instrument(original_wat), workdir)
    observed, counts = run_once(instrumented_bytes, reps, read_counters=True)
    if observed != reference:
        raise RuntimeError(f"instrumented result {observed} differs from reference {reference} for {wasm_path.name}")
    return {"counts": counts, "result": observed}


def main() -> int:
    import tempfile
    with PLAN_PATH.open() as handle:
        cells = list(csv.DictReader(handle))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch, OUT_PATH.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["kernel", "group", "opt_level", "reps", *CLASS_NAMES, "dynamic_total", "result"])
        workdir = Path(scratch)
        for cell in cells:
            outcome = count_cell(Path(cell["path"]), int(cell["reps"]), workdir)
            counts = outcome["counts"]
            total = sum(counts.values())
            writer.writerow([cell["kernel"], cell["group"], cell["opt_level"], cell["reps"],
                             *[counts[c] for c in CLASS_NAMES], total, outcome["result"]])
            print(cell["kernel"], cell["opt_level"], total, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
