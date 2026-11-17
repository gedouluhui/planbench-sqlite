import copy
import unittest

try:
    from planbench_sqlite.report import render_html
except ImportError:
    render_html = None


def example_report():
    arm = {'status': 'complete', 'sql': 'SELECT x FROM t', 'index_definitions': [],
           'plan': [{'id': 2, 'parent': 0, 'auxiliary': 0, 'detail': 'SCAN t'}],
           'columns': ['x'], 'row_count': 3, 'result_bytes': 30, 'result_sha256': 'abcd',
           'progress_calls': 23, 'elapsed_seconds': 0.002, 'error': None}
    return {'schema_version': 1, 'title': 'Renderer fixture (not benchmark data)', 'status': 'equivalent',
            'comparison': 'multiset', 'environment': {'python': '3.12', 'sqlite': '3.49'},
            'source': {'database': 'demo.sqlite', 'snapshot_bytes': 4096}, 'limits': {'max_rows': 100},
            'baseline': copy.deepcopy(arm), 'candidate': copy.deepcopy(arm),
            'equality': {'comparable': True, 'equivalent': True, 'schema_equal': True, 'reason': 'Schemas and rows match', 'progress_ratio': 1.0},
            'notes': ['Snapshot-only evidence']}


class ReportTests(unittest.TestCase):
    def render(self, report=None):
        self.assertTrue(callable(render_html), 'render_html must be implemented')
        return render_html(report or example_report())

    def test_portable_accessible_report(self):
        html = self.render()
        for text in ['<!doctype html>', 'lang="en"', 'Baseline', 'Candidate', 'SCAN t', 'Progress callbacks', 'viewport', '@media', 'focus-visible']:
            self.assertIn(text, html)
        self.assertNotIn('<script', html.lower())
        self.assertNotIn('src="http', html)
        self.assertNotIn('url(https:', html)

    def test_every_user_field_is_escaped(self):
        r = example_report()
        poison = '</pre><script>alert(1)</script><img src=x onerror=alert(2)>'
        r['title'] = poison
        r['baseline']['sql'] = poison
        r['candidate']['plan'][0]['detail'] = poison
        r['candidate']['index_definitions'] = [poison]
        r['notes'] = [poison]
        r['environment']['sqlite'] = poison
        html = self.render(r)
        self.assertNotIn(poison, html)
        self.assertIn('&lt;script&gt;', html)

    def test_incomplete_report_never_claims_equivalence(self):
        r = example_report()
        r['baseline']['status'] = 'limit'
        r['baseline']['error'] = 'Row budget exceeded'
        html = self.render(r)
        self.assertIn('Comparison not established', html)
        self.assertNotIn('Same rows. Different route.', html)
        self.assertIn('Row budget exceeded', html)

    def test_different_report(self):
        r = example_report()
        r['status'] = 'different'
        r['equality']['equivalent'] = False
        html = self.render(r)
        self.assertIn('The results differ.', html)
        self.assertIn('Not a speedup', html)

    def test_empty_plan_cycle_and_none_do_not_hang(self):
        r = example_report()
        r['baseline']['plan'] = []
        r['candidate']['plan'] = [{'id': 1, 'parent': 2, 'auxiliary': 0, 'detail': 'A'},
                                 {'id': 2, 'parent': 1, 'auxiliary': 0, 'detail': 'B'}]
        r['candidate']['result_sha256'] = None
        html = self.render(r)
        self.assertIn('No plan captured', html)
        self.assertIn('Not available', html)


if __name__ == '__main__':
    unittest.main()
