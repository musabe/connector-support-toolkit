# Sample Report

## Terminal output

```
[CONNECTIVITY]
  ✔ PASS  TCP reachability               host=localhost port=5432
  ✔ PASS  Authenticated connect          latency=3ms
  ✔ PASS  SSL                            in use: no

[PERMISSIONS]
  ✔ PASS  Replication privilege          rolreplication=true
  ✔ PASS  Database read access           CONNECT privilege granted
  ⚠ WARN  Superuser status               Not superuser — CDC setup may require elevated privileges

[CDC]
  ✔ PASS  wal_level                      logical
  ✔ PASS  Replication slots              1/10 used
  ✔ PASS  wal_sender_timeout             60000

[JDBC]
  ✔ PASS  Driver version                 psycopg2==2.9.9
  ✔ PASS  Common issues reference        Connection refused: check host/port/firewall. SSL handshake: set sslmode=require or sslmode=disable. Auth failure: verify pg_hba.conf allows md5/scram-sha-256.
```

## JSON report (`--output-file report.json`)

```json
{
  "timestamp": "2026-05-02T10:00:00+00:00",
  "host": "localhost",
  "db_type": "postgres",
  "summary": {
    "passed": 7,
    "warned": 1,
    "failed": 0,
    "skipped": 0
  },
  "checks": [
    { "category": "connectivity", "name": "TCP reachability",        "status": "PASS", "detail": "host=localhost port=5432" },
    { "category": "connectivity", "name": "Authenticated connect",   "status": "PASS", "detail": "latency=3ms" },
    { "category": "connectivity", "name": "SSL",                     "status": "PASS", "detail": "in use: no" },
    { "category": "permissions",  "name": "Replication privilege",   "status": "PASS", "detail": "rolreplication=true" },
    { "category": "permissions",  "name": "Database read access",    "status": "PASS", "detail": "CONNECT privilege granted" },
    { "category": "permissions",  "name": "Superuser status",        "status": "WARN", "detail": "Not superuser — CDC setup may require elevated privileges" },
    { "category": "cdc",          "name": "wal_level",               "status": "PASS", "detail": "logical" },
    { "category": "cdc",          "name": "Replication slots",       "status": "PASS", "detail": "1/10 used" },
    { "category": "cdc",          "name": "wal_sender_timeout",      "status": "PASS", "detail": "60000" },
    { "category": "jdbc",         "name": "Driver version",          "status": "PASS", "detail": "psycopg2==2.9.9" },
    { "category": "jdbc",         "name": "Common issues reference", "status": "PASS", "detail": "Connection refused: check host/port/firewall. SSL handshake: set sslmode=require or sslmode=disable. Auth failure: verify pg_hba.conf allows md5/scram-sha-256." }
  ]
}
```

## Failure example — CDC not configured

Terminal output when `wal_level` is `replica` and connectivity succeeds:

```
[CONNECTIVITY]
  ✔ PASS  TCP reachability               host=prod-db port=5432
  ✔ PASS  Authenticated connect          latency=12ms
  ✔ PASS  SSL                            in use: yes

[PERMISSIONS]
  ✔ PASS  Replication privilege          rolreplication=true
  ✔ PASS  Database read access           CONNECT privilege granted
  ⚠ WARN  Superuser status               Not superuser — CDC setup may require elevated privileges

[CDC]
  ✗ FAIL  wal_level                      wal_level=replica (must be logical)
  ✔ PASS  Replication slots              0/10 used
  ✔ PASS  wal_sender_timeout             60000

[JDBC]
  ✔ PASS  Driver version                 psycopg2==2.9.9
  ✔ PASS  Common issues reference        Connection refused: check host/port/firewall. ...
```

## Connectivity failure example — all downstream checks skipped

```
[CONNECTIVITY]
  ✗ FAIL  TCP reachability               [Errno 111] Connection refused

[PERMISSIONS]
  – SKIP  All checks                     Skipped — connectivity failed

[CDC]
  – SKIP  All checks                     Skipped — connectivity failed

[JDBC]
  – SKIP  All checks                     Skipped — connectivity failed
```
