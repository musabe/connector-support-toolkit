# Changelog

All notable changes to connector-support-toolkit are documented here.

This project follows [Semantic Versioning](https://semver.org/):
- **PATCH** (`1.0.x`) — bug fixes, remediation hint corrections, doc updates
- **MINOR** (`1.x.0`) — new checks within an existing connector, new reporters, backwards-compatible config fields
- **MAJOR** (`x.0.0`) — new database connectors, breaking CLI or config changes, removed flags

When embedding this tool in a runbook or CI pipeline, pin to a minor version
(`~=1.2`) so you get bug fixes automatically but no new required config fields.

---

## [Unreleased]

### Added
- `MongoConnector` — connectivity, permissions, CDC (replica set topology,
  oplog window, change stream smoke-test), and driver checks for MongoDB
  replica sets and sharded clusters (`checks/mongo.py`)
- MongoDB remediation hints in `remediation.py` (14 new constants: `MG_*`)
- YAML config file support (`--config toolkit.yml`) with `${VAR}` and
  `${VAR:-default}` env-var interpolation (`config.py`)
- `toolkit.example.yml` — annotated config schema with common setup examples
- Exit code 3 (`EXIT_SKIPPED`) when all checks are skipped via `--skip`
- Symbolic exit code constants (`EXIT_PASS`, `EXIT_FAIL`, `EXIT_WARN`,
  `EXIT_SKIPPED`) in `runner.py` for use in scripts and tests
- `CONTRIBUTING.md` — contributor guide covering new connectors, reporters,
  checks, remediation hints, and PR checklist
- Centralised remediation hint catalogue (`remediation.py`) — all FAIL/WARN
  hints now live as named constants; no inline strings in connectors
- `tests/test_exit_codes.py` — 8 tests covering all four exit code paths
- `tests/test_mongo.py` — 11 tests for MongoConnector using MagicMock
- `tests/test_config.py` — 20 tests for the YAML loader and interpolation

### Changed
- Refactored monolithic `connector_check.py` into pluggable package structure:
  `checks/`, `reporters/`, `runner.py`, `cli.py`, `models.py`, `base.py`
- `--host`, `--port`, `--db`, `--user`, `--password`, `--db-type` are now
  optional when `--config` is supplied; CLI flags always override file values
- `wal_sender_timeout` check now emits WARN (not PASS) when value is `0`
  (disabled), which can mask stalled CDC consumers
- PostgreSQL `Superuser status` WARN now includes a remediation hint
  (`GRANT pg_monitor TO <user>`)
- All exception-path FAILs now include remediation hints (previously silent)

### Fixed
- SSL WARN on both PostgreSQL and MySQL was missing remediation hint
- MySQL CDC variable checks were using inline strings instead of catalogue constants

---

## [1.0.0] — 2026-04-15

### Added
- PostgreSQL checks: connectivity (TCP, authenticated connect, SSL),
  permissions (replication privilege, superuser status, database read access),
  CDC (`wal_level`, replication slots, `wal_sender_timeout`), JDBC driver version
- MySQL checks: connectivity (TCP, authenticated connect, SSL),
  permissions (`SHOW GRANTS`, replication slave, SELECT access),
  CDC (`log_bin`, `binlog_format`, `binlog_row_image`, `gtid_mode`), JDBC driver version
- Terminal reporter with colour-coded output via `rich`
- JSON reporter (`--output-file report.json`)
- `--skip` flag to exclude categories: `connectivity,permissions,cdc,jdbc`
- `--timeout` flag for connection and query timeouts
- Exit codes: 0 (all pass), 1 (any fail), 2 (warn only)
- Docker Compose environment for local integration testing
  (Postgres 15 on port 5435, MySQL 8.0 on port 3306)
- Reference docs: `postgres-connector-debugging.md`, `mysql-connector-debugging.md`,
  `cdc-readiness-checklist.md`, `jdbc-troubleshooting.md`

---

## Version history summary

| Version | Date       | Highlights                                      |
|---------|------------|-------------------------------------------------|
| 1.1.0   | unreleased | MongoDB, config file, pluggable architecture    |
| 1.0.0   | 2026-04-15 | PostgreSQL + MySQL checks, terminal + JSON output |
