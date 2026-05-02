# Connector Support Toolkit — Implementation Design

**Date:** 2026-05-02
**Status:** Approved

---

## Overview

A CLI tool that validates database connector readiness and troubleshoots common issues for PostgreSQL and MySQL. Runs four categories of checks, prints colored terminal output, and optionally writes a machine-readable JSON report.

---

## Architecture

```
src/
  connector_check.py     # CLI entry point (argparse)
  runner.py              # CheckRunner: orchestrates checks, collects results
  reporter.py            # Terminal output (rich) + JSON report writer
  models.py              # CheckResult dataclass
  checkers/
    __init__.py
    base.py              # BaseChecker abstract class
    postgres.py          # PostgresChecker(BaseChecker)
    mysql.py             # MySQLChecker(BaseChecker)
```

`BaseChecker` defines four abstract methods — one per check category. `PostgresChecker` and `MySQLChecker` each implement all four. `CheckRunner` instantiates the right checker based on `--db-type`, runs all checks in order, and hands results to `Reporter`. `Reporter` handles terminal and JSON output independently of checker logic.

---

## Check Categories

Each checker implements four categories, run in order:

### 1. Connectivity
- TCP reachability (socket connect to host:port)
- Authenticated DB connection (psycopg2 / mysql-connector-python)
- Round-trip latency measurement
- SSL in use (yes/no)

### 2. Permissions
- Replication privilege (`pg_has_role` for Postgres / `SHOW GRANTS` for MySQL)
- Read access to target database
- Superuser status (warn if not superuser — CDC setup typically requires it)

### 3. CDC Readiness
**Postgres:**
- `wal_level = logical`
- Max replication slots vs. used slots (FAIL if none available)
- `wal_sender_timeout` value

**MySQL:**
- `log_bin = ON`
- `binlog_format = ROW`
- `binlog_row_image = FULL`
- `gtid_mode` status

### 4. JDBC / Driver
- Detected driver version (`psycopg2.__version__` / `mysql.connector.__version__`)
- Known issue flags (psycopg2 < 2.9 asyncio incompatibility, MySQL connector SSL quirks)
- Static guidance text for common errors: connection refused, SSL handshake failure, auth plugin mismatch

---

## Check Result Model

```python
@dataclass
class CheckResult:
    category: str       # connectivity | permissions | cdc | jdbc
    name: str           # human-readable check name
    status: str         # PASS | WARN | FAIL | SKIP
    detail: str         # description or error message
```

---

## CLI Interface

```
python connector_check.py
  --host        DB hostname (required)
  --port        DB port (required)
  --db          Database name (required)
  --user        Username (required)
  --password    Password (required)
  --db-type     postgres | mysql (required)
  --output-file Path to save JSON report (optional)
  --skip        Comma-separated categories to skip: connectivity,permissions,cdc,jdbc (optional)
```

---

## Output

### Terminal (rich)

Checks grouped by category, each on one line with a colored status badge:

```
[Connectivity]
  ✔ PASS  TCP reachability       host=localhost port=5432
  ✔ PASS  Authenticated connect  latency=12ms
  ✔ PASS  SSL                    in use: yes

[CDC Readiness]
  ✔ PASS  wal_level              logical
  ✗ FAIL  Replication slots      3/3 used — no slots available
```

Status colors: PASS=green, WARN=yellow, FAIL=red, SKIP=dim

### JSON Report (written when `--output-file` is set)

```json
{
  "timestamp": "2026-05-02T11:30:00Z",
  "host": "localhost",
  "db_type": "postgres",
  "summary": {"passed": 8, "warned": 1, "failed": 1, "skipped": 0},
  "checks": [
    {
      "category": "cdc",
      "name": "Replication slots",
      "status": "FAIL",
      "detail": "3/3 used — no slots available"
    }
  ]
}
```

---

## Error Handling

- If the DB connection fails, connectivity checks mark as `FAIL` and all downstream checks are marked `SKIP` — no point checking permissions or CDC if connectivity is broken.
- Individual check failures (e.g., permission denied querying `pg_settings`) catch the exception, mark that check `FAIL` with the error message as detail, and continue — one bad check does not abort the run.
- Missing optional dependency (e.g., `psycopg2` not installed) exits early with a clear install message before any checks run.

---

## Testing

- Unit tests in `tests/test_checks.py` use `unittest.mock` to patch DB connections — no live DB required.
- One test class per checker: `TestPostgresChecker`, `TestMySQLChecker`.
- Tests cover: PASS case, FAIL case, exception-during-check case, and the skip-on-connection-failure cascade.
- `docker/docker-compose.yml` provides Postgres + MySQL services for optional integration testing.

---

## Dependencies

```
psycopg2-binary
mysql-connector-python
rich
```
