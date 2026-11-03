#!/usr/bin/env bash
# Resumes the post-campaign experiments after the iCloud eviction interrupted them: the quota
# experiments, the Python recycling check, the WASI rerun, and the WasmEdge interpreter rerun.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=data/r4
LOGS=results/logs/r4
PSI_REF=0.0379
BIN=rust_harness/target/release
load1() { sysctl -n vm.loadavg | awk '{print $2}'; }
wait_quiet() { while awk -v l="$(load1)" 'BEGIN{exit !(l>3.0)}'; do sleep 15; done; }
step() {
  local name="$1"; shift
  wait_quiet
  echo "$(date +%s) START $name load=$(load1)" >> "$LOGS/extras.log"
  "$@" 2> "$LOGS/$name.err"
  echo "$(date +%s) DONE $name" >> "$LOGS/extras.log"
}
QUOTA_PLAN="$OUT/quota_plan.csv"
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
step rq3_wasi_rerun ./scripts/run_wasi_rerun.sh
echo "$(date +%s) WASI_RERUN_DONE" >> "$LOGS/extras.log"
./scripts/run_interp_rerun.sh
echo "$(date +%s) RESUME_FINISHED" >> "$LOGS/extras.log"
