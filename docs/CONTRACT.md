# Evidence contract

## Runtime and inputs

Python 3.11 or newer is required for the native SQLite value-length limit and error codes. The bundled SQLite must implement and confirm `PRAGMA trusted_schema=OFF` (SQLite 3.31+); otherwise the experiment is refused. Optional SQLite functions may be missing from a particular build: a failed query remains an error, never an equivalent result.

Inputs are trusted local ordinary SQLite files and JSON case objects. This is not a hostile-file parser sandbox. The source path is opened with a percent-encoded `mode=ro` URI. SQLite backup supplies one committed snapshot, including WAL content; two fresh in-memory clones derive from that snapshot. Connections are always closed. SQLite can manage WAL shared-memory sidecars while reading. No user SQL is executed on the source connection.

The configuration accepts exactly `schema_version`, `title`, `database`, `baseline`, `candidate`, `comparison` and `limits`. `schema_version` must be integer 1, not a boolean. Baseline accepts SQL and a positional list of JSON scalar parameters. Candidate additionally accepts up to 32 ordinary index definitions, each with name, table and a list of 1–32 nongenerated columns. Existing table/column names must match exactly. Names are quoted; no expression or partial indexes, UNIQUE constraints, index deletion or arbitrary setup SQL are supported. Index names already present cause a blocked setup.

Text parameters may contain NUL because they are bound as data. SQL, paths, identifiers and titles may not. Nonfinite parameters, unknown fields and out-of-range numbers are invalid. The CLI rejects duplicate JSON keys, nonfinite constants and case files over 2 MB. The Python API consumes an already-parsed dict and cannot recover duplicate keys discarded by a caller's JSON parser.

## Result comparison

Both arms must complete. Column names and count must match, in order. Row values use a length-framed encoding with distinct NULL, INTEGER, REAL, TEXT and BLOB tags. Finite REAL values use `float.hex()`; this is representation-sensitive, including signed zero when SQLite preserves it. TEXT uses UTF-8, BLOB uses the original bytes. Nonfinite REAL and undecodable text are unsupported.

- `ordered`: exact encoded row sequence comparison.
- `multiset` (default): exact encoded-row multiplicity comparison using a Counter.

No checksums decide equality. SHA-256 fingerprints are diagnostic only and include duplicate rows. Multiset fingerprints sort encoded rows before hashing. Values exist only in bounded memory and are not written into the report.

A matching result proves neither query equivalence over other databases nor deterministic ordering. An index can change the rows chosen by unordered LIMIT, ordering among ties, floating-point aggregation order or group_concat order. These remain observable differences, not automatically tool bugs. No floating-point tolerance is applied.

## SQL boundary

The deny-by-default authorizer is installed before preparing both EXPLAIN QUERY PLAN and the actual query. It remains active during fetching. It permits SELECT/recursive SELECT, reads of known main-database ordinary tables/views/schema objects, and an explicit set of built-in functions. Unknown actions and functions return SQLITE_DENY, never SQLITE_IGNORE. Implicit virtual modules such as json_each, dbstat and pragma_* are not admitted simply because they were absent from the schema preflight.

The canonical function list is `ALLOWED_FUNCTIONS` in [engine.py](../src/planbench_sqlite/engine.py). It includes common aggregates, text functions and window functions; inclusion does not promise availability in every SQLite build or order-invariant results. random, time/environment-dependent functions, extension loading and user-defined functions are not supported. The tool never registers functions or loads extensions. Virtual/shadow tables cause source rejection.

These controls are defense in depth for a restricted experiment, not protection from a malicious SQLite native file or a guaranteed process resource sandbox.

## Budgets and observations

Defaults:

| Setting | Default |
|---|---:|
| max_rows | 100000 |
| max_result_bytes | 33554432 |
| max_progress_calls | 2000000 |
| timeout_seconds | 5.0 |
| max_database_bytes | 67108864 |

Exact ranges are enforced by `MAX_LIMITS` in [engine_config.py](../src/planbench_sqlite/engine_config.py). All limits have hard configuration ceilings, but they do not constitute a hard process-RSS limit.

Snapshot and clone operations each consume a separate backup-progress callback budget, where a callback covers up to 64 copied pages. Index creation, plan preparation and query execution use their own SQLite progress callback budgets with interval 1. These are different units; backup counters are never mixed into the query callback ratio. The size limit also constrains candidate index growth through SQLite's page quota. Runtime result cells are capped with Connection.setlimit; very small requested encoded-result budgets use a 1024-byte native cell-limit floor while retaining the exact smaller Python encoded-result limit.

Time is checked at cooperative boundaries, after result fingerprinting and before final comparison is declared. A native operation or Python sort/comparison can overrun the deadline until it returns; there is no process-killing watchdog. Query elapsed time includes instrumentation, row conversion, encoding and fingerprinting. Equality has a separate cooperative deadline. Snapshot/index/plan setup time is not included in the query time field. No machine-independent throughput or speedup is reported.

`progress_calls` counts actual callbacks observed by the tool, not exact VM instructions. SQLite describes the interval as approximate, and recent versions can invoke callbacks during preparation. Only an equivalent result may carry candidate/baseline callback ratio. Raw plan fields are diagnostic data tied to the reported SQLite version; they are not a stable string-scoring format.

`max_result_bytes` limits encoded payload, not all Python list/Counter overhead. SQLite can allocate temporary working memory. Do not use this tool to execute adversarial resource-exhaustion queries.

## Reports and errors

Top-level status is `equivalent`, `different` or `inconclusive`. Per-arm status is `complete`, `blocked`, `limit` or `error`. A failed arm may retain partial counters but never a completed result fingerprint. Invalid configuration raises ValueError in the API; CLI input/output problems exit 2.

No raw result values, bound parameters, absolute source paths or original SQLite error strings enter reports. SQL, embedded literals, identifiers and the source basename do. Inspect those before sharing. JSON/HTML publication is staged; publishing two files is not a filesystem transaction, so a later output failure may leave an earlier complete report. Such a failure exits 2, not success. Exclusive publication requires hard-link support; forced publication uses atomic replacement of reviewed report destinations.

HTML is fully escaped and script-free. Its displayed equivalent/different state additionally requires completed arms and consistent equality flags. Malformed external report dictionaries are not a substitute for calling the engine; report schema validation beyond generated data is not a public import feature.

## Primary references

- [SQLite progress handler](https://www.sqlite.org/c3ref/progress_handler.html): approximate intervals, preparation callbacks and cooperative interruption.
- [EXPLAIN QUERY PLAN](https://www.sqlite.org/eqp.html): four raw columns and unstable display format.
- [SQLite authorizer](https://www.sqlite.org/c3ref/set_authorizer.html): authorization at statement preparation.
- [SQLite security guidance](https://www.sqlite.org/security.html): trusted_schema and additional application responsibilities.
- [SQLite WAL read-only behavior](https://www.sqlite.org/wal.html#read_only_databases).
- [Python sqlite3](https://docs.python.org/3/library/sqlite3.html): backup, setlimit and connection lifetime.
- [SELECT ordering](https://www.sqlite.org/lang_select.html#the_order_by_clause) and [aggregate semantics](https://www.sqlite.org/lang_aggfunc.html).
