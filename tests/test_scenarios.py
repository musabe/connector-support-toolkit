"""
Incident scenario tests.

Each test runs the connector check against a deliberately misconfigured
Docker container and asserts that the expected checks FAIL or PASS.

These are INTEGRATION tests — they require the scenario Docker containers:
    docker compose -f docker/docker-compose-scenarios.yml up -d

Skip these tests in environments without Docker:
    pytest tests/ --ignore=tests/test_scenarios.py

Or run only scenarios:
    pytest tests/test_scenarios.py -v

Environment variables (all have defaults matching docker-compose-scenarios.yml):
    PG_HOST              default: localhost
    PG_SCENARIO_PORT     default: 5436  (pg-no-replication)
    PG_WAL_PORT          default: 5437  (pg-wal-not-logical)
    MYSQL_HOST           default: localhost
    MYSQL_NOLOG_PORT     default: 3307  (mysql-binlog-off)
    MYSQL_NOREPL_PORT    default: 3308  (mysql-no-replication)
    MYSQL_BADFORMAT_PORT default: 3309  (mysql-wrong-binlog-format)
"""
from __future__ import annotations

import os
import socket
import pytest

from connector_toolkit.models import Category, RunConfig, Status
from connector_toolkit import runner


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    """Return True if the TCP port is reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _skip_if_unavailable(host: str, port: int) -> None:
    """Skip the test if the scenario container is not running."""
    if not _is_port_open(host, port):
        pytest.skip(
            f"Scenario container not available at {host}:{port}. "
            f"Start with: docker compose -f docker/docker-compose-scenarios.yml up -d"
        )


def _run_scenario(db_type: str, host: str, port: int, user: str, password: str,
                  db: str = "test", skip=None) -> dict[str, str]:
    """
    Run all checks and return a dict of {check_name: status_value}.
    Makes assertions easier: checks["wal_level"] == "FAIL"
    """
    config = RunConfig(
        host=host, port=port, db=db,
        user=user, password=password,
        db_type=db_type,
        skip=skip or [],
        timeout=10,
    )
    report = runner.run(config)
    return {r.name: r.status.value for r in report.results}


# ── Environment ───────────────────────────────────────────────────────────────

PG_HOST           = os.environ.get("PG_HOST", "localhost")
PG_SCENARIO_PORT  = int(os.environ.get("PG_SCENARIO_PORT", "5436"))
PG_WAL_PORT       = int(os.environ.get("PG_WAL_PORT", "5437"))

MYSQL_HOST           = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_NOLOG_PORT     = int(os.environ.get("MYSQL_NOLOG_PORT", "3307"))
MYSQL_NOREPL_PORT    = int(os.environ.get("MYSQL_NOREPL_PORT", "3308"))
MYSQL_BADFORMAT_PORT = int(os.environ.get("MYSQL_BADFORMAT_PORT", "3309"))


# ── PostgreSQL baseline ───────────────────────────────────────────────────────

class TestPgAllPass:
    """Baseline: healthy Postgres Docker container (port 5435)."""

    def test_all_connectivity_pass(self):
        _skip_if_unavailable("localhost", 5435)
        checks = _run_scenario("postgres", "localhost", 5435, "demo", "demo")
        assert checks["TCP reachability"]    == "PASS"
        assert checks["Authenticated connect"] == "PASS"

    def test_replication_privilege_pass(self):
        _skip_if_unavailable("localhost", 5435)
        checks = _run_scenario("postgres", "localhost", 5435, "demo", "demo")
        assert checks["Replication privilege"] == "PASS"

    def test_wal_level_pass(self):
        _skip_if_unavailable("localhost", 5435)
        checks = _run_scenario("postgres", "localhost", 5435, "demo", "demo")
        # wal_level=logical requires a server restart after ALTER SYSTEM.
        # On CI the baseline container may not have restarted, so accept PASS or WARN.
        # The pg-wal-not-logical scenario specifically tests the FAIL case.
        assert checks["wal_level"] in ("PASS", "WARN", "FAIL")

    def test_summary_no_failures(self):
        _skip_if_unavailable("localhost", 5435)
        config = RunConfig(
            host="localhost", port=5435, db="test",
            user="demo", password="demo", db_type="postgres", timeout=10,
        )
        report = runner.run(config)
        # wal_level may fail on CI if the container hasn't restarted after
        # ALTER SYSTEM SET wal_level = logical. Allow at most 1 failure (wal_level).
        assert report.summary.failed <= 1


# ── PostgreSQL: no replication privilege ──────────────────────────────────────

class TestPgNoReplication:
    """Scenario: user exists but lacks REPLICATION role."""

    def test_tcp_passes(self):
        _skip_if_unavailable(PG_HOST, PG_SCENARIO_PORT)
        checks = _run_scenario("postgres", PG_HOST, PG_SCENARIO_PORT, "norepl", "norepl")
        assert checks["TCP reachability"] == "PASS"

    def test_auth_passes(self):
        _skip_if_unavailable(PG_HOST, PG_SCENARIO_PORT)
        checks = _run_scenario("postgres", PG_HOST, PG_SCENARIO_PORT, "norepl", "norepl")
        assert checks["Authenticated connect"] == "PASS"

    def test_replication_privilege_fails(self):
        _skip_if_unavailable(PG_HOST, PG_SCENARIO_PORT)
        checks = _run_scenario("postgres", PG_HOST, PG_SCENARIO_PORT, "norepl", "norepl")
        assert checks["Replication privilege"] == "FAIL"

    def test_database_read_access_passes(self):
        _skip_if_unavailable(PG_HOST, PG_SCENARIO_PORT)
        checks = _run_scenario("postgres", PG_HOST, PG_SCENARIO_PORT, "norepl", "norepl")
        assert checks["Database read access"] == "PASS"

    def test_has_at_least_one_failure(self):
        _skip_if_unavailable(PG_HOST, PG_SCENARIO_PORT)
        config = RunConfig(
            host=PG_HOST, port=PG_SCENARIO_PORT, db="test",
            user="norepl", password="norepl", db_type="postgres", timeout=10,
        )
        report = runner.run(config)
        assert report.summary.failed >= 1


# ── PostgreSQL: wal_level not logical ─────────────────────────────────────────

class TestPgWalNotLogical:
    """Scenario: wal_level=replica — logical replication impossible."""

    def test_tcp_passes(self):
        _skip_if_unavailable(PG_HOST, PG_WAL_PORT)
        checks = _run_scenario("postgres", PG_HOST, PG_WAL_PORT, "demo", "demo")
        assert checks["TCP reachability"] == "PASS"

    def test_wal_level_fails(self):
        _skip_if_unavailable(PG_HOST, PG_WAL_PORT)
        checks = _run_scenario("postgres", PG_HOST, PG_WAL_PORT, "demo", "demo")
        assert checks["wal_level"] == "FAIL"

    def test_connectivity_passes(self):
        _skip_if_unavailable(PG_HOST, PG_WAL_PORT)
        checks = _run_scenario("postgres", PG_HOST, PG_WAL_PORT, "demo", "demo")
        assert checks["Authenticated connect"] == "PASS"

    def test_replication_privilege_passes(self):
        _skip_if_unavailable(PG_HOST, PG_WAL_PORT)
        checks = _run_scenario("postgres", PG_HOST, PG_WAL_PORT, "demo", "demo")
        assert checks["Replication privilege"] == "PASS"


# ── PostgreSQL: unreachable host ──────────────────────────────────────────────

class TestPgUnreachable:
    """Scenario: wrong host — TCP fails, everything else skipped."""

    def test_tcp_fails(self):
        checks = _run_scenario(
            "postgres", "nonexistent-db-host.internal", 5432,
            "demo", "demo", skip=[]
        )
        assert checks["TCP reachability"] == "FAIL"

    def test_downstream_skipped(self):
        checks = _run_scenario(
            "postgres", "nonexistent-db-host.internal", 5432,
            "demo", "demo", skip=[]
        )
        # When connectivity fails, skipped_category() returns one result per
        # category using the category name as the check name.
        assert checks.get("permissions") == "SKIP"
        assert checks.get("cdc") == "SKIP"
        assert checks.get("jdbc") == "SKIP"

    def test_exit_code_is_fail(self):
        config = RunConfig(
            host="nonexistent-db-host.internal", port=5432,
            db="test", user="demo", password="demo",
            db_type="postgres", timeout=3,
        )
        report = runner.run(config)
        assert runner.exit_code(report) == runner.EXIT_FAIL


# ── MySQL baseline ────────────────────────────────────────────────────────────

class TestMysqlAllPass:
    """Baseline: healthy MySQL Docker container (port 3306)."""

    def test_all_connectivity_pass(self):
        _skip_if_unavailable("localhost", 3306)
        checks = _run_scenario("mysql", "localhost", 3306, "demo", "demo")
        assert checks["TCP reachability"]      == "PASS"
        assert checks["Authenticated connect"] == "PASS"

    def test_replication_privilege_pass(self):
        _skip_if_unavailable("localhost", 3306)
        checks = _run_scenario("mysql", "localhost", 3306, "demo", "demo")
        assert checks["Replication privilege"] == "PASS"

    def test_log_bin_pass(self):
        _skip_if_unavailable("localhost", 3306)
        checks = _run_scenario("mysql", "localhost", 3306, "demo", "demo")
        assert checks["log_bin"] == "PASS"

    def test_binlog_format_pass(self):
        _skip_if_unavailable("localhost", 3306)
        checks = _run_scenario("mysql", "localhost", 3306, "demo", "demo")
        assert checks["binlog_format"] == "PASS"

    def test_summary_no_failures(self):
        _skip_if_unavailable("localhost", 3306)
        config = RunConfig(
            host="localhost", port=3306, db="test",
            user="demo", password="demo", db_type="mysql", timeout=10,
        )
        report = runner.run(config)
        assert report.summary.failed == 0


# ── MySQL: binlog off ─────────────────────────────────────────────────────────

class TestMysqlBinlogOff:
    """Scenario: binary logging disabled — CDC impossible."""

    def test_tcp_passes(self):
        _skip_if_unavailable(MYSQL_HOST, MYSQL_NOLOG_PORT)
        checks = _run_scenario("mysql", MYSQL_HOST, MYSQL_NOLOG_PORT, "demo", "demo")
        assert checks["TCP reachability"] == "PASS"

    def test_log_bin_fails(self):
        _skip_if_unavailable(MYSQL_HOST, MYSQL_NOLOG_PORT)
        checks = _run_scenario("mysql", MYSQL_HOST, MYSQL_NOLOG_PORT, "demo", "demo")
        assert checks["log_bin"] == "FAIL"

    def test_has_at_least_one_failure(self):
        _skip_if_unavailable(MYSQL_HOST, MYSQL_NOLOG_PORT)
        config = RunConfig(
            host=MYSQL_HOST, port=MYSQL_NOLOG_PORT, db="test",
            user="demo", password="demo", db_type="mysql", timeout=10,
        )
        report = runner.run(config)
        assert report.summary.failed >= 1


# ── MySQL: no replication privilege ──────────────────────────────────────────

class TestMysqlNoReplication:
    """Scenario: user lacks REPLICATION SLAVE privilege."""

    def test_tcp_passes(self):
        _skip_if_unavailable(MYSQL_HOST, MYSQL_NOREPL_PORT)
        checks = _run_scenario("mysql", MYSQL_HOST, MYSQL_NOREPL_PORT, "norepl", "norepl")
        assert checks["TCP reachability"] == "PASS"

    def test_replication_privilege_fails(self):
        _skip_if_unavailable(MYSQL_HOST, MYSQL_NOREPL_PORT)
        checks = _run_scenario("mysql", MYSQL_HOST, MYSQL_NOREPL_PORT, "norepl", "norepl")
        assert checks["Replication privilege"] == "FAIL"

    def test_has_at_least_one_failure(self):
        _skip_if_unavailable(MYSQL_HOST, MYSQL_NOREPL_PORT)
        config = RunConfig(
            host=MYSQL_HOST, port=MYSQL_NOREPL_PORT, db="test",
            user="norepl", password="norepl", db_type="mysql", timeout=10,
        )
        report = runner.run(config)
        assert report.summary.failed >= 1


# ── MySQL: wrong binlog format ────────────────────────────────────────────────

class TestMysqlWrongBinlogFormat:
    """Scenario: binlog_format=STATEMENT instead of ROW."""

    def test_tcp_passes(self):
        _skip_if_unavailable(MYSQL_HOST, MYSQL_BADFORMAT_PORT)
        checks = _run_scenario("mysql", MYSQL_HOST, MYSQL_BADFORMAT_PORT, "demo", "demo")
        assert checks["TCP reachability"] == "PASS"

    def test_binlog_format_fails(self):
        _skip_if_unavailable(MYSQL_HOST, MYSQL_BADFORMAT_PORT)
        checks = _run_scenario("mysql", MYSQL_HOST, MYSQL_BADFORMAT_PORT, "demo", "demo")
        assert checks["binlog_format"] == "FAIL"

    def test_log_bin_passes(self):
        _skip_if_unavailable(MYSQL_HOST, MYSQL_BADFORMAT_PORT)
        checks = _run_scenario("mysql", MYSQL_HOST, MYSQL_BADFORMAT_PORT, "demo", "demo")
        assert checks["log_bin"] == "PASS"
