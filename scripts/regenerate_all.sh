#!/usr/bin/env bash
# Regenerates every metric, table, and figure in the manuscript from the raw data files,
# then compiles the paper. The order matters: the round-4 generators run last because they
# replace Tables 4, 5, 8, and 17 and Figures 6 and 7 that older generators also wrote.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=/usr/local/bin/python3

$PY src/rq1_analysis.py > /dev/null
$PY src/make_figures.py
$PY src/make_tables.py
$PY src/make_springer_tables.py
$PY src/make_springer_rq_tables.py
$PY src/make_springer_appendix.py
$PY src/make_springer_appendix2.py
$PY src/calibration_v2.py > /dev/null
$PY src/make_round4_tables.py
$PY src/make_round4_figures.py
$PY src/make_round4_rq3.py > /dev/null
$PY src/analyze_quota.py > /dev/null
$PY src/load_summary.py > /dev/null
$PY src/check_paper_numbers.py
(cd paper && tectonic --keep-logs main.tex)
echo "paper/main.pdf rebuilt"
