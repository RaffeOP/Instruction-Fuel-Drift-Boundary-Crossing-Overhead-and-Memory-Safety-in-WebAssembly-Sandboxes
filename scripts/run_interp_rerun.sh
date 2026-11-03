#!/usr/bin/env bash
# Re-runs the WasmEdge interpreter configuration (about 2.5 hours), whose round-4 run was cut
# short when the disk filled. On success the result replaces data/rq1_wasmedge-interp.csv.
set -euo pipefail
cd "$(dirname "$0")/.."
while awk -v l="$(sysctl -n vm.loadavg | awk '{print $2}')" 'BEGIN{exit !(l>3.0)}'; do sleep 15; done
echo "$(date +%s) START wasmedge-interp-rerun" >> results/logs/r4/extras.log
./c_harness/wasmedge_runner --runtime wasmedge-interp --plan data/timing_plan.csv \
  --out data/r4/rq1_wasmedge-interp.csv --replicates 3 --warmup 1 --run-mode interpreter \
  > /dev/null 2> >(while IFS= read -r l; do printf '%s %s\n' "$(date +%s)" "$l"; done | grep -v "\[info\]" > results/logs/r4/wasmedge-interp.err)
echo "result in data/r4/rq1_wasmedge-interp.csv; copy it to data/ and run scripts/regenerate_all.sh to use it"
echo "$(date +%s) DONE wasmedge-interp-rerun" >> results/logs/r4/extras.log
