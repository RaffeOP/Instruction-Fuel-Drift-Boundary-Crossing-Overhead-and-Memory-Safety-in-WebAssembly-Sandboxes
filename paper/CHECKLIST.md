# Submission checklist: Instruction-Fuel Drift manuscript

Target journal: *Cluster Computing* (Springer Nature, hybrid). Template: `sn-jnl` (`sn-jnl.cls`, `sn-mathphys.bst`).

## Verified in this repository

- [x] Builds with `tectonic main.tex` to 43 pages, with zero errors.
- [x] No unresolved references or citations (`??` count is zero).
- [x] No duplicate labels.
- [x] No text runs past the right margin on any page (checked page by page).
- [x] Seven figures sit inline (Sections 5 and 6), with embedded TrueType fonts and no Type 3 fonts.
- [x] 219 clickable links: cross-references to tables, figures, sections, appendices, equations, citations, and URLs.
- [x] PDF metadata: title, author, keywords.
- [x] All 44 bibliography entries are cited.
- [x] Every table and number is generated from the raw data by the scripts in `src/`.
- [x] Declarations: no external funding; no competing interests; ethics not applicable; consent for publication; author contributions.
- [x] Corresponding author email: `devarsh.patel2024@vitstudent.ac.in` (as provided).
- [x] Banned filler phrases from the project directive are strictly absent from the manuscript.
- [x] Abstracts cache: all records verified and updated in `literature/abstracts_crossref.md` (including Titzer ASPLOS 2024, Kakati CCGrid 2024, Mao SSE 2024, Khan IEEE Access 2026, Jansen IPDPSW 2025, Yu ACM TACO 2026, and USENIX entries).
- [x] Taxonomy table (`tables/tab_taxonomy.tex`): all cells independently verified against published papers.
- [x] Load-telemetry caveat disclosed in threats section and in Appendix (load telemetry); runtime-ratio claim scoped to within-replicate time-sharing.
- [x] Official Springer bibliography style: complete official Springer Nature `.bst` bundle installed in `paper/` (`sn-mathphys.bst`, `sn-basic.bst`, `sn-aps.bst`, `sn-nature.bst`, `sn-vancouver.bst`, `sn-chicago.bst`, `sn-apacite.bst`). Numbered citation format verified (`[1]`, `[2]`).
- [x] Journal requirements for *Cluster Computing*: verified hybrid model ($0 APC under traditional subscription), single-blind review format, standard Springer declarations, and numbered reference style.
- [x] Repository URL and License placeholders filled: `https://github.com/RaffeOP/Instruction-Fuel-Drift-Boundary-Crossing-Overhead-and-Memory-Safety-in-WebAssembly-Sandboxes` and MIT License.
- [x] Line-by-line copy-edit completed across all sections and appendices with clean typography and no bad breaks.

## Key Journal & Editorial Decisions

- **Target journal:** *Cluster Computing* (Springer Nature). The paper's systems benchmarking, cross-runtime evaluation, and sandbox hardening align directly with the journal scope.
- **Publishing model:** Traditional subscription model ($0 APC / no author fees required; optional Open Choice CC-BY available if funded).
- **Reference style:** Numbered style (`sn-mathphys.bst` with `natbib` numbers), sorted sequentially by order of citation in the text with complete DOIs.
- **Author details:** Single-blind peer review with author name, institution (SCOPE, VIT Vellore), and corresponding author email included on title page.
- **Reproducibility deposit:** All raw traces, manifests, harnesses, figures, and LaTeX tables linked to `https://github.com/RaffeOP/Instruction-Fuel-Drift-Boundary-Crossing-Overhead-and-Memory-Safety-in-WebAssembly-Sandboxes` under MIT License.
