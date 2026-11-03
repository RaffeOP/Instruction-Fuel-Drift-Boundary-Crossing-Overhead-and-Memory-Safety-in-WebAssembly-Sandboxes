#!/usr/bin/env bash
# Round-4 gated rerun of the twelve-configuration RQ1 campaign and the RQ3 sweeps.
#
# Load control: a sampler appends (unix time, 1-minute load) to data/r4/load_samples.csv
# every 2 s, and every runner's per-cell "done" line is timestamped on arrival, so each
# cell's execution window can be joined to the load samples it overlapped. Each step
# starts only when the 1-minute load is at or below LOAD_GATE.
set -u
cd "$(dirname "$0")/.."

OUT=data/r4
LOGS=results/logs/r4
LOAD_GATE="${LOAD_GATE:-3.0}"
SAMPLE_PERIOD=2
GATE_POLL=15
mkdir -p "$OUT" "$LOGS"

load1() { sysctl -n vm.loadavg | awk '{print $2}'; }
echo "unix_time,load1" > "$OUT/load_samples.csv"
( while true; do echo "$(date +%s),$(load1)" >> "$OUT/load_samples.csv"; sleep "$SAMPLE_PERIOD"; done ) &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null' EXIT

wait_quiet() {
  while awk -v l="$(load1)" -v g="$LOAD_GATE" 'BEGIN{exit !(l>g)}'; do sleep "$GATE_POLL"; done
}

# Prefixes every stderr line with the unix time at which it arrived.
stamp_lines() { while IFS= read -r line; do printf '%s %s\n' "$(date +%s)" "$line"; done; }

step() {
  local name="$1"; shift
  wait_quiet
  echo "$(date +%s) START $name load=$(load1)" >> "$LOGS/campaign.log"
  if "$@" > "$LOGS/$name.out" 2> >(stamp_lines > "$LOGS/$name.err"); then
    echo "$(date +%s) DONE $name" >> "$LOGS/campaign.log"
  else
    echo "$(date +%s) FAILED $name" >> "$LOGS/campaign.log"
  fi
}

PLAN=data/timing_plan.csv
AOT_PLAN=data/timing_plan_wasmedge_aot.csv
R=./rust_harness/target/release
step wasmtime-cranelift $R/r3bench --runtime wasmtime-cranelift --plan $PLAN --out $OUT/rq1_wasmtime-cranelift.csv --replicates 100 --warmup 2
step wasmtime-winch $R/r3bench --runtime wasmtime-winch --plan $PLAN --out $OUT/rq1_wasmtime-winch.csv --replicates 100 --warmup 2
step wasmer-cranelift $R/r3bench --runtime wasmer-cranelift --plan $PLAN --out $OUT/rq1_wasmer-cranelift.csv --replicates 100 --warmup 2
step wasmer-llvm $R/r3bench --runtime wasmer-llvm --plan $PLAN --out $OUT/rq1_wasmer-llvm.csv --replicates 100 --warmup 2
step wasmer-singlepass $R/r3bench --runtime wasmer-singlepass --plan $PLAN --out $OUT/rq1_wasmer-singlepass.csv --replicates 10 --warmup 2
step wasmer-cranelift-metered $R/wasmer_fuel --backend cranelift --plan $PLAN --out $OUT/rq1_wasmer-cranelift-metered.csv --replicates 100
step wasmer-llvm-metered $R/wasmer_fuel --backend llvm --plan $PLAN --out $OUT/rq1_wasmer-llvm-metered.csv --replicates 100
step wasmer-singlepass-metered $R/wasmer_fuel --backend singlepass --plan $PLAN --out $OUT/rq1_wasmer-singlepass-metered.csv --replicates 10
step wamr-interp ./c_harness/wamr_runner --runtime wamr-interp --plan $PLAN --out $OUT/rq1_wamr-interp.csv --replicates 10 --warmup 2
step wasmedge-aot ./c_harness/wasmedge_runner --runtime wasmedge-aot --plan $AOT_PLAN --out $OUT/rq1_wasmedge-aot.csv --replicates 100 --warmup 2 --run-mode aot
step v8 env R3_REPLICATES=100 R3_PLAN=$PLAN R3_OUT=$OUT/rq1_v8.csv node src/v8_benchmarker.mjs
step rq3_host_rust $R/host_bench --module kernels/build_wasm/host_boundary.wasm --out $OUT/rq3_host_call_rust.csv --replicates 200
step rq3_wasi ./scripts/run_wasi_rerun.sh
# (was: $R/wasi_bench, whose stdout must go to /dev/null; see run_wasi_rerun.sh)
: $R/wasi_bench --p1 rust_harness/wasi_guest/target/wasm32-wasip1/release/wasi_guest.wasm \
  --p2 rust_harness/wasi_guest/target/wasm32-wasip2/release/wasi_guest.wasm \
  --sizes 64,1024,16384,262144,1048576,4194304,16777216 --replicates 463 --out $OUT/rq3_wasi_p1_p2.csv
step wasmedge-interp ./c_harness/wasmedge_runner --runtime wasmedge-interp --plan $PLAN --out $OUT/rq1_wasmedge-interp.csv --replicates 3 --warmup 1 --run-mode interpreter
echo "$(date +%s) CAMPAIGN_FINISHED" >> "$LOGS/campaign.log"
