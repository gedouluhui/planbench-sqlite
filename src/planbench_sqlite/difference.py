"""Bounded location/type evidence. Raw values and per-row hashes never escape."""
from collections import Counter
from itertools import zip_longest
import struct

EXAMPLES_LIMIT = 10
_TYPES = {b'N': 'NULL', b'I': 'INTEGER', b'R': 'REAL', b'T': 'TEXT', b'B': 'BLOB'}


def _cells(row):
    if row is None:
        return
    view = memoryview(row)
    offset = 0
    while offset < len(row):
        length = struct.unpack_from('>Q', view, offset + 1)[0]
        end = offset + 9 + length
        yield _TYPES[row[offset:offset + 1]], view[offset:end]
        offset = end


def _types(row):
    types = []
    count = 0
    for name, cell in _cells(row):
        count += 1
        if len(types) < EXAMPLES_LIMIT:
            types.append(name)
    return types, count


def _counts(rows, check):
    counts, first = Counter(), {}
    for index, row in enumerate(rows):
        check()
        counts[row] += 1
        first.setdefault(row, index)
    return counts, first


def describe_difference(left, right, left_columns, right_columns, mode, check):
    """Describe exact bag differences and first sequence mismatch, not edit distance.

    Rows must be internal encode_row() bytes; indices reference original arm
    output order, not sorted order or database keys. Caller owns the deadline.
    """
    a, first_a = _counts(left, check)
    b, first_b = _counts(right, check)
    matched = sum(min(count, b.get(row, 0)) for row, count in a.items())
    result = {'mode': mode, 'baseline_rows': len(left), 'candidate_rows': len(right),
              'matched_rows': matched, 'missing_rows': len(left)-matched, 'extra_rows': len(right)-matched,
              'schema_changes': [], 'schema_change_count': 0, 'missing_examples': [], 'extra_examples': [],
              'first_mismatch': None, 'examples_limit': EXAMPLES_LIMIT, 'examples_truncated': False}
    for index, (x, y) in enumerate(zip_longest(left_columns, right_columns)):
        check()
        if x != y:
            result['schema_change_count'] += 1
            if len(result['schema_changes']) < EXAMPLES_LIMIT:
                result['schema_changes'].append({'column_index': index, 'baseline_name': x, 'candidate_name': y})
            else:
                result['examples_truncated'] = True
    for key, own, other, first in [('missing_examples', a, b, first_a), ('extra_examples', b, a, first_b)]:
        for row, count in own.items():
            check()
            excess = count - other.get(row, 0)
            if excess <= 0:
                continue
            if len(result[key]) >= EXAMPLES_LIMIT:
                result['examples_truncated'] = True
                continue
            names, columns = _types(row)
            result[key].append({'row_index': first[row], 'count': excess, 'column_types': names,
                                'column_count': columns, 'columns_truncated': columns > EXAMPLES_LIMIT})
            if columns > EXAMPLES_LIMIT:
                result['examples_truncated'] = True
    if mode == 'ordered':
        for index, (x, y) in enumerate(zip_longest(left, right)):
            check()
            if x == y:
                continue
            columns, total = [], 0
            for col, (u, v) in enumerate(zip_longest(_cells(x), _cells(y))):
                check()
                if u is not None and v is not None and u[1] == v[1]:
                    continue
                total += 1
                if len(columns) < EXAMPLES_LIMIT:
                    columns.append({'column_index': col, 'baseline_type': u[0] if u else 'ABSENT',
                                    'candidate_type': v[0] if v else 'ABSENT'})
            result['first_mismatch'] = {'row_index': index, 'columns': columns, 'column_change_count': total}
            result['examples_truncated'] |= total > EXAMPLES_LIMIT
            break
    check()
    return result
