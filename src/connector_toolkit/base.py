from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import Category, CheckResult, RunConfig, Status


class BaseConnector(ABC):
    """
    Abstract base for all database connector checks.

    Subclass this for each new database target and implement the four
    check methods. Register the subclass in runner.CONNECTOR_REGISTRY.

    Example
    -------
        class MongoConnector(BaseConnector):
            db_type = "mongo"

            def check_connectivity(self) -> list[CheckResult]: ...
            def check_permissions(self) -> list[CheckResult]: ...
            def check_cdc(self) -> list[CheckResult]: ...
            def check_jdbc(self) -> list[CheckResult]: ...
    """

    db_type: str = ""

    def __init__(self, config: RunConfig) -> None:
        self.config = config
        self._conn: Any = None

    # ------------------------------------------------------------------
    # Abstract check methods — each returns a list of CheckResult
    # ------------------------------------------------------------------

    @abstractmethod
    def check_connectivity(self) -> list[CheckResult]:
        """TCP reachability, authenticated connect, SSL status."""
        ...

    @abstractmethod
    def check_permissions(self) -> list[CheckResult]:
        """Replication privilege, read access, superuser / GRANTS."""
        ...

    @abstractmethod
    def check_cdc(self) -> list[CheckResult]:
        """WAL level / binlog format, slots, GTID, timeouts."""
        ...

    @abstractmethod
    def check_jdbc(self) -> list[CheckResult]:
        """Driver version compatibility, known connection issues."""
        ...

    # ------------------------------------------------------------------
    # Helpers available to all subclasses
    # ------------------------------------------------------------------

    def skip_result(self, category: Category, name: str, reason: str) -> CheckResult:
        return CheckResult(
            category=category,
            name=name,
            status=Status.SKIP,
            detail=reason,
        )

    def skipped_category(self, category: Category) -> list[CheckResult]:
        """Return a single SKIP result standing in for a whole category."""
        return [
            self.skip_result(
                category,
                category.value,
                f"Skipped via --skip {category.value}",
            )
        ]

    def _dsn(self) -> str:
        c = self.config
        return f"{c.db_type}://{c.user}:***@{c.host}:{c.port}/{c.db}"
