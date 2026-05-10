"""Unit tests for PostgresConnector — no live database required."""
from __future__ import annotations

import pytest

from connector_toolkit.checks.postgres import PostgresConnector
from connector_toolkit.models import Category, RunConfig, Status
from tests.fixtures.mock_db import MockConnection


@pytest.fixture
def config():
    return RunConfig(
        host="localhost", port=5432, db="test",
        user="demo", password="demo", db_type="postgres",
    )


@pytest.fixture
def connector(config):
    c = PostgresConnector(config)
    return c


def _with_conn(connector, query_map):
    connector._conn = MockConnection(query_map)
    return connector


# ------------------------------------------------------------------
# Permissions
# ------------------------------------------------------------------

class TestPermissions:
    def test_replication_privilege_pass(self, connector):
        _with_conn(connector, {
            "SELECT rolreplication, rolsuper FROM pg_roles WHERE rolname = current_user": [(True, False)],
            "SELECT has_database_privilege(current_user, current_database(), 'CONNECT')": [(True,)],
        })
        results = connector.check_permissions()
        repl = next(r for r in results if r.name == "Replication privilege")
        assert repl.status == Status.PASS

    def test_replication_privilege_fail(self, connector):
        _with_conn(connector, {
            "SELECT rolreplication, rolsuper FROM pg_roles WHERE rolname = current_user": [(False, False)],
            "SELECT has_database_privilege(current_user, current_database(), 'CONNECT')": [(True,)],
        })
        results = connector.check_permissions()
        repl = next(r for r in results if r.name == "Replication privilege")
        assert repl.status == Status.FAIL
        assert repl.remediation is not None

    def test_superuser_warn_when_false(self, connector):
        _with_conn(connector, {
            "SELECT rolreplication, rolsuper FROM pg_roles WHERE rolname = current_user": [(True, False)],
            "SELECT has_database_privilege(current_user, current_database(), 'CONNECT')": [(True,)],
        })
        results = connector.check_permissions()
        su = next(r for r in results if r.name == "Superuser status")
        assert su.status == Status.WARN


# ------------------------------------------------------------------
# CDC
# ------------------------------------------------------------------

class TestCDC:
    def test_wal_level_logical_passes(self, connector):
        _with_conn(connector, {
            "SHOW wal_level": [("logical",)],
            "SELECT count(*) FROM pg_replication_slots": [(0,)],
            "SHOW wal_sender_timeout": [("60s",)],
        })
        results = connector.check_cdc()
        wal = next(r for r in results if r.name == "wal_level")
        assert wal.status == Status.PASS

    def test_wal_level_replica_fails(self, connector):
        _with_conn(connector, {
            "SHOW wal_level": [("replica",)],
            "SELECT count(*) FROM pg_replication_slots": [(0,)],
            "SHOW wal_sender_timeout": [("60s",)],
        })
        results = connector.check_cdc()
        wal = next(r for r in results if r.name == "wal_level")
        assert wal.status == Status.FAIL
        assert "ALTER SYSTEM" in wal.remediation
