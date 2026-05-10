"""
Report diff engine.

Loads two JSON reports produced by --output-file and computes a structured
diff: checks that changed status, checks that appeared or disappeared, and
a summary delta showing how counts moved between runs.

Usage (from CLI):
    connector-check compare report-before.json report-after.json
    connector-check compare report-before.json report-after.json --output-file diff.json

Public API:
    diff_reports(before, after) -> ReportDiff
    load_report(path)           -> dict          (raw JSON, validated)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Exceptions ────────────────────────────────────────────────────────────────

class DiffError(Exception):
    """Raised for invalid or incompatible report files."""


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class CheckDelta:
    """A single check whose status changed, appeared, or disappeared."""
    category: str
    name: str
    before: Optional[str]   # status string or None if check didn't exist
    after: Optional[str]    # status string or None if check was removed
    detail_before: str = ""
    detail_after: str = ""
    remediation: Optional[str] = None  # from the 'after' report

    @property
    def kind(self) -> str:
        """Human-readable change type."""
        if self.before is None:
            return "added"
        if self.after is None:
            return "removed"
        return "changed"

    @property
    def improved(self) -> bool:
        """True when the status moved toward PASS (FAIL→WARN, FAIL→PASS, WARN→PASS)."""
        _rank = {"PASS": 0, "WARN": 1, "SKIP": 2, "FAIL": 3}
        if self.before is None or self.after is None:
            return False
        return _rank.get(self.after, 99) < _rank.get(self.before, 99)

    @property
    def regressed(self) -> bool:
        """True when the status moved away from PASS."""
        return not self.improved and self.before != self.after and self.kind == "changed"

    def to_dict(self) -> dict:
        d = {
            "category": self.category,
            "name": self.name,
            "kind": self.kind,
            "before": self.before,
            "after": self.after,
        }
        if self.detail_before:
            d["detail_before"] = self.detail_before
        if self.detail_after:
            d["detail_after"] = self.detail_after
        if self.remediation:
            d["remediation"] = self.remediation
        return d


@dataclass
class SummaryDelta:
    passed:  int = 0
    warned:  int = 0
    failed:  int = 0
    skipped: int = 0

    def to_dict(self) -> dict:
        return {
            "passed":  self.passed,
            "warned":  self.warned,
            "failed":  self.failed,
            "skipped": self.skipped,
        }

    def any_nonzero(self) -> bool:
        return any([self.passed, self.warned, self.failed, self.skipped])


@dataclass
class ReportDiff:
    before_path: str
    after_path: str
    before_timestamp: str
    after_timestamp: str
    before_host: str
    after_host: str
    db_type: str
    deltas: list[CheckDelta] = field(default_factory=list)
    summary_before: dict = field(default_factory=dict)
    summary_after: dict = field(default_factory=dict)
    summary_delta: SummaryDelta = field(default_factory=SummaryDelta)

    @property
    def regressions(self) -> list[CheckDelta]:
        return [d for d in self.deltas if d.regressed]

    @property
    def improvements(self) -> list[CheckDelta]:
        return [d for d in self.deltas if d.improved]

    @property
    def added(self) -> list[CheckDelta]:
        return [d for d in self.deltas if d.kind == "added"]

    @property
    def removed(self) -> list[CheckDelta]:
        return [d for d in self.deltas if d.kind == "removed"]

    def to_dict(self) -> dict:
        return {
            "before": {
                "path": self.before_path,
                "timestamp": self.before_timestamp,
                "host": self.before_host,
            },
            "after": {
                "path": self.after_path,
                "timestamp": self.after_timestamp,
                "host": self.after_host,
            },
            "db_type": self.db_type,
            "summary_before": self.summary_before,
            "summary_after": self.summary_after,
            "summary_delta": self.summary_delta.to_dict(),
            "regressions": len(self.regressions),
            "improvements": len(self.improvements),
            "deltas": [d.to_dict() for d in self.deltas],
        }


# ── Loading ───────────────────────────────────────────────────────────────────

_REQUIRED_KEYS = {"timestamp", "host", "db_type", "summary", "checks"}


def load_report(path: str | Path) -> dict:
    """
    Load and validate a JSON report file.
    Raises DiffError on missing file, invalid JSON, or missing required keys.
    """
    p = Path(path)
    if not p.exists():
        raise DiffError(f"Report file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DiffError(f"Invalid JSON in '{p}': {exc}") from exc
    if not isinstance(data, dict):
        raise DiffError(f"Report '{p}' must be a JSON object, got {type(data).__name__}")
    missing = _REQUIRED_KEYS - data.keys()
    if missing:
        raise DiffError(
            f"Report '{p}' is missing required keys: {', '.join(sorted(missing))}. "
            f"Make sure it was produced with --output-file."
        )
    return data


# ── Diff engine ───────────────────────────────────────────────────────────────

def _check_key(check: dict) -> str:
    """Stable identity key for a check: category + name."""
    return f"{check['category']}::{check['name']}"


def diff_reports(before: dict, after: dict) -> ReportDiff:
    """
    Compare two loaded report dicts and return a ReportDiff.

    Checks are matched by (category, name). Status changes, additions, and
    removals are all captured. db_type mismatch raises DiffError.
    """
    if before["db_type"] != after["db_type"]:
        raise DiffError(
            f"Cannot diff reports from different database types: "
            f"'{before['db_type']}' vs '{after['db_type']}'. "
            f"Both reports must be for the same db_type."
        )

    before_map = {_check_key(c): c for c in before.get("checks", [])}
    after_map  = {_check_key(c): c for c in after.get("checks", [])}
    all_keys   = sorted(set(before_map) | set(after_map))

    deltas: list[CheckDelta] = []
    for key in all_keys:
        b = before_map.get(key)
        a = after_map.get(key)

        b_status = b["status"] if b else None
        a_status = a["status"] if a else None

        if b_status == a_status:
            continue  # unchanged — skip

        deltas.append(CheckDelta(
            category=      (a or b)["category"],
            name=          (a or b)["name"],
            before=        b_status,
            after=         a_status,
            detail_before= b.get("detail", "") if b else "",
            detail_after=  a.get("detail", "") if a else "",
            remediation=   a.get("remediation") if a else None,
        ))

    # Summary delta (after − before, so positive = more of that status)
    bs = before.get("summary", {})
    as_ = after.get("summary", {})
    delta = SummaryDelta(
        passed=  as_.get("passed",  0) - bs.get("passed",  0),
        warned=  as_.get("warned",  0) - bs.get("warned",  0),
        failed=  as_.get("failed",  0) - bs.get("failed",  0),
        skipped= as_.get("skipped", 0) - bs.get("skipped", 0),
    )

    return ReportDiff(
        before_path=      str(before.get("_source_path", "before")),
        after_path=       str(after.get("_source_path", "after")),
        before_timestamp= before.get("timestamp", ""),
        after_timestamp=  after.get("timestamp", ""),
        before_host=      before.get("host", ""),
        after_host=       after.get("host", ""),
        db_type=          before["db_type"],
        deltas=           deltas,
        summary_before=   bs,
        summary_after=    as_,
        summary_delta=    delta,
    )
