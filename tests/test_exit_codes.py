"""
Unit tests for runner.exit_code().

Each test builds a minimal RunReport with a crafted Summary and asserts
the correct POSIX exit code is returned. No DB connection required.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from connector_toolkit.models import (
    Category, CheckResult, RunConfig, RunReport, Status, Summary,
)
from connector_toolkit.runner import (
    EXIT_FAIL, EXIT_PASS, EXIT_SKIPPED, EXIT_WARN, exit_code,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def base_config():
    return RunConfig(
        host="localhost", port=5432, db="test",
        user="demo", password="demo", db_type="postgres",
    )


def _report(config, results: list[CheckResult]) -> RunReport:
    summary = Summary.from_results(results)
    return RunReport(
        config=config,
        results=results,
        summary=summary,
        timestamp=datetime.now(timezone.utc),
    )


def _result(status: Status, category=Category.CONNECTIVITY) -> CheckResult:
    return CheckResult(category=category, name="test-check", status=status)


# ── Exit code tests ───────────────────────────────────────────────────────────

class TestExitCodes:
    def test_all_pass_returns_0(self, base_config):
        report = _report(base_config, [
            _result(Status.PASS, Category.CONNECTIVITY),
            _result(Status.PASS, Category.PERMISSIONS),
            _result(Status.PASS, Category.CDC),
            _result(Status.PASS, Category.JDBC),
        ])
        assert exit_code(report) == EXIT_PASS

    def test_any_fail_returns_1(self, base_config):
        report = _report(base_config, [
            _result(Status.PASS, Category.CONNECTIVITY),
            _result(Status.FAIL, Category.PERMISSIONS),
            _result(Status.PASS, Category.CDC),
        ])
        assert exit_code(report) == EXIT_FAIL

    def test_fail_takes_priority_over_warn(self, base_config):
        report = _report(base_config, [
            _result(Status.FAIL, Category.CONNECTIVITY),
            _result(Status.WARN, Category.PERMISSIONS),
        ])
        assert exit_code(report) == EXIT_FAIL

    def test_warn_only_returns_2(self, base_config):
        report = _report(base_config, [
            _result(Status.PASS, Category.CONNECTIVITY),
            _result(Status.WARN, Category.CDC),
        ])
        assert exit_code(report) == EXIT_WARN

    def test_multiple_warns_still_returns_2(self, base_config):
        report = _report(base_config, [
            _result(Status.WARN, Category.CONNECTIVITY),
            _result(Status.WARN, Category.PERMISSIONS),
            _result(Status.WARN, Category.CDC),
        ])
        assert exit_code(report) == EXIT_WARN

    def test_all_skipped_returns_3(self, base_config):
        report = _report(base_config, [
            _result(Status.SKIP, Category.CONNECTIVITY),
            _result(Status.SKIP, Category.PERMISSIONS),
            _result(Status.SKIP, Category.CDC),
            _result(Status.SKIP, Category.JDBC),
        ])
        assert exit_code(report) == EXIT_SKIPPED

    def test_mixed_pass_and_skip_returns_0(self, base_config):
        """Skipping some categories while others pass should still be exit 0."""
        report = _report(base_config, [
            _result(Status.PASS, Category.CONNECTIVITY),
            _result(Status.PASS, Category.PERMISSIONS),
            _result(Status.SKIP, Category.CDC),
            _result(Status.SKIP, Category.JDBC),
        ])
        assert exit_code(report) == EXIT_PASS

    def test_symbolic_constants_match_expected_values(self):
        assert EXIT_PASS    == 0
        assert EXIT_FAIL    == 1
        assert EXIT_WARN    == 2
        assert EXIT_SKIPPED == 3
