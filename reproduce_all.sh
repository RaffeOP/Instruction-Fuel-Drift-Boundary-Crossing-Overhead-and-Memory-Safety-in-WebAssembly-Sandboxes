#!/usr/bin/env bash
# ==============================================================================
# Master Reproduction Script for Paper R3:
# "Instruction-Fuel Drift, Boundary-Crossing Overhead, and Memory Safety
#  in WebAssembly Sandboxes: A Multi-Runtime Measurement Study"
# Journal of Circuits, Systems, and Computers (JCSC), World Scientific
# ==============================================================================
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PYTHON="${PYTHON:-python3}"

echo "========================================================================"
echo " [Step 1/4] Checking Environment & Python Dependencies"
echo "========================================================================"
command -v "$PYTHON" >/dev/null 2>&1 || { echo >&2 "Python3 not found."; exit 1; }
"$PYTHON" -c "import numpy, scipy, pandas, matplotlib; print('Core numerical & plotting libraries available.')"

echo "========================================================================"
echo " [Step 2/4] Regenerating Statistical Metrics, LaTeX Tables & Figures"
echo "========================================================================"
"$PYTHON" src/rq1_analysis.py > /dev/null
"$PYTHON" src/make_figures.py
"$PYTHON" src/make_tables.py
"$PYTHON" src/make_springer_tables.py
"$PYTHON" src/make_springer_rq_tables.py
"$PYTHON" src/make_springer_appendix.py
"$PYTHON" src/make_springer_appendix2.py
"$PYTHON" src/calibration_v2.py > /dev/null
"$PYTHON" src/make_round4_tables.py
"$PYTHON" src/make_round4_figures.py
"$PYTHON" src/make_round4_rq3.py > /dev/null
"$PYTHON" src/analyze_quota.py > /dev/null
"$PYTHON" src/load_summary.py > /dev/null

echo "========================================================================"
echo " [Step 3/4] Verifying Core Empirical & Microarchitectural Bounds"
echo "========================================================================"
"$PYTHON" verify_bounds.py

echo "========================================================================"
echo " [Step 4/4] Building World Scientific JCSC Manuscript PDF"
echo "========================================================================"
if command -v tectonic >/dev/null 2>&1; then
    (cd paper && tectonic --keep-logs main.tex)
elif [ -x /opt/homebrew/bin/tectonic ]; then
    (cd paper && /opt/homebrew/bin/tectonic --keep-logs main.tex)
else
    (cd paper && pdflatex -interaction=nonstopmode main.tex && bibtex main && pdflatex -interaction=nonstopmode main.tex)
fi

echo "========================================================================"
echo " SUCCESS: Full reproduction complete. PDF generated at paper/main.pdf"
echo "========================================================================"
