#!/usr/bin/env python3
"""
Builds the 50-kernel corpus for the study at four frontend optimization levels.

Groups:
  polybench  : the 30 PolyBench/C 4.2.1 kernels, unmodified, MEDIUM dataset.
  integer    : 10 integer, crypto, and adversarial kernels (kernels/c_src/integer).
  memory     : 10 linear-memory kernels (kernels/c_src/memory).

Every module exports run(reps) for timing and check() for an output checksum.
PolyBench modules are linked against wasi-libc with the process-clock emulation
library; their WASI imports are satisfied by an empty WASI environment because
no timed path calls them. Handwritten modules import nothing.

Opcode profiles count instructions only in functions reachable from run(),
so the profile describes the timed path and excludes the checksum path.
"""

import csv
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

from opcode_profile import profile_module, write_profiles

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KERNEL_ROOT = PROJECT_ROOT / "kernels"
HAND_SRC = KERNEL_ROOT / "c_src"
POLYBENCH_ROOT = KERNEL_ROOT / "polybench"
WRAPPER_DIR = KERNEL_ROOT / "c_src" / "polybench_wrappers"
BUILD_DIR = KERNEL_ROOT / "build_wasm"
OBJECT_DIR = KERNEL_ROOT / "build_obj"
DATA_DIR = PROJECT_ROOT / "data"
MANIFEST_PATH = DATA_DIR / "corpus_manifest.csv"

CLANG = "/opt/homebrew/opt/llvm/bin/clang"
WASM_LD = "/opt/homebrew/opt/lld/bin/wasm-ld"
SYSROOT = "/opt/homebrew/opt/wasi-libc/share/wasi-sysroot"
POLYBENCH_GROUP_DIRS = ("linear-algebra", "stencils", "datamining", "medley")
HAND_GROUPS = ("integer", "memory")
OPT_LEVELS = ("O0", "O2", "O3", "Oz")
DATASET_FLAG = "-DMEDIUM_DATASET"
WASI_CLOCK_FLAG = "-D_WASI_EMULATED_PROCESS_CLOCKS"
WASI_CLOCK_LIB = "-lwasi-emulated-process-clocks"
PROCESS_FLAGS = ("-Dmain=pb_main",)

WRAPPER_TEMPLATE = """#include <stdarg.h>
#include <stdio.h>
#include <string.h>

static unsigned long long pb_state = 1469598103934665603ULL;

static void pb_mix(unsigned long long bits) {{
  pb_state ^= bits;
  pb_state *= 1099511628211ULL;
}}

static int pb_fprintf(FILE *stream, const char *format, ...) {{
  va_list args;
  va_start(args, format);
  for (const char *p = format; *p; p++) {{
    if (*p != '%') {{
      continue;
    }}
    p++;
    while (*p && strchr("-+ #0123456789.l", *p)) {{
      p++;
    }}
    if (*p == 'd') {{
      pb_mix((unsigned long long)(long long)va_arg(args, int));
    }} else if (*p == 'f' || *p == 'e' || *p == 'g') {{
      double value = va_arg(args, double);
      unsigned long long bits;
      memcpy(&bits, &value, sizeof bits);
      pb_mix(bits);
    }} else if (*p == 's') {{
      (void)va_arg(args, const char *);
    }}
  }}
  va_end(args);
  return 0;
}}

#define fprintf pb_fprintf
#include "{kernel_path}"

__attribute__((export_name("run")))
long long run(int reps) {{
  long long acc = 0;
  for (int r = 0; r < reps; r++) {{
    acc += pb_main(0, 0);
  }}
  return acc;
}}

__attribute__((export_name("check")))
long long check(void) {{
  char *argv[] = {{"", 0}};
  pb_state = 1469598103934665603ULL;
  pb_main(43, argv);
  return (long long)pb_state;
}}
"""

@dataclass(frozen=True)
class Kernel:
    key: str
    group: str
    source: Path

def discover_polybench() -> List[Kernel]:
    kernels = []
    for directory in POLYBENCH_GROUP_DIRS:
        for source in sorted((POLYBENCH_ROOT / directory).rglob("*.c")):
            if "int main(" in source.read_text(errors="ignore"):
                kernels.append(Kernel(f"pb_{source.stem.replace('-', '_')}", "polybench", source))
    return kernels

def discover_handwritten() -> List[Kernel]:
    kernels = []
    for group in HAND_GROUPS:
        for source in sorted((HAND_SRC / group).glob("*.c")):
            kernels.append(Kernel(source.stem, group, source))
    return kernels

def discover_all() -> List[Kernel]:
    kernels = discover_polybench() + discover_handwritten()
    keys = [k.key for k in kernels]
    if len(set(keys)) != len(keys):
        raise RuntimeError("duplicate kernel keys")
    return kernels

def write_wrapper(kernel: Kernel) -> Path:
    WRAPPER_DIR.mkdir(parents=True, exist_ok=True)
    path = WRAPPER_DIR / f"{kernel.key}_wrap.c"
    path.write_text(WRAPPER_TEMPLATE.format(kernel_path=kernel.source.resolve()))
    return path

def run_checked(command: List[str]) -> None:
    subprocess.run(command, check=True)

def build_polybench(kernel: Kernel, opt: str, output: Path) -> None:
    wrapper = write_wrapper(kernel)
    polybench_source = POLYBENCH_ROOT / "utilities" / "polybench.c"
    include_dirs = ["-I", str(POLYBENCH_ROOT / "utilities"), "-I", str(kernel.source.parent)]
    command = [
        CLANG, "--target=wasm32-wasip1", f"--sysroot={SYSROOT}", "-mexec-model=reactor",
        f"-{opt}", DATASET_FLAG, WASI_CLOCK_FLAG, *PROCESS_FLAGS, *include_dirs,
        "-o", str(output), str(wrapper), str(polybench_source), WASI_CLOCK_LIB,
    ]
    run_checked(command)

def build_handwritten(kernel: Kernel, opt: str, output: Path) -> None:
    OBJECT_DIR.mkdir(parents=True, exist_ok=True)
    object_path = OBJECT_DIR / f"{kernel.key}-{opt}.o"
    run_checked([CLANG, "--target=wasm32", f"-{opt}", "-c", "-o", str(object_path), str(kernel.source)])
    run_checked([WASM_LD, "--no-entry", "--export-dynamic", "--export-memory",
                 "--allow-undefined", "-o", str(output), str(object_path)])

def build_module(kernel: Kernel, opt: str) -> Path:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    output = BUILD_DIR / f"{kernel.key}-{opt}.wasm"
    if kernel.group == "polybench":
        build_polybench(kernel, opt, output)
    else:
        build_handwritten(kernel, opt, output)
    return output


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    kernels = discover_all()
    print(f"kernels: {len(kernels)} (polybench {sum(k.group == 'polybench' for k in kernels)}, "
          f"integer {sum(k.group == 'integer' for k in kernels)}, "
          f"memory {sum(k.group == 'memory' for k in kernels)})")
    manifest_rows = []
    for opt in OPT_LEVELS:
        profile_rows = {}
        for kernel in kernels:
            output = build_module(kernel, opt)
            profile_rows[kernel.key] = {"group": kernel.group, "counts": profile_module(output)}
            manifest_rows.append({"kernel": kernel.key, "group": kernel.group, "opt_level": opt,
                                  "wasm_bytes": output.stat().st_size, "path": str(output)})
        write_profiles(profile_rows, opt)
        print(f"built and profiled {len(profile_rows)} modules at -{opt}")
    with MANIFEST_PATH.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["kernel", "group", "opt_level", "wasm_bytes", "path"])
        writer.writeheader()
        writer.writerows(manifest_rows)
    print("manifest:", MANIFEST_PATH)


if __name__ == "__main__":
    main()
