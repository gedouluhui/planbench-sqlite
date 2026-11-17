"""Falsify key assertions in disposable copies. Never mutate the checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ('discard_duplicates', 'engine_values.py', 'return Counter(left) == Counter(right)', 'return set(left) == set(right)', 'test_engine.py', 'test_multiplicity_is_not_set_equality'),
    ('force_equivalence', 'engine.py', "equal = schema_equal and results_equal(rows['baseline'], rows['candidate'], config['comparison'])", 'equal = True', 'test_engine.py', 'test_changed_predicate_is_different'),
    ('disable_authorizer', 'engine.py', 'def authorize(action, arg1, arg2, database, trigger):', 'def authorize(action, arg1, arg2, database, trigger):\n        return sqlite3.SQLITE_OK', 'test_engine.py', 'test_write_attach_pragma_and_unsafe_functions_blocked'),
    ('ignore_row_limit', 'engine.py', "if len(encoded) >= limits['max_rows']:", 'if False:', 'test_engine.py', 'test_row_budget_is_inconclusive_not_equal_partial'),
    ('miscount_missing_rows', 'difference.py', "'missing_rows': len(left)-matched", "'missing_rows': len(left)-matched+1", 'test_difference.py', 'test_duplicate_excess_counts_and_first_source_index'),
    ('green_incomplete_suite', 'suite.py', "        return 'inconclusive'\n    if any(item['status'] == 'different'", "        return 'equivalent'\n    if any(item['status'] == 'different'", 'test_suite.py', 'test_aggregate_priorities_invariant_under_permutation'),
    ('omit_manifest_bytes', 'suite.py', 'value = read_json(path, account_bytes=account_bytes)', 'value = read_json(path)', 'test_suite.py', 'test_cumulative_budget_includes_manifest_exact_boundary'),
]


def caught_by_assertion(rc, output, name):
    return (rc == 1 and ('FAIL: ' + name + ' ') in output and 'AssertionError' in output
            and 'FAILED (failures=' in output and '\nERROR:' not in output and 'errors=' not in output)


def run_test(work, filename, name):
    env = dict(os.environ, PYTHONPATH=str(work / 'src'), PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    r = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(work / 'tests'), '-p', filename, '-k', name, '-v'],
                       cwd=work, env=env, capture_output=True, text=True, encoding='utf-8', timeout=60)
    return r.returncode, r.stdout + r.stderr


def verify_case(work, case):
    label, filename, old, new, testfile, name = case
    shutil.copytree(ROOT / 'src/planbench_sqlite', work / 'src/planbench_sqlite', ignore=shutil.ignore_patterns('__pycache__'))
    (work / 'tests').mkdir()
    shutil.copyfile(ROOT / 'tests' / testfile, work / 'tests' / testfile)
    rc, output = run_test(work, testfile, name)
    if rc != 0 or '\nOK' not in output or 'Ran 0 tests' in output or 'skipped=' in output:
        raise ValueError(label + ': clean control did not pass\n' + output)
    target = work / 'src/planbench_sqlite' / filename
    before = target.read_text(encoding='utf-8')
    if before.count(old) != 1:
        raise ValueError(label + ': mutation anchor is not unique')
    after = before.replace(old, new, 1)
    if after == before:
        raise ValueError(label + ': NOP mutation rejected')
    with target.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(after)
    rc, output = run_test(work, testfile, name)
    caught = caught_by_assertion(rc, output, name)
    return {'mutation': label, 'test': name, 'control_passed': True, 'caught_by_named_assertion': caught}


def source_hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'src/planbench_sqlite').glob('*.py')}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path, help='Optional new receipt file; existing files are refused')
    args=parser.parse_args(argv)
    if args.json and args.json.exists():
        parser.error('Receipt already exists; use a new path')
    before=source_hashes()
    results=[]
    with tempfile.TemporaryDirectory(prefix='planbench-mutation-') as folder:
        root=Path(folder)
        for case in CASES:
            row=verify_case(root/case[0],case)
            results.append(row)
            print(row['mutation']+': '+('CAUGHT' if row['caught_by_named_assertion'] else 'MISSED'),flush=True)
        # The verifier must distinguish an unchanged file from a surviving bug.
        base=CASES[0]
        nop=(base[0]+'-nop',base[1],base[2],base[2],base[4],base[5])
        try:
            verify_case(root/'nop-control',nop)
        except ValueError as exc:
            if 'NOP mutation rejected' not in str(exc):
                raise
        else:
            raise ValueError('Verifier accepted a NOP mutation')
    unchanged=before==source_hashes()
    receipt={'source_sha256':before,'controls':results,'nop_rejected':True,'real_source_unchanged':unchanged,
             'all_caught':unchanged and all(r['caught_by_named_assertion'] for r in results)}
    if args.json:
        with args.json.open('x',encoding='utf-8',newline='\n') as stream:
            json.dump(receipt,stream,indent=2);stream.write('\n')
    print('Named assertions caught:',sum(r['caught_by_named_assertion'] for r in results),'/',len(results),'; real source unchanged:',unchanged)
    return 0 if receipt['all_caught'] else 1


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print('Mutation verification failed: '+str(exc),file=sys.stderr)
        raise SystemExit(2)
