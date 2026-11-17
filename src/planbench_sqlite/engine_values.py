"""Type-preserving row encoding and exact in-memory result comparison."""

from collections import Counter
import hashlib
import math
import struct


def encode_row(row):
    parts = []
    for value in row:
        if value is None:
            tag, payload = b'N', b''
        elif type(value) is int:
            tag, payload = b'I', str(value).encode('ascii')
        elif type(value) is float:
            if not math.isfinite(value):
                raise ValueError('Nonfinite REAL results are unsupported')
            tag, payload = b'R', value.hex().encode('ascii')
        elif type(value) is str:
            tag, payload = b'T', value.encode('utf-8')
        elif type(value) is bytes:
            tag, payload = b'B', value
        else:
            raise ValueError('Unsupported SQLite result type')
        parts.extend((tag, struct.pack('>Q', len(payload)), payload))
    return b''.join(parts)


def results_equal(left, right, mode):
    if mode == 'ordered':
        return left == right
    return Counter(left) == Counter(right)


def result_digest(rows, mode, check=None):
    """Diagnostic only. Equality is never inferred from this digest."""
    digest = hashlib.sha256()
    ordered = rows if mode == 'ordered' else sorted(rows)
    for row in ordered:
        if check is not None:
            check()
        digest.update(struct.pack('>Q', len(row)))
        digest.update(row)
    if check is not None:
        check()
    return digest.hexdigest()
