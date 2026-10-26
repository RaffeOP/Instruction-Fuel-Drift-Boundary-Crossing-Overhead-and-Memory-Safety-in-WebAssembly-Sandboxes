# Instruction-Fuel Drift, Boundary-Crossing Overhead, and Memory Safety in WebAssembly Sandboxes

## Authors
- **Devarsh Patel** (`devarsh.patel2024@vitstudent.ac.in`)
- **Dr. Ranjithkumar S** (*Corresponding Author*, `ranjithkumar.s@vit.ac.in`)

*School of Computer Science and Engineering (SCOPE), Vellore Institute of Technology (VIT), Vellore, Tamil Nadu, India.*

---

## Overview
This replication package contains the experimental harness, benchmark kernels, empirical dataset traces, and statistical analysis pipeline for the paper:
> **"Instruction-Fuel Drift, Boundary-Crossing Overhead, and Memory Safety in WebAssembly Sandboxes: A Multi-Runtime Measurement Study"**  
> *Target Venue: Springer Nature Journal (Cluster Computing / Journal of Cloud Computing)*

---

## Directory Structure
- `c_harness/`: C-based microbenchmarking harness and timing utilities.
- `rust_harness/`: Low-overhead embedded Rust measurement engine with in-process PMU counter support.
- `kernels/`: 50 standardized benchmark kernels (PolyBench/C, integer/cryptographic, and linear-memory kernels) across four optimization levels (`-O0`, `-O2`, `-O3`, `-Oz`).
- `data/`: Raw execution measurements, boundary probe logs, and WASI preview comparisons.
- `results/`: Processed metric summaries, ANOVA statistics, and calibration outputs.
- `scripts/`: Shell reproduction scripts for running sweeps and reproducing campaign results.
- `src/`: Python analysis pipelines, parametric statistics engine, and figure/table generators.
- `tables/`: Publication LaTeX table fragments.
- `figures/`: Publication vector plots and diagrams.
- `paper/`: Complete LaTeX source (`main.tex`, `main.pdf`) using the Springer Nature `sn-jnl` class.
- `tests/`: Automated test suite for data validation and analysis modules.

---

## Prerequisites & Setup

### Environment Requirements
- Python 3.10+ (recommended: Python 3.12)
- Rust toolchain (`cargo`, `rustc`) with `wasm32-wasip1` / `wasm32-wasip2` targets
- `tectonic` or `pdflatex` for compiling the manuscript

### Python Dependencies
```bash
pip install -r requirements.txt
```

---

## Reproducing Empirical Results

### 1. Regenerate Figures and Tables from Stored Data
```bash
python3 src/make_figures.py
python3 src/make_tables.py
python3 src/make_springer_tables.py
python3 src/make_springer_rq_tables.py
```

### 2. Run Analysis Pipelines
```bash
python3 src/rq1_analysis.py
python3 src/memory_boundary_auditor.py
python3 src/host_call_benchmarker.py
python3 src/dynamic_opcode_counter.py
```

### 3. Compile the Manuscript
```bash
cd paper
tectonic main.tex
```

---

## License
This replication package is released under the MIT License. See [LICENSE](LICENSE) for details.
