"""Opcode-class profile of a WebAssembly module's reachable functions.

The static profile counts instruction lines of the functions reachable from a module's run export,
using the wasm2wat text. The class table and the classifier are shared with the dynamic counter.
"""
import csv
import re
import subprocess
from collections import deque
from pathlib import Path
from typing import Dict, List, Set

WASM2WAT = "/opt/homebrew/bin/wasm2wat"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

FUNC_DEFINITION = re.compile(r"^  \(func(?: (\$[^\s()]+))?[\s)]")

IMPORT_FUNC = re.compile(r"^  \(import \"[^\"]*\" \"[^\"]*\" \(func(?: (\$[^\s()]+))?[\s)]")

EXPORT_LINE = re.compile(r'\(export "(\w+)" \(func (\$[^\s)]+|\d+)\)\)')

CALL_LINE = re.compile(r"^\s*call (\$[^\s)]+|\d+)\)?\s*$")

MNEMONIC = re.compile(r"^\s*([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)?)")

OPCODE_CLASSES = (
    ("int_arith", r"^(i32|i64)\.(add|sub|mul|div_[su]|rem_[su]|and|or|xor|shl|shr_[su]|rotl|rotr)$"),
    ("float_arith", r"^(f32|f64)\.(add|sub|mul|div|sqrt|min|max|abs|neg)$"),
    ("compare", r"^(i32|i64|f32|f64)\.(eq|ne|lt_[su]?|gt_[su]?|le_[su]?|ge_[su]?|eqz)$"),
    ("memory_load", r"^(i32|i64|f32|f64)\.load"),
    ("memory_store", r"^(i32|i64|f32|f64)\.store"),
    ("branch", r"^(br|br_if|br_table)$"),
    ("control", r"^(block|loop|if|else|end)$"),
    ("call", r"^call(_indirect)?$"),
    ("local_global", r"^(local|global)\.(get|set|tee)$"),
    ("const", r"^(i32|i64|f32|f64)\.const$"),
    ("conversion", r"^(i32|i64|f32|f64)\.(wrap|trunc|extend|convert|reinterpret|demote|promote)"),
    ("memory_ops", r"^memory\."),
)

def parse_functions(wat: str):
    """Returns (index->body lines, name->index, export name->target) for module-level functions.

    Function indices count imported functions first, then definitions in order,
    which matches the WebAssembly index space that call and export refer to.
    """
    bodies: Dict[int, List[str]] = {}
    name_to_index: Dict[str, int] = {}
    exports: Dict[str, str] = {}
    next_index = 0
    current = None
    for line in wat.splitlines():
        imported = IMPORT_FUNC.match(line)
        if imported:
            if imported.group(1):
                name_to_index[imported.group(1)] = next_index
            next_index += 1
            current = None
            continue
        definition = FUNC_DEFINITION.match(line)
        if definition:
            current = next_index
            bodies[current] = []
            if definition.group(1):
                name_to_index[definition.group(1)] = current
            next_index += 1
            continue
        export = EXPORT_LINE.search(line)
        if export:
            exports[export.group(1)] = export.group(2)
        if current is not None and line.startswith("  ") and not line.startswith("   ("):
            current_body = bodies[current]
            current_body.append(line.strip())
    return bodies, name_to_index, exports

def resolve(target: str, name_to_index: Dict[str, int]) -> int:
    return name_to_index[target] if target.startswith("$") else int(target)

def reachable_from(entry: int, bodies: Dict[int, List[str]], name_to_index: Dict[str, int]) -> Set[int]:
    seen = {entry}
    queue = deque([entry])
    while queue:
        current = queue.popleft()
        for line in bodies.get(current, []):
            call = CALL_LINE.match(line)
            if call:
                target = resolve(call.group(1), name_to_index)
                if target not in seen:
                    seen.add(target)
                    queue.append(target)
    return seen

def classify(mnemonic: str) -> str:
    for name, pattern in OPCODE_CLASSES:
        if re.match(pattern, mnemonic):
            return name
    return "other"

def profile_module(wasm_path: Path) -> Dict[str, int]:
    wat = subprocess.run([WASM2WAT, str(wasm_path)], capture_output=True, text=True, check=True).stdout
    bodies, name_to_index, exports = parse_functions(wat)
    if "run" not in exports:
        raise RuntimeError(f"{wasm_path.name} does not export run")
    entry = resolve(exports["run"], name_to_index)
    counts = {name: 0 for name, _ in OPCODE_CLASSES}
    counts["other"] = 0
    for index in reachable_from(entry, bodies, name_to_index):
        for line in bodies.get(index, []):
            match = MNEMONIC.match(line)
            if match:
                counts[classify(match.group(1))] += 1
    return counts

def write_profiles(rows: Dict[str, Dict[str, object]], opt: str) -> None:
    out_path = DATA_DIR / f"opcode_mix_{opt}.csv"
    columns = [name for name, _ in OPCODE_CLASSES] + ["other"]
    with out_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["kernel", "group", *columns])
        for key in sorted(rows):
            writer.writerow([key, rows[key]["group"], *(rows[key]["counts"][c] for c in columns)])
