# Changelog

## 0.2.0 — Difference evidence and regression suites

- Explain complete mismatches with exact row-occurrence counts, zero-based source positions, schema changes and bounded type evidence without exporting raw rows.
- Add strict suite manifests with a full ordered case ledger, worst-outcome exit codes, independent snapshots and a cooperative run budget.
- Protect all identifiable suite inputs/sidecars before execution and refuse input-budget exhaustion before publishing a partial inventory.
- Add script-free suite reports, per-case expandable evidence and deterministic three-outcome suite examples.
- Ship a reproducible isolated mutation verifier, including its NOP/crash classification controls.
- Configure built-wheel CI checks and a macOS matrix in addition to Windows/Ubuntu. A configured matrix is not a claim that unrun jobs passed.
- Keep case schema1 and add optional report fields without changing existing0/1/2 outcome codes.

## 0.1.0 — Initial alpha

- Run two SQLite query/index variants against clones of one backup snapshot.
- Compare exact typed row sequences or multisets, including duplicates and column names.
- Distinguish equivalent, different and inconclusive outcomes with CLI exit codes.
- Bound snapshot copying, index growth, execution and result retention; reject unsupported SQL operations and virtual modules.
- Generate escaped, script-free offline HTML plus JSON evidence.
- Include deterministic equivalent, different and budget-limited examples.

This is an early local experiment tool, not a production performance benchmark, SQL equivalence prover or hostile-input sandbox. See the evidence contract for restrictions.
