from contextlib import closing, redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from planbench_sqlite import cli, demo, engine
from planbench_sqlite.report import render_html


class DeliveryRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'source.sqlite'
        with closing(sqlite3.connect(self.db)) as con, con:
            con.executescript('CREATE TABLE t(x); INSERT INTO t VALUES(1);')
        self.case = {'schema_version': 1, 'database': str(self.db), 'baseline': {'sql': 'SELECT x FROM t'}, 'candidate': {'sql': 'SELECT x FROM t'}}
        self.path = self.root / 'case.json'
        self.path.write_text(json.dumps(self.case), encoding='utf-8')

    def invoke(self, *args):
        err, out = StringIO(), StringIO()
        with redirect_stderr(err), redirect_stdout(out):
            try:
                result = cli.main(list(map(str, args)))
            except Exception as exc:
                self.fail('CLI leaked exception instead of returning exit 2: ' + type(exc).__name__)
        self.assertNotIn('Traceback', err.getvalue())
        return result

    @unittest.skipUnless(os.name == 'nt', 'Windows path alias policy')
    def test_nonexistent_windows_output_aliases_refused(self):
        for i, suffix in enumerate(['.', ' ', '..']):
            output = self.root / ('new' + str(i) + '.json')
            alias = Path(str(output) + suffix)
            with self.subTest(suffix=suffix):
                result = self.invoke('compare', self.path, '--json', output, '--html', alias, '--force')
                self.assertEqual(result, 2)
                self.assertFalse(output.exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows sidecar alias policy')
    def test_nonexistent_windows_sidecar_aliases_refused(self):
        for suffix in ['-wal.', '-shm ', '-journal.']:
            with self.subTest(suffix=suffix):
                result = self.invoke('compare', self.path, '--json', str(self.db) + suffix, '--force')
                self.assertEqual(result, 2)
                self.assertFalse(Path(str(self.db) + suffix.rstrip('. ')).exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows parent navigation policy')
    def test_windows_parent_navigation_remains_usable(self):
        child = self.root / 'child'
        child.mkdir()
        output = child / '..' / 'ordinary.json'
        self.assertEqual(self.invoke('compare', self.path, '--json', output), 0)
        self.assertEqual(json.loads(output.read_text())['status'], 'equivalent')
        demo_output = child / '..' / 'parent-demo'
        self.assertEqual(self.invoke('demo', '--out', demo_output), 0)
        self.assertTrue((demo_output / 'report.html').is_file())

    def test_real_sqlite_full_in_demo_is_sanitized_exit_two(self):
        original = sqlite3.connect
        def quota_connection(*args, **kwargs):
            connection = original(*args, **kwargs)
            connection.execute('PRAGMA max_page_count=2')
            return connection
        with patch.object(demo.sqlite3, 'connect', side_effect=quota_connection):
            self.assertEqual(self.invoke('demo', '--out', self.root / 'quota-demo'), 2)

    def test_report_preserves_real_final_comparison_timeout_reason(self):
        clock = [0.0]
        original = engine.results_equal
        def compare_then_expire(*args):
            result = original(*args)
            clock[0] += 10
            return result
        with patch.object(engine.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(engine, 'results_equal', side_effect=compare_then_expire):
            report = engine.run_experiment(self.case)
        self.assertEqual(report['status'], 'inconclusive')
        self.assertEqual(report['baseline']['status'], 'complete')
        html = render_html(report)
        self.assertIn(report['equality']['reason'], html)
        self.assertNotIn('One or both runs did not complete.', html)


if __name__ == '__main__':
    unittest.main()
