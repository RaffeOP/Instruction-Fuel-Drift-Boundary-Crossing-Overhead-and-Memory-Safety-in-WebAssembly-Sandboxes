#!/usr/bin/env bash
# Re-times the steps whose campaign windows were contended (WasmEdge AOT, V8) and the host-call sweep,
# with a per-replicate (per-sample for the host-call sweep) 1-minute load gate of 4.
set -u
cd "$(dirname "$0")/.."
LOG=results/logs/gated_rerun.log
stamp() { date "+%a %b %d %H:%M:%S IST %Y"; }
echo "$(stamp) START wasmedge-aot" >> "$LOG"
./c_harness/wasmedge_runner --runtime wasmedge-aot --plan data/timing_plan_wasmedge_aot.csv \
  --out data/rq1_wasmedge-aot.csv --replicates 100 --warmup 2 --run-mode aot > /dev/null 2> results/logs/gated_aot.err
echo "$(stamp) DONE wasmedge-aot status=$?" >> "$LOG"
echo "$(stamp) START v8" >> "$LOG"
env R3_REPLICATES=100 node src/v8_benchmarker.mjs > results/logs/gated_v8.out 2> results/logs/gated_v8.err
echo "$(stamp) DONE v8 status=$?" >> "$LOG"
echo "$(stamp) START rq3_host" >> "$LOG"
/usr/local/bin/python3 src/host_call_benchmarker.py > results/logs/gated_rq3.out 2> results/logs/gated_rq3.err
echo "$(stamp) DONE rq3_host status=$?" >> "$LOG"
echo "$(stamp) GATED_RERUNS_FINISHED" >> "$LOG"
