from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Status(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"


class Category(str, Enum):
    CONNECTIVITY = "connectivity"
    PERMISSIONS = "permissions"
    CDC = "cdc"
    JDBC = "jdbc"


@dataclass
class CheckResult:
    category: Category
    name: str
    status: Status
    detail: str = ""
    remediation: Optional[str] = None

    def passed(self) -> bool:
        return self.status == Status.PASS

    def failed(self) -> bool:
        return self.status == Status.FAIL

    def to_dict(self) -> dict:
        d = {
            "category": self.category.value,
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
        }
        if self.remediation:
            d["remediation"] = self.remediation
        return d


@dataclass
class Summary:
    passed: int = 0
    warned: int = 0
    failed: int = 0
    skipped: int = 0

    @classmethod
    def from_results(cls, results: list[CheckResult]) -> Summary:
        s = cls()
        for r in results:
            match r.status:
                case Status.PASS:
                    s.passed += 1
                case Status.WARN:
                    s.warned += 1
                case Status.FAIL:
                    s.failed += 1
                case Status.SKIP:
                    s.skipped += 1
        return s

    def any_failed(self) -> bool:
        return self.failed > 0

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "warned": self.warned,
            "failed": self.failed,
            "skipped": self.skipped,
        }


@dataclass
class RunConfig:
    host: str
    port: int
    db: str
    user: str
    password: str
    db_type: str
    skip: list[Category] = field(default_factory=list)
    output_file: Optional[str] = None
    timeout: int = 10


@dataclass
class RunReport:
    config: RunConfig
    results: list[CheckResult]
    summary: Summary
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "host": self.config.host,
            "db_type": self.config.db_type,
            "summary": self.summary.to_dict(),
            "checks": [r.to_dict() for r in self.results],
        }
