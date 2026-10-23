# Changelog

## 0.1.0 — 2026-10-23

- Deterministic SHA-256 snapshots with relative paths and strict input validation.
- Snapshot comparison and direct baseline checks with saved exclusion rules.
- Conservative move detection, with ambiguous matches left as additions/removals.
- Text, JSON and Markdown reports; documented 0/1/2 exit codes.
- Default exclusions, `.treeledgerignore` and repeated `--exclude` flags.
- Streaming reads, detected in-flight change failures and atomic output replacement.
- Link, Windows junction/reparse point and special-file skipping.
- Consistent per-API timestamp comparisons for Windows stat/fstat compatibility.
- English/Chinese documentation, reproducible example data and cross-platform CI.
