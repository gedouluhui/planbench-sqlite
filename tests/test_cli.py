from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

try:
    from planbench_sqlite.cli import main
except ImportError:
    main = None


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'source.sqlite'
        with closing(sqlite3.connect(self.db)) as con, con:
            con.executescript('CREATE TABLE t(x); INSERT INTO t VALUES (1),(2);')
        self.case = self.root / 'case.json'
        self.config = {'schema_version': 1, 'database': self.db.name, 'baseline': {'sql': 'SELECT x FROM t'}, 'candidate': {'sql': 'SELECT x FROM t'}}
        self.save_case()

    def save_case(self):
        self.case.write_text(json.dumps(self.config), encoding='utf-8')

    def invoke(self, *args):
        self.assertTrue(callable(main), 'CLI main must be implemented')
        env = dict(os.environ, PYTHONUTF8='1')
        result = subprocess.run([sys.executable, '-m', 'planbench_sqlite', *map(str, args)], capture_output=True, text=True, encoding='utf-8', env=env, timeout=30)
        self.assertNotIn('Traceback', result.stderr)
        return result

    def test_real_cli_json_and_html(self):
        output, html = self.root / 'report.json', self.root / 'report.html'
        r = self.invoke('compare', self.case, '--json', output, '--html', html)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(output.read_text())['status'], 'equivalent')
        self.assertIn('Same rows.', html.read_text(encoding='utf-8'))

    def test_different_and_inconclusive_exit_codes(self):
        self.config['candidate']['sql'] = 'SELECT 3 AS x'
        self.save_case()
        self.assertEqual(self.invoke('compare', self.case).returncode, 1)
        self.config['candidate']['sql'] = 'DELETE FROM t'
        self.save_case()
        self.assertEqual(self.invoke('compare', self.case).returncode, 2)

    def test_input_database_case_and_sidecar_protection_with_force(self):
        for target in [self.db, self.case, Path(str(self.db) + '-wal'), Path(str(self.db) + '-shm')]:
            with self.subTest(target=target):
                before = self.db.read_bytes()
                r = self.invoke('compare', self.case, '--json', target, '--force')
                self.assertEqual(r.returncode, 2)
                self.assertEqual(self.db.read_bytes(), before)
                self.assertEqual(json.loads(self.case.read_text()), self.config)

    def test_output_aliases_rejected(self):
        out = self.root / 'same.out'
        self.assertEqual(self.invoke('compare', self.case, '--json', out, '--html', out).returncode, 2)
        self.assertFalse(out.exists())

    def test_existing_output_refused_then_explicit_force(self):
        out = self.root / 'report.json'
        out.write_text('original', encoding='utf-8')
        self.assertEqual(self.invoke('compare', self.case, '--json', out).returncode, 2)
        self.assertEqual(out.read_text(), 'original')
        self.assertEqual(self.invoke('compare', self.case, '--json', out, '--force').returncode, 0)

    def test_hardlink_to_source_refused(self):
        alias = self.root / 'alias.json'
        try:
            os.link(self.db, alias)
        except OSError:
            self.skipTest('Hard links unavailable')
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.assertEqual(self.invoke('compare', self.case, '--json', alias, '--force').returncode, 2)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)

    def test_bad_json_and_unknown_config_do_not_traceback(self):
        for body in ['{', '{"schema_version":1,"schema_version":1}', '{"x":NaN}', '[]', '"text"']:
            self.case.write_text(body, encoding='utf-8')
            self.assertEqual(self.invoke('compare', self.case).returncode, 2)

    def test_deterministic_demo_three_states_and_overwrite_refusal(self):
        out = self.root / 'demo'
        r = self.invoke('demo', '--out', out)
        self.assertEqual(r.returncode, 0, r.stderr)
        report = json.loads((out / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'equivalent')
        self.assertIn('orders_customer', ' '.join(row['detail'] for row in report['candidate']['plan']))
        self.assertEqual(self.invoke('compare', out / 'different.json').returncode, 1)
        self.assertEqual(self.invoke('compare', out / 'limited.json').returncode, 2)
        self.assertEqual(self.invoke('demo', '--out', out).returncode, 2)

    def test_version_and_missing_command(self):
        self.assertEqual(self.invoke('--version').returncode, 0)
        self.assertEqual(self.invoke().returncode, 2)


if __name__ == '__main__':
    unittest.main()
