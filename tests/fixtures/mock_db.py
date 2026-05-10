"""
Mock DB connection and cursor for unit testing connectors without a live database.

Usage
-----
    from tests.fixtures.mock_db import MockConnection, MockCursor

    def test_wal_level_fail(monkeypatch):
        mock_conn = MockConnection(query_map={"SHOW wal_level": [("replica",)]})

        monkeypatch.setattr(psycopg2, "connect", lambda **_: mock_conn)

        connector = PostgresConnector(config)
        connector._conn = mock_conn
        results = connector.check_cdc()

        assert any(r.name == "wal_level" and r.status == Status.FAIL for r in results)
"""
from __future__ import annotations

from typing import Any


class MockCursor:
    def __init__(self, query_map: dict[str, list[tuple]]) -> None:
        self._query_map = query_map
        self._results: list[tuple] = []

    def execute(self, query: str, params: Any = None) -> None:
        key = query.strip()
        self._results = self._query_map.get(key, [(None,)])

    def fetchone(self) -> tuple | None:
        return self._results[0] if self._results else None

    def fetchall(self) -> list[tuple]:
        return self._results

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def close(self):
        pass


class MockConnection:
    """
    Minimal mock for both psycopg2 and mysql.connector connections.

    Parameters
    ----------
    query_map:
        Maps query strings (stripped) to a list of row tuples that fetchall/fetchone returns.

    Example
    -------
        MockConnection(query_map={
            "SHOW wal_level": [("logical",)],
            "SELECT rolreplication, rolsuper FROM pg_roles WHERE rolname = current_user": [(True, False)],
        })
    """

    def __init__(self, query_map: dict[str, list[tuple]] | None = None) -> None:
        self._query_map = query_map or {}

    def cursor(self):
        return MockCursor(self._query_map)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass
