#!/usr/bin/env bash
# WASI Preview 1 versus Preview 2 write-cost benchmark, run only when load is at most 4.
set -u
cd "$(dirname "$0")/.."
LOG=results/logs/wasi_bench.log
while true; do
  load=$(uptime | sed 's/.*load averages*: //' | awk '{print $1}' | tr -d ,)
  if awk -v l="$load" 'BEGIN{exit !(l<=4)}'; then break; fi
  echo "$(date) WAITING load=$load" >> "$LOG"; sleep 60
done
echo "$(date) START wasi_bench load=$load" >> "$LOG"
./rust_harness/target/release/wasi_bench \
  --p1 rust_harness/wasi_guest/target/wasm32-wasip1/release/wasi_guest.wasm \
  --p2 rust_harness/wasi_guest/target/wasm32-wasip2/release/wasi_guest.wasm \
  --sizes 64,1024,16384,262144,1048576,4194304,16777216 --replicates 463 \
  --out data/rq3_wasi_p1_p2.csv > /dev/null 2> results/logs/wasi_bench.err
echo "$(date) DONE wasi_bench status=$?" >> "$LOG"
