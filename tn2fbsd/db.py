"""Thin helpers around the TrueNAS SQLite configuration database.

The database uses SQLAlchemy-generated tables. Booleans are stored as integers
(0/1), several TEXT columns hold JSON, and a few hold space-separated strings.
These helpers keep the generators free of sqlite boilerplate.
"""
import json
import sqlite3


class DB:
    def __init__(self, path):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row

    def all(self, table, where="", order=""):
        """Return every row of a table as a list of dicts."""
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        if order:
            sql += f" ORDER BY {order}"
        return [dict(r) for r in self._conn.execute(sql)]

    def one(self, table, where="", order=""):
        """Return the first matching row as a dict, or None."""
        rows = self.all(table, where, order)
        return rows[0] if rows else None

    def close(self):
        self._conn.close()


def as_bool(value):
    """TrueNAS stores booleans as integers."""
    return bool(value)


def json_list(value):
    """Decode a JSON-encoded list column, tolerating empty/NULL values."""
    if not value:
        return []
    return json.loads(value)


def words(value):
    """Split a space-separated string column into a list."""
    if not value:
        return []
    return value.split()
