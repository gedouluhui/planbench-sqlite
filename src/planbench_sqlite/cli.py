"""Single-case and suite CLI; shared strict inputs and destination safety."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

from . import __version__
from .demo import create_demo
from .engine import run_experiment
from .inputs import InputError, load_case
from .outputs import check_outputs, write_outputs
from .report import render_html
from .suite import database_paths, load_suite, run_suite
from .suite_report import render_suite_html


def _publish(report, json_path, html_path, protected, force):
    outputs = []
    if json_path is not None:
        outputs.append((Path(json_path).absolute(), json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n'))
    if html_path is not None:
        renderer = render_suite_html if report.get('kind') == 'suite' else render_html
        outputs.append((Path(html_path).absolute(), renderer(report)))
    check_outputs([path for path, text in outputs], protected, force)
    write_outputs(outputs, force)
    for path, text in outputs:
        print('  report: ' + str(path))


def _compare(case_path, json_path=None, html_path=None, force=False):
    case_path = Path(case_path).resolve()
    case = load_case(case_path)
    protected = [case_path, *database_paths(case_path.parent / case['database'])]
    check_outputs([Path(path).absolute() for path in (json_path, html_path) if path is not None], protected, force)
    report = run_experiment(case, base_dir=case_path.parent)
    print(report['status'].upper() + ': ' + report['equality']['reason'])
    for label in ('baseline', 'candidate'):
        arm = report[label]
        print(f"  {label}: {arm['status']}; {arm['row_count']} rows; {arm['progress_calls']} progress callbacks")
        if arm.get('error'):
            print('    ' + arm['error'])
    if report['status'] == 'different' and report.get('difference'):
        d = report['difference']
        print(f"  bag difference: {d['missing_rows']} missing; {d['extra_rows']} extra rows (occurrences)")
        if d['first_mismatch']:
            print('  first differing position (zero-based): ' + str(d['first_mismatch']['row_index']))
    _publish(report, json_path, html_path, protected, force)
    return {'equivalent': 0, 'different': 1, 'inconclusive': 2}[report['status']]


def _suite(path, json_path=None, html_path=None, force=False):
    plan = load_suite(path)
    paths = [Path(p).absolute() for p in (json_path, html_path) if p is not None]
    check_outputs(paths, plan.protected_paths, force)
    report = run_suite(plan)
    print(report['status'].upper() + ': ' + str(report['counts']['total']) + ' cases accounted for')
    for item in report['cases']:
        print('  ' + item['id'] + ': ' + item['status'] + ' (' + item['execution'] + ')')
        if item['error']:
            print('    ' + item['error'])
    _publish(report, json_path, html_path, plan.protected_paths, force)
    return {'equivalent': 0, 'different': 1, 'inconclusive': 2}[report['status']]


def main(argv=None):
    parser = argparse.ArgumentParser(prog='planbench-sqlite', description='Compare SQLite queries and indexes on disposable clones. Offline; no runtime dependencies.')
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name, help_text in [('compare', 'Compare two arms from a local JSON case'), ('suite', 'Run a bounded manifest of independent cases')]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument('case', type=Path)
        command.add_argument('--json', type=Path, metavar='PATH', help='Write a machine-readable report')
        command.add_argument('--html', type=Path, metavar='PATH', help='Write an offline HTML report')
        command.add_argument('--force', action='store_true', help='Replace existing report files, never inputs')
    demo = commands.add_parser('demo', help='Create and run deterministic query experiments')
    demo.add_argument('--out', type=Path, required=True, help='New directory for generated database, cases and reports')
    args = parser.parse_args(argv)
    try:
        if args.command == 'demo':
            case = create_demo(args.out)
            return _compare(case, args.out / 'report.json', args.out / 'report.html')
        action = _suite if args.command == 'suite' else _compare
        return action(args.case, args.json, args.html, args.force)
    except (OSError, ValueError, OverflowError, RecursionError, sqlite3.Error) as exc:
        message = str(exc) if isinstance(exc, InputError) else 'Input or output failed (' + type(exc).__name__ + '); check case schema, paths and permissions'
        print('planbench-sqlite: ' + message, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('planbench-sqlite: cancelled; no equivalence established', file=sys.stderr)
        return 130
