"""
Tests for verbose mode, per-check timing, and HTML reporter.
"""
from __future__ import annotations

import os
import re
import tempfile
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from connector_toolkit.models import (
    Category, CheckResult, RunConfig, RunReport, Status, Summary,
)
from connector_toolkit.reporters.terminal import TerminalReporter
from connector_toolkit.reporters.html_report import HtmlReporter
from connector_toolkit import runner


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _config(verbose: bool = False, output_file: str = None) -> RunConfig:
    return RunConfig(
        host="localhost", port=5432, db="testdb",
        user="admin", password="secret", db_type="postgres",
        verbose=verbose, output_file=output_file,
    )


def _result(status: Status, name: str = "TCP reachability",
            category: Category = Category.CONNECTIVITY,
            duration_ms: int = None, exception: str = None) -> CheckResult:
    return CheckResult(
        category=category, name=name, status=status,
        detail="host=localhost", duration_ms=duration_ms, exception=exception,
    )


def _run(results, verbose=False, output_file=None) -> RunReport:
    config = _config(verbose=verbose, output_file=output_file)
    return RunReport(
        config=config,
        results=results,
        summary=Summary.from_results(results),
        total_duration_ms=123,
    )


def _buf_reporter(verbose=False):
    buf = StringIO()
    console = Console(file=buf, highlight=False, no_color=True)
    reporter = TerminalReporter(console=console)
    return reporter, buf


# ── CheckResult.duration_ms ───────────────────────────────────────────────────

class TestDurationMs:
    def test_duration_ms_defaults_to_none(self):
        r = _result(Status.PASS)
        assert r.duration_ms is None

    def test_duration_ms_stored(self):
        r = _result(Status.PASS, duration_ms=42)
        assert r.duration_ms == 42

    def test_duration_ms_in_to_dict(self):
        r = _result(Status.PASS, duration_ms=42)
        assert r.to_dict()["duration_ms"] == 42

    def test_duration_ms_omitted_when_none(self):
        r = _result(Status.PASS)
        assert "duration_ms" not in r.to_dict()

    def test_exception_in_to_dict(self):
        r = _result(Status.FAIL, exception="Traceback...\nValueError: oops")
        assert r.to_dict()["exception"] == "Traceback...\nValueError: oops"

    def test_exception_omitted_when_none(self):
        r = _result(Status.PASS)
        assert "exception" not in r.to_dict()


# ── RunReport.total_duration_ms ───────────────────────────────────────────────

class TestRunReportTiming:
    def test_total_duration_in_to_dict(self):
        run = _run([_result(Status.PASS)])
        assert run.to_dict()["total_duration_ms"] == 123

    def test_total_duration_omitted_when_none(self):
        config = _config()
        run = RunReport(config=config, results=[], summary=Summary())
        assert "total_duration_ms" not in run.to_dict()


# ── RunConfig.verbose ─────────────────────────────────────────────────────────

class TestRunConfigVerbose:
    def test_verbose_defaults_to_false(self):
        assert _config().verbose is False

    def test_verbose_can_be_set(self):
        assert _config(verbose=True).verbose is True


# ── Terminal reporter — verbose mode ──────────────────────────────────────────

class TestTerminalReporterVerbose:
    def test_timing_shown_in_verbose_mode(self):
        reporter, buf = _buf_reporter()
        run = _run([_result(Status.PASS, duration_ms=55)], verbose=True)
        reporter.report(run)
        assert "55ms" in buf.getvalue()

    def test_timing_hidden_in_normal_mode(self):
        reporter, buf = _buf_reporter()
        run = _run([_result(Status.PASS, duration_ms=55)], verbose=False)
        reporter.report(run)
        assert "55ms" not in buf.getvalue()

    def test_total_timing_shown_in_verbose_mode(self):
        reporter, buf = _buf_reporter()
        run = _run([_result(Status.PASS)], verbose=True)
        reporter.report(run)
        assert "123ms" in buf.getvalue()

    def test_connection_params_shown_in_verbose_mode(self):
        reporter, buf = _buf_reporter()
        run = _run([_result(Status.PASS)], verbose=True)
        reporter.report(run)
        output = buf.getvalue()
        assert "localhost" in output
        assert "5432" in output
        # Password must be masked
        assert "secret" not in output

    def test_exception_shown_in_verbose_mode(self):
        reporter, buf = _buf_reporter()
        r = _result(Status.FAIL, exception="Traceback (most recent call last):\nValueError")
        run = _run([r], verbose=True)
        reporter.report(run)
        assert "Traceback" in buf.getvalue()

    def test_exception_hidden_in_normal_mode(self):
        reporter, buf = _buf_reporter()
        r = _result(Status.FAIL, exception="Traceback (most recent call last):\nValueError")
        run = _run([r], verbose=False)
        reporter.report(run)
        assert "Traceback" not in buf.getvalue()


# ── Runner timing ─────────────────────────────────────────────────────────────

class TestRunnerTiming:
    def test_total_duration_set_after_run(self):
        mock_conn = MagicMock()
        with patch.dict(runner.CONNECTOR_REGISTRY, {
            "postgres": lambda cfg: MagicMock(
                check_connectivity=lambda: [_result(Status.PASS)],
                check_permissions=lambda: [_result(Status.PASS, category=Category.PERMISSIONS)],
                check_cdc=lambda: [_result(Status.PASS, category=Category.CDC)],
                check_jdbc=lambda: [_result(Status.PASS, category=Category.JDBC)],
                skipped_category=lambda cat: [_result(Status.SKIP, category=cat)],
            )
        }):
            report = runner.run(_config())
        assert report.total_duration_ms is not None
        assert report.total_duration_ms >= 0

    def test_check_results_have_duration(self):
        with patch.dict(runner.CONNECTOR_REGISTRY, {
            "postgres": lambda cfg: MagicMock(
                check_connectivity=lambda: [_result(Status.PASS)],
                check_permissions=lambda: [_result(Status.PASS, category=Category.PERMISSIONS)],
                check_cdc=lambda: [_result(Status.PASS, category=Category.CDC)],
                check_jdbc=lambda: [_result(Status.PASS, category=Category.JDBC)],
                skipped_category=lambda cat: [_result(Status.SKIP, category=cat)],
            )
        }):
            report = runner.run(_config())
        for r in report.results:
            if r.status != Status.SKIP:
                assert r.duration_ms is not None


# ── HTML reporter ─────────────────────────────────────────────────────────────

class TestHtmlReporter:
    def _make_run(self, verbose=False) -> RunReport:
        results = [
            CheckResult(
                category=Category.CONNECTIVITY, name="TCP reachability",
                status=Status.PASS, detail="host=localhost port=5432",
                duration_ms=12,
            ),
            CheckResult(
                category=Category.CDC, name="wal_level",
                status=Status.FAIL, detail="wal_level=replica",
                remediation="ALTER SYSTEM SET wal_level = logical;",
                duration_ms=34,
            ),
            CheckResult(
                category=Category.PERMISSIONS, name="Replication privilege",
                status=Status.WARN, detail="rolreplication=False",
                remediation="ALTER ROLE admin REPLICATION;",
                duration_ms=8,
            ),
        ]
        config = _config(verbose=verbose)
        return RunReport(
            config=config,
            results=results,
            summary=Summary.from_results(results),
            total_duration_ms=54,
        )

    def test_produces_valid_html(self):
        run = self._make_run()
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
            path = f.name
        try:
            run.config.output_file = path
            HtmlReporter().report(run)
            content = open(path).read()
            assert "<!DOCTYPE html>" in content
            assert "<html" in content
            assert "</html>" in content
        finally:
            os.unlink(path)

    def test_contains_check_names(self):
        run = self._make_run()
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
            path = f.name
        try:
            run.config.output_file = path
            HtmlReporter().report(run)
            content = open(path).read()
            assert "TCP reachability" in content
            assert "wal_level" in content
            assert "Replication privilege" in content
        finally:
            os.unlink(path)

    def test_contains_all_statuses(self):
        run = self._make_run()
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
            path = f.name
        try:
            run.config.output_file = path
            HtmlReporter().report(run)
            content = open(path).read()
            assert "PASS" in content
            assert "FAIL" in content
            assert "WARN" in content
        finally:
            os.unlink(path)

    def test_remediation_shown(self):
        run = self._make_run()
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
            path = f.name
        try:
            run.config.output_file = path
            HtmlReporter().report(run)
            content = open(path).read()
            assert "ALTER SYSTEM" in content
        finally:
            os.unlink(path)

    def test_password_not_in_output(self):
        run = self._make_run()
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
            path = f.name
        try:
            run.config.output_file = path
            HtmlReporter().report(run)
            content = open(path).read()
            assert "secret" not in content
        finally:
            os.unlink(path)

    def test_timing_shown_in_verbose_mode(self):
        run = self._make_run(verbose=True)
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
            path = f.name
        try:
            run.config.output_file = path
            HtmlReporter().report(run)
            content = open(path).read()
            assert "12ms" in content
        finally:
            os.unlink(path)

    def test_html_extension_triggers_html_reporter(self):
        """runner selects HtmlReporter when output file ends in .html"""
        with patch.dict(runner.CONNECTOR_REGISTRY, {
            "postgres": lambda cfg: MagicMock(
                check_connectivity=lambda: [_result(Status.PASS)],
                check_permissions=lambda: [_result(Status.PASS, category=Category.PERMISSIONS)],
                check_cdc=lambda: [_result(Status.PASS, category=Category.CDC)],
                check_jdbc=lambda: [_result(Status.PASS, category=Category.JDBC)],
                skipped_category=lambda cat: [_result(Status.SKIP, category=cat)],
            )
        }):
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
                path = f.name
            try:
                config = _config(output_file=path)
                runner.run(config)
                content = open(path).read()
                assert "<!DOCTYPE html>" in content
            finally:
                os.unlink(path)
