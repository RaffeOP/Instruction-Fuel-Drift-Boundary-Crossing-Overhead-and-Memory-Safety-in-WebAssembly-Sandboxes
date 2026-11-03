#!/usr/bin/env python3
"""
Builds the five serverless-style kernels (kernels/c_src/serverless) at the four corpus
optimization levels, validates them, and writes an uncalibrated plan.

Validation: check() must agree across the four levels, and the HMAC kernel must reproduce
RFC 4231 test case 2. Modules import nothing, like the hand-written corpus kernels.

Writes kernels/build_wasm/sl_<name>-<opt>.wasm and data/serverless_plan_uncalibrated.csv.
"""

import csv
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = PROJECT_ROOT / "kernels" / "c_src" / "serverless"
BUILD_DIR = PROJECT_ROOT / "kernels" / "build_wasm"
OBJECT_DIR = PROJECT_ROOT / "kernels" / "build_obj"
PLAN = PROJECT_ROOT / "data" / "serverless_plan_uncalibrated.csv"
CLANG = "/opt/homebrew/opt/llvm/bin/clang"
WASM_LD = "/opt/homebrew/opt/lld/bin/wasm-ld"
OPT_LEVELS = ("O0", "O2", "O3", "Oz")
KERNELS = ("json_parse", "base64", "http_route", "lz_compress", "hmac_sha256")
RFC4231_CASE2_WORD0 = 0x5BDCC146
SELF_CHECK_FAILURES = (-1, -2)  # run() returns these when decode or decompression verification fails


def run(command: list) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()


def build(kernel: str, opt: str) -> Path:
    obj = OBJECT_DIR / f"sl_{kernel}-{opt}.o"
    out = BUILD_DIR / f"sl_{kernel}-{opt}.wasm"
    run([CLANG, "--target=wasm32", f"-{opt}", "-c", "-o", str(obj), str(SOURCE_DIR / f"{kernel}.c")])
    run([WASM_LD, "--no-entry", "--export-dynamic", "--export-memory", "-o", str(out), str(obj)])
    return out


def invoke(module: Path, export: str) -> int:
    return int(run(["wasmtime", "run", "--invoke", export, str(module)]).split()[-1])


def main() -> None:
    OBJECT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for kernel in KERNELS:
        checks = {}
        for opt in OPT_LEVELS:
            module = build(kernel, opt)
            checks[opt] = invoke(module, "check")
            if checks[opt] in SELF_CHECK_FAILURES:
                raise RuntimeError(f"{kernel} {opt}: self-check failed with {checks[opt]}")
            rows.append({"kernel": f"sl_{kernel}", "group": "serverless", "opt_level": opt, "path": str(module), "reps": 1})
        if len(set(checks.values())) != 1:
            raise RuntimeError(f"{kernel}: check() differs across levels: {checks}")
        if kernel == "hmac_sha256":
            for opt in OPT_LEVELS:
                word = invoke(BUILD_DIR / f"sl_{kernel}-{opt}.wasm", "rfc4231_case2_word0") & 0xFFFFFFFF
                if word != RFC4231_CASE2_WORD0:
                    raise RuntimeError(f"HMAC {opt}: RFC 4231 case 2 gives {word:#x}")
        print(f"{kernel}: check {checks['O2']} agrees across levels")
    with PLAN.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["kernel", "group", "opt_level", "path", "reps"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {PLAN}")


if __name__ == "__main__":
    main()
