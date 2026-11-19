# PlanBench SQLite

[![CI](https://github.com/gedouluhui/planbench-sqlite/actions/workflows/ci.yml/badge.svg)](https://github.com/gedouluhui/planbench-sqlite/actions/workflows/ci.yml)

**Try an index. Keep the evidence. Don't mistake a faster wrong answer for an optimization.**

PlanBench runs two queries against disposable clones of the **same SQLite snapshot**, compares their typed results, and produces one offline report containing both execution plans. It has no runtime dependencies, server, API key or telemetry.

[Open a real report](https://gedouluhui.github.io/planbench-sqlite/) · [Different results](https://gedouluhui.github.io/planbench-sqlite/different.html) · [Budget exhausted](https://gedouluhui.github.io/planbench-sqlite/limited.html)

[中文快速开始](README.zh-CN.md) · [Comparison contract](docs/CONTRACT.md) · [Contributing](CONTRIBUTING.md)

## A useful experiment in one command

With Python 3.11+ (including SQLite), install from this checkout and run:

```sh
python -m pip install .
planbench-sqlite demo --out demo-output
```

Open `demo-output/report.html`. The demonstration creates its own deterministic orders database, compares a customer lookup with and without a candidate index, and checks the returned rows. No data is downloaded. The output directory must be new.

Two counterexamples are included:

```sh
planbench-sqlite compare demo-output/different.json
# Exit 1: a changed predicate returns different rows.

planbench-sqlite compare demo-output/limited.json
# Exit 2: row budget exceeded; equivalence was NOT established.
```

A smaller callback count is an instrumented observation, **not a production speedup**. PlanBench does not recommend indexes automatically.

## Compare your own query

Save this as `case.json` beside a trusted local `shop.sqlite` database:

```json
{
  "schema_version": 1,
  "title": "Customer lookup",
  "database": "shop.sqlite",
  "baseline": {
    "sql": "SELECT id, total_cents FROM orders WHERE customer_id = ? ORDER BY id",
    "parameters": [17]
  },
  "candidate": {
    "sql": "SELECT id, total_cents FROM orders WHERE customer_id = ? ORDER BY id",
    "parameters": [17],
    "indexes": [
      {"name": "orders_customer", "table": "orders", "columns": ["customer_id"]}
    ]
  },
  "comparison": "ordered"
}
```

```sh
planbench-sqlite compare case.json --json report.json --html report.html
```

The database path is relative to the case file, not your shell's directory. Existing report files are refused unless `--force` is supplied. Inputs and SQLite sidecars cannot be chosen as outputs, even with `--force`. On filesystems that do not support hard links, exclusive report publication can fail explicitly; no report is silently overwritten.

You can also compare two different SELECT queries by changing `candidate.sql` and its bound parameters. Candidate indexes are optional. Only ordinary nonunique indexes over explicitly named existing columns are supported. There is no arbitrary setup SQL or source migration.

## Pinpoint the difference without exporting your data

A `different` result now includes exact matched, missing and extra **row occurrence** counts, schema changes by column position, and bounded type/location examples. Ordered comparisons also identify the first unequal row and changed column positions. Reordering can give zero missing/extra rows while still failing ordered comparison.

Examples point to the first occurrence in that arm's **original returned order**, using zero-based indices—not primary keys or sorted-hash order. At most ten examples/column details are shown; totals remain exact and truncation is explicit. Raw values, lengths and per-row hashes are not added to reports. Same-type cells can still hold different values.

## Run a regression suite in CI

Create `suite.json`:

```json
{
  "suite_version": 1,
  "title": "Orders query regressions",
  "timeout_seconds": 30,
  "cases": [
    {"id": "customer-lookup", "case": "case.json"},
    {"id": "another-query", "case": "another-case.json"}
  ]
}
```

```sh
planbench-sqlite suite suite.json --json suite-report.json --html suite-report.html
```

Every case is accounted for, in input order. Any invalid, blocked, timed-out or unrun case makes the suite inconclusive (exit 2); otherwise any difference gives exit 1; only all equivalent gives exit 0. There is no averaging away failures or passing empty suites. Each case takes an **independent snapshot**; this is not a common snapshot across the entire suite.

Manifests allow 1–50 unique cases, unique IDs and no repeated file aliases. Paths are relative to the manifest. Input preflight is byte-bounded (2 MB each / 16 MB total), and the run has a cooperative overall time budget. Input-budget exhaustion rejects the entire preflight before outputs, rather than publishing from an incomplete protection inventory. Output protection covers the manifest, every case and every identifiable database/sidecar, including invalid cases.

The demo also generates `suite-clean.json`, `suite-different.json` and `suite-inconclusive.json` with actual expected exit codes 0, 1 and 2. The [example suite report](docs/suite.html) comes from the real generated inconclusive suite, not a hand-authored mockup.

## What the result means

| Result | Exit | Meaning |
|---|---:|---|
| `equivalent` | 0 | Both runs completed; column names/count and the requested typed row comparison match. |
| `different` | 1 | Both runs completed, but the schema, values, multiplicity or required order differ. |
| `inconclusive` | 2 | A run was refused, failed or exceeded a budget. There is no equality conclusion. |
| Invalid input/output | 2 | Case schema, file access or report publication failed. |

`ordered` compares the row sequence. `multiset` ignores row order but retains duplicates. INTEGER `1`, REAL `1.0`, TEXT `'1'` and BLOB `X'31'` are different under this deliberately strict contract. Hashes in reports are diagnostic; they do not decide equality.

This is **one-snapshot evidence**, not proof that arbitrary SQL queries are equivalent. Unordered `LIMIT`, tied sort keys and order-sensitive aggregation may change values after indexing. Zero rows caused by an interrupted query never count as a successful match.

## Under the hood

```text
read-only source ── SQLite backup ── consistent snapshot
                                      ├─ fresh baseline clone ── plan + query ─┐
                                      └─ fresh candidate clone + indexes ────┤
                                              exact bounded row comparison ──┴─ JSON / HTML
```

- Uses SQLite backup rather than copying the main file and accidentally losing committed WAL data.
- Uses a deny-by-default SQL authorizer before preparing user SQL. Writes, PRAGMA, ATTACH, unknown functions and extension loading are rejected.
- Limits snapshot bytes, result rows, encoded result bytes, progress callbacks and cooperative elapsed time. Incomplete runs remain inconclusive.
- Preserves SQLite's raw plan fields and version instead of treating `EXPLAIN QUERY PLAN` strings as a stable API.
- Adds indexes only on the disposable candidate clone. Existing statistics are retained; no `ANALYZE`, cache flushing or production configuration changes are performed.
- Produces script-free HTML with escaped content, keyboard-accessible disclosure panels, responsive layout and no remote resources.

## Choose the right tool

| If you need… | Use… |
|---|---|
| Manual plans, low-level statement statistics or index suggestions | [SQLite CLI](https://www.sqlite.org/cli.html), including `.eqp`, `.stats`, `.timer` and `.expert` |
| General database conversion, inspection and index management | [sqlite-utils](https://sqlite-utils.datasette.io/en/stable/cli.html) |
| An interactive data publishing/query service | [Datasette](https://docs.datasette.io/en/stable/sql_queries.html) |
| A portable two-arm experiment with explicit result-comparison outcomes | PlanBench SQLite |

The differentiation is the complete experiment workflow, not a new database algorithm or a claim that other tools cannot export HTML.

## Limits, privacy and maturity

This is an early, narrowly scoped tool for **trusted local ordinary SQLite databases**. It is not a sandbox for malicious database files or SQL denial-of-service attacks. Limits are cooperative: a native operation can delay cancellation. Native SQLite allocations and Python container overhead are not a hard resident-memory cap. SQLite may manage WAL shared-memory sidecars while reading a source.

Reports omit result rows and bound parameter values, but **SQL text, SQL literals, identifiers and the database basename remain visible**. Review them before sharing. No redaction engine can be inferred from the omission of rows. Virtual tables, loadable extensions, user-defined functions and nonfinite REAL results are unsupported.

No real-user adoption, production performance gain or cross-platform result is asserted merely because local tests pass. Compatibility and known limits are recorded in the contract.

## Python API

```python
import json
from pathlib import Path
from planbench_sqlite.engine import run_experiment
from planbench_sqlite.report import render_html

case_file = Path("case.json")
case = json.loads(case_file.read_text(encoding="utf-8"))
report = run_experiment(case, base_dir=case_file.parent)
print(report["status"])
# render_html(report) returns escaped, standalone HTML; it does not write files.
```

For strict duplicate-key/nonfinite JSON rejection and output protection, use the CLI. The Python API validates the parsed dict and returns a report; structurally invalid dicts raise `ValueError`.

## Develop

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python scripts/mutation_check.py
```

Tests execute real SQLite databases and real CLI subprocesses, including source-file protection, committed WAL data, result-type distinctions, duplicate multiplicity, incomplete runs and report injection strings. No paid service is needed. Build with `python -m pip install build` followed by `python -m build`.

MIT licensed. The implementation and demonstration data are original to this project; Python's bundled SQLite retains its own license terms. Development was AI-assisted; correctness claims must be supported by reproducible tests, not authorship claims.
