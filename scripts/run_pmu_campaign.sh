#!/usr/bin/env bash
# Round-4 revision campaign: PMU counters (kperf), per-replicate load log, and the
# adversarial kernel family. Must run as root because kperf needs it:
#
#   sudo ./scripts/run_pmu_campaign.sh
#
# Close other applications first. The harness waits for the 1-minute load to fall to
# LOAD_GATE before each cell and records the load before every replicate.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/rust_harness/target/release/pmu_bench"
VALIDATE="$ROOT/c_harness/kpc_validate"
OUT="$ROOT/data/pmu"
LOAD_GATE="${LOAD_GATE:-3.0}"
OWNER="${SUDO_USER:-$(id -un)}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "run with sudo: kperf counters need root" >&2
  exit 1
fi
mkdir -p "$OUT"

echo "[1/5] counter validation"
"$VALIDATE" | tee "$OUT/counter_validation.csv"

echo "[2/5] corpus, Cranelift, 100 replicates"
"$BIN" --backend cranelift --plan "$ROOT/data/timing_plan.csv" \
  --out "$OUT/pmu_corpus_cranelift.csv" --replicates 100 --load-gate "$LOAD_GATE" 2> "$OUT/log_corpus_cranelift.txt"

echo "[3/5] corpus, Winch, 100 replicates"
"$BIN" --backend winch --plan "$ROOT/data/timing_plan.csv" \
  --out "$OUT/pmu_corpus_winch.csv" --replicates 100 --load-gate "$LOAD_GATE" 2> "$OUT/log_corpus_winch.txt"

echo "[4/5] adversarial family, Cranelift, 30 replicates"
"$BIN" --backend cranelift --plan "$ROOT/data/adversarial_plan.csv" \
  --out "$OUT/pmu_adversarial_cranelift.csv" --replicates 30 --load-gate "$LOAD_GATE" 2> "$OUT/log_adv_cranelift.txt"

echo "[5/5] adversarial family, Winch, 30 replicates"
"$BIN" --backend winch --plan "$ROOT/data/adversarial_plan.csv" \
  --out "$OUT/pmu_adversarial_winch.csv" --replicates 30 --load-gate "$LOAD_GATE" 2> "$OUT/log_adv_winch.txt"

chown -R "$OWNER" "$OUT"
echo "done: results in $OUT"
