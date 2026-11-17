"""CLI entry point and output safety. No network or subprocess dependencies."""

import argparse
import json
import os
from pathlib import Path, PureWindowsPath
import sqlite3
import sys
import tempfile

from . import __version__
from .demo import create_demo
from .engine import run_experiment
from .engine_config import validate_config
from .report import render_html


class InputError(ValueError):
    pass


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError('Duplicate JSON object key')
        result[key] = value
    return result


def _constant(value):
    raise InputError('Nonfinite JSON constants are not supported')


def load_case(path):
    if path.stat().st_size > 2_000_000:
        raise InputError('Case file exceeds 2 MB input limit')
    with path.open(encoding='utf-8') as stream:
        value = json.load(stream, object_pairs_hook=_object, parse_constant=_constant)
    # Validation happens before any output/database activity. Keep the original
    # object: normalization adds default indexes to baseline for internal use.
    validate_config(value)
    return value


def _aliases(a, b):
    if a.resolve() == b.resolve():
        return True
    return a.exists() and b.exists() and os.path.samefile(a, b)


def _check_outputs(paths, protected, force):
    for index, path in enumerate(paths):
        if os.name == 'nt':
            # Win32 normalizes nonexistent trailing-dot/space paths at write
            # time; resolve()/samefile() alone cannot identify those aliases.
            for part in path.parts:
                if part == path.anchor or part in ('.', '..'):
                    continue
                if part.endswith(('.', ' ')) or ':' in part or PureWindowsPath(part).is_reserved():
                    raise InputError('Ambiguous or reserved Windows output path component')
        if any(_aliases(path, source) for source in protected):
            raise InputError('Output would overwrite an input database, sidecar or case file')
        if any(_aliases(path, other) for other in paths[:index]):
            raise InputError('JSON and HTML outputs must be distinct files')
        if not path.parent.is_dir():
            raise InputError('Output parent directory does not exist')
        if path.is_symlink():
            raise InputError('Refusing a symbolic-link output')
        if path.exists() and (not force or not path.is_file()):
            raise InputError('Output exists; use --force only for an ordinary report file')


def _write_outputs(outputs, force):
    """Stage all text first. Exclusive publication never truncates existing files.

    Multiple outputs are not a transactional filesystem operation: a failure
    during publication can leave an earlier report published. The CLI reports
    an error, and never labels a failed publication successful.
    """
    staged = []
    try:
        for destination, text in outputs:
            handle, name = tempfile.mkstemp(prefix='.planbench-', suffix='.tmp', dir=destination.parent)
            temporary = Path(name)
            staged.append((temporary, destination))
            with os.fdopen(handle, 'w', encoding='utf-8', newline='\n') as stream:
                stream.write(text)
        for temporary, destination in staged:
            if force:
                os.replace(temporary, destination)
            else:
                # Hard linking an already complete same-directory temporary
                # publishes exclusively; unlike exists()+replace it cannot
                # silently overwrite a racing writer's file.
                os.link(temporary, destination)
                temporary.unlink()
    finally:
        for temporary, destination in staged:
            temporary.unlink(missing_ok=True)


def _compare(case_path, json_path=None, html_path=None, force=False):
    case_path = Path(case_path).resolve()
    case = load_case(case_path)
    database = (case_path.parent / case['database']).resolve()
    paths = [Path(path).absolute() for path in (json_path, html_path) if path is not None]
    protected = [case_path, database] + [Path(str(database) + suffix) for suffix in ('-wal', '-shm', '-journal')]
    _check_outputs(paths, protected, force)
    report = run_experiment(case, base_dir=case_path.parent)
    outputs = []
    if json_path is not None:
        outputs.append((Path(json_path).absolute(), json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n'))
    if html_path is not None:
        outputs.append((Path(html_path).absolute(), render_html(report)))
    _check_outputs(paths, protected, force)
    _write_outputs(outputs, force)
    print(report['status'].upper() + ': ' + report['equality']['reason'])
    for label in ('baseline', 'candidate'):
        arm = report[label]
        print(f"  {label}: {arm['status']}; {arm['row_count']} rows; {arm['progress_calls']} progress callbacks")
        if arm.get('error'):
            print('    ' + arm['error'])
    for path in paths:
        print('  report: ' + str(path))
    return {'equivalent': 0, 'different': 1, 'inconclusive': 2}[report['status']]


def main(argv=None):
    parser = argparse.ArgumentParser(prog='planbench-sqlite', description='Compare SQLite queries and indexes on disposable clones. Offline; no runtime dependencies.')
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', required=True)
    compare = commands.add_parser('compare', help='Compare two arms from a local JSON case')
    compare.add_argument('case', type=Path)
    compare.add_argument('--json', type=Path, metavar='PATH', help='Write a machine-readable report')
    compare.add_argument('--html', type=Path, metavar='PATH', help='Write an offline HTML report')
    compare.add_argument('--force', action='store_true', help='Replace existing report files, never inputs')
    demo = commands.add_parser('demo', help='Create and run a deterministic index experiment')
    demo.add_argument('--out', type=Path, required=True, help='New directory for generated database, cases and reports')
    args = parser.parse_args(argv)
    try:
        if args.command == 'demo':
            case = create_demo(args.out)
            return _compare(case, args.out / 'report.json', args.out / 'report.html')
        return _compare(args.case, args.json, args.html, args.force)
    except (OSError, ValueError, OverflowError, RecursionError, sqlite3.Error) as exc:
        # Avoid echoing invalid JSON, parameters, full SQL errors or credentials.
        message = str(exc) if isinstance(exc, InputError) else 'Input or output failed (' + type(exc).__name__ + '); check case schema, paths and permissions'
        print('planbench-sqlite: ' + message, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('planbench-sqlite: cancelled; no equivalence established', file=sys.stderr)
        return 130
