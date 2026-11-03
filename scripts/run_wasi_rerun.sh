#!/usr/bin/env bash
# Re-runs the WASI Preview 1 / Preview 2 sweep. The guest writes its payload to stdout, which
# must go to /dev/null: that is the sink the measurement models, and a file sink fills the disk.
set -euo pipefail
cd "$(dirname "$0")/.."
while awk -v l="$(sysctl -n vm.loadavg | awk '{print $2}')" 'BEGIN{exit !(l>3.0)}'; do sleep 15; done
rust_harness/target/release/wasi_bench \
  --p1 rust_harness/wasi_guest/target/wasm32-wasip1/release/wasi_guest.wasm \
  --p2 rust_harness/wasi_guest/target/wasm32-wasip2/release/wasi_guest.wasm \
  --sizes 64,1024,16384,262144,1048576,4194304,16777216 --replicates 463 \
  --out data/r4/rq3_wasi_p1_p2.csv > /dev/null 2> results/logs/r4/rq3_wasi.err
