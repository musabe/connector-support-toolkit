from __future__ import annotations

import sys
import time
import traceback

from .base import BaseConnector
from .checks.postgres import PostgresConnector
from .checks.mysql import MySQLConnector
from .checks.mongo import MongoConnector
from .checks.redshift import RedshiftConnector
from .models import Category, RunConfig, RunReport, Summary
from .reporters.base import BaseReporter
from .reporters.terminal import TerminalReporter
from .reporters.json_report import JsonReporter
from .reporters.html_report import HtmlReporter

# ------------------------------------------------------------------
# Registries — add new targets here, nothing else changes
# ------------------------------------------------------------------

CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {
    "postgres": PostgresConnector,
    "mysql":    MySQLConnector,
    "mongo":    MongoConnector,
    "redshift": RedshiftConnector,
}

REPORTER_REGISTRY: dict[str, type[BaseReporter]] = {
    "terminal": TerminalReporter,
    "json":     JsonReporter,
    "html":     HtmlReporter,
}

# Checks run in this order; connectivity failure skips the rest
_CHECK_ORDER = [
    Category.CONNECTIVITY,
    Category.PERMISSIONS,
    Category.CDC,
    Category.JDBC,
]

_CHECK_METHOD = {
    Category.CONNECTIVITY: "check_connectivity",
    Category.PERMISSIONS: "check_permissions",
    Category.CDC: "check_cdc",
    Category.JDBC: "check_jdbc",
}


def run(config: RunConfig) -> RunReport:
    connector_cls = CONNECTOR_REGISTRY.get(config.db_type)
    if connector_cls is None:
        supported = ", ".join(CONNECTOR_REGISTRY)
        print(f"Unknown db-type '{config.db_type}'. Supported: {supported}", file=sys.stderr)
        sys.exit(1)

    connector = connector_cls(config)
    all_results = []
    connectivity_failed = False
    run_start = time.monotonic()

    for category in _CHECK_ORDER:
        if category in config.skip:
            all_results.extend(connector.skipped_category(category))
            continue

        if connectivity_failed and category != Category.CONNECTIVITY:
            all_results.extend(connector.skipped_category(category))
            continue

        method = getattr(connector, _CHECK_METHOD[category])
        category_start = time.monotonic()

        try:
            results = method()
        except Exception as exc:
            # Unexpected exception from the check method itself — wrap it
            tb = traceback.format_exc() if config.verbose else None
            from .models import CheckResult, Status
            results = [CheckResult(
                category=category,
                name=f"{category.value} (unexpected error)",
                status=Status.FAIL,
                detail=str(exc),
                exception=tb,
            )]

        category_ms = int((time.monotonic() - category_start) * 1000)

        # Distribute category time across its results proportionally
        if results:
            per_check_ms = category_ms // len(results)
            for r in results:
                if r.duration_ms is None:
                    r.duration_ms = per_check_ms

        all_results.extend(results)

        if category == Category.CONNECTIVITY and any(r.failed() for r in results):
            connectivity_failed = True

    total_ms = int((time.monotonic() - run_start) * 1000)
    summary = Summary.from_results(all_results)
    report = RunReport(
        config=config,
        results=all_results,
        summary=summary,
        total_duration_ms=total_ms,
    )

    reporter_key = "terminal"
    if config.output_file:
        if config.output_file.endswith(".html") or config.output_file.endswith(".htm"):
            reporter_key = "html"
        else:
            reporter_key = "json"

    reporter_cls = REPORTER_REGISTRY[reporter_key]
    reporter_cls().report(report)

    return report


def exit_code(report: RunReport) -> int:
    """
    Return a POSIX exit code suitable for CI/CD gating.

    Code  Meaning                         Script usage
    ----  ------------------------------  ----------------------------------------
    0     All checks passed               Safe to proceed with ingestion setup
    1     One or more checks FAILED       Block pipeline; connector will not work
    2     No failures but WARNs present   Investigate before going to production
    3     All checks were skipped         Nothing ran; check your --skip flags

    Bash — fail pipeline on any FAIL or WARN:
        connector-check --config toolkit.yml || exit 1

    Bash — fail only on hard FAIL, tolerate WARNs:
        connector-check --config toolkit.yml
        code=$?; [ $code -eq 1 ] && exit 1 || exit 0

    GitHub Actions — step fails automatically on exit 1 or 2:
        - run: connector-check --config toolkit.yml
    """
    if report.summary.failed:
        return EXIT_FAIL
    if report.summary.warned:
        return EXIT_WARN
    total = sum([
        report.summary.passed,
        report.summary.warned,
        report.summary.failed,
        report.summary.skipped,
    ])
    if total > 0 and total == report.summary.skipped:
        return EXIT_SKIPPED
    return EXIT_PASS


# Symbolic constants — import these in scripts and tests instead of bare ints
EXIT_PASS    = 0  # noqa: E221  all checks passed
EXIT_FAIL    = 1  # noqa: E221  one or more FAILs
EXIT_WARN    = 2  # noqa: E221  no FAILs, at least one WARN
EXIT_SKIPPED = 3  # all checks were skipped
