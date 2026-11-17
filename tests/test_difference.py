from contextlib import closing
import itertools
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from planbench_sqlite import engine
from planbench_sqlite.engine_values import encode_row


class DifferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'data.sqlite'
        with closing(sqlite3.connect(self.db)) as con, con:
            con.executescript('CREATE TABLE t(x); INSERT INTO t VALUES(1),(2),(3);')

    def compare(self, left, right, mode='multiset', parameters=None):
        case = {'schema_version': 1, 'database': str(self.db), 'comparison': mode,
                'baseline': {'sql': left, 'parameters': parameters or []},
                'candidate': {'sql': right, 'parameters': parameters or []}}
        r = engine.run_experiment(case)
        self.assertIn('difference', r, 'The generated report must contain additive difference evidence')
        return r

    def test_duplicate_excess_counts_and_first_source_index(self):
        r = self.compare('SELECT 1 AS x UNION ALL SELECT 1', 'SELECT 1 AS x')
        d = r['difference']
        self.assertEqual((d['matched_rows'], d['missing_rows'], d['extra_rows']), (1, 1, 0))
        self.assertEqual(d['missing_examples'][0]['row_index'], 0)
        self.assertEqual(d['missing_examples'][0]['count'], 1)
        self.assertEqual(d['missing_examples'][0]['column_types'], ['INTEGER'])

    def test_order_is_not_missing_data(self):
        r = self.compare('SELECT x FROM t ORDER BY x', 'SELECT x FROM t ORDER BY x DESC', 'ordered')
        self.assertEqual(r['status'], 'different')
        d = r['difference']
        self.assertEqual((d['missing_rows'], d['extra_rows']), (0, 0))
        self.assertEqual(d['first_mismatch']['row_index'], 0)
        self.assertEqual(d['first_mismatch']['columns'], [{'column_index': 0, 'baseline_type': 'INTEGER', 'candidate_type': 'INTEGER'}])

    def test_schema_only_and_absent_row_are_explicit(self):
        r = self.compare('SELECT 1 AS a WHERE 0', 'SELECT 1 AS b WHERE 0')
        self.assertEqual(r['difference']['schema_changes'], [{'column_index': 0, 'baseline_name': 'a', 'candidate_name': 'b'}])
        r = self.compare('SELECT NULL AS x UNION ALL SELECT 1', 'SELECT NULL AS x', 'ordered')
        self.assertEqual(r['difference']['first_mismatch']['row_index'], 1)
        self.assertEqual(r['difference']['first_mismatch']['columns'][0]['candidate_type'], 'ABSENT')

    def test_many_examples_are_bounded_but_totals_exact(self):
        q = 'WITH RECURSIVE a(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM a WHERE x<25) SELECT x FROM a'
        r = self.compare(q, 'SELECT 99 AS x')
        d = r['difference']
        self.assertEqual((d['missing_rows'], d['extra_rows']), (25, 1))
        self.assertEqual(len(d['missing_examples']), 10)
        self.assertTrue(d['examples_truncated'])

    def test_evidence_omits_values_and_per_row_hashes(self):
        secret = 'PRIVATE-ROW-AND-PARAMETER'
        r = self.compare('SELECT ? AS x', "SELECT ? || ' changed' AS x", parameters=[secret])
        text = json.dumps(r['difference'])
        self.assertNotIn(secret, text)
        self.assertNotIn('sha256', text)
        self.assertEqual(r['difference']['missing_examples'][0]['column_types'], ['TEXT'])
        self.assertIn('tool_version', r['environment'])

    def test_cancelled_diagnosis_has_no_completed_evidence(self):
        self.assertTrue(hasattr(engine, 'describe_difference'), 'Difference diagnosis must be integrated')
        original = engine.describe_difference
        clock = [0.0]
        def expire(*args, **kwargs):
            result = original(*args, **kwargs)
            clock[0] += 10
            return result
        with patch.object(engine.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(engine, 'describe_difference', side_effect=expire):
            r = self.compare('SELECT 1 AS x', 'SELECT 2 AS x')
        self.assertEqual(r['status'], 'inconclusive')
        self.assertIsNone(r['difference'])

    def test_identical_diagnostic_hashes_do_not_hide_real_difference(self):
        with patch.object(engine, 'result_digest', return_value='0'*64):
            r = self.compare('SELECT 1 AS x', 'SELECT 2 AS x')
        self.assertEqual(r['status'], 'different')
        self.assertEqual(r['baseline']['result_sha256'], r['candidate']['result_sha256'])
        self.assertEqual((r['difference']['missing_rows'], r['difference']['extra_rows']), (1, 1))

    def test_exhaustive_bag_oracle_does_not_share_counter_logic(self):
        self.assertTrue(hasattr(engine, 'describe_difference'), 'Difference diagnosis must be implemented')
        alphabet = [None, 1, 1.0, '1', b'1']
        sequences = [()] + [x for n in (1, 2) for x in itertools.product(alphabet, repeat=n)]
        for a in sequences:
            for b in sequences:
                left = [encode_row((x,)) for x in a]
                right = [encode_row((x,)) for x in b]
                remaining = list(right)
                matched = 0
                for row in left:
                    if row in remaining:
                        remaining.remove(row)
                        matched += 1
                d = engine.describe_difference(left, right, ['x'], ['x'], 'multiset', lambda: None)
                self.assertEqual((d['matched_rows'], d['missing_rows'], d['extra_rows']), (matched, len(left)-matched, len(right)-matched))
                self.assertEqual(d['matched_rows'] + d['missing_rows'], len(a))
                self.assertEqual(d['matched_rows'] + d['extra_rows'], len(b))


if __name__ == '__main__':
    unittest.main()
