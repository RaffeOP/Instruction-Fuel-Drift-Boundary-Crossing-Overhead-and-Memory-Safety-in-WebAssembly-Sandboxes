#!/usr/bin/env python3
"""
RQ2 linear-memory boundary auditor.

Each trial runs one probe in a fresh child process so that a host-level crash
(SIGSEGV/SIGBUS) is recorded as an outcome rather than terminating the audit.
Outcomes follow the classes in the W3C-conformance rate tau_trap:
  graceful_trap   : runtime raised a Trap for an access the specification traps on
  spec_return     : runtime returned the value the specification requires
  silent_corrupt  : runtime returned a value where the specification requires a trap
  host_crash      : child process terminated by a signal or non-zero exit
"""

import argparse
import csv
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = PROJECT_ROOT / "kernels" / "build_wasm" / "boundary.wasm"
DEFAULT_OUT = PROJECT_ROOT / "data" / "rq2_boundary_conformance.csv"
WASM_PAGE_BYTES = 65536
MAX_PAGES = 65536
GIB = 1 << 30
DEFAULT_GUARD_BYTES = 2 * GIB
REDUCED_GUARD_BYTES = 64 * 1024
TRIALS_PER_PROBE = 100
CSV_FIELDS = ("config", "probe", "trial", "outcome", "detail")


@dataclass(frozen=True)
class RuntimeConfig:
    name: str
    guard_bytes: Optional[int]
    signals_based_traps: bool
    reservation_for_growth: Optional[int]


CONFIGS: List[RuntimeConfig] = [
    RuntimeConfig("default_2gib_guard", DEFAULT_GUARD_BYTES, True, None),
    RuntimeConfig("reduced_64kib_guard", REDUCED_GUARD_BYTES, True, None),
    RuntimeConfig("zero_guard", 0, True, None),
    RuntimeConfig("zero_guard_explicit_checks", 0, False, None),
    RuntimeConfig("no_growth_reservation", DEFAULT_GUARD_BYTES, True, 0),
    RuntimeConfig("zero_guard_no_growth_reservation", 0, True, 0),
]

# (probe name, export, arguments, expectation)
# expectation: ("trap",) for accesses the specification must trap, or
#              ("value", v) for a required return value, or ("grow", ok_bool).
PROBES = [
    ("grow_one_page", "grow", (1,), ("grow", None)),
    ("grow_to_max_minus_one", "grow", (MAX_PAGES - 1,), ("grow", None)),
    ("grow_past_4gib", "grow", (MAX_PAGES,), ("grow", None)),
    ("store_last_word_in_bounds", "store_at", (None, 7), ("value", 7)),
    ("store_one_past_end", "store_at", (None, 7), ("trap",)),
    ("load_addr_4gib_minus_4", "load_at", (0xFFFFFFFC,), ("trap",)),
    ("load_high_half", "load_at", (0x80000000,), ("trap",)),
    ("load_at_zero", "load_at", (0,), ("in_bounds",)),
]


def build_engine(config: RuntimeConfig):
    import wasmtime

    cfg = wasmtime.Config()
    cfg.consume_fuel = False
    cfg.signals_based_traps = config.signals_based_traps
    if config.guard_bytes is not None:
        cfg.memory_guard_size = config.guard_bytes
    if config.reservation_for_growth is not None:
        cfg.memory_reservation_for_growth = config.reservation_for_growth
    return wasmtime.Engine(cfg)


def memory_pages(store, memory) -> int:
    return int(memory.size(store))


def run_probe_once(config_name: str, probe_name: str) -> dict:
    import wasmtime

    config = next(c for c in CONFIGS if c.name == config_name)
    probe = next(p for p in PROBES if p[0] == probe_name)
    _, export, args, expectation = probe
    engine = build_engine(config)
    store = wasmtime.Store(engine)
    module = wasmtime.Module.from_file(engine, str(MODULE_PATH))
    instance = wasmtime.Instance(store, module, [])
    exports = instance.exports(store)
    memory = exports["memory"]
    resolved_args = resolve_args(store, memory, args, export, expectation)
    if expectation[0] == "grow":
        expectation = ("grow", memory_pages(store, memory) + args[0] <= MAX_PAGES)
    try:
        value = exports[export](store, *resolved_args)
    except wasmtime.Trap as trap:
        return {"outcome": "graceful_trap", "detail": str(trap).splitlines()[0]}
    return {"outcome": classify_return(store, memory, value, expectation, resolved_args),
            "detail": f"returned={value}"}


def resolve_args(store, memory, args, export, expectation):
    if export == "store_at":
        boundary = memory.data_len(store) - 4
        if expectation[0] == "trap":
            return (memory.data_len(store), 7)
        return (boundary, 7)
    if export == "grow":
        return args
    return args


def classify_return(store, memory, value, expectation, resolved_args) -> str:
    kind = expectation[0]
    if kind == "grow":
        succeeded = int(value) != -1
        return "spec_return" if succeeded == expectation[1] else "silent_corrupt"
    if kind == "value":
        return "spec_return" if int(value) == expectation[1] else "silent_corrupt"
    if kind == "in_bounds":
        return "spec_return"
    return "silent_corrupt"


def run_child(config_name: str, probe_name: str) -> dict:
    command = [
        sys.executable, str(Path(__file__).resolve()), "--child",
        "--config", config_name, "--probe", probe_name,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if completed.returncode < 0:
        return {"outcome": "host_crash", "detail": f"signal={-completed.returncode}"}
    if completed.returncode != 0 and "Traceback" in completed.stderr:
        raise RuntimeError(f"probe harness failed for {config_name}/{probe_name}: "
                           f"{completed.stderr.strip().splitlines()[-1]}")
    if completed.returncode != 0:
        return {"outcome": "host_crash", "detail": f"exit={completed.returncode}"}
    return json.loads(completed.stdout.strip().splitlines()[-1])


def run_audit(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for config in CONFIGS:
            for probe in PROBES:
                for trial in range(TRIALS_PER_PROBE):
                    result = run_child(config.name, probe[0])
                    writer.writerow({
                        "config": config.name, "probe": probe[0], "trial": trial,
                        "outcome": result["outcome"], "detail": result["detail"],
                    })
                handle.flush()


def child_main(config_name: str, probe_name: str) -> None:
    result = run_probe_once(config_name, probe_name)
    print(json.dumps(result))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--config")
    parser.add_argument("--probe")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    if arguments.child:
        child_main(arguments.config, arguments.probe)
    else:
        started = time.time()
        run_audit(arguments.out)
        print(f"boundary audit finished in {time.time() - started:.1f}s")
