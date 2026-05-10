"""
Tests for MySQLChecker — connectivity, permissions, CDC, JDBC.
Replaces the old test_mysql_checker.py (which imported from src.checkers.mysql).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from connector_toolkit.checks.mysql import MySQLConnector
from connector_toolkit.models import RunConfig, Status


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def config():
    return RunConfig(
        host="localhost", port=3306, db="testdb",
        user="user", password="pass", db_type="mysql",
    )


@pytest.fixture
def checker(config):
    return MySQLConnector(config)


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


# ── Connectivity ──────────────────────────────────────────────────────────────

class TestConnectivity:
    @patch("connector_toolkit.checks.mysql.mysql.connector.connect")
    @patch("connector_toolkit.checks.mysql.socket.create_connection")
    def test_all_pass_on_healthy_connection(self, mock_sock, mock_connect, checker):
        mock_sock.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_sock.return_value.__exit__ = MagicMock(return_value=False)
        conn, cur = _mock_conn()
        mock_connect.return_value = conn
        cur.fetchone.return_value = ("Ssl_cipher", "AES256-SHA")

        results = checker.check_connectivity()
        assert all(r.status != Status.FAIL for r in results)

    @patch("connector_toolkit.checks.mysql.socket.create_connection")
    def test_tcp_fail_returns_fail_and_stops(self, mock_sock, checker):
        mock_sock.side_effect = ConnectionRefusedError("Connection refused")
        results = checker.check_connectivity()
        assert results[0].status == Status.FAIL
        assert "TCP" in results[0].name
        assert len(results) == 1

    @patch("connector_toolkit.checks.mysql.mysql.connector.connect")
    @patch("connector_toolkit.checks.mysql.socket.create_connection")
    def test_auth_fail_returns_fail(self, mock_sock, mock_connect, checker):
        mock_sock.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_sock.return_value.__exit__ = MagicMock(return_value=False)
        import mysql.connector as mc
        mock_connect.side_effect = mc.Error("Access denied")
        results = checker.check_connectivity()
        auth = next(r for r in results if "connect" in r.name.lower())
        assert auth.status == Status.FAIL
        assert auth.remediation is not None


# ── Permissions ───────────────────────────────────────────────────────────────

class TestPermissions:
    def _connected_checker(self, checker, cur):
        conn = MagicMock()
        conn.cursor.return_value = cur
        checker._conn = conn

    def test_replication_privilege_pass(self, checker):
        cur = MagicMock()
        cur.fetchall.return_value = [
            ("GRANT ALL PRIVILEGES ON *.* TO 'user'@'localhost'",)
        ]
        self._connected_checker(checker, cur)
        results = checker.check_permissions()
        repl = next(r for r in results if "Replication" in r.name)
        assert repl.status == Status.PASS

    def test_replication_privilege_fail(self, checker):
        cur = MagicMock()
        cur.fetchall.return_value = [
            ("GRANT SELECT ON *.* TO 'user'@'localhost'",)
        ]
        self._connected_checker(checker, cur)
        results = checker.check_permissions()
        repl = next(r for r in results if "Replication" in r.name)
        assert repl.status == Status.FAIL
        assert repl.remediation is not None
        assert "REPLICATION SLAVE" in repl.remediation

    def test_read_access_fail(self, checker):
        cur = MagicMock()
        cur.fetchall.return_value = [
            ("GRANT REPLICATION SLAVE ON *.* TO 'user'@'localhost'",)
        ]
        self._connected_checker(checker, cur)
        results = checker.check_permissions()
        read = next(r for r in results if "read access" in r.name.lower())
        assert read.status == Status.FAIL
        assert read.remediation is not None


# ── CDC ───────────────────────────────────────────────────────────────────────

class TestCDC:
    def _connected_checker(self, checker, cur):
        conn = MagicMock()
        conn.cursor.return_value = cur
        checker._conn = conn

    def test_all_correct_settings_pass(self, checker):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("log_bin", "ON"),
            ("binlog_format", "ROW"),
            ("binlog_row_image", "FULL"),
            ("gtid_mode", "ON"),
        ]
        self._connected_checker(checker, cur)
        results = checker.check_cdc()
        log_bin = next(r for r in results if "log_bin" in r.name)
        assert log_bin.status == Status.PASS

    def test_log_bin_off_fails(self, checker):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("log_bin", "OFF"),
            ("binlog_format", "ROW"),
            ("binlog_row_image", "FULL"),
            ("gtid_mode", "ON"),
        ]
        self._connected_checker(checker, cur)
        results = checker.check_cdc()
        log_bin = next(r for r in results if "log_bin" in r.name)
        assert log_bin.status == Status.FAIL
        assert log_bin.remediation is not None
        assert "my.cnf" in log_bin.remediation

    def test_binlog_format_wrong_fails(self, checker):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("log_bin", "ON"),
            ("binlog_format", "STATEMENT"),
            ("binlog_row_image", "FULL"),
            ("gtid_mode", "ON"),
        ]
        self._connected_checker(checker, cur)
        results = checker.check_cdc()
        fmt = next(r for r in results if "binlog_format" in r.name)
        assert fmt.status == Status.FAIL
        assert fmt.remediation is not None

    def test_binlog_row_image_not_full_warns(self, checker):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("log_bin", "ON"),
            ("binlog_format", "ROW"),
            ("binlog_row_image", "MINIMAL"),
            ("gtid_mode", "ON"),
        ]
        self._connected_checker(checker, cur)
        results = checker.check_cdc()
        img = next(r for r in results if "binlog_row_image" in r.name)
        assert img.status == Status.WARN
        assert img.remediation is not None

    def test_gtid_mode_off_warns(self, checker):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("log_bin", "ON"),
            ("binlog_format", "ROW"),
            ("binlog_row_image", "FULL"),
            ("gtid_mode", "OFF"),
        ]
        self._connected_checker(checker, cur)
        results = checker.check_cdc()
        gtid = next(r for r in results if "gtid_mode" in r.name)
        assert gtid.status == Status.WARN
        assert gtid.remediation is not None


# ── JDBC ──────────────────────────────────────────────────────────────────────

class TestJDBC:
    def test_returns_at_least_one_result(self, checker):
        results = checker.check_jdbc()
        assert len(results) >= 1

    def test_result_has_driver_in_name(self, checker):
        results = checker.check_jdbc()
        assert any("Driver" in r.name for r in results)

    def test_status_is_valid(self, checker):
        results = checker.check_jdbc()
        assert all(r.status in (Status.PASS, Status.WARN, Status.FAIL) for r in results)
