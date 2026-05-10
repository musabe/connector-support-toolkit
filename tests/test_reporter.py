"""
Tests for terminal and JSON reporters.
Replaces the old test_reporter.py (which imported from src.reporter).
"""
from __future__ import annotations

import json
import os
import tempfile
from io import StringIO

import pytest
from rich.console import Console

from connector_toolkit.models import Category, CheckResult, RunConfig, RunReport, Status, Summary
from connector_toolkit.reporters.terminal import TerminalReporter
from connector_toolkit.reporters.json_report import JsonReporter


# ── Helpers ───────────────────────────────────────────────────────────────────

def _result(category: Category, name: str, status: Status, detail: str = "") -> CheckResult:
    return CheckResult(category=category, name=name, status=status, detail=detail)


def _run(results: list[CheckResult]) -> RunReport:
    config = RunConfig(
        host="localhost", port=5432, db="testdb",
        user="admin", password="secret", db_type="postgres",
    )
    return RunReport(config=config, results=results, summary=Summary.from_results(results))


def _terminal_with_buffer() -> tuple[TerminalReporter, StringIO]:
    buf = StringIO()
    console = Console(file=buf, highlight=False, no_color=True)
    reporter = TerminalReporter(console=console)
    return reporter, buf


# ── Terminal reporter ─────────────────────────────────────────────────────────

class TestTerminalReporter:
    def test_category_header_shown(self):
        reporter, buf = _terminal_with_buffer()
        run = _run([_result(Category.CONNECTIVITY, "TCP reachability", Status.PASS, "host=localhost")])
        reporter.report(run)
        assert "CONNECTIVITY" in buf.getvalue()

    def test_check_name_and_status_shown(self):
        reporter, buf = _terminal_with_buffer()
        run = _run([_result(Category.CONNECTIVITY, "TCP reachability", Status.PASS, "host=localhost")])
        reporter.report(run)
        output = buf.getvalue()
        assert "PASS" in output
        assert "TCP reachability" in output

    def test_categories_appear_in_order(self):
        reporter, buf = _terminal_with_buffer()
        run = _run([
            _result(Category.CONNECTIVITY, "TCP reachability", Status.PASS),
            _result(Category.CONNECTIVITY, "SSL", Status.PASS),
            _result(Category.PERMISSIONS, "Replication privilege", Status.WARN),
        ])
        reporter.report(run)
        output = buf.getvalue()
        assert output.index("CONNECTIVITY") < output.index("PERMISSIONS")

    def test_remediation_hint_shown_on_fail(self):
        reporter, buf = _terminal_with_buffer()
        result = CheckResult(
            category=Category.CDC,
            name="wal_level",
            status=Status.FAIL,
            detail="wal_level=replica",
            remediation="ALTER SYSTEM SET wal_level = logical;",
        )
        run = _run([result])
        reporter.report(run)
        assert "ALTER SYSTEM" in buf.getvalue()

    def test_summary_line_shown(self):
        reporter, buf = _terminal_with_buffer()
        run = _run([
            _result(Category.CONNECTIVITY, "TCP", Status.PASS),
            _result(Category.CDC, "wal_level", Status.FAIL),
        ])
        reporter.report(run)
        output = buf.getvalue()
        assert "passed" in output.lower()
        assert "failed" in output.lower()


# ── JSON reporter ─────────────────────────────────────────────────────────────

class TestJsonReporter:
    def test_json_structure(self):
        results = [
            _result(Category.CONNECTIVITY, "TCP reachability", Status.PASS, "host=localhost"),
            _result(Category.CDC, "wal_level", Status.FAIL, "found: replica"),
        ]
        run = _run(results)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            path = f.name

        run.config.output_file = path
        try:
            JsonReporter().report(run)
            with open(path) as f:
                report = json.load(f)

            assert report["host"] == "localhost"
            assert report["db_type"] == "postgres"
            assert report["summary"]["passed"] == 1
            assert report["summary"]["failed"] == 1
            assert report["summary"]["warned"] == 0
            assert len(report["checks"]) == 2
            assert "timestamp" in report
        finally:
            os.unlink(path)

    def test_json_check_fields(self):
        results = [_result(Category.CONNECTIVITY, "TCP reachability", Status.PASS, "ok")]
        run = _run(results)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            path = f.name

        run.config.output_file = path
        try:
            JsonReporter().report(run)
            with open(path) as f:
                report = json.load(f)
            check = report["checks"][0]
            assert check["category"] == "connectivity"
            assert check["name"] == "TCP reachability"
            assert check["status"] == "PASS"
            assert check["detail"] == "ok"
        finally:
            os.unlink(path)

    def test_json_includes_remediation_when_present(self):
        result = CheckResult(
            category=Category.CDC,
            name="wal_level",
            status=Status.FAIL,
            detail="replica",
            remediation="ALTER SYSTEM SET wal_level = logical;",
        )
        run = _run([result])

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            path = f.name

        run.config.output_file = path
        try:
            JsonReporter().report(run)
            with open(path) as f:
                report = json.load(f)
            assert "remediation" in report["checks"][0]
        finally:
            os.unlink(path)
