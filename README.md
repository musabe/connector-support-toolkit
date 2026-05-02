# 🛠️ Connector Support Toolkit

> CLI tool to validate database connector readiness for PostgreSQL and MySQL — runs connectivity, permissions, CDC, and JDBC checks and reports results in the terminal or as a JSON file.

![Language](https://img.shields.io/badge/language-Python-blue?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![Status](https://img.shields.io/badge/status-active-brightgreen?style=flat-square)

---

## 🎯 Overview

A CLI diagnostic tool that validates whether a database is ready to be used as a connector source. It checks connectivity, permissions, CDC configuration, and driver compatibility — helping support engineers and developers quickly identify root causes before escalation.

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

```bash
pip install -r requirements.txt
```

```bash
python -m src.connector_check --host localhost --port 5432 --db mydb --user myuser --password mypassword --db-type postgres
```

---

## 👤 Author

Mustapha Abella  
https://github.com/musabe
