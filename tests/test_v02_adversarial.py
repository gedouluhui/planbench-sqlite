from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from planbench_sqlite.engine import run_experiment
from planbench_sqlite.suite import load_suite, run_suite
from planbench_sqlite.suite_report import render_suite_html


class AdversarialV02Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'data.sqlite'
        with closing(sqlite3.connect(self.db)) as c,c:
            c.execute('CREATE TABLE t(x)')

    def test_wide_same_name_columns_count_by_position(self):
        a='SELECT '+','.join('1 AS x' for _ in range(12))
        b='SELECT '+','.join('2.0 AS x' for _ in range(12))
        r=run_experiment({'schema_version':1,'database':str(self.db),'comparison':'ordered','baseline':{'sql':a},'candidate':{'sql':b}})
        d=r['difference'];first=d['first_mismatch']
        self.assertEqual(d['schema_change_count'],0)
        self.assertEqual(first['column_change_count'],12)
        self.assertEqual([col['column_index'] for col in first['columns']],list(range(10)))
        self.assertTrue(d['examples_truncated'])
        self.assertEqual(d['missing_examples'][0]['column_count'],12)
        self.assertTrue(d['missing_examples'][0]['columns_truncated'])

    def test_suite_html_escapes_real_generated_fields(self):
        marker='<script>window.bad=1</script>'
        case={'schema_version':1,'title':marker,'database':'data.sqlite','baseline':{'sql':"SELECT 1 AS '<img onerror=x>'"},'candidate':{'sql':"SELECT 2 AS '<img onerror=x>'"}}
        (self.root/'a.json').write_text(json.dumps(case),encoding='utf-8')
        manifest={'suite_version':1,'title':marker,'cases':[{'id':'check','case':'a.json'}]}
        p=self.root/'suite.json';p.write_text(json.dumps(manifest),encoding='utf-8')
        r=run_suite(load_suite(p));html=render_suite_html(r)
        self.assertEqual(r['status'],'different')
        self.assertNotIn('<script>',html)
        self.assertNotIn('<img onerror',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertIn('Missing from candidate',html)

    def test_large_case_is_a_preflight_error_not_a_partial_suite(self):
        (self.root/'a.json').write_bytes(b' '*2_000_001)
        p=self.root/'suite.json';p.write_text(json.dumps({'suite_version':1,'cases':[{'id':'huge','case':'a.json'}]}))
        with self.assertRaises(ValueError):load_suite(p)

    def test_schema_changes_truncate_without_losing_total(self):
        a='SELECT '+','.join(f'{i} AS a{i}' for i in range(14))+' WHERE 0'
        b='SELECT '+','.join(f'{i} AS b{i}' for i in range(14))+' WHERE 0'
        r=run_experiment({'schema_version':1,'database':str(self.db),'baseline':{'sql':a},'candidate':{'sql':b}})
        self.assertEqual(r['status'],'different')
        self.assertEqual(r['difference']['schema_change_count'],14)
        self.assertEqual(len(r['difference']['schema_changes']),10)
        self.assertEqual(r['difference']['missing_rows'],0)
        self.assertTrue(r['difference']['examples_truncated'])


if __name__=='__main__':unittest.main()
