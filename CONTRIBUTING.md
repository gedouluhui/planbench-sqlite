# Contributing

Start with a concrete query experiment or a minimal failing test. This project prioritizes trustworthy outcomes over broad SQL compatibility.

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

Use self-generated data only. Do not attach a private database, SQL literals with secrets, report rows, credentials or identifying filesystem paths. Report your Python/SQLite versions, case structure with sensitive values removed, expected result and actual status. A tiny CREATE TABLE/INSERT script is more useful than a production dump.

Changes to equality, limits or allowed SQL operations need a positive control and a negative control that would fail if the implementation were weakened. Keep the JSON outcome contract and CLI exit codes consistent with the documentation. Do not add runtime dependencies, telemetry, automatic network access, arbitrary extension loading or performance claims without an explicit design discussion.

HTML changes must remain offline and script-free, with escaped inputs, mobile layout and keyboard access. A screenshot is not a substitute for a runnable report.

AI-assisted contributions are welcome. Contributors remain responsible for understanding the change, preserving license terms and supplying executable evidence. Do not invent benchmarks, user endorsements or compatibility claims.

License: contributions are provided under the repository's MIT license. For a security-sensitive report, avoid posting confidential repro data publicly; first share a minimal, sanitized description of the affected boundary.
