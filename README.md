# 🛠️ Connector Support Toolkit

> CLI tool to validate database connector readiness for PostgreSQL and MySQL — runs connectivity, permissions, CDC, and JDBC checks and reports results in the terminal or as a JSON file.

![Language](https://img.shields.io/badge/language-Python-blue?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![Status](https://img.shields.io/badge/status-active-brightgreen?style=flat-square)

---

## 🎯 Overview

A CLI diagnostic tool that validates whether a database is ready to be used as a connector source. It checks connectivity, permissions, CDC configuration, and driver compatibility — helping support engineers and developers quickly identify blockers before escalation.

---

## 🧰 Tech Stack

- **Language** — Python 3.8+
- **Databases** — PostgreSQL 15, MySQL 8.0
- **Libraries** — psycopg2-binary, mysql-connector-python, rich
- **Infrastructure** — Docker Compose
- **Output** — Terminal (colour-coded) or JSON report

---

## 📁 Project Structure

```
connector-support-toolkit/
├── docker/
├── docs/
│   ├── postgres-connector-debugging.md
│   ├── mysql-connector-debugging.md
│   ├── cdc-readiness-checklist.md
│   └── jdbc-troubleshooting.md
├── examples/
│   ├── sample_command.txt
│   └── sample_report.md
├── reports/
├── src/
│   └── connector_check.py
├── tests/
├── README.md
└── requirements.txt
```

---

## 💡 Why This Tool Exists

Database connectors often fail due to misconfiguration before data ever starts flowing.

Common issues include:

- Missing replication privileges
- Incorrect CDC configuration (WAL / binlog)
- Driver incompatibilities
- Insufficient database permissions

This tool shifts debugging **left** by validating connector readiness before ingestion begins.

---

## 🚀 Getting Started

### ✅ Prerequisites

- Docker installed and running
- Python 3.8+
- pip installed

### ▶️ Step 1 — Install dependencies

```bash
pip install -r requirements.txt
```

### ▶️ Step 2 — Run against PostgreSQL

```bash
python -m src.connector_check \
  --host localhost --port 5432 \
  --db mydb --user myuser --password mypassword \
  --db-type postgres
```

### ▶️ Step 3 — Run against MySQL

```bash
python -m src.connector_check \
  --host localhost --port 3306 \
  --db mydb --user myuser --password mypassword \
  --db-type mysql
```

### ⚙️ Full usage

```bash
python -m src.connector_check \
  --host <host> \
  --port <port> \
  --db <database> \
  --user <user> \
  --password <password> \
  --db-type postgres|mysql \
  [--output-file report.json] \
  [--skip connectivity,permissions,cdc,jdbc]
```

See `examples/sample_command.txt` for more examples including `--skip` and `--output-file`.

---

## 🔍 What It Checks

| Category | Checks |
|---|---|
| **connectivity** | TCP reachability, authenticated connect (with latency), SSL |
| **permissions** | Replication privilege, database read access, superuser status (Postgres) / SHOW GRANTS (MySQL) |
| **cdc** | `wal_level=logical`, replication slots, `wal_sender_timeout` (Postgres) / `log_bin`, `binlog_format=ROW`, `binlog_row_image=FULL`, `gtid_mode` (MySQL) |
| **jdbc** | Driver version, common connection issue reference |

Each check returns `PASS`, `WARN`, `FAIL`, or `SKIP`. A `FAIL` on any connectivity check skips all downstream categories.

---

## 📤 Output

**Terminal** (default) — colour-coded by category using rich:

```
[CONNECTIVITY]
  ✔ PASS  TCP reachability               host=localhost port=5432
  ✔ PASS  Authenticated connect          latency=3ms
  ✔ PASS  SSL                            in use: no

[PERMISSIONS]
  ✔ PASS  Replication privilege          rolreplication=true
  ⚠ WARN  Superuser status               Not superuser — CDC setup may require elevated privileges
```

**JSON** (`--output-file report.json`):

```json
{
  "timestamp": "2026-05-02T10:00:00+00:00",
  "host": "localhost",
  "db_type": "postgres",
  "summary": { "passed": 7, "warned": 1, "failed": 0, "skipped": 0 },
  "checks": [
    { "category": "connectivity", "name": "TCP reachability", "status": "PASS", "detail": "host=localhost port=5432" }
  ]
}
```

See `examples/sample_report.md` for full terminal and JSON output examples.

---

## 🧪 Local Development

### Install and test

```bash
pip install -r requirements.txt
pytest tests/
```

### Docker containers for integration testing

```bash
cd docker && docker compose up -d
```

Starts Postgres 15 on port `5435` (`wal_level=logical`) and MySQL 8.0 on port `3306` (binlog ROW, GTID ON), both with credentials `demo/demo`, database `test`.

```bash
# Postgres
python -m src.connector_check \
  --host localhost --port 5435 --db test --user demo --password demo --db-type postgres

# MySQL
python -m src.connector_check \
  --host localhost --port 3306 --db test --user demo --password demo --db-type mysql
```

---

## 📚 Reference Docs

- `docs/postgres-connector-debugging.md`
- `docs/mysql-connector-debugging.md`
- `docs/cdc-readiness-checklist.md`
- `docs/jdbc-troubleshooting.md`

---

## 🚧 Status

| Feature | Status |
|---|---|
| PostgreSQL checks (connectivity, permissions, CDC, JDBC) | ✅ Done |
| MySQL checks (connectivity, permissions, CDC, JDBC) | ✅ Done |
| JSON report output | ✅ Done |
| Docker integration test environment | ✅ Done |
| Additional database targets | 🔜 Planned |

---

## 👤 Author

**Mustapha Abella**
Senior Technical Support Engineer
Focused on API-driven SaaS, data integration, and developer-facing support

[github.com/mabella1](https://github.com/musabe)
