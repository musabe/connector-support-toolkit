# Incident scenarios

Pre-built scenarios that simulate real support escalations. Each scenario
is a YAML config that connects to a deliberately misconfigured database
and produces the expected FAILs.

## Quick start

```bash
# Start all scenario containers
docker compose -f docker/docker-compose-scenarios.yml up -d

# Run a scenario
python -m src.connector_check --config scenarios/pg-no-replication.yml
python -m src.connector_check --config scenarios/pg-wal-not-logical.yml
python -m src.connector_check --config scenarios/pg-unreachable.yml
python -m src.connector_check --config scenarios/mysql-binlog-off.yml
python -m src.connector_check --config scenarios/mysql-no-replication.yml
python -m src.connector_check --config scenarios/mysql-wrong-binlog-format.yml

# Run all scenario integration tests
pytest tests/test_scenarios.py -v

# Stop containers when done
docker compose -f docker/docker-compose-scenarios.yml down
```

## Scenario reference

| File | DB | Port | What's broken | Expected FAIL |
|------|----|----|---|---|
| `pg-all-pass.yml` | Postgres | 5435 | Nothing — baseline | — |
| `pg-no-replication.yml` | Postgres | 5436 | User lacks `REPLICATION` role | Replication privilege |
| `pg-wal-not-logical.yml` | Postgres | 5437 | `wal_level=replica` | wal_level |
| `pg-unreachable.yml` | Postgres | — | Wrong host | TCP reachability |
| `mysql-all-pass.yml` | MySQL | 3306 | Nothing — baseline | — |
| `mysql-binlog-off.yml` | MySQL | 3307 | `log_bin=OFF` | log_bin |
| `mysql-no-replication.yml` | MySQL | 3308 | User lacks `REPLICATION SLAVE` | Replication privilege |
| `mysql-wrong-binlog-format.yml` | MySQL | 3309 | `binlog_format=STATEMENT` | binlog_format |

## Adding a new scenario

1. Add a YAML file to `scenarios/` following the existing pattern.
2. If it needs a misconfigured container, add a service to
   `docker/docker-compose-scenarios.yml` and an init SQL script to
   `docker/init/`.
3. Add test assertions to `tests/test_scenarios.py`.

## Use in demos

These scenarios are ideal for showing customers or new engineers exactly
what a specific misconfiguration looks like — run the failing scenario,
show the remediation hint, apply the fix, run the passing scenario.

The `pg-unreachable.yml` scenario requires no Docker — it points at a
non-existent host and can be run anywhere to demonstrate the connectivity
cascade (TCP FAIL → all downstream SKIP).
