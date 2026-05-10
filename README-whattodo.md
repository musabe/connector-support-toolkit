# What to do when a check fails

This section maps every possible FAIL and WARN result to a concrete next step.
The tool prints a remediation hint beneath each failing check in the terminal —
this table is the full reference version, organized by database and category.

**Exit codes at a glance:**

| Code | Meaning | Action |
|------|---------|--------|
| `0` | All checks passed | Safe to proceed |
| `1` | One or more FAILs | Fix before connecting — the connector will not work |
| `2` | Warns only, no FAILs | Connector may work but investigate before production |
| `3` | All checks skipped | Nothing ran — check your `--skip` flags |

---

## PostgreSQL

### Connectivity

| Check | Status | What it means | Fix |
|-------|--------|--------------|-----|
| TCP reachability | FAIL | The host or port is not reachable | Verify the server is running. Check firewall/security-group rules. Try: `nc -zv <host> <port>` |
| Authenticated connect | FAIL | Credentials rejected or user lacks CONNECT | Verify password. Check `pg_hba.conf` allows this IP with the configured auth method (`md5` / `scram-sha-256`). Run: `GRANT CONNECT ON DATABASE <db> TO <user>;` |
| SSL | WARN | Could not determine SSL status | Non-critical — connection succeeded. If SSL is required add `sslmode=require` to the connection string and set `ssl=on` in `postgresql.conf` |

### Permissions

| Check | Status | What it means | Fix |
|-------|--------|--------------|-----|
| Replication privilege | FAIL | User cannot replicate — CDC will not start | `ALTER ROLE <user> REPLICATION;` |
| Superuser status | WARN | User is not superuser | Usually fine. If CDC setup fails, grant minimal roles: `GRANT pg_monitor TO <user>;` |
| Database read access | FAIL | User lacks CONNECT on the database | `GRANT CONNECT ON DATABASE <db> TO <user>;` |
| Replication privilege *(query error)* | FAIL | Could not read `pg_roles` | `GRANT SELECT ON pg_catalog.pg_roles TO <user>;` or run as superuser |

### CDC

| Check | Status | What it means | Fix |
|-------|--------|--------------|-----|
| `wal_level` | FAIL | Not set to `logical` — change streams disabled | `ALTER SYSTEM SET wal_level = logical;` then **restart PostgreSQL**. Verify: `SHOW wal_level;` |
| `wal_sender_timeout` | WARN | Set to `0` (disabled) — stalled consumers won't be detected | `ALTER SYSTEM SET wal_sender_timeout = '60s';` |
| CDC configuration *(query error)* | FAIL | User cannot run `SHOW` on server variables | `GRANT pg_monitor TO <user>;` |

### JDBC

| Check | Status | What it means | Fix |
|-------|--------|--------------|-----|
| Driver version | FAIL | `psycopg2` not installed | `pip install psycopg2-binary` (dev) or `pip install psycopg2` (production) |
| Driver version | WARN | `psycopg2` older than 2.9 | `pip install --upgrade psycopg2-binary` |

---

## MySQL

### Connectivity

| Check | Status | What it means | Fix |
|-------|--------|--------------|-----|
| TCP reachability | FAIL | Host or port not reachable | Verify the server is running and the port is open. Try: `nc -zv <host> <port>` |
| Authenticated connect | FAIL | Credentials rejected or user host-scoped to wrong host | Verify password. MySQL users are host-scoped — a user created as `'user'@'localhost'` cannot connect remotely. Check: `SELECT user, host FROM mysql.user WHERE user='<user>';` |
| SSL | WARN | Could not determine SSL cipher | Non-critical. If SSL is required, add `ssl_ca`, `ssl_cert`, `ssl_key` to `my.cnf` and `ssl_disabled=False` to the connector |

### Permissions

| Check | Status | What it means | Fix |
|-------|--------|--------------|-----|
| Replication privilege | FAIL | User lacks `REPLICATION SLAVE` | `GRANT REPLICATION SLAVE ON *.* TO '<user>'@'%'; FLUSH PRIVILEGES;` Also grant `REPLICATION CLIENT` if `SHOW MASTER STATUS` is needed |
| Database read access | FAIL | User lacks `SELECT` on target database | `GRANT SELECT ON <db>.* TO '<user>'@'%'; FLUSH PRIVILEGES;` |
| SHOW GRANTS *(query error)* | FAIL | Could not read grants | Connect as DBA and run: `SHOW GRANTS FOR '<user>'@'%';` |

### CDC

| Check | Status | What it means | Fix |
|-------|--------|--------------|-----|
| `log_bin` | FAIL | Binary logging disabled — CDC impossible | Add to `my.cnf` under `[mysqld]`: `log_bin = /var/log/mysql/mysql-bin.log` and `server_id = 1`, then **restart MySQL** |
| `binlog_format` | FAIL | Not `ROW` — CDC will produce unreliable data | `SET GLOBAL binlog_format = 'ROW';` (no restart). Add to `my.cnf` to persist |
| `binlog_row_image` | WARN | Not `FULL` — before-image capture may fail | `SET GLOBAL binlog_row_image = 'FULL';` (no restart). Add to `my.cnf` to persist |
| `gtid_mode` | WARN | GTID not enabled — resuming after failure is unreliable | Add `gtid_mode = ON` and `enforce_gtid_consistency = ON` to `my.cnf`, then **restart MySQL** |
| CDC configuration *(query error)* | FAIL | User cannot query server variables | `GRANT REPLICATION CLIENT ON *.* TO '<user>'@'%'; FLUSH PRIVILEGES;` |

### JDBC

| Check | Status | What it means | Fix |
|-------|--------|--------------|-----|
| Driver version | FAIL | `mysql-connector-python` not installed | `pip install mysql-connector-python` |
| Driver version | WARN | Version may not support MySQL 8.0+ | `pip install --upgrade mysql-connector-python` |

---

## MongoDB

### Connectivity

| Check | Status | What it means | Fix |
|-------|--------|--------------|-----|
| TCP reachability | FAIL | Host or port not reachable | Verify `mongod` is running and the port is open. Try: `nc -zv <host> <port>` |
| Authenticated connect | FAIL | Auth failed — wrong credentials or authSource | Verify password. Check user exists: `db.getSiblingDB('admin').getUser('<user>')`. Ensure driver supports SCRAM-SHA-256: `pip install 'pymongo[srv]>=4.0'` |
| TLS | WARN | Could not determine TLS status | Non-critical. If TLS is required, add `tls=True` and `tlsCAFile=` to the URI and set `net.tls.mode: requireTLS` in `mongod.conf` |

### Permissions

| Check | Status | What it means | Fix |
|-------|--------|--------------|-----|
| Database read access | FAIL | User cannot list collections or read data | `db.grantRolesToUser('<user>', [{ role: 'read', db: '<db>' }])` |
| Change stream access | FAIL | User cannot open a change stream | Grant `read` on the database and `clusterMonitor` on admin: see remediation hint in terminal output |
| Change stream access | WARN | Unexpected error opening change stream | Check `clusterMonitor` role and MongoDB server version (3.6+ required) |

### CDC

| Check | Status | What it means | Fix |
|-------|--------|--------------|-----|
| Replica set topology | FAIL | Standalone instance — change streams not available | Convert to replica set (development: add `replSetName: rs0` to `mongod.conf`, restart, run `rs.initiate()`). For production, provision a 3-node replica set |
| Oplog window | WARN | Oplog covers less than 24 hours — risk of event loss during downtime | `db.adminCommand({ replSetResizeOplog: 1, size: 51200 })` (50 GB). Requires replica set admin |
| Change stream smoke-test | FAIL | Deployment-level change stream unavailable | Verify MongoDB 3.6+, replica set or sharded cluster, and `changeStream` privilege |
| CDC configuration *(query error)* | FAIL | User cannot run `rs.status()` | `db.grantRolesToUser('<user>', [{ role: 'clusterMonitor', db: 'admin' }])` |

### JDBC

| Check | Status | What it means | Fix |
|-------|--------|--------------|-----|
| Driver version | FAIL | `pymongo` not installed | `pip install 'pymongo[srv]>=4.0'` |
| Driver version | WARN | `pymongo` older than 4.0 | `pip install --upgrade 'pymongo[srv]'` |

---

## Common patterns

**All connectivity checks fail**
The host is unreachable. Downstream categories are automatically skipped. Fix TCP
reachability first — everything else depends on it.

**Connectivity passes, permissions fail**
The server is reachable but the user is misconfigured. Run the grant commands
from the Permissions table above as a DBA, then re-run the tool to confirm.

**CDC checks fail after permissions pass**
Server-side configuration needs changing. Some fixes (WAL level, `log_bin`,
GTID) require a server restart — coordinate with your DBA before applying in
production.

**Exit code 2 (WARNs only) in CI**
Treat WARNs as blockers before going to production. In development pipelines
you can tolerate exit 2 with:
```bash
connector-check --config toolkit.yml
code=$?; [ $code -eq 1 ] && exit 1 || exit 0
```
