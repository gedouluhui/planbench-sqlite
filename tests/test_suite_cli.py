from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class SuiteCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        with closing(sqlite3.connect(self.root/'data.sqlite')) as con, con:
            con.executescript('CREATE TABLE t(x); INSERT INTO t VALUES(1),(2);')
        self.case={'schema_version':1,'database':'data.sqlite','baseline':{'sql':'SELECT x FROM t'},'candidate':{'sql':'SELECT x FROM t'}}
        (self.root/'a.json').write_text(json.dumps(self.case),encoding='utf-8')
        self.definition={'suite_version':1,'cases':[{'id':'lookup','case':'a.json'}]}
        self.manifest=self.root/'suite.json'
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.definition),encoding='utf-8')

    def run_cli(self,*args):
        result=subprocess.run([sys.executable,'-m','planbench_sqlite',*map(str,args)],env=dict(os.environ,PYTHONUTF8='1'),capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertNotIn('Traceback',result.stderr)
        return result

    def test_suite_cli_writes_both_reports(self):
        out=self.root/'result.json'; html=self.root/'result.html'
        r=self.run_cli('suite',self.manifest,'--json',out,'--html',html)
        self.assertEqual(r.returncode,0,r.stderr)
        data=json.loads(out.read_text())
        self.assertEqual(data['counts']['total'],1)
        self.assertIn('lookup',html.read_text(encoding='utf-8'))
        self.assertIn('Every case has a result',html.read_text(encoding='utf-8'))

    def test_suite_protects_later_invalid_case_database_and_sidecars(self):
        future=self.root/'future.sqlite'
        invalid={'database':'future.sqlite','schema_version':True}
        (self.root/'invalid.json').write_text(json.dumps(invalid),encoding='utf-8')
        self.definition['cases'].append({'id':'invalid','case':'invalid.json'})
        self.save()
        for path in [future,Path(str(future)+'-wal'),self.manifest,self.root/'invalid.json']:
            before=path.read_bytes() if path.exists() else None
            r=self.run_cli('suite',self.manifest,'--json',path,'--force')
            self.assertEqual(r.returncode,2)
            self.assertIn('overwrite an input',r.stderr)
            self.assertEqual(path.read_bytes() if path.exists() else None,before)

    def test_suite_invalid_case_is_recorded_in_output(self):
        self.definition['cases'].append({'id':'missing','case':'missing.json'})
        self.save(); out=self.root/'report.json'
        r=self.run_cli('suite',self.manifest,'--json',out)
        self.assertEqual(r.returncode,2)
        self.assertTrue(out.is_file(),'An invalid item must not discard the whole suite report')
        self.assertEqual(json.loads(out.read_text())['cases'][1]['execution'],'error')

    def test_demo_generates_three_suite_outcomes(self):
        target=self.root/'demo'
        self.assertEqual(self.run_cli('demo','--out',target).returncode,0)
        for name,code in [('suite-clean.json',0),('suite-different.json',1),('suite-inconclusive.json',2)]:
            r=self.run_cli('suite',target/name)
            self.assertEqual(r.returncode,code,r.stderr)


if __name__=='__main__':
    unittest.main()
