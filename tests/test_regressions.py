from contextlib import closing
from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from planbench_sqlite import engine


class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'db.sqlite'
        with closing(sqlite3.connect(self.db)) as con, con:
            con.executescript('CREATE TABLE t(x); INSERT INTO t VALUES (1),(2); CREATE INDEX existing ON t(x); CREATE VIEW ordinary AS SELECT x FROM t;')
        self.case = {'schema_version': 1, 'database': str(self.db), 'baseline': {'sql': 'SELECT 1 AS x'}, 'candidate': {'sql': 'SELECT 1 AS x'}}

    def test_huge_limit_integer_is_value_error(self):
        for name in engine.validate_config(self.case)['limits']:
            for number in (10 ** 400, -(10 ** 400)):
                case = dict(self.case, limits={name: number})
                with self.subTest(name=name, sign=number > 0), self.assertRaises(ValueError):
                    engine.run_experiment(case)

    def test_digest_completion_crossing_deadline_is_not_green(self):
        clock = [0.0]
        original = engine.result_digest
        with patch.object(engine.time, 'monotonic', side_effect=lambda: clock[0]):
            self.assertEqual(engine.run_experiment(self.case)['status'], 'equivalent')
            def digest_then_advance(*args):
                result = original(*args)
                clock[0] += 10
                return result
            with patch.object(engine, 'result_digest', side_effect=digest_then_advance):
                result = engine.run_experiment(self.case)
        self.assertEqual(result['status'], 'inconclusive')
        self.assertEqual(result['baseline']['status'], 'limit')
        self.assertIsNone(result['baseline']['result_sha256'])

    def test_backup_progress_consumes_its_own_budget(self):
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute('CREATE TABLE payload(x)')
            con.executemany('INSERT INTO payload VALUES(zeroblob(4000))', [()] * 1024)
        self.case['limits'] = {'max_progress_calls': 10}
        result = engine.run_experiment(self.case)
        self.assertEqual(result['status'], 'inconclusive')
        self.assertEqual(result['baseline']['status'], 'limit')

    def test_implicit_virtual_modules_refused_but_ctes_views_work(self):
        for sql in ["SELECT value FROM json_each('[1,2]')", 'SELECT name FROM dbstat']:
            with self.subTest(sql=sql):
                with closing(sqlite3.connect(self.db)) as con:
                    try:
                        con.execute(sql).fetchall()
                    except sqlite3.Error:
                        self.skipTest('Optional module unavailable: ' + sql.split(' FROM ')[-1])
                self.case['candidate'] = {'sql': sql}
                result = engine.run_experiment(self.case)
                self.assertEqual(result['status'], 'inconclusive')
                self.assertEqual(result['candidate']['status'], 'blocked')
                self.assertIsNone(result['candidate']['result_sha256'])
                self.assertIsNone(result['equality']['progress_ratio'])
        for sql in ['SELECT x FROM ordinary',
                    'WITH RECURSIVE cnt(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM cnt WHERE x<4) SELECT x FROM cnt']:
            with self.subTest(sql=sql):
                self.case['baseline'] = self.case['candidate'] = {'sql': sql}
                self.assertEqual(engine.run_experiment(self.case)['status'], 'equivalent')

    def test_index_name_conflict_is_setup_blocked(self):
        self.case['candidate']['indexes'] = [{'name': 'existing', 'table': 't', 'columns': ['x']}]
        result = engine.run_experiment(self.case)
        self.assertEqual(result['candidate']['status'], 'blocked')
        self.assertIsNone(result['candidate']['result_sha256'])

    def test_final_comparison_deadline_is_checked(self):
        clock = [0.0]
        original = engine.results_equal
        def compare_then_advance(*args):
            result = original(*args)
            clock[0] += 10
            return result
        with patch.object(engine.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(engine, 'results_equal', side_effect=compare_then_advance):
            result = engine.run_experiment(self.case)
        self.assertEqual(result['status'], 'inconclusive')
        self.assertIsNone(result['equality']['equivalent'])

    def test_candidate_index_growth_respects_database_budget(self):
        self.case['limits'] = {'max_database_bytes': self.db.stat().st_size}
        self.case['candidate']['indexes'] = [{'name': 'another', 'table': 't', 'columns': ['x']}]
        result = engine.run_experiment(self.case)
        self.assertEqual(result['status'], 'inconclusive')
        self.assertEqual(result['candidate']['status'], 'limit')

    def test_parameter_nul_is_preserved_not_interpreted_as_sql(self):
        self.case['baseline'] = {'sql': 'SELECT ? AS x', 'parameters': ['a\x00b']}
        self.case['candidate'] = {'sql': 'SELECT ? AS x', 'parameters': ['a\x00b']}
        self.assertEqual(engine.run_experiment(self.case)['status'], 'equivalent')
        for value in ['a\x00c', 'a']:
            self.case['candidate'] = {'sql': 'SELECT ? AS x', 'parameters': [value]}
            self.assertEqual(engine.run_experiment(self.case)['status'], 'different')


if __name__ == '__main__':
    unittest.main()
