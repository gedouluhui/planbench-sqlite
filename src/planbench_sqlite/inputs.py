"""Bounded strict JSON loading shared by single cases and suites."""
import json
from pathlib import Path

from .engine_config import validate_config


class InputError(ValueError):
    pass


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError('Duplicate JSON object key')
        result[key] = value
    return result


def _constant(value):
    raise InputError('Nonfinite JSON constants are not supported')


class InputBudgetError(InputError):
    pass


def read_json(path, max_bytes=2_000_000, account_bytes=None):
    """Bound actual bytes read, not only a potentially stale stat size."""
    with Path(path).open('rb') as stream:
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise InputBudgetError('JSON input exceeds byte budget')
    if account_bytes is not None:
        account_bytes(len(data))
    return json.loads(data.decode('utf-8'), object_pairs_hook=_object, parse_constant=_constant)


def load_case(path):
    value = read_json(path)
    validate_config(value)
    return value
