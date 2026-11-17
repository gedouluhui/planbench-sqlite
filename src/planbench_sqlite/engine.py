"""SQLite experiments on disposable clones, never on the source connection.

This module is intended for trusted local databases, not hostile-file sandboxing.
"""

from contextlib import closing
from pathlib import Path
import platform
import sqlite3
import time

from .engine_config import validate_config
from .engine_values import encode_row, result_digest, results_equal

# Explicit surface: newly introduced or extension-provided functions are not
# admitted automatically. Order-sensitive aggregates remain snapshot observations.
ALLOWED_FUNCTIONS = frozenset({
    'abs', 'avg', 'char', 'coalesce', 'count', 'cume_dist', 'dense_rank',
    'first_value', 'glob', 'group_concat', 'hex', 'ifnull', 'iif', 'instr',
    'lag', 'last_value', 'lead', 'length', 'like', 'likelihood', 'likely',
    'lower', 'ltrim', 'max', 'min', 'nth_value', 'ntile', 'nullif',
    'percent_rank', 'printf', 'quote', 'rank', 'replace', 'round',
    'row_number', 'rtrim', 'sign', 'substr', 'substring', 'sum', 'total',
    'trim', 'typeof', 'unicode', 'unlikely', 'upper', 'zeroblob',
})
_ALLOWED_ACTIONS = frozenset({sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE})


class BudgetExceeded(Exception):
    pass


class Unsupported(Exception):
    pass


class _Budget:
    def __init__(self, limits):
        self.calls = 0
        self.limit = limits['max_progress_calls']
        self.deadline = time.monotonic() + limits['timeout_seconds']
        self.reason = None

    def check(self):
        if time.monotonic() >= self.deadline:
            self.reason = 'Cooperative elapsed-time budget exceeded'
            raise BudgetExceeded(self.reason)

    def progress(self):
        self.calls += 1
        if self.calls >= self.limit:
            self.reason = 'Progress-callback budget reached'
            return 1
        if time.monotonic() >= self.deadline:
            self.reason = 'Cooperative elapsed-time budget exceeded'
            return 1
        return 0


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _harden(con):
    con.execute('PRAGMA temp_store=MEMORY')
    con.execute('PRAGMA trusted_schema=OFF')
    row = con.execute('PRAGMA trusted_schema').fetchone()
    if row != (0,):
        raise Unsupported('This SQLite build cannot verify trusted_schema=OFF')


def _backup(source, dest, limits):
    budget = _Budget(limits)
    page_size = source.execute('PRAGMA page_size').fetchone()[0]
    pages = source.execute('PRAGMA page_count').fetchone()[0]
    if pages * page_size > limits['max_database_bytes']:
        raise BudgetExceeded('Database snapshot exceeds byte budget')

    def progress(status, remaining, total):
        if budget.progress():
            raise BudgetExceeded('Snapshot ' + budget.reason)
        if total * page_size > limits['max_database_bytes']:
            raise BudgetExceeded('Database grew beyond snapshot byte budget')

    source.backup(dest, pages=64, progress=progress, sleep=0.001)
    budget.check()
    size = dest.execute('PRAGMA page_count').fetchone()[0] * dest.execute('PRAGMA page_size').fetchone()[0]
    if size > limits['max_database_bytes']:
        raise BudgetExceeded('Database snapshot exceeds byte budget')
    return size


def _check_schema(con):
    # table_list distinguishes ordinary, virtual and shadow tables on recent
    # SQLite. The SQL fallback also rejects virtual-table declarations.
    for row in con.execute('PRAGMA table_list'):
        if row[2] in ('virtual', 'shadow'):
            raise Unsupported('Virtual and shadow tables are outside this version\'s scope')
    for sql, in con.execute("SELECT sql FROM sqlite_schema WHERE type='table'"):
        if sql and sql.lstrip().upper().startswith('CREATE VIRTUAL'):
            raise Unsupported('Virtual tables are outside this version\'s scope')


def _create_indexes(con, definitions, limits):
    budget = _Budget(limits)
    con.set_progress_handler(budget.progress, 1)
    statements = []
    try:
        page_size = con.execute('PRAGMA page_size').fetchone()[0]
        page_limit = limits['max_database_bytes'] // page_size
        if page_limit < 1:
            raise BudgetExceeded('Candidate database byte budget is smaller than one page')
        con.execute('PRAGMA max_page_count=' + str(page_limit))
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        for definition in definitions:
            budget.check()
            table = definition['table']
            if table not in tables or table.lower().startswith('sqlite_'):
                raise Unsupported('Index table must name an existing ordinary user table exactly')
            columns = {row[1] for row in con.execute('PRAGMA table_xinfo(' + _quote(table) + ')') if row[6] == 0}
            if not set(definition['columns']).issubset(columns):
                raise Unsupported('Index columns must name existing non-generated columns exactly')
            sql = 'CREATE INDEX ' + _quote(definition['name']) + ' ON ' + _quote(table)
            sql += ' (' + ', '.join(_quote(col) for col in definition['columns']) + ')'
            con.execute(sql)
            statements.append(sql)
        con.commit()
        budget.check()
    except sqlite3.Error as exc:
        if budget.reason:
            raise BudgetExceeded(budget.reason) from None
        if getattr(exc, 'sqlite_errorcode', None) == sqlite3.SQLITE_FULL:
            raise BudgetExceeded('Candidate index growth exceeds database page budget') from None
        raise Unsupported('Candidate index setup was rejected by SQLite') from None
    finally:
        con.set_progress_handler(None, 0)
    return statements


def _empty_arm(arm):
    return {'status': 'blocked', 'sql': arm['sql'], 'index_definitions': [],
            'plan': [], 'columns': [], 'row_count': 0, 'result_bytes': 0,
            'result_sha256': None, 'progress_calls': 0, 'elapsed_seconds': 0.0, 'error': None}


def _execute(con, arm, limits, mode):
    result = _empty_arm(arm)
    encoded = []
    budget = None
    denied = []
    # Eponymous modules (json_each, dbstat, pragma_*) need not appear in
    # table_list until first use. Permit reads only of captured real objects.
    ordinary_objects = {row[0] for row in con.execute("SELECT name FROM sqlite_schema WHERE type IN ('table','view')")}
    ordinary_objects.update(('sqlite_schema', 'sqlite_master'))

    def authorize(action, arg1, arg2, database, trigger):
        # SQLite can emit a columnless READ with database=None for an
        # optimized rowid scan. Object membership still excludes modules.
        if action == sqlite3.SQLITE_READ and database in ('main', None) and arg1 in ordinary_objects:
            return sqlite3.SQLITE_OK
        if action in _ALLOWED_ACTIONS:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or '').lower() in ALLOWED_FUNCTIONS:
            return sqlite3.SQLITE_OK
        denied.append(action)
        return sqlite3.SQLITE_DENY

    try:
        result['index_definitions'] = _create_indexes(con, arm['indexes'], limits) if arm['indexes'] else []
        con.set_authorizer(authorize)
        # Python 3.11+ is required so the native value-size guard is always
        # present rather than silently skipped on an older interpreter.
        con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, max(1024, limits['max_result_bytes']))
        con.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 100000)
        plan_budget = _Budget(limits)
        con.set_progress_handler(plan_budget.progress, 1)
        try:
            plan_cursor = con.execute('EXPLAIN QUERY PLAN ' + arm['sql'], arm['parameters'])
            for node in plan_cursor:
                plan_budget.check()
                if len(result['plan']) >= 10000:
                    raise BudgetExceeded('Query plan node budget exceeded')
                result['plan'].append({'id': node[0], 'parent': node[1], 'auxiliary': node[2], 'detail': node[3]})
        except sqlite3.Error:
            if plan_budget.reason:
                raise BudgetExceeded(plan_budget.reason) from None
            raise
        finally:
            con.set_progress_handler(None, 0)
        # Explain counters are deliberately not mixed into execution counters.
        budget = _Budget(limits)
        started = time.monotonic()
        con.set_progress_handler(budget.progress, 1)
        try:
            cursor = con.execute(arm['sql'], arm['parameters'])
            if cursor.description is None:
                raise Unsupported('Query must return a SELECT result')
            result['columns'] = [item[0] for item in cursor.description]
            for row in cursor:
                budget.check()
                if len(encoded) >= limits['max_rows']:
                    raise BudgetExceeded('Result row budget exceeded')
                data = encode_row(row)
                if result['result_bytes'] + len(data) > limits['max_result_bytes']:
                    raise BudgetExceeded('Encoded result byte budget exceeded')
                encoded.append(data)
                result['result_bytes'] += len(data)
                result['row_count'] = len(encoded)
            budget.check()
            result['result_sha256'] = result_digest(encoded, mode, budget.check)
            budget.check()
            result['status'] = 'complete'
        finally:
            result['progress_calls'] = budget.calls
            result['elapsed_seconds'] = time.monotonic() - started
    except BudgetExceeded as exc:
        result.update(status='limit', error=str(exc))
    except (Unsupported, ValueError, UnicodeError) as exc:
        result.update(status='blocked', error=str(exc))
    except sqlite3.Error as exc:
        if budget is not None and budget.reason:
            result.update(status='limit', error=budget.reason)
        elif getattr(exc, 'sqlite_errorcode', None) == sqlite3.SQLITE_TOOBIG:
            result.update(status='limit', error='SQLite value-size budget exceeded')
        elif denied:
            result.update(status='blocked', error='SQL operation or function is outside the read-only allowlist')
        else:
            # SQLite errors can echo literals from input. Keep raw exception
            # text out of portable reports; the SQL itself remains visible.
            result.update(status='error', error='SQLite rejected the query or index (' + type(exc).__name__ + ')')
    finally:
        con.set_progress_handler(None, 0)
        con.set_authorizer(None)
    if result['status'] != 'complete':
        result['result_sha256'] = None
        encoded = []
    return result, encoded


def run_experiment(config: dict, *, base_dir: str | Path = '.') -> dict:
    """Compare two arms on one snapshot. Invalid input raises ValueError.

    Completed equivalence describes only these parameters and this snapshot.
    Limits are cooperative, not a sandbox or a guaranteed hard time bound.
    """
    config = validate_config(config)
    limits = config['limits']
    path = (Path(base_dir) / config['database']).resolve()
    report = {'schema_version': 1, 'title': config['title'], 'status': 'inconclusive',
              'comparison': config['comparison'],
              'environment': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version},
              'source': {'database': path.name, 'snapshot_bytes': None}, 'limits': limits,
              'baseline': _empty_arm(config['baseline']), 'candidate': _empty_arm(config['candidate']),
              'equality': {'comparable': False, 'equivalent': None, 'schema_equal': None,
                           'reason': 'Both arms must complete before comparison', 'progress_ratio': None},
              'notes': [
                  'Equality covers only this snapshot and the supplied parameters, not all possible databases.',
                  'Progress callbacks (interval 1) are not exact VM instruction counts. Preparation may contribute.',
                  'Wall time includes instrumentation and result encoding; it is not a production benchmark.',
                  'SQL and identifiers are included. Review literals before sharing; row and parameter values are omitted.',
                  'No ANALYZE is run. Existing statistics are cloned; only candidate indexes are added. No cache flush is attempted.',
                  'SQLite EQP text is diagnostic and version-dependent. Time limits are cooperative.',
                  'Unordered LIMIT, tied ordering and order-sensitive aggregates can change results after indexing.',
              ]}
    try:
        if not path.is_file():
            raise Unsupported('Source database does not exist as a regular file')
        if path.stat().st_size > limits['max_database_bytes']:
            raise BudgetExceeded('Source database file exceeds byte budget')
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=min(1.0, limits['timeout_seconds']), cached_statements=0)) as source:
            with closing(sqlite3.connect(':memory:', cached_statements=0)) as snapshot:
                _harden(source)
                report['source']['snapshot_bytes'] = _backup(source, snapshot, limits)
                _harden(snapshot)
                _check_schema(snapshot)
                rows = {}
                for label in ('baseline', 'candidate'):
                    with closing(sqlite3.connect(':memory:', cached_statements=0)) as con:
                        _backup(snapshot, con, limits)
                        _harden(con)
                        report[label], rows[label] = _execute(con, config[label], limits, config['comparison'])
                a, b = report['baseline'], report['candidate']
                if a['status'] == b['status'] == 'complete':
                    comparison_budget = _Budget(limits)
                    schema_equal = a['columns'] == b['columns']
                    equal = schema_equal and results_equal(rows['baseline'], rows['candidate'], config['comparison'])
                    comparison_budget.check()
                    report['status'] = 'equivalent' if equal else 'different'
                    report['equality'].update(comparable=True, equivalent=equal, schema_equal=schema_equal,
                                             reason=('Schemas and typed rows match for this snapshot' if equal else
                                                     'Result column names/count differ' if not schema_equal else
                                                     'Typed row values, multiplicity or required order differ'))
                    if equal and a['progress_calls']:
                        report['equality']['progress_ratio'] = b['progress_calls'] / a['progress_calls']
    except (Unsupported, BudgetExceeded, sqlite3.Error, OSError) as exc:
        status = 'limit' if isinstance(exc, BudgetExceeded) else 'blocked'
        message = str(exc) if isinstance(exc, (Unsupported, BudgetExceeded)) else 'Source snapshot could not be read (' + type(exc).__name__ + ')'
        for label in ('baseline', 'candidate'):
            if report[label]['status'] != 'complete':
                report[label].update(status=status, error=message)
        report['equality']['reason'] = message
    return report
