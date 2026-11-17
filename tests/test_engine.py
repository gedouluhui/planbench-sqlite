import copy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

try:
    from planbench_sqlite.engine import run_experiment
except ImportError:
    run_experiment = None


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'sample #数据.sqlite'
        with closing(sqlite3.connect(self.db)) as con, con:
            con.executescript('CREATE TABLE t(id INTEGER PRIMARY KEY, x INTEGER, label TEXT);')
            con.executemany('INSERT INTO t VALUES (?,?,?)', [(i, i % 73, 'row-' + str(i)) for i in range(2000)])
        self.case = {'schema_version': 1, 'database': self.db.name, 'title': 'Real experiment',
                     'baseline': {'sql': 'SELECT id,x FROM t WHERE x = ? ORDER BY id', 'parameters': [17]},
                     'candidate': {'sql': 'SELECT id,x FROM t WHERE x = ? ORDER BY id', 'parameters': [17],
                                   'indexes': [{'name': 'by_x', 'table': 't', 'columns': ['x']}]},
                     'comparison': 'ordered'}

    def run_case(self, case=None):
        self.assertTrue(callable(run_experiment), 'run_experiment must be implemented')
        return run_experiment(case or self.case, base_dir=self.root)

    def pair(self, a, b, mode='multiset'):
        case = copy.deepcopy(self.case)
        case['baseline'] = {'sql': a}
        case['candidate'] = {'sql': b}
        case['comparison'] = mode
        return self.run_case(case)

    def test_real_index_equivalent_and_less_instrumented_work(self):
        result = self.run_case()
        self.assertEqual(result['status'], 'equivalent')
        self.assertIs(result['equality']['equivalent'], True)
        self.assertGreater(result['baseline']['progress_calls'], result['candidate']['progress_calls'])
        self.assertIn('by_x', ' '.join(row['detail'] for row in result['candidate']['plan']))
        with closing(sqlite3.connect(self.db)) as con, con:
            expected = con.execute(self.case['baseline']['sql'], (17,)).fetchall()
            self.assertEqual(con.execute("SELECT count(*) FROM sqlite_master WHERE name='by_x'").fetchone()[0], 0)
        self.assertEqual(result['candidate']['row_count'], len(expected))

    def test_source_bytes_unchanged(self):
        before = hashlib.sha256(self.db.read_bytes()).digest()
        self.run_case()
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).digest(), before)

    def test_multiplicity_is_not_set_equality(self):
        r = self.pair('SELECT 1 AS x UNION ALL SELECT 1', 'SELECT 1 AS x')
        self.assertEqual(r['status'], 'different')

    def test_multiset_accepts_reordering_but_ordered_does_not(self):
        a = 'SELECT id FROM t WHERE id < 3 ORDER BY id ASC'
        b = 'SELECT id FROM t WHERE id < 3 ORDER BY id DESC'
        self.assertEqual(self.pair(a, b)['status'], 'equivalent')
        self.assertEqual(self.pair(a, b, 'ordered')['status'], 'different')

    def test_types_are_distinct(self):
        for b in ["SELECT '1' AS x", 'SELECT 1.0 AS x', "SELECT X'31' AS x"]:
            with self.subTest(b=b):
                self.assertEqual(self.pair('SELECT 1 AS x', b)['status'], 'different')

    def test_null_blob_and_delimiter_values(self):
        q = "SELECT NULL AS a, X'0001ff' AS b, char(0)||'a:1' AS c"
        self.assertEqual(self.pair(q, q)['status'], 'equivalent')

    def test_schema_mismatch_and_empty_results(self):
        self.assertEqual(self.pair('SELECT 1 AS a WHERE 0', 'SELECT 1 AS b WHERE 0')['status'], 'different')
        self.assertEqual(self.pair('SELECT 1 AS a WHERE 0', 'SELECT 1 AS a WHERE 0')['status'], 'equivalent')

    def test_changed_predicate_is_different(self):
        self.case['candidate']['parameters'] = [18]
        r = self.run_case()
        self.assertEqual(r['status'], 'different')
        self.assertIsNone(r['equality']['progress_ratio'])

    def test_row_budget_is_inconclusive_not_equal_partial(self):
        self.case['limits'] = {'max_rows': 1}
        r = self.run_case()
        self.assertEqual(r['status'], 'inconclusive')
        self.assertIsNone(r['equality']['equivalent'])
        self.assertEqual(r['baseline']['status'], 'limit')
        self.assertIsNone(r['baseline']['result_sha256'])

    def test_result_byte_budget(self):
        self.case['limits'] = {'max_result_bytes': 1}
        self.assertEqual(self.run_case()['status'], 'inconclusive')

    def test_progress_budget(self):
        self.case['limits'] = {'max_progress_calls': 1}
        self.assertEqual(self.run_case()['status'], 'inconclusive')

    def test_database_budget(self):
        self.case['limits'] = {'max_database_bytes': 4096}
        self.assertEqual(self.run_case()['status'], 'inconclusive')

    def test_write_attach_pragma_and_unsafe_functions_blocked(self):
        queries = ['DELETE FROM t RETURNING id', 'PRAGMA user_version=20',
                   "ATTACH DATABASE ':memory:' AS other", 'SELECT random()',
                   "SELECT datetime('now')", "SELECT load_extension('anything')", 'BEGIN',
                   'UPDATE t SET x=0 RETURNING id', 'CREATE TABLE z(x)']
        for q in queries:
            with self.subTest(q=q):
                self.case['candidate'] = {'sql': q}
                r = self.run_case()
                self.assertEqual(r['status'], 'inconclusive')
                self.assertIn(r['candidate']['status'], ('blocked', 'error'))
        with closing(sqlite3.connect(self.db)) as con, con:
            self.assertEqual(con.execute('SELECT count(*) FROM t').fetchone()[0], 2000)
            self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0], 0)

    def test_cte_aggregate_and_bound_parameter(self):
        q = 'WITH a AS (SELECT x FROM t WHERE id < ?) SELECT sum(x) AS total FROM a'
        self.case['baseline'] = {'sql': q, 'parameters': [10]}
        self.case['candidate'] = {'sql': q, 'parameters': [10]}
        self.assertEqual(self.run_case()['status'], 'equivalent')

    def test_invalid_config_rejected(self):
        self.assertTrue(callable(run_experiment), 'run_experiment must be implemented')
        variants = [dict(self.case, schema_version=True), dict(self.case, unknown=1),
                    dict(self.case, comparison='approximate'), dict(self.case, limits={'max_rows': True}),
                    dict(self.case, limits={'timeout_seconds': float('nan')}),
                    dict(self.case, baseline={'sql': 'SELECT ?', 'parameters': [[1]]}),
                    dict(self.case, candidate={'sql': 'SELECT 1', 'indexes': [{'name': 'i', 'table': 't', 'columns': []}]})]
        for case in variants:
            with self.subTest(case=str(case)[:80]), self.assertRaises(ValueError):
                run_experiment(case, base_dir=self.root)

    def test_missing_database_not_created(self):
        self.case['database'] = 'absent.sqlite'
        r = self.run_case()
        self.assertEqual(r['status'], 'inconclusive')
        self.assertFalse((self.root / 'absent.sqlite').exists())

    def test_bad_index_is_explicit_not_ignored(self):
        self.case['candidate']['indexes'][0]['columns'] = ['absent']
        r = self.run_case()
        self.assertEqual(r['status'], 'inconclusive')
        self.assertNotEqual(r['candidate']['status'], 'complete')

    def test_report_does_not_include_values_or_private_path(self):
        secret = 'unique-bound-value-do-not-report'
        q = 'SELECT ? AS val'
        self.case['baseline'] = {'sql': q, 'parameters': [secret]}
        self.case['candidate'] = {'sql': q, 'parameters': [secret]}
        r = self.run_case()
        text = json.dumps(r)
        self.assertNotIn(secret, text)
        self.assertNotIn(str(self.root), text)
        self.assertEqual(r['status'], 'equivalent')

    def test_committed_wal_rows_are_in_snapshot(self):
        con = sqlite3.connect(self.db)
        self.addCleanup(con.close)
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('INSERT INTO t VALUES (5000,17,?)', ('wal-only-row',))
        con.commit()
        self.assertTrue(Path(str(self.db) + '-wal').exists())
        expected = con.execute('SELECT count(*) FROM t WHERE x=17').fetchone()[0]
        r = self.run_case()
        self.assertEqual(r['status'], 'equivalent')
        self.assertEqual(r['baseline']['row_count'], expected)

    def test_virtual_table_refused(self):
        with closing(sqlite3.connect(self.db)) as con, con:
            try:
                con.execute('CREATE VIRTUAL TABLE docs USING fts5(text)')
            except sqlite3.OperationalError:
                self.skipTest('This SQLite build has no FTS5')
        self.assertEqual(self.run_case()['status'], 'inconclusive')

    def test_multi_statement_and_nonfinite_result_refused(self):
        for q in ['SELECT 1; SELECT 2', 'SELECT 1e999 AS x']:
            with self.subTest(q=q):
                self.case['candidate'] = {'sql': q}
                self.assertEqual(self.run_case()['status'], 'inconclusive')


if __name__ == '__main__':
    unittest.main()
