"""
Tests for the report diff engine (diff.py) and diff reporters.
No live database or file system required for most tests.
"""
from __future__ import annotations

import json
import os
import tempfile
from io import StringIO

import pytest
from rich.console import Console

from connector_toolkit.diff import (
    CheckDelta,
    DiffError,
    ReportDiff,
    SummaryDelta,
    diff_reports,
    load_report,
)
from connector_toolkit.reporters.diff_reporter import DiffTerminalReporter


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _report(
    host="localhost",
    db_type="postgres",
    checks=None,
    passed=2, warned=0, failed=0, skipped=0,
) -> dict:
    return {
        "timestamp": "2026-05-01T10:00:00+00:00",
        "host": host,
        "db_type": db_type,
        "summary": {"passed": passed, "warned": warned, "failed": failed, "skipped": skipped},
        "checks": checks or [
            {"category": "connectivity", "name": "TCP reachability", "status": "PASS", "detail": ""},
            {"category": "cdc",          "name": "wal_level",        "status": "PASS", "detail": "logical"},
        ],
    }


def _write_report(tmp_path, data: dict, name: str = "report.json") -> str:
    p = tmp_path / name
    p.write_text(json.dumps(data))
    return str(p)


# ── load_report ───────────────────────────────────────────────────────────────

class TestLoadReport:
    def test_valid_file_loads(self, tmp_path):
        path = _write_report(tmp_path, _report())
        data = load_report(path)
        assert data["host"] == "localhost"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(DiffError, match="not found"):
            load_report(tmp_path / "nonexistent.json")

    def test_invalid_json_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json")
        with pytest.raises(DiffError, match="Invalid JSON"):
            load_report(p)

    def test_missing_required_key_raises(self, tmp_path):
        data = _report()
        del data["checks"]
        path = _write_report(tmp_path, data)
        with pytest.raises(DiffError, match="checks"):
            load_report(path)

    def test_non_object_json_raises(self, tmp_path):
        p = tmp_path / "list.json"
        p.write_text("[1, 2, 3]")
        with pytest.raises(DiffError, match="JSON object"):
            load_report(p)


# ── diff_reports ──────────────────────────────────────────────────────────────

class TestDiffReports:
    def test_identical_reports_produce_no_deltas(self):
        r = _report()
        diff = diff_reports(r, r)
        assert diff.deltas == []

    def test_status_change_detected(self):
        before = _report(checks=[
            {"category": "cdc", "name": "wal_level", "status": "FAIL", "detail": "replica"},
        ], failed=1, passed=0)
        after = _report(checks=[
            {"category": "cdc", "name": "wal_level", "status": "PASS", "detail": "logical"},
        ], passed=1, failed=0)
        diff = diff_reports(before, after)
        assert len(diff.deltas) == 1
        d = diff.deltas[0]
        assert d.name == "wal_level"
        assert d.before == "FAIL"
        assert d.after == "PASS"

    def test_improvement_detected(self):
        before = _report(checks=[
            {"category": "cdc", "name": "wal_level", "status": "FAIL", "detail": ""},
        ], failed=1, passed=0)
        after = _report(checks=[
            {"category": "cdc", "name": "wal_level", "status": "PASS", "detail": ""},
        ], passed=1, failed=0)
        diff = diff_reports(before, after)
        assert len(diff.improvements) == 1
        assert len(diff.regressions) == 0

    def test_regression_detected(self):
        before = _report(checks=[
            {"category": "cdc", "name": "wal_level", "status": "PASS", "detail": ""},
        ], passed=1)
        after = _report(checks=[
            {"category": "cdc", "name": "wal_level", "status": "FAIL", "detail": ""},
        ], failed=1, passed=0)
        diff = diff_reports(before, after)
        assert len(diff.regressions) == 1
        assert len(diff.improvements) == 0

    def test_added_check_detected(self):
        before = _report(checks=[
            {"category": "connectivity", "name": "TCP reachability", "status": "PASS", "detail": ""},
        ], passed=1)
        after = _report(checks=[
            {"category": "connectivity", "name": "TCP reachability", "status": "PASS", "detail": ""},
            {"category": "jdbc",         "name": "Driver version",   "status": "PASS", "detail": ""},
        ], passed=2)
        diff = diff_reports(before, after)
        assert len(diff.added) == 1
        assert diff.added[0].name == "Driver version"

    def test_removed_check_detected(self):
        before = _report(checks=[
            {"category": "connectivity", "name": "TCP reachability", "status": "PASS", "detail": ""},
            {"category": "jdbc",         "name": "Driver version",   "status": "PASS", "detail": ""},
        ], passed=2)
        after = _report(checks=[
            {"category": "connectivity", "name": "TCP reachability", "status": "PASS", "detail": ""},
        ], passed=1)
        diff = diff_reports(before, after)
        assert len(diff.removed) == 1
        assert diff.removed[0].name == "Driver version"

    def test_different_db_types_raise(self):
        before = _report(db_type="postgres")
        after  = _report(db_type="mysql")
        with pytest.raises(DiffError, match="database types"):
            diff_reports(before, after)

    def test_summary_delta_computed(self):
        before = _report(passed=5, warned=1, failed=2, skipped=0)
        after  = _report(passed=6, warned=0, failed=1, skipped=1)
        diff = diff_reports(before, after)
        assert diff.summary_delta.passed  ==  1
        assert diff.summary_delta.warned  == -1
        assert diff.summary_delta.failed  == -1
        assert diff.summary_delta.skipped ==  1

    def test_remediation_carried_from_after(self):
        before = _report(checks=[
            {"category": "cdc", "name": "wal_level", "status": "PASS", "detail": ""},
        ], passed=1)
        after = _report(checks=[
            {
                "category": "cdc", "name": "wal_level", "status": "FAIL",
                "detail": "replica", "remediation": "ALTER SYSTEM SET wal_level = logical;",
            },
        ], failed=1, passed=0)
        diff = diff_reports(before, after)
        assert diff.deltas[0].remediation == "ALTER SYSTEM SET wal_level = logical;"

    def test_to_dict_structure(self):
        before = _report()
        after  = _report()
        diff = diff_reports(before, after)
        d = diff.to_dict()
        assert "before" in d
        assert "after" in d
        assert "summary_delta" in d
        assert "deltas" in d
        assert "regressions" in d
        assert "improvements" in d


# ── CheckDelta helpers ────────────────────────────────────────────────────────

class TestCheckDelta:
    def test_kind_changed(self):
        d = CheckDelta("cdc", "wal_level", before="FAIL", after="PASS")
        assert d.kind == "changed"

    def test_kind_added(self):
        d = CheckDelta("cdc", "wal_level", before=None, after="PASS")
        assert d.kind == "added"

    def test_kind_removed(self):
        d = CheckDelta("cdc", "wal_level", before="PASS", after=None)
        assert d.kind == "removed"

    def test_improved_fail_to_pass(self):
        assert CheckDelta("cdc", "x", before="FAIL", after="PASS").improved

    def test_improved_fail_to_warn(self):
        assert CheckDelta("cdc", "x", before="FAIL", after="WARN").improved

    def test_regressed_pass_to_fail(self):
        assert CheckDelta("cdc", "x", before="PASS", after="FAIL").regressed

    def test_not_regressed_when_improved(self):
        assert not CheckDelta("cdc", "x", before="FAIL", after="PASS").regressed


# ── DiffTerminalReporter ──────────────────────────────────────────────────────

class TestDiffTerminalReporter:
    def _reporter_buf(self):
        buf = StringIO()
        console = Console(file=buf, highlight=False, no_color=True)
        return DiffTerminalReporter(console=console), buf

    def _make_diff(self, deltas=None):
        return ReportDiff(
            before_path="before.json",
            after_path="after.json",
            before_timestamp="2026-05-01T09:00:00+00:00",
            after_timestamp="2026-05-01T10:00:00+00:00",
            before_host="host-a",
            after_host="host-b",
            db_type="postgres",
            deltas=deltas or [],
            summary_before={"passed": 5, "warned": 0, "failed": 1, "skipped": 0},
            summary_after= {"passed": 6, "warned": 0, "failed": 0, "skipped": 0},
            summary_delta= SummaryDelta(passed=1, failed=-1),
        )

    def test_no_changes_message_shown(self):
        reporter, buf = self._reporter_buf()
        reporter.report(self._make_diff(deltas=[]))
        assert "identical" in buf.getvalue().lower()

    def test_regression_shown(self):
        reporter, buf = self._reporter_buf()
        diff = self._make_diff(deltas=[
            CheckDelta("cdc", "wal_level", before="PASS", after="FAIL"),
        ])
        reporter.report(diff)
        output = buf.getvalue()
        assert "Regression" in output or "FAIL" in output

    def test_improvement_shown(self):
        reporter, buf = self._reporter_buf()
        diff = self._make_diff(deltas=[
            CheckDelta("cdc", "wal_level", before="FAIL", after="PASS"),
        ])
        reporter.report(diff)
        assert "Improvement" in buf.getvalue() or "PASS" in buf.getvalue()

    def test_summary_delta_shown(self):
        reporter, buf = self._reporter_buf()
        reporter.report(self._make_diff())
        assert "passed" in buf.getvalue().lower()
