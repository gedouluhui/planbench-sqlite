import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'mutation_check.py'


class MutationToolTests(unittest.TestCase):
    def test_assertion_classifier_rejects_crashes_and_wrong_tests(self):
        self.assertTrue(SCRIPT.is_file(), 'The reproducible mutation tool must ship with the source')
        spec=importlib.util.spec_from_file_location('mutation_check',SCRIPT)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        valid='FAIL: test_target (Tests.test_target)\nAssertionError: broken\nFAILED (failures=1)'
        self.assertTrue(module.caught_by_assertion(1,valid,'test_target'))
        for rc,text in [(0,valid),(2,valid),(1,valid.replace('test_target','test_other')),(1,'ERROR: test_target\nImportError\nFAILED (errors=1)'),(1,'Traceback: encoding error')]:
            self.assertFalse(module.caught_by_assertion(rc,text,'test_target'))


if __name__=='__main__':
    unittest.main()
