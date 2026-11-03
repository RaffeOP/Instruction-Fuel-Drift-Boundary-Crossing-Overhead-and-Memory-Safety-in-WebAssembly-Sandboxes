#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."
LOG=results/logs/remaining_experiments.log
wait_for_quiet() {
  local cores; cores=$(sysctl -n hw.ncpu)
  while true; do
    local load; load=$(uptime | sed 's/.*load averages*: //' | awk '{print $1}' | tr -d ,)
    if awk -v l="$load" -v c="$cores" 'BEGIN{exit !(l<=c)}'; then return; fi
    echo "$(date) WAITING load=$load" >> "$LOG"; sleep 60
  done
}
run_step() {
  local name="$1"; shift
  wait_for_quiet
  echo "$(date) START $name (rerun)" >> "$LOG"
  if "$@" > "results/logs/$name.stdout" 2> "results/logs/$name.stderr"; then
    echo "$(date) DONE $name (rerun)" >> "$LOG"
  else
    echo "$(date) FAILED $name (rerun)" >> "$LOG"
  fi
}
run_step rq2_boundary /usr/local/bin/python3 src/memory_boundary_auditor.py
run_step rq3_host /usr/local/bin/python3 src/host_call_benchmarker.py
run_step rq4_recycling /usr/local/bin/python3 src/recycling_auditor.py
run_step rq1_analysis /usr/local/bin/python3 src/rq1_analysis.py
echo "$(date) ALL_EXPERIMENTS_FINISHED (rerun)" >> "$LOG"
