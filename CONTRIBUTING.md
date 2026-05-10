# Contributing to connector-support-toolkit

Thank you for improving the toolkit. This guide covers everything you need to
add a new database connector, reporter, or check — and what a pull request needs
to include before it's ready to merge.

---

## Table of contents

1. [Project structure recap](#project-structure-recap)
2. [Development setup](#development-setup)
3. [Adding a new database connector](#adding-a-new-database-connector)
4. [Adding a new reporter](#adding-a-new-reporter)
5. [Adding or changing a check](#adding-or-changing-a-check)
6. [Adding remediation hints](#adding-remediation-hints)
7. [Running tests](#running-tests)
8. [Pull request checklist](#pull-request-checklist)
9. [Code style](#code-style)

---

## Project structure recap

```
src/connector_toolkit/
├── cli.py          — arg parsing and entrypoint only
├── runner.py       — orchestrates checks; holds CONNECTOR_REGISTRY and REPORTER_REGISTRY
├── base.py         — BaseConnector ABC
├── models.py       — CheckResult, Summary, RunConfig, RunReport dataclasses
├── config.py       — YAML config loader with env-var interpolation
├── remediation.py  — ALL remediation hint strings (one place, named constants)
├── checks/
│   ├── postgres.py
│   ├── mysql.py
│   └── mongo.py
└── reporters/
    ├── base.py     — BaseReporter ABC
    ├── terminal.py
    └── json_report.py
```

The only file you need to edit when adding a new connector is
`checks/<db>.py` (new) and one line in `runner.py` (registry entry).
Everything else — CLI flags, skip logic, exit codes, reporters — is automatic.

---

## Development setup

```bash
# 1. Clone and create a virtual environment
git clone https://github.com/mabella1/connector-support-toolkit
cd connector-support-toolkit
python -m venv .venv && source .venv/bin/activate

# 2. Install dependencies (including dev extras)
pip install -r requirements.txt
pip install pytest pytest-mock pyyaml

# 3. Start the local test databases
cd docker && docker compose up -d && cd ..

# 4. Run the full test suite
pytest tests/

# 5. Verify against the Docker databases
python -m src.connector_check --host localhost --port 5435 \
  --db test --user demo --password demo --db-type postgres

python -m src.connector_check --host localhost --port 3306 \
  --db test --user demo --password demo --db-type mysql
```

---

## Adding a new database connector

### Step 1 — create `checks/<db>.py`

Subclass `BaseConnector` and implement all four abstract methods.
Each method must return `list[CheckResult]`.

```python
# checks/redshift.py
from __future__ import annotations
from ..base import BaseConnector
from ..models import Category, CheckResult, Status
from .. import remediation as R


class RedshiftConnector(BaseConnector):
    db_type = "redshift"

    def check_connectivity(self) -> list[CheckResult]:
        # TCP, authenticated connect, SSL
        ...

    def check_permissions(self) -> list[CheckResult]:
        # Replication privilege, read access
        ...

    def check_cdc(self) -> list[CheckResult]:
        # Redshift-specific CDC config (e.g. STL_REPLICATION_ALERTS)
        ...

    def check_jdbc(self) -> list[CheckResult]:
        # Driver version check
        ...
```

Rules:
- Every FAIL and WARN result **must** have a `remediation` string referencing a
  constant from `remediation.py` (see [Adding remediation hints](#adding-remediation-hints)).
- A connectivity FAIL should `return results` early — the runner will skip
  downstream categories automatically, but returning early avoids confusing
  errors from subsequent checks that expect `self._conn` to be set.
- Use `self.config.timeout` for all socket and driver timeouts.
- Store the live connection on `self._conn` so permission and CDC checks can reuse it.

### Step 2 — register the connector

In `runner.py`, add one line:

```python
from .checks.redshift import RedshiftConnector

CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {
    "postgres":  PostgresConnector,
    "mysql":     MySQLConnector,
    "mongo":     MongoConnector,
    "redshift":  RedshiftConnector,   # ← add this
}
```

That's it. The CLI, config file validation, skip logic, and exit codes all
pick up the new target automatically.

### Step 3 — add to `checks/__init__.py`

```python
from .redshift import RedshiftConnector
__all__ = [..., "RedshiftConnector"]
```

### Step 4 — add a Docker service (optional but strongly preferred)

Add a service to `docker/docker-compose.yml` so integration tests can run
locally without an external database. See the existing `postgres` and `mysql`
services as a template.

### Step 5 — write tests

Create `tests/test_<db>.py`. Use `tests/fixtures/mock_db.py` (or
`unittest.mock.MagicMock`) to inject a fake connection — tests must not require
a live database. See `tests/test_postgres.py` and `tests/test_mongo.py` for
patterns.

Minimum required test coverage:
- At least one PASS case per check method.
- At least one FAIL case for every check that can fail, asserting both
  `result.status == Status.FAIL` and `result.remediation is not None`.
- At least one WARN case for every check that can warn.
- The exception path for each check method (when the query itself fails).

---

## Adding a new reporter

Subclass `BaseReporter`, implement `report(run: RunReport) -> None`,
and register it in `runner.REPORTER_REGISTRY`.

```python
# reporters/markdown.py
from ..models import RunReport
from .base import BaseReporter


class MarkdownReporter(BaseReporter):
    reporter_type = "markdown"

    def report(self, run: RunReport) -> None:
        lines = [f"# Connector check — {run.config.host}\n"]
        for result in run.results:
            icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "SKIP": "–"}[result.status.value]
            lines.append(f"- {icon} **{result.name}** — {result.detail}")
            if result.remediation:
                lines.append(f"  > {result.remediation}")
        print("\n".join(lines))
```

Then in `runner.py`:

```python
from .reporters.markdown import MarkdownReporter

REPORTER_REGISTRY = {
    "terminal": TerminalReporter,
    "json":     JsonReporter,
    "markdown": MarkdownReporter,   # ← add this
}
```

---

## Adding or changing a check

To add a new check inside an existing connector:

1. Add it to the appropriate method (`check_connectivity`, `check_permissions`,
   `check_cdc`, or `check_jdbc`).
2. Return a `CheckResult` with a meaningful `name`, the correct `category`,
   and — if the result can be FAIL or WARN — a `remediation` constant from
   `remediation.py`.
3. Add a test for the new check in the corresponding `tests/test_<db>.py`.

To change an existing check's behaviour, update the check **and** its
remediation hint. A FAIL with a stale hint is worse than no hint.

---

## Adding remediation hints

All hint strings live in `remediation.py`. Never inline a hint string directly
into a connector — always define a named constant and reference it.

Naming convention: `<DB>_<CATEGORY>_<DESCRIPTION>`
- `PG_` — PostgreSQL
- `MY_` — MySQL
- `MG_` — MongoDB
- `SHARED_` — applies to multiple databases

Hint format — every hint should answer three questions:
1. **What** is wrong (one sentence).
2. **Why** it matters for CDC / connector operation.
3. **How** to fix it — include the exact SQL, config change, or shell command.

For fixes that require a server restart, say so explicitly. For fixes that
interpolate runtime values (username, db name, current value), use
`.format(user=..., value=...)` placeholders.

```python
# Good
MG_OPLOG_SIZE_WARN = (
    "The oplog window is shorter than recommended (current: ~{value} hours). "
    "A small oplog risks losing change events during connector downtime. "
    "Recommended minimum: 24 hours.\n"
    "Fix: db.adminCommand({{ replSetResizeOplog: 1, size: 51200 }})"
)

# Bad — no context, no command, vague
MG_OPLOG_SIZE_WARN = "Oplog too small."
```

---

## Running tests

```bash
# All tests (no live database required)
pytest tests/

# A specific file
pytest tests/test_postgres.py -v

# Show output on failure
pytest tests/ -s

# With coverage
pip install pytest-cov
pytest tests/ --cov=connector_toolkit --cov-report=term-missing
```

Tests are split into:
- `tests/test_postgres.py` — PostgresConnector
- `tests/test_mysql.py` — MySQLConnector
- `tests/test_mongo.py` — MongoConnector
- `tests/test_config.py` — YAML config loader and env-var interpolation
- `tests/test_exit_codes.py` — runner.exit_code() and all four exit paths
- `tests/test_reporters.py` — terminal and JSON reporter output
- `tests/fixtures/mock_db.py` — shared mock connection and cursor

---

## Pull request checklist

Before opening a PR, confirm all of the following:

- [ ] `pytest tests/` passes with no failures or warnings
- [ ] Every new FAIL/WARN result has a `remediation` constant in `remediation.py`
- [ ] New constants follow the `<DB>_<CATEGORY>_<DESCRIPTION>` naming convention
- [ ] New connector is registered in `runner.CONNECTOR_REGISTRY`
- [ ] New connector is exported from `checks/__init__.py`
- [ ] Tests cover at least one PASS, FAIL, and WARN case per check method
- [ ] Exception paths (when a query fails) are tested
- [ ] No credentials, passwords, or tokens appear anywhere in the diff
- [ ] `toolkit.example.yml` updated if new config fields were added
- [ ] `README.md` updated if new `--db-type` values or CLI flags were added

---

## Code style

- Python 3.10+ (uses `match` statements in `models.py`).
- `from __future__ import annotations` at the top of every file.
- Type hints on all function signatures.
- No third-party linters are enforced, but the existing code follows PEP 8
  with 100-character line length.
- Keep `cli.py` free of business logic. If you find yourself writing an `if`
  in `cli.py` that isn't about argument parsing, it belongs in `runner.py` or
  a connector method.
