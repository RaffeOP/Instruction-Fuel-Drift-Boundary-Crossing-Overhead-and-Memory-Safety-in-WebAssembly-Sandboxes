#!/usr/bin/env bash
# Re-runs the high-load reference sweeps under a stricter load gate (1-minute load <= 4).
set -u
cd "$(dirname "$0")/.."
LOG=results/logs/quiet_reruns.log
wait_for_quiet() {
  while true; do
    local load; load=$(uptime | sed 's/.*load averages*: //' | awk '{print $1}' | tr -d ,)
    if awk -v l="$load" 'BEGIN{exit !(l<=4)}'; then return; fi
    echo "$(date) WAITING load=$load" >> "$LOG"; sleep 60
  done
}
run_step() {
  local name="$1"; shift
  wait_for_quiet
  echo "$(date) START $name" >> "$LOG"
  if "$@" > "results/logs/$name.quiet.stdout" 2> "results/logs/$name.quiet.stderr"; then
    echo "$(date) DONE $name" >> "$LOG"
  else
    echo "$(date) FAILED $name" >> "$LOG"
  fi
}
run_step wasmtime-cranelift ./rust_harness/target/release/r3bench --runtime wasmtime-cranelift --plan data/timing_plan.csv --out data/rq1_wasmtime-cranelift.csv --replicates 100 --warmup 2
run_step v8 env R3_REPLICATES=100 node src/v8_benchmarker.mjs
run_step wasmer-cranelift ./rust_harness/target/release/r3bench --runtime wasmer-cranelift --plan data/timing_plan.csv --out data/rq1_wasmer-cranelift.csv --replicates 100 --warmup 2
run_step rq1_analysis /usr/local/bin/python3 src/rq1_analysis.py
echo "$(date) ALL_QUIET_RERUNS_FINISHED" >> "$LOG"
