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

    def test_difference_evidence_and_tiny_positive_time_are_visible(self):
        r = example_report()
        r['status'] = 'different'
        r['equality']['equivalent'] = False
        r['baseline']['elapsed_seconds'] = 0.000002
        r['difference'] = {'matched_rows': 2, 'missing_rows': 1, 'extra_rows': 0, 'schema_change_count': 0,
            'schema_changes': [], 'examples_limit': 10, 'examples_truncated': True, 'first_mismatch': None,
            'missing_examples': [{'row_index': 5, 'count': 1, 'column_types': ['INTEGER'], 'column_count': 1, 'columns_truncated': False}], 'extra_examples': []}
        html = self.render(r)
        self.assertIn('Difference evidence', html)
        self.assertIn('row 5', html)
        self.assertIn('INTEGER', html)
        self.assertIn('Examples are truncated', html)
        self.assertIn('&lt;0.0001', html)

    def test_inconsistent_equality_cannot_display_completed_difference_evidence(self):
        r = example_report()
        r['difference'] = {'matched_rows': 3}
        r['equality'].update(comparable=False, equivalent=None)
        html = self.render(r)
        self.assertIn('Comparison not established.', html)
        self.assertNotIn('No schema or required row differences in this completed comparison.', html)

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
