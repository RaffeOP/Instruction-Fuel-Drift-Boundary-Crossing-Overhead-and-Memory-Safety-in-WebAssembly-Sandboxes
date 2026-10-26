#!/usr/bin/env bash
# Sequential timing sweeps: one runtime at a time, never in parallel.
# A background sampler records the 1-minute load average every 5 s so each run's
# contention can be checked afterwards. Replicate counts for slow runtimes are reduced.
set -u
cd "$(dirname "$0")/.."
LOG=results/logs/timing_sweeps.log
LOAD=data/load_log.csv
mkdir -p data results/logs
[ -s "$LOAD" ] || echo "timestamp,load1" > "$LOAD"
( while true; do echo "$(date +%s),$(uptime | sed 's/.*load averages*: //' | awk '{print $1}' | tr -d ,)" >> "$LOAD"; sleep 5; done ) &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null' EXIT

PLAN=data/timing_plan.csv
AOT_PLAN=data/timing_plan_wasmedge_aot.csv
RUST=rust_harness/target/release/r3bench
RUN_C=c_harness/wasmedge_runner
WAMR=c_harness/wamr_runner

wait_for_quiet() {
  # Waits until the 1-minute load average is at most one per core before a run starts.
  local cores; cores=$(( $(sysctl -n hw.ncpu) * 3 / 2 ))
  while true; do
    local load; load=$(uptime | sed 's/.*load averages*: //' | awk '{print $1}' | tr -d ,)
    if awk -v l="$load" -v c="$cores" 'BEGIN{exit !(l<=c)}'; then return; fi
    echo "$(date) WAITING load=$load" >> "$LOG"
    sleep 60
  done
}

run_step() {
  local name="$1"; shift
  wait_for_quiet
  if grep -q "DONE $name" "$LOG" 2>/dev/null; then return; fi
  echo "$(date) START $name" >> "$LOG"
  if "$@" 2>> "$LOG.$name.err"; then
    echo "$(date) DONE $name" >> "$LOG"
  else
    echo "$(date) FAILED $name" >> "$LOG"
  fi
}

run_step v8 env R3_REPLICATES=100 node src/v8_benchmarker.mjs
run_step wasmtime-cranelift $RUST --runtime wasmtime-cranelift --plan $PLAN --out data/rq1_wasmtime-cranelift.csv --replicates 100 --warmup 2
run_step wasmer-cranelift $RUST --runtime wasmer-cranelift --plan $PLAN --out data/rq1_wasmer-cranelift.csv --replicates 100 --warmup 2
run_step wasmer-llvm $RUST --runtime wasmer-llvm --plan $PLAN --out data/rq1_wasmer-llvm.csv --replicates 100 --warmup 2
run_step wamr-interp $WAMR --runtime wamr-interp --plan $PLAN --out data/rq1_wamr-interp.csv --replicates 10 --warmup 2
run_step wasmtime-winch $RUST --runtime wasmtime-winch --plan $PLAN --out data/rq1_wasmtime-winch.csv --replicates 100 --warmup 2
run_step wasmer-singlepass $RUST --runtime wasmer-singlepass --plan $PLAN --out data/rq1_wasmer-singlepass.csv --replicates 10 --warmup 2
run_step wasmedge-interp $RUN_C --runtime wasmedge-interp --plan $PLAN --out data/rq1_wasmedge-interp.csv --replicates 3 --warmup 1
echo "$(date) ALL_SWEEPS_FINISHED" >> "$LOG"
