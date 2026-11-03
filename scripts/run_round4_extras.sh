#!/usr/bin/env bash
# Experiments added after the review that need no root: serverless-style kernel timing,
# the DualGate quota experiments, and the Python recycling-harness check. Each step waits for
# the 1-minute load to fall to LOAD_GATE.
set -euo pipefail
cd "$(dirname "$0")/.."

OUT=data/r4
LOGS=results/logs/r4
LOAD_GATE="${LOAD_GATE:-3.0}"
PSI_REF=0.0379   # benign median cost per fuel unit, Cranelift, gated kperf campaign (ns)
BIN=rust_harness/target/release
mkdir -p "$OUT" "$LOGS"

load1() { sysctl -n vm.loadavg | awk '{print $2}'; }
wait_quiet() { while awk -v l="$(load1)" -v g="$LOAD_GATE" 'BEGIN{exit !(l>g)}'; do sleep 15; done; }
step() {
  local name="$1"; shift
  wait_quiet
  echo "$(date +%s) START $name load=$(load1)" >> "$LOGS/extras.log"
  "$@" 2> "$LOGS/$name.err"
  echo "$(date +%s) DONE $name" >> "$LOGS/extras.log"
}

# Combined plan for enforcement: corpus, serverless, and adversarial kernels.
QUOTA_PLAN="$OUT/quota_plan.csv"
{ cat data/timing_plan.csv; tail -n +2 data/serverless_plan.csv; tail -n +2 data/adversarial_plan.csv; } > "$QUOTA_PLAN"

step serverless_cranelift $BIN/pmu_bench --pmu 0 --backend cranelift --plan data/serverless_plan.csv \
  --out "$OUT/serverless_cranelift.csv" --replicates 100 --load-gate "$LOAD_GATE"
step serverless_winch $BIN/pmu_bench --pmu 0 --backend winch --plan data/serverless_plan.csv \
  --out "$OUT/serverless_winch.csv" --replicates 100 --load-gate "$LOAD_GATE"
step quota_enforce_cranelift $BIN/quota_bench --mode enforce --backend cranelift --plan "$QUOTA_PLAN" \
  --out "$OUT/quota_enforce_cranelift.csv" --psi-ref $PSI_REF --replicates 5
step quota_enforce_winch $BIN/quota_bench --mode enforce --backend winch --plan data/adversarial_plan.csv \
  --out "$OUT/quota_enforce_winch.csv" --psi-ref $PSI_REF --replicates 5
step quota_probe $BIN/quota_bench --mode enforce --backend cranelift --plan data/quota_probe_plan.csv \
  --out "$OUT/quota_probe_cranelift.csv" --psi-ref $PSI_REF --replicates 5
step quota_overhead $BIN/quota_bench --mode overhead --backend cranelift --plan data/timing_plan.csv \
  --out "$OUT/quota_overhead_cranelift.csv" --replicates 20
for TICK in 100 10000; do
  step "quota_tick_$TICK" $BIN/quota_bench --mode enforce --backend cranelift --plan data/adversarial_plan.csv \
    --out "$OUT/quota_tick_${TICK}us.csv" --psi-ref $PSI_REF --replicates 3 --tick-us $TICK
done
step rq4_python_check /usr/local/bin/python3 src/rq4_python_buffer_check.py
echo "$(date +%s) EXTRAS_FINISHED" >> "$LOGS/extras.log"
