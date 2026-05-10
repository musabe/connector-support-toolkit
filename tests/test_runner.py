"""
Tests for runner orchestration — all categories run, connectivity cascade,
skip flag, db-type registry, unknown db-type error.
Replaces the old test_runner.py (which imported from src.runner).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from connector_toolkit.models import Category, CheckResult, RunConfig, Status
from connector_toolkit import runner
from connector_toolkit.runner import EXIT_FAIL, EXIT_PASS, EXIT_WARN, exit_code


# ── Helpers ───────────────────────────────────────────────────────────────────

def _result(category: Category, status: Status) -> CheckResult:
    return CheckResult(category=category, name="check", status=status, detail="")


def _config(**kwargs) -> RunConfig:
    defaults = dict(
        host="localhost", port=5432, db="db",
        user="user", password="pass", db_type="postgres",
    )
    defaults.update(kwargs)
    return RunConfig(**defaults)


def _mock_connector(connectivity_status: Status = Status.PASS) -> MagicMock:
    """Return a mock connector whose four check methods return single-item lists."""
    m = MagicMock()
    m.check_connectivity.return_value = [_result(Category.CONNECTIVITY, connectivity_status)]
    m.check_permissions.return_value = [_result(Category.PERMISSIONS, Status.PASS)]
    m.check_cdc.return_value       = [_result(Category.CDC, Status.PASS)]
    m.check_jdbc.return_value      = [_result(Category.JDBC, Status.PASS)]
    # skipped_category mirrors BaseConnector behaviour
    m.skipped_category.side_effect = lambda cat: [_result(cat, Status.SKIP)]
    return m


# ── Orchestration ─────────────────────────────────────────────────────────────

class TestRunnerOrchestration:
    def test_all_four_categories_run_on_pass(self):
        mock = _mock_connector()
        with patch.dict(runner.CONNECTOR_REGISTRY, {"postgres": lambda cfg: mock}):
            report = runner.run(_config())

        mock.check_connectivity.assert_called_once()
        mock.check_permissions.assert_called_once()
        mock.check_cdc.assert_called_once()
        mock.check_jdbc.assert_called_once()
        assert len(report.results) == 4

    def test_connectivity_fail_skips_downstream(self):
        mock = _mock_connector(connectivity_status=Status.FAIL)
        with patch.dict(runner.CONNECTOR_REGISTRY, {"postgres": lambda cfg: mock}):
            report = runner.run(_config())

        mock.check_permissions.assert_not_called()
        mock.check_cdc.assert_not_called()
        mock.check_jdbc.assert_not_called()

        skipped = [r for r in report.results if r.status == Status.SKIP]
        assert len(skipped) == 3

    def test_skip_flag_excludes_category(self):
        mock = _mock_connector()
        with patch.dict(runner.CONNECTOR_REGISTRY, {"postgres": lambda cfg: mock}):
            report = runner.run(_config(skip=[Category.CDC]))

        mock.check_cdc.assert_not_called()
        mock.check_permissions.assert_called_once()
        skipped = [r for r in report.results if r.status == Status.SKIP]
        assert any(r.category == Category.CDC for r in skipped)

    def test_multiple_skip_categories(self):
        mock = _mock_connector()
        with patch.dict(runner.CONNECTOR_REGISTRY, {"postgres": lambda cfg: mock}):
            runner.run(_config(skip=[Category.CDC, Category.JDBC]))

        mock.check_cdc.assert_not_called()
        mock.check_jdbc.assert_not_called()
        mock.check_permissions.assert_called_once()

    def test_mysql_connector_selected_for_mysql_db_type(self):
        mock = _mock_connector()
        mysql_cls = MagicMock(return_value=mock)
        with patch.dict(runner.CONNECTOR_REGISTRY, {"mysql": mysql_cls}):
            runner.run(_config(db_type="mysql", port=3306))
        mysql_cls.assert_called_once()

    def test_unknown_db_type_exits(self):
        with pytest.raises(SystemExit) as exc:
            runner.run(_config(db_type="oracle"))
        assert exc.value.code == 1

    def test_summary_counts_correct(self):
        mock = _mock_connector()
        mock.check_cdc.return_value = [_result(Category.CDC, Status.FAIL)]
        mock.check_jdbc.return_value = [_result(Category.JDBC, Status.WARN)]
        with patch.dict(runner.CONNECTOR_REGISTRY, {"postgres": lambda cfg: mock}):
            report = runner.run(_config())

        assert report.summary.passed == 2
        assert report.summary.failed == 1
        assert report.summary.warned == 1


# ── Exit codes ────────────────────────────────────────────────────────────────

class TestExitCode:
    def test_all_pass_returns_0(self):
        mock = _mock_connector()
        with patch.dict(runner.CONNECTOR_REGISTRY, {"postgres": lambda cfg: mock}):
            report = runner.run(_config())
        assert exit_code(report) == EXIT_PASS

    def test_any_fail_returns_1(self):
        mock = _mock_connector()
        mock.check_cdc.return_value = [_result(Category.CDC, Status.FAIL)]
        with patch.dict(runner.CONNECTOR_REGISTRY, {"postgres": lambda cfg: mock}):
            report = runner.run(_config())
        assert exit_code(report) == EXIT_FAIL

    def test_warn_only_returns_2(self):
        mock = _mock_connector()
        mock.check_jdbc.return_value = [_result(Category.JDBC, Status.WARN)]
        with patch.dict(runner.CONNECTOR_REGISTRY, {"postgres": lambda cfg: mock}):
            report = runner.run(_config())
        assert exit_code(report) == EXIT_WARN
