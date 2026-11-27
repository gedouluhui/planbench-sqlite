# Contributing

Start with a concrete query experiment or a minimal failing test. This project prioritizes trustworthy outcomes over broad SQL compatibility. Read the README support status and limitations before proposing work.

## Before you start

- Use self-generated data only. Do not attach a private database, SQL literals with secrets, report rows, credentials, or identifying filesystem paths.
- Search existing issues and pull requests before opening a duplicate.
- Add a failing regression test first for behavior changes, with a positive control and a negative control that would fail if the implementation were weakened.

## Development setup

Supported version: **0.2.0** with Python 3.11+ and SQLite.

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python scripts/check_docs.py
```

Changes to equality, limits, or allowed SQL operations need explicit contract discussion. Keep the JSON outcome contract and CLI exit codes consistent with the documentation.

## Pull requests

- Do not add runtime dependencies, telemetry, automatic network access, arbitrary extension loading, or performance claims without an explicit design discussion.
- HTML changes must remain offline and script-free, with escaped inputs, mobile layout, and keyboard access. A screenshot is not a substitute for a runnable report.
- Preserve source-file and sidecar protection, typed row comparison, and inconclusive outcomes.
- AI-assisted contributions are welcome. Contributors remain responsible for understanding the change, preserving license terms, and supplying executable evidence.
- Do not invent benchmarks, user endorsements, release URLs, or compatibility claims. Contributions are provided under the repository's MIT license.

## Reporting issues

Use the bug or feature template. Include Python/SQLite and OS versions, package version or commit, the exact command, a tiny self-generated CREATE TABLE/INSERT example and sanitized case JSON, expected and actual status/exit code, and whether the issue reproduces from an installed package. For security-sensitive reports, follow [SECURITY.md](SECURITY.md) instead of posting confidential repro data publicly.
