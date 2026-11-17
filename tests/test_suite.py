from contextlib import closing
import itertools
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

try:
    from planbench_sqlite import suite
except ImportError:
    suite = None


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        with closing(sqlite3.connect(self.root / 'data.sqlite')) as con, con:
            con.executescript('CREATE TABLE t(x); INSERT INTO t VALUES(1),(2);')
        self.manifest = self.root / 'suite.json'
        self.definition = {'suite_version': 1, 'title': 'Real suite', 'cases': []}
        for name, sql in [('good','SELECT x FROM t'),('different','SELECT 3 AS x'),('blocked','DELETE FROM t')]:
            case = {'schema_version': 1, 'database': 'data.sqlite', 'baseline': {'sql': 'SELECT x FROM t'}, 'candidate': {'sql': sql}}
            (self.root/(name+'.json')).write_text(json.dumps(case), encoding='utf-8')
        self.definition['cases'] = [{'id': name, 'case': name+'.json'} for name in ('good','different','blocked')]
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.definition), encoding='utf-8')

    def load(self):
        self.assertIsNotNone(suite, 'Suite execution must be implemented')
        return suite.load_suite(self.manifest)

    def test_complete_ledger_and_worst_outcome(self):
        result = suite.run_suite(self.load()) if suite else self.load()
        self.assertEqual(result['status'], 'inconclusive')
        self.assertEqual([r['id'] for r in result['cases']], ['good','different','blocked'])
        self.assertEqual(result['counts'], {'total':3,'equivalent':1,'different':1,'inconclusive':1,'not_run':0})
        self.assertEqual(result['cases'][0]['report']['status'], 'equivalent')

    def test_different_and_all_equivalent_aggregation(self):
        self.definition['cases'] = self.definition['cases'][:2]
        self.save()
        self.assertEqual(suite.run_suite(self.load())['status'] if suite else self.load(), 'different')
        self.definition['cases'] = self.definition['cases'][:1]
        self.save()
        self.assertEqual(suite.run_suite(self.load())['status'], 'equivalent')

    def test_invalid_case_retained_and_other_cases_run(self):
        (self.root/'different.json').write_text('{bad', encoding='utf-8')
        result = suite.run_suite(self.load()) if suite else self.load()
        self.assertEqual(result['counts']['total'], 3)
        self.assertEqual(result['cases'][1]['execution'], 'error')
        self.assertEqual(result['cases'][0]['status'], 'equivalent')
        self.assertEqual(result['cases'][2]['execution'], 'complete')

    def test_empty_duplicate_and_unknown_manifest_rejected(self):
        self.assertIsNotNone(suite, 'Suite execution must be implemented')
        for cases in [[], self.definition['cases']*2, [{'id':'x','case':'good.json'},{'id':'y','case':'./good.json'}], [{'id':'x','case':'good.json'}]*51]:
            self.definition['cases'] = cases
            self.save()
            with self.assertRaises(ValueError):
                suite.load_suite(self.manifest)

    def test_distinct_case_files_sharing_one_database_are_allowed(self):
        result = suite.run_suite(self.load()) if suite else self.load()
        self.assertEqual(len(result['cases']), 3)

    def test_case_hardlink_alias_rejected(self):
        self.assertIsNotNone(suite, 'Suite execution must be implemented')
        try:
            os.link(self.root/'good.json', self.root/'alias.json')
        except OSError:
            self.skipTest('Hard links unavailable')
        self.definition['cases'] = [{'id':'a','case':'good.json'},{'id':'b','case':'alias.json'}]
        self.save()
        with self.assertRaises(ValueError):
            self.load()

    def test_deadline_marks_current_timeout_and_remaining_not_run(self):
        plan = self.load()
        clock = [0.0]
        original = suite.run_experiment
        def run_then_expire(*args, **kwargs):
            report = original(*args, **kwargs)
            clock[0] = 100.0
            return report
        with patch.object(suite.time, 'monotonic', side_effect=lambda:clock[0]), patch.object(suite, 'run_experiment', side_effect=run_then_expire):
            result = suite.run_suite(plan)
        self.assertEqual(result['status'], 'inconclusive')
        self.assertEqual([x['execution'] for x in result['cases']], ['timeout','not_run','not_run'])
        self.assertEqual(result['counts']['not_run'], 2)
        self.assertIsNone(result['cases'][0]['report'])

    def test_preflight_protects_database_even_when_case_invalid(self):
        case = {'schema_version':1,'database':'private.sqlite','bad-field':True}
        (self.root/'different.json').write_text(json.dumps(case),encoding='utf-8')
        plan = self.load()
        self.assertIn((self.root/'private.sqlite').resolve(), plan.protected_paths)
        self.assertIn((self.root/'private.sqlite-wal').resolve(), plan.protected_paths)

    def test_aggregate_priorities_invariant_under_permutation(self):
        self.assertIsNotNone(suite, 'Suite execution must be implemented')
        for values in itertools.permutations(['equivalent','different','inconclusive']):
            self.assertEqual(suite.suite_status([{'status':x,'execution':'complete'} for x in values]), 'inconclusive')
        self.assertEqual(suite.suite_status([]), 'inconclusive')
        self.assertEqual(suite.suite_status([{'status':'equivalent','execution':'not_run'}]), 'inconclusive')

    def test_cumulative_input_budget_rejects_before_any_partial_plan(self):
        self.assertIsNotNone(suite, 'Suite execution must be implemented')
        self.definition['cases'] = []
        for i in range(9):
            name = f'large-{i}.json'
            payload = {'database': 'must-not-overwrite.sqlite', 'padding': 'x' * 1_800_000}
            (self.root/name).write_text(json.dumps(payload), encoding='utf-8')
            self.definition['cases'].append({'id': f'c{i}', 'case': name})
        self.save()
        with self.assertRaises(ValueError):
            suite.load_suite(self.manifest)

    def test_cumulative_budget_includes_manifest_exact_boundary(self):
        self.assertIsNotNone(suite, 'Suite execution must be implemented')
        raw = (self.root/'good.json').read_bytes()
        self.definition['cases'] = [{'id': f'c{i}', 'case': f'part-{i}.json'} for i in range(8)]
        self.save()
        manifest_size = len(self.manifest.read_bytes())
        for i in range(8):
            size = 2_000_000 if i < 7 else 16_000_000 - 7*2_000_000 - manifest_size
            (self.root/f'part-{i}.json').write_bytes(raw + b' '*(size-len(raw)))
        self.assertEqual(len(suite.load_suite(self.manifest).items), 8)
        with self.manifest.open('ab') as stream:
            stream.write(b' ')
        with self.assertRaises(ValueError):
            suite.load_suite(self.manifest)

    def test_each_case_uses_its_own_snapshot(self):
        self.assertIsNotNone(suite, 'Suite execution must be implemented')
        case = {'schema_version': 1, 'database': 'data.sqlite', 'baseline': {'sql': 'SELECT sum(x) AS x FROM t'}, 'candidate': {'sql': 'SELECT 3 AS x'}}
        for name in ('one', 'two'):
            (self.root/(name+'.json')).write_text(json.dumps(case), encoding='utf-8')
        self.definition['cases'] = [{'id': x, 'case': x+'.json'} for x in ('one', 'two')]
        self.save()
        original = suite.run_experiment
        calls = []
        def run_then_change_database(*args, **kwargs):
            result = original(*args, **kwargs)
            calls.append(result['status'])
            if len(calls) == 1:
                with closing(sqlite3.connect(self.root/'data.sqlite')) as con, con:
                    con.execute('UPDATE t SET x=x+1')
            return result
        with patch.object(suite, 'run_experiment', side_effect=run_then_change_database):
            result = suite.run_suite(self.load())
        self.assertEqual([item['status'] for item in result['cases']], ['equivalent', 'different'])
        self.assertEqual(result['status'], 'different')

    def test_suite_does_not_export_bound_values_or_absolute_paths(self):
        secret='BOUND-PRIVATE-SUITE-123'
        case={'schema_version':1,'database':'data.sqlite','baseline':{'sql':'SELECT ? AS x','parameters':[secret]},'candidate':{'sql':'SELECT ? AS x','parameters':[secret]}}
        (self.root/'good.json').write_text(json.dumps(case),encoding='utf-8')
        result=suite.run_suite(self.load()) if suite else self.load()
        text=json.dumps(result)
        self.assertNotIn(secret,text)
        self.assertNotIn(str(self.root),text)


if __name__=='__main__':
    unittest.main()
