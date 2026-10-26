#!/usr/bin/env python3
"""
Validates the 200-module corpus before any timing run.

Checks:
  1. Every module exports run and check, and check is deterministic across two instances.
  2. For each kernel, check() agrees across the four optimization levels.
  3. sha256 digest of the generated message equals hashlib.sha256 (first 4 bytes).
  4. chacha20 first keystream word matches RFC 7539 section 2.3.2 (0xe4e7f110).
"""

import csv
import hashlib
import sys
from collections import defaultdict
from pathlib import Path

import wasmtime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = PROJECT_ROOT / "data" / "corpus_manifest.csv"
OPT_LEVELS = ("O0", "O2", "O3", "Oz")
SHA_MESSAGE_BYTES = 256 * 1024
RFC7539_FIRST_WORD = 0xE4E7F110


def instantiate(path: Path):
    engine = wasmtime.Engine(wasmtime.Config())
    store = wasmtime.Store(engine)
    store.set_wasi(wasmtime.WasiConfig())
    linker = wasmtime.Linker(engine)
    linker.define_wasi()
    module = wasmtime.Module.from_file(engine, str(path))
    instance = linker.instantiate(store, module)
    return store, instance.exports(store)


def check_module(path: Path) -> int:
    store, exports = instantiate(path)
    first = int(exports["check"](store))
    second_store, second_exports = instantiate(path)
    second = int(second_exports["check"](second_store))
    if first != second:
        raise AssertionError(f"{path.name}: check() differs between instances")
    return first


def validate_sha256() -> None:
    path = PROJECT_ROOT / "kernels" / "build_wasm" / "sha256-O2.wasm"
    store, exports = instantiate(path)
    exports["run"](store, 1)
    pointer = int(exports["message_ptr"](store))
    message = bytes(exports["memory"].read(store, pointer, pointer + SHA_MESSAGE_BYTES))
    expected = int.from_bytes(hashlib.sha256(message).digest()[:4], "big")
    actual = int(exports["digest_word0"](store)) & 0xFFFFFFFF
    if actual != expected:
        raise AssertionError(f"sha256 mismatch: wasm {actual:08x} vs hashlib {expected:08x}")
    print(f"sha256 validated against hashlib: {actual:08x}")


def validate_chacha20() -> None:
    path = PROJECT_ROOT / "kernels" / "build_wasm" / "chacha20-O2.wasm"
    store, exports = instantiate(path)
    word = int(exports["rfc7539_word0"](store)) & 0xFFFFFFFF
    if word != RFC7539_FIRST_WORD:
        raise AssertionError(f"chacha20 word0 {word:08x} != RFC 7539 {RFC7539_FIRST_WORD:08x}")
    print(f"chacha20 validated against RFC 7539: {word:08x}")


def main() -> int:
    with MANIFEST.open() as handle:
        rows = list(csv.DictReader(handle))
    checksums = defaultdict(dict)
    failures = []
    for row in rows:
        path = Path(row["path"])
        try:
            checksums[row["kernel"]][row["opt_level"]] = check_module(path)
        except (AssertionError, wasmtime.WasmtimeError, KeyError) as error:
            failures.append(f"{path.name}: {error}")
    for kernel, by_opt in sorted(checksums.items()):
        values = set(by_opt.values())
        if len(values) != 1:
            failures.append(f"{kernel}: checksum differs across opt levels {by_opt}")
    validate_sha256()
    validate_chacha20()
    print(f"modules checked: {len(rows)}; kernels: {len(checksums)}")
    if failures:
        print("FAILURES:")
        for line in failures:
            print("  ", line)
        return 1
    print("all modules validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
