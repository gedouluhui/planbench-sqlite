"""Independent per-case snapshots and a complete, bounded CI outcome ledger."""
from copy import deepcopy
from dataclasses import dataclass
import math
import os
from pathlib import Path
import platform
import re
import sqlite3
import time

from . import __version__
from .engine import run_experiment
from .engine_config import DEFAULT_LIMITS, validate_config
from .inputs import InputError, InputBudgetError, read_json


@dataclass
class SuitePlan:
    title: str
    timeout_seconds: float
    items: list
    protected_paths: list


def database_paths(path):
    path = Path(path).resolve()
    return [path] + [Path(str(path) + suffix) for suffix in ('-wal', '-shm', '-journal')]


def paths_alias(a, b):
    return a.resolve() == b.resolve() or (a.exists() and b.exists() and os.path.samefile(a, b))


def load_suite(path):
    """Preflight every input once; even invalid cases retain their protected paths."""
    path = Path(path).resolve()
    input_bytes = 0

    def account_bytes(count):
        nonlocal input_bytes
        input_bytes += count
        if input_bytes > 16_000_000:
            raise InputBudgetError('Suite inputs exceed the 16 MB cumulative budget')

    value = read_json(path, account_bytes=account_bytes)
    allowed = {'suite_version', 'title', 'timeout_seconds', 'cases'}
    if type(value) is not dict or set(value) - allowed:
        raise InputError('Suite must be an object with supported keys')
    if type(value.get('suite_version')) is not int or value['suite_version'] != 1:
        raise InputError('suite_version must be integer 1')
    title = value.get('title', 'SQLite regression suite')
    if not isinstance(title, str) or not title.strip() or len(title) > 256 or '\x00' in title:
        raise InputError('Suite title must be nonempty text, at most 256 characters')
    try:
        title.encode('utf-8')
    except UnicodeError:
        raise InputError('Suite title must be valid UTF-8') from None
    timeout = value.get('timeout_seconds', 30.0)
    if type(timeout) not in (int, float) or not 0.01 <= timeout <= 600 or not math.isfinite(timeout):
        raise InputError('Suite timeout_seconds must be finite and between 0.01 and 600')
    cases = value.get('cases')
    if type(cases) is not list or not 1 <= len(cases) <= 50:
        raise InputError('Suite must contain 1 to 50 cases')
    seen_ids, case_paths, descriptors = set(), [], []
    for entry in cases:
        if type(entry) is not dict or set(entry) != {'id', 'case'}:
            raise InputError('Each suite item requires exactly id and case')
        identifier, name = entry['id'], entry['case']
        if type(identifier) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', identifier) or identifier in seen_ids:
            raise InputError('Case IDs must be unique ASCII letters/digits/underscore/hyphen')
        if type(name) is not str or not name.strip() or '\x00' in name or len(name) > 32768:
            raise InputError('Case path must be nonempty text without NUL')
        try:
            name.encode('utf-8')
            case_path = (path.parent / name).resolve()
        except (OSError, ValueError, UnicodeError):
            raise InputError('Invalid case path') from None
        if any(paths_alias(case_path, previous) for previous in case_paths):
            raise InputError('Suite cannot repeat a case file or filesystem alias')
        seen_ids.add(identifier)
        case_paths.append(case_path)
        descriptors.append((identifier, case_path))
    protected, items = [path, *case_paths], []
    for identifier, case_path in descriptors:
        item = {'id': identifier, 'case': case_path.name, '_path': case_path, '_config': None, 'error': None}
        try:
            raw = read_json(case_path, account_bytes=account_bytes)
            if type(raw) is dict and isinstance(raw.get('database'), str) and raw['database'] and '\x00' not in raw['database']:
                protected.extend(database_paths(case_path.parent / raw['database']))
            validate_config(raw)
            item['_config'] = raw
        except InputBudgetError:
            # Never publish from a partial protection inventory when budget
            # prevented reading a case's database reference.
            raise
        except (OSError, ValueError, OverflowError, RecursionError) as exc:
            item['error'] = 'Case input could not be prepared (' + type(exc).__name__ + ')'
        items.append(item)
    return SuitePlan(title, float(timeout), items, protected)


def suite_status(items):
    if not items or any(item.get('execution') != 'complete' or item.get('status') not in ('equivalent', 'different') for item in items):
        return 'inconclusive'
    if any(item['status'] == 'different' for item in items):
        return 'different'
    return 'equivalent'


def run_suite(plan: SuitePlan):
    """Run cases sequentially. Cooperative deadlines cannot guarantee hard limits."""
    started = time.monotonic()
    deadline = started + plan.timeout_seconds
    items = []
    for prepared in plan.items:
        item = {key: prepared[key] for key in ('id', 'case', 'error')}
        item.update(execution='not_run', status='inconclusive', report=None)
        if prepared['error']:
            item['execution'] = 'error'
        else:
            remaining = deadline - time.monotonic()
            if remaining < 0.001:
                item['error'] = 'Suite time budget exhausted before this case'
            else:
                config = deepcopy(prepared['_config'])
                config.setdefault('limits', {})
                config['limits']['timeout_seconds'] = min(config['limits'].get('timeout_seconds', DEFAULT_LIMITS['timeout_seconds']), remaining)
                try:
                    report = run_experiment(config, base_dir=prepared['_path'].parent)
                    if time.monotonic() >= deadline:
                        item.update(execution='timeout', error='Suite time budget exceeded during this case')
                    else:
                        item.update(execution='complete', status=report['status'], report=report)
                except (OSError, ValueError, sqlite3.Error, OverflowError, RecursionError) as exc:
                    item.update(execution='error', error='Case execution failed (' + type(exc).__name__ + ')')
        items.append(item)
    counts = {'total': len(items), **{state: sum(item['status'] == state for item in items) for state in ('equivalent', 'different', 'inconclusive')},
              'not_run': sum(item['execution'] == 'not_run' for item in items)}
    return {'schema_version': 1, 'kind': 'suite', 'title': plan.title, 'status': suite_status(items),
            'environment': {'tool_version': __version__, 'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version},
            'timeout_seconds': plan.timeout_seconds, 'elapsed_seconds': time.monotonic()-started, 'counts': counts, 'cases': items,
            'notes': ['Each case uses its own snapshot. The entire suite does not share one snapshot.',
                      'Any error, blocked case, timeout or unrun case makes the suite inconclusive; no cases are silently dropped.',
                      'Suite execution has a cooperative deadline; native operations can overrun until control returns. Input preflight is byte-bounded separately.',
                      'Reports omit result values and bound parameters; SQL literals, identifiers and file basenames remain visible.',
                      'This is a regression ledger, not a performance score or production speedup benchmark.']}
