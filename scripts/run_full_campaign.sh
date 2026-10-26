#!/usr/bin/env bash
# Full timed campaign, run strictly one experiment at a time. Each step starts only when the
# 1-minute load average is at most 4. A sampler logs load every 5 s throughout.
set -u
cd "$(dirname "$0")/.."
LOG=results/logs/full_campaign.log
LOAD=data/load_log.csv
mkdir -p data results/logs
[ -s "$LOAD" ] || echo "timestamp,load1" > "$LOAD"
( while true; do echo "$(date +%s),$(uptime | sed 's/.*load averages*: //' | awk '{print $1}' | tr -d ,)" >> "$LOAD"; sleep 5; done ) &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null' EXIT

wait_quiet() {
  while true; do
    local load; load=$(uptime | sed 's/.*load averages*: //' | awk '{print $1}' | tr -d ,)
    if awk -v l="$load" 'BEGIN{exit !(l<=4)}'; then return; fi
    echo "$(date) WAITING load=$load" >> "$LOG"; sleep 60
  done
}
step() {
  local name="$1"; shift
  wait_quiet
  echo "$(date) START $name" >> "$LOG"
  if "$@" > "results/logs/campaign_$name.out" 2> "results/logs/campaign_$name.err"; then
    echo "$(date) DONE $name" >> "$LOG"
  else
    echo "$(date) FAILED $name" >> "$LOG"
  fi
}
R3=./rust_harness/target/release
step wasmtime-cranelift $R3/r3bench --runtime wasmtime-cranelift --plan data/timing_plan.csv --out data/rq1_wasmtime-cranelift.csv --replicates 100 --warmup 2
step wasmtime-winch $R3/r3bench --runtime wasmtime-winch --plan data/timing_plan.csv --out data/rq1_wasmtime-winch.csv --replicates 100 --warmup 2
step wasmer-cranelift $R3/r3bench --runtime wasmer-cranelift --plan data/timing_plan.csv --out data/rq1_wasmer-cranelift.csv --replicates 100 --warmup 2
step wasmer-llvm $R3/r3bench --runtime wasmer-llvm --plan data/timing_plan.csv --out data/rq1_wasmer-llvm.csv --replicates 100 --warmup 2
step wasmer-singlepass $R3/r3bench --runtime wasmer-singlepass --plan data/timing_plan.csv --out data/rq1_wasmer-singlepass.csv --replicates 10 --warmup 2
step wasmer-cranelift-metered $R3/wasmer_fuel --backend cranelift --plan data/timing_plan.csv --out data/rq1_wasmer-cranelift-metered.csv --replicates 100
step wasmer-llvm-metered $R3/wasmer_fuel --backend llvm --plan data/timing_plan.csv --out data/rq1_wasmer-llvm-metered.csv --replicates 100
step wasmer-singlepass-metered $R3/wasmer_fuel --backend singlepass --plan data/timing_plan.csv --out data/rq1_wasmer-singlepass-metered.csv --replicates 10
step wamr-interp ./c_harness/wamr_runner --runtime wamr-interp --plan data/timing_plan.csv --out data/rq1_wamr-interp.csv --replicates 10 --warmup 2
step wasmedge-interp ./c_harness/wasmedge_runner --runtime wasmedge-interp --plan data/timing_plan.csv --out data/rq1_wasmedge-interp.csv --replicates 3 --warmup 1 --run-mode interpreter
step wasmedge-aot ./c_harness/wasmedge_runner --runtime wasmedge-aot --plan data/timing_plan_wasmedge_aot.csv --out data/rq1_wasmedge-aot.csv --replicates 100 --warmup 2 --run-mode aot
step v8 env R3_REPLICATES=100 node src/v8_benchmarker.mjs
step rq3_host /usr/local/bin/python3 src/host_call_benchmarker.py
step rq4_pooled /usr/local/bin/python3 src/pooled_recycling_auditor.py
step rq4_ondemand_process /usr/local/bin/python3 src/recycling_auditor.py
step init_share /usr/local/bin/python3 src/init_share_analysis.py
echo "$(date) CAMPAIGN_FINISHED" >> "$LOG"
