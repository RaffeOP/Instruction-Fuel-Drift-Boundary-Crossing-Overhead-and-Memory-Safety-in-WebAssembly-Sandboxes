#!/usr/bin/env bash
# Metered Wasmer sweeps (fuel via the official metering middleware), run one backend at a time
# under a strict load gate (1-minute load <= 4).
set -u
cd "$(dirname "$0")/.."
LOG=results/logs/wasmer_metered.log
wait_quiet() {
  while true; do
    local load; load=$(uptime | sed 's/.*load averages*: //' | awk '{print $1}' | tr -d ,)
    if awk -v l="$load" 'BEGIN{exit !(l<=4)}'; then return; fi
    echo "$(date) WAITING load=$load" >> "$LOG"; sleep 60
  done
}
for spec in "llvm 100" "cranelift 100" "singlepass 10"; do
  set -- $spec
  wait_quiet
  echo "$(date) START $1" >> "$LOG"
  ./rust_harness/target/release/wasmer_fuel --backend "$1" --plan data/timing_plan.csv \
      --out "data/rq1_wasmer-$1-metered.csv" --replicates "$2" 2>> "results/logs/wasmer_metered_$1.err"
  echo "$(date) DONE $1 status=$?" >> "$LOG"
done
echo "$(date) ALL_METERED_FINISHED" >> "$LOG"
