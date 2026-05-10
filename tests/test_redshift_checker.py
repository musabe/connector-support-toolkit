"""
Tests for RedshiftConnector — connectivity, permissions, CDC, JDBC.
No live Redshift cluster required — psycopg2 calls are mocked.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from connector_toolkit.checks.redshift import RedshiftConnector
from connector_toolkit.models import RunConfig, Status


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def config():
    return RunConfig(
        host="my-cluster.us-east-1.redshift.amazonaws.com",
        port=5439,
        db="dev",
        user="admin",
        password="secret",
        db_type="redshift",
    )


@pytest.fixture
def checker(config):
    return RedshiftConnector(config)


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


def _attach(checker, cur):
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    checker._conn = conn


# ── Connectivity ──────────────────────────────────────────────────────────────

class TestConnectivity:
    @patch("connector_toolkit.checks.redshift.psycopg2.connect")
    @patch("connector_toolkit.checks.redshift.socket.create_connection")
    def test_all_pass_on_healthy_connection(self, mock_sock, mock_connect, checker):
        mock_sock.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_sock.return_value.__exit__ = MagicMock(return_value=False)
        conn, cur = _mock_conn()
        mock_connect.return_value = conn
        cur.fetchone.side_effect = [
            (True,),                     # ssl_is_used()
            ("PostgreSQL 8.0.2 Redshift 1.0.50033",),  # version()
        ]
        results = checker.check_connectivity()
        assert all(r.status != Status.FAIL for r in results)
        assert any("TCP" in r.name for r in results)

    @patch("connector_toolkit.checks.redshift.socket.create_connection")
    def test_tcp_fail_stops_early(self, mock_sock, checker):
        mock_sock.side_effect = ConnectionRefusedError("refused")
        results = checker.check_connectivity()
        assert results[0].status == Status.FAIL
        assert "TCP" in results[0].name
        assert len(results) == 1

    @patch("connector_toolkit.checks.redshift.psycopg2.connect")
    @patch("connector_toolkit.checks.redshift.socket.create_connection")
    def test_auth_fail(self, mock_sock, mock_connect, checker):
        mock_sock.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_sock.return_value.__exit__ = MagicMock(return_value=False)
        import psycopg2
        mock_connect.side_effect = psycopg2.OperationalError("password authentication failed")
        results = checker.check_connectivity()
        auth = next(r for r in results if "connect" in r.name.lower())
        assert auth.status == Status.FAIL
        assert auth.remediation is not None

    @patch("connector_toolkit.checks.redshift.psycopg2.connect")
    @patch("connector_toolkit.checks.redshift.socket.create_connection")
    def test_ssl_failure_is_warn(self, mock_sock, mock_connect, checker):
        mock_sock.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_sock.return_value.__exit__ = MagicMock(return_value=False)
        conn, cur = _mock_conn()
        mock_connect.return_value = conn
        cur.fetchone.side_effect = Exception("ssl_is_used not available")
        results = checker.check_connectivity()
        ssl = next(r for r in results if "SSL" in r.name)
        assert ssl.status == Status.WARN
        assert ssl.remediation is not None


# ── Permissions ───────────────────────────────────────────────────────────────

class TestPermissions:
    def test_replication_privilege_pass(self, checker):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (True, False, True),  # usecreatedb, usesuper, usereplication
            (True,),              # has_database_privilege
            (True,),              # has_schema_privilege
        ]
        _attach(checker, cur)
        results = checker.check_permissions()
        repl = next(r for r in results if "Replication" in r.name)
        assert repl.status == Status.PASS

    def test_replication_privilege_fail(self, checker):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (False, False, False),  # no replication
            (True,),
            (True,),
        ]
        _attach(checker, cur)
        results = checker.check_permissions()
        repl = next(r for r in results if "Replication" in r.name)
        assert repl.status == Status.FAIL
        assert repl.remediation is not None

    def test_not_superuser_warns(self, checker):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (False, False, True),  # not superuser
            (True,),
            (True,),
        ]
        _attach(checker, cur)
        results = checker.check_permissions()
        su = next(r for r in results if "Superuser" in r.name)
        assert su.status == Status.WARN
        assert su.remediation is not None

    def test_schema_access_fail(self, checker):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (False, True, True),  # has replication + superuser
            (True,),              # has database CONNECT
            (False,),             # no schema USAGE
        ]
        _attach(checker, cur)
        results = checker.check_permissions()
        schema = next(r for r in results if "Schema" in r.name)
        assert schema.status == Status.FAIL
        assert schema.remediation is not None


# ── CDC ───────────────────────────────────────────────────────────────────────

class TestCDC:
    def test_logical_replication_pass(self, checker):
        cur = MagicMock()
        cur.fetchall.return_value = [
            ("wal_level", "logical"),
            ("enable_logical_replication", "on"),
        ]
        cur.fetchone.side_effect = [
            (0,),     # replication slots count
            ("60s",), # wal_sender_timeout
        ]
        _attach(checker, cur)
        results = checker.check_cdc()
        logical = next(r for r in results if "Logical" in r.name)
        assert logical.status == Status.PASS

    def test_logical_replication_fail(self, checker):
        cur = MagicMock()
        cur.fetchall.return_value = [
            ("wal_level", "minimal"),
            ("enable_logical_replication", "off"),
        ]
        cur.fetchone.side_effect = [
            (0,),
            ("60s",),
        ]
        _attach(checker, cur)
        results = checker.check_cdc()
        logical = next(r for r in results if "Logical" in r.name)
        assert logical.status == Status.FAIL
        assert logical.remediation is not None
        assert "enable_logical_replication" in logical.remediation

    def test_wal_sender_timeout_zero_warns(self, checker):
        cur = MagicMock()
        cur.fetchall.return_value = [("wal_level", "logical")]
        cur.fetchone.side_effect = [
            (0,),
            ("0",),  # disabled
        ]
        _attach(checker, cur)
        results = checker.check_cdc()
        wst = next(r for r in results if "wal_sender_timeout" in r.name)
        assert wst.status == Status.WARN
        assert wst.remediation is not None


# ── JDBC ──────────────────────────────────────────────────────────────────────

class TestJDBC:
    def test_psycopg2_pass_when_installed(self, checker):
        results = checker.check_jdbc()
        psycopg2_result = next(r for r in results if "psycopg2" in r.name)
        assert psycopg2_result.status == Status.PASS

    def test_redshift_connector_warn_when_missing(self, checker):
        with patch.dict("sys.modules", {"redshift_connector": None}):
            results = checker.check_jdbc()
        rc = next(r for r in results if "redshift-connector" in r.name)
        assert rc.status == Status.WARN
        assert rc.remediation is not None

    def test_all_results_have_valid_status(self, checker):
        results = checker.check_jdbc()
        assert all(r.status in (Status.PASS, Status.WARN, Status.FAIL) for r in results)
