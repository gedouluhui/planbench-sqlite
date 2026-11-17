"""Deterministic, self-generated data: no downloads, secrets or private inputs."""

from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3


def create_demo(directory: Path) -> Path:
    """Create a new directory with three runnable cases; refuse existing paths."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    with closing(sqlite3.connect(directory / 'shop.sqlite')) as con, con:
        con.execute('CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, total_cents INTEGER NOT NULL, status TEXT NOT NULL)')
        con.executemany('INSERT INTO orders VALUES (?,?,?,?)', ((i, (i * 37) % 997, 100 + (i * 19) % 40000, 'shipped' if i % 5 else 'pending') for i in range(20000)))
    sql = 'SELECT id, total_cents FROM orders WHERE customer_id = ? ORDER BY id'
    case = {'schema_version': 1, 'title': 'Customer lookup / one index, same rows', 'database': 'shop.sqlite',
            'baseline': {'sql': sql, 'parameters': [17]},
            'candidate': {'sql': sql, 'parameters': [17], 'indexes': [{'name': 'orders_customer', 'table': 'orders', 'columns': ['customer_id']}]},
            'comparison': 'ordered'}
    different = deepcopy(case)
    different['title'] = 'A changed predicate is not an optimization'
    different['candidate']['parameters'] = [18]
    limited = deepcopy(case)
    limited['title'] = 'A partial result cannot establish equivalence'
    limited['limits'] = {'max_rows': 1}
    for name, value in [('case.json', case), ('different.json', different), ('limited.json', limited)]:
        with (directory / name).open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write('\n')
    return directory / 'case.json'
