# Replication Package: Instruction-Fuel Drift in WebAssembly Sandboxes

Official artifact and replication repository for the research manuscript:
> **"Instruction-Fuel Drift, Boundary-Crossing Overhead, and Memory Safety in WebAssembly Sandboxes: A Multi-Runtime Measurement Study"**  
> *Journal of Circuits, Systems, and Computers (JCSC)*, World Scientific.

### Authors
- **Devarsh Patel** (First Author) — *School of Computer Science and Engineering (SCOPE), Vellore Institute of Technology (VIT), Vellore, Tamil Nadu, 632014, India* (`devarsh.patel2024@vitstudent.ac.in`)
- **Ranjithkumar S** (Corresponding Author) — *School of Computer Science and Engineering (SCOPE), Vellore Institute of Technology (VIT), Vellore, Tamil Nadu, 632014, India* (`ranjithkumar.s@vit.ac.in`)

---

## 1. Overview & Key Empirical Findings

Multi-tenant serverless and edge platforms enforce resource boundaries using **instruction fuel** metering. This replication package contains the full empirical telemetry, microarchitectural performance counter traces, benchmarking harnesses, adversarial kernels, and end-to-end reproduction scripts for our measurement study across 12 runtime configurations on an 8-core ARMv8.6-A processor under a load-logged execution environment.

### Core Discoveries:
1. **Benign Fuel-to-Time Dispersion ($34\times\text{--}38\times$):** Across 50 benchmark kernels and four frontend optimization tiers (`-O0`, `-O2`, `-O3`, `-Oz`), the CPU execution time per unit of instruction fuel under Wasmtime's Cranelift compiler exhibits a 34- to 38-fold dispersion ($0.010\text{ ns}$ to $0.402\text{ ns}$ per fuel unit).
2. **Microarchitectural Attribution (84% Variance):** Hardware performance monitoring unit (PMU) counters establish that cycles per native instruction ($\mathrm{CPI}_{\mathrm{native}}$) explains **$84\%$ of the log-variance** in fuel unit cost, with cache misses, TLB walks, and branch mispredictions accounting for approximately half of the observed dispersion.
3. **Adversarial Worst Case ($260\times$ Benign Max):** Structured adversarial memory traversal raising dependent cache-missing loads achieves **$93.8\text{ ns}$ per fuel unit**---$260\times$ the benign maximum and $8{,}879\times$ the benign minimum.
4. **Winch Accounting Gap ($15{,}673\times$):** Wasmtime's Winch baseline compiler meters bulk-memory instructions (`memory.copy`, `memory.fill`) per operation rather than per byte, creating an unbounded accounting discrepancy ($7{,}518\text{ ns}$ per fuel unit on 4 MiB copies, $15{,}673\times$ Winch benign maximum).
5. **Linear Recalibration Failure:** Static opcode re-weighting under leave-one-kernel-out (LOKO) cross-validation fails to reduce prediction error ($0.682$ log score vs $0.551$ for hardware counters), and fails completely under adversarial code.
6. **DualGate CPU-Time Enforcement:** Coupling instruction fuel with asynchronous epoch interruption strictly confines execution within **$6.3\%$ of a 20 ms CPU budget** across benign, serverless, and adversarial workloads, where fuel alone overshoots by up to $49\times$, at a minimal geometric-mean overhead of $6.8\%$.
7. **Sandbox Boundary Conformance:** 4,800 single-operation linear-memory probes and 4,200 compound trials yielded 0 silent memory corruptions and 0 host panics.

---

## 2. Directory Structure

```
replication_package_R3/
├── README.md                          # Comprehensive replication documentation
├── LICENSE                            # MIT License
├── requirements.txt                   # Pinned Python dependencies
├── reproduce_all.sh                   # One-click master script: regenerates tables, figures & paper
├── verify_bounds.py                   # Automated assertion check of all 19 paper claims
├── data/                              # Raw empirical telemetry & load logs (114 MB)
│   ├── pmu/                           # Apple PMU / kperf cycle, instruction, and cache traces
│   ├── r4/                            # Host-call and compound trial execution logs
│   ├── rq1_wasmtime-cranelift.csv     # 20,000 Cranelift execution records
│   ├── rq1_wasmtime-winch.csv         # 20,000 Winch execution records
│   └── corpus_manifest.csv            # 200 compiled bytecode module catalog
├── figures/                           # Publication vector PDFs (fig01 to fig08)
├── tables/                            # Generated publication LaTeX tables (tab01 to tab25)
├── kernels/                           # Benchmark corpus & test modules
│   ├── c_src/                         # Integer, hashing, and linear-memory C kernels
│   ├── polybench/                     # PolyBench/C numerical benchmarks
│   ├── adversarial/                   # Cache-thrashing & dependent load kernels
│   └── build_wasm/                    # 200 pre-compiled WebAssembly bytecode binaries
├── rust_harness/                      # Rust multi-runtime driver (Wasmtime, Wasmer, V8)
│   ├── Cargo.toml                     # Cargo workspace configuration
│   └── src/                           # DualGate, boundary stress, and recycling runners
├── c_harness/                         # C embedder harnesses for WAMR & WasmEdge
├── src/                               # Statistical analysis & figure generation pipelines
│   ├── rq1_analysis.py                # Fuel-to-time dispersion analysis
│   ├── calibration_v2.py              # LOKO ridge regression & cross-validation
│   ├── dynamic_calibration.py         # Dynamic opcode class evaluation
│   ├── make_round4_tables.py          # Publication table formatters
│   ├── make_round4_figures.py         # Matplotlib publication figures
│   └── check_paper_numbers.py         # Paper assertion validation script
├── scripts/                           # Harness compilation & benchmark runners
├── literature/                        # Verified CrossRef BibTeX database
└── paper/                             # Publication manuscript source
    ├── main.tex                       # World Scientific JCSC LaTeX source
    ├── main.pdf                       # Typeset 50-page publication PDF
    ├── ws-jcsc.cls                    # Official JCSC LaTeX2e document class
    ├── ws-jcsc.bst                    # World Scientific numeric BibTeX style
    └── compile_paper.sh               # Deterministic build script (tectonic / pdflatex)
```

---

## 3. Quick Start & Reproduction

### Prerequisites
- Python 3.10+ with `pip`
- Rust 1.75+ (optional, only if recompiling Rust runtime harnesses)
- `tectonic` or standard TeX Live (for compiling the manuscript PDF)

### Installation
```bash
# Clone the repository
git clone https://github.com/RaffeOP/Instruction_Fuel_Drift_in_WebAssembly_Sandboxes.git
cd Instruction_Fuel_Drift_in_WebAssembly_Sandboxes

# Install Python dependencies
pip install -r requirements.txt
```

### End-to-End Reproduction (One Command)
Run the master script to reproduce all statistical models, re-verify all mathematical bounds, regenerate all LaTeX tables and figures from raw telemetry, and compile the final PDF:

```bash
./reproduce_all.sh
```

### Standalone Paper Claim Verification
To recompute the headline metrics directly from `data/` and verify that every claimed number in `paper/main.tex` matches with zero deviation:

```bash
python3 verify_bounds.py
```
Expected output:
```
OK   A_adv Cranelift, cross-runtime rerun: recomputed 38.3, text needle '=38.3$'
OK   A_adv Cranelift, kperf run: recomputed 34.1, text needle '$34.1$'
OK   fuel O0/O2 min: recomputed 0.36, text needle '$0.36$'
OK   fuel O0/O2 max: recomputed 6.5, text needle '$6.5$'
OK   Winch disagreement cells above noise: recomputed 20, text needle 'in 20 cells above numerical noise'
OK   flat-bulk Cranelift equals Winch in all cells: recomputed 200, text needle 'all 200 cells'
OK   r(time, fuel): recomputed 0.73, text needle '$r=0.73$'
OK   Winch time ratio: recomputed 2.11, text needle 'Winch is at $2.11$'
OK   WasmEdge AOT ratio: recomputed 0.77, text needle 'WasmEdge AOT at $0.77$'
OK   adversarial max Cranelift: recomputed 93.8, text needle '$93.8$'
OK   adversarial max / benign max: recomputed 260, text needle '$260$'
OK   adversarial max / benign min: recomputed 8{,}879, text needle '$8{,}879$'
OK   Winch bulk copy 4M psi: recomputed 7{,}518, text needle '$7{,}518$'
OK   Winch bulk / Winch benign max: recomputed 15{,}673, text needle '$15{,}673$'
OK   LOKO dynamic shares: recomputed 0.682, text needle '$0.682$'
OK   LOKO PMU + instructions: recomputed 0.551, text needle '$0.551$'
OK   RQ4 paired buffer difference: recomputed 8.02, text needle '$8.02$'
OK   host call / native at 64 B: recomputed 2.10, text needle '$2.10$ times'
OK   compound trials conforming: recomputed 4200, text needle 'All 4{,}200 trials conform'
19 of 19 headline numbers found in the paper text
```

---

## 4. Compiling the Manuscript PDF

```bash
cd paper
./compile_paper.sh
# Generates paper/main.pdf formatted for JCSC (9.75" x 6.5" trim, ws-jcsc.cls)
```

---

## 5. Citation

```bibtex
@article{patel2026instructionfuel,
  title={Instruction-Fuel Drift, Boundary-Crossing Overhead, and Memory Safety in WebAssembly Sandboxes: A Multi-Runtime Measurement Study},
  author={Patel, Devarsh and Ranjithkumar, S},
  journal={Journal of Circuits, Systems, and Computers},
  year={2026},
  publisher={World Scientific}
}
```

---

## 6. License
This project is open-sourced under the [MIT License](LICENSE).
