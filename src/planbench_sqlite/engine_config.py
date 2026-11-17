"""Strict input validation. No database or filesystem side effects."""

import math

DEFAULT_LIMITS = {
    'max_rows': 100_000,
    'max_result_bytes': 33_554_432,
    'max_progress_calls': 2_000_000,
    'timeout_seconds': 5.0,
    'max_database_bytes': 67_108_864,
}
MAX_LIMITS = {
    'max_rows': 1_000_000,
    'max_result_bytes': 268_435_456,
    'max_progress_calls': 50_000_000,
    'timeout_seconds': 120.0,
    'max_database_bytes': 268_435_456,
}


def _object(value, allowed, label):
    if type(value) is not dict or any(type(k) is not str for k in value):
        raise ValueError(f'{label} must be an object')
    if set(value) - set(allowed):
        raise ValueError(f'{label} contains unsupported keys')


def _text(value, label, maximum):
    if not isinstance(value, str) or not value.strip() or '\x00' in value or len(value) > maximum:
        raise ValueError(f'{label} must be nonempty text without NUL (max {maximum} characters)')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise ValueError(f'{label} must be valid UTF-8 text') from None
    return value


def validate_config(config):
    """Return a normalized, independent config or raise ValueError."""
    _object(config, {'schema_version', 'title', 'database', 'baseline', 'candidate', 'comparison', 'limits'}, 'case')
    if type(config.get('schema_version')) is not int or config['schema_version'] != 1:
        raise ValueError('schema_version must be integer 1')
    database = _text(config.get('database'), 'database', 32768)
    title = _text(config.get('title', 'SQLite query experiment'), 'title', 256)
    mode = config.get('comparison', 'multiset')
    if mode not in ('multiset', 'ordered'):
        raise ValueError('comparison must be multiset or ordered')
    limits = dict(DEFAULT_LIMITS)
    supplied = config.get('limits', {})
    _object(supplied, limits, 'limits')
    for key, value in supplied.items():
        valid_type = type(value) in (int, float) if key == 'timeout_seconds' else type(value) is int
        minimum = 0.001 if key == 'timeout_seconds' else 1
        if not valid_type or not minimum <= value <= MAX_LIMITS[key] or (type(value) is float and not math.isfinite(value)):
            raise ValueError(f'{key} must be in [{minimum}, {MAX_LIMITS[key]}] with the required numeric type')
        limits[key] = value
    result = {'schema_version': 1, 'title': title, 'database': database, 'comparison': mode, 'limits': limits}
    for label in ('baseline', 'candidate'):
        arm = config.get(label)
        _object(arm, {'sql', 'parameters', 'indexes'} if label == 'candidate' else {'sql', 'parameters'}, label)
        sql = _text(arm.get('sql'), label + '.sql', 100000)
        parameters = arm.get('parameters', [])
        if type(parameters) is not list or len(parameters) > 1000:
            raise ValueError(f'{label}.parameters must be a list of at most 1000 scalar values')
        for value in parameters:
            if value is None or type(value) is bool:
                continue
            if type(value) is int and -(2 ** 63) <= value < 2 ** 63:
                continue
            if type(value) is float and math.isfinite(value):
                continue
            if type(value) is str and len(value) <= 1_000_000:
                try:
                    value.encode('utf-8')
                    continue
                except UnicodeError:
                    pass
            raise ValueError(f'{label}.parameters contains an unsupported value')
        indexes = arm.get('indexes', [])
        if type(indexes) is not list or len(indexes) > 32:
            raise ValueError('indexes must be a list of at most 32 definitions')
        normalized_indexes = []
        for index in indexes:
            _object(index, {'name', 'table', 'columns'}, 'index')
            name = _text(index.get('name'), 'index.name', 128)
            table = _text(index.get('table'), 'index.table', 128)
            columns = index.get('columns')
            if type(columns) is not list or not 1 <= len(columns) <= 32:
                raise ValueError('index.columns must list 1 to 32 ordinary columns')
            columns = [_text(col, 'index column', 128) for col in columns]
            normalized_indexes.append({'name': name, 'table': table, 'columns': columns})
        result[label] = {'sql': sql, 'parameters': list(parameters), 'indexes': normalized_indexes}
    return result
