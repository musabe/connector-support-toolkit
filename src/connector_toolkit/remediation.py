"""
Centralised remediation hint catalogue.

Every FAIL and WARN check in the toolkit should reference a constant from
this module rather than inlining a string. This makes it easy to:

  - review all hints in one place
  - keep SQL consistent (same casing, same syntax) across connectors
  - test that no check is silently missing a hint

Naming convention:  <DB>_<CATEGORY>_<CHECK>
Use PG_ prefix for PostgreSQL, MY_ prefix for MySQL, and SHARED_ for hints
that apply to both (e.g. network / firewall guidance).
"""

from __future__ import annotations


# ── Shared ────────────────────────────────────────────────────────────────────

SHARED_TCP_UNREACHABLE = (
    "Host or port is not reachable. Verify the server is running, the hostname "
    "resolves correctly, and that no firewall or security-group rule is blocking "
    "the connection. Try: nc -zv {host} {port}"
)

SHARED_AUTH_FAILED = (
    "Authentication failed. Check that the username and password are correct and "
    "that the user exists on this host. Verify pg_hba.conf (Postgres) or the user "
    "host-restriction (MySQL) allows connections from this client IP."
)

SHARED_SSL_QUERY_FAILED = (
    "Could not determine SSL status — the SSL status query raised an error. "
    "This is non-critical; the connection itself succeeded. Check driver version "
    "compatibility if SSL enforcement is required."
)

SHARED_DRIVER_MISSING = (
    "The required Python driver is not installed in this environment. "
    "Install it and re-run the check."
)


# ── PostgreSQL — Connectivity ──────────────────────────────────────────────────

PG_TCP_UNREACHABLE = SHARED_TCP_UNREACHABLE

PG_AUTH_FAILED = (
    "Authentication failed. Verify the password is correct and that pg_hba.conf "
    "allows this user to connect from this host using the configured auth method "
    "(md5 / scram-sha-256 / trust). Also confirm the user has CONNECT privilege: "
    "GRANT CONNECT ON DATABASE {db} TO {user};"
)

PG_SSL_WARN = (
    "SSL status could not be queried (ssl_is_used() returned an error). "
    "If SSL is required by your security policy, add sslmode=require to the "
    "connection string and ensure the server has ssl=on in postgresql.conf."
)


# ── PostgreSQL — Permissions ───────────────────────────────────────────────────

PG_REPLICATION_MISSING = (
    "The user does not have the REPLICATION privilege, which is required for "
    "logical replication and CDC. Fix: ALTER ROLE {user} REPLICATION;\n"
    "If the user also needs to create replication slots, it additionally needs "
    "USAGE on the replication slot functions or superuser."
)

PG_SUPERUSER_WARN = (
    "The user is not a superuser. This is usually fine — replication itself does "
    "not require superuser. However, some initial CDC setup steps (e.g. creating "
    "publications on all tables) may require superuser or at least the pg_monitor "
    "and pg_read_all_data roles. Grant only what is needed: "
    "GRANT pg_monitor TO {user};"
)

PG_CONNECT_PRIVILEGE_MISSING = (
    "The user lacks CONNECT privilege on the database. "
    "Fix: GRANT CONNECT ON DATABASE {db} TO {user};"
)

PG_PERMISSIONS_QUERY_FAILED = (
    "Could not query pg_roles — the user may lack SELECT on system catalogs. "
    "Ensure the user can read pg_roles: GRANT SELECT ON pg_catalog.pg_roles TO {user}; "
    "or run the check as a superuser."
)


# ── PostgreSQL — CDC ───────────────────────────────────────────────────────────

PG_WAL_LEVEL_NOT_LOGICAL = (
    "wal_level must be 'logical' for CDC / logical replication. Current value: {value}.\n"
    "Fix (requires superuser and a PostgreSQL restart):\n"
    "  ALTER SYSTEM SET wal_level = logical;\n"
    "  -- then restart PostgreSQL --\n"
    "Verify after restart: SHOW wal_level;"
)

PG_WAL_SENDER_TIMEOUT_WARN = (
    "wal_sender_timeout controls how long the server waits before disconnecting "
    "an idle replication connection. A value of 0 disables the timeout entirely, "
    "which can mask stalled consumers. A value that is too low (< 30s) risks "
    "spurious disconnections under load.\n"
    "Recommended: ALTER SYSTEM SET wal_sender_timeout = '60s';\n"
    "Current value: {value}"
)

PG_CDC_QUERY_FAILED = (
    "Could not read CDC-related server variables. The user may lack the pg_monitor "
    "role required to run SHOW commands on certain variables. "
    "Fix: GRANT pg_monitor TO {user};"
)


# ── PostgreSQL — JDBC ──────────────────────────────────────────────────────────

PG_DRIVER_MISSING = (
    "psycopg2 is not installed. Install it with:\n"
    "  pip install psycopg2-binary\n"
    "For production use prefer the source build: pip install psycopg2\n"
    "Minimum recommended version: 2.9.x (supports binary protocol and COPY)"
)

PG_DRIVER_VERSION_WARN = (
    "psycopg2 version {version} is older than the recommended minimum (2.9). "
    "Upgrade with: pip install --upgrade psycopg2-binary"
)


# ── MySQL — Connectivity ───────────────────────────────────────────────────────

MY_TCP_UNREACHABLE = SHARED_TCP_UNREACHABLE

MY_AUTH_FAILED = (
    "Authentication failed. Verify the password is correct and that the user is "
    "permitted to connect from this host. In MySQL, users are host-scoped — a user "
    "created as '{user}'@'localhost' cannot connect from a remote host. Check with:\n"
    "  SELECT user, host FROM mysql.user WHERE user = '{user}';\n"
    "If needed: CREATE USER '{user}'@'%' IDENTIFIED BY '...'; "
    "GRANT ... ON *.* TO '{user}'@'%';"
)

MY_SSL_WARN = (
    "SSL cipher status could not be determined (SHOW STATUS LIKE 'Ssl_cipher' failed). "
    "If SSL is required, verify the MySQL server has ssl_ca, ssl_cert, and ssl_key "
    "configured in my.cnf and add ssl_disabled=False to the connector options."
)


# ── MySQL — Permissions ────────────────────────────────────────────────────────

MY_REPLICATION_MISSING = (
    "The user does not have REPLICATION SLAVE privilege, which is required for "
    "binlog-based CDC. Fix:\n"
    "  GRANT REPLICATION SLAVE ON *.* TO '{user}'@'%';\n"
    "  FLUSH PRIVILEGES;\n"
    "Also grant REPLICATION CLIENT if the connector needs to call SHOW MASTER STATUS."
)

MY_READ_ACCESS_MISSING = (
    "The user does not have SELECT privilege on the target database. "
    "CDC connectors need to read table schema and row data during snapshot. Fix:\n"
    "  GRANT SELECT ON {db}.* TO '{user}'@'%';\n"
    "  FLUSH PRIVILEGES;"
)

MY_GRANTS_QUERY_FAILED = (
    "SHOW GRANTS FOR CURRENT_USER() failed — the user may not have permission "
    "to view their own grants, which is unusual. Try connecting as a DBA and "
    "running: SHOW GRANTS FOR '{user}'@'%';"
)


# ── MySQL — CDC ────────────────────────────────────────────────────────────────

MY_LOG_BIN_DISABLED = (
    "Binary logging is disabled (log_bin=OFF). It must be enabled for CDC. "
    "Add the following to my.cnf under [mysqld] and restart MySQL:\n"
    "  log_bin = /var/log/mysql/mysql-bin.log\n"
    "  server_id = 1          # must be unique if using replication\n"
    "  expire_logs_days = 7   # recommended — prevents unbounded disk growth\n"
    "Verify after restart: SHOW VARIABLES LIKE 'log_bin';"
)

MY_BINLOG_FORMAT_WRONG = (
    "binlog_format must be ROW for CDC (current: {value}). ROW format records "
    "the actual before/after values of changed rows; STATEMENT format only records "
    "the SQL, which is not sufficient for reliable CDC.\n"
    "Fix (no restart needed): SET GLOBAL binlog_format = 'ROW';\n"
    "To make it permanent, add binlog_format = ROW to my.cnf."
)

MY_BINLOG_ROW_IMAGE_WARN = (
    "binlog_row_image is not FULL (current: {value}). FULL mode logs all columns "
    "for every changed row, which is required by most CDC connectors for reliable "
    "before-image capture.\n"
    "Fix (no restart needed): SET GLOBAL binlog_row_image = 'FULL';\n"
    "To make it permanent, add binlog_row_image = FULL to my.cnf."
)

MY_GTID_MODE_WARN = (
    "GTID mode is not ON (current: {value}). GTID is not strictly required for "
    "CDC but is strongly recommended — it makes resuming after failure reliable "
    "and is required by some connectors (e.g. Debezium in GTID mode).\n"
    "Enabling GTID requires a coordinated rolling change; consult the MySQL docs. "
    "Short path for a standalone instance (requires restart):\n"
    "  gtid_mode = ON\n"
    "  enforce_gtid_consistency = ON\n"
    "  # add both to my.cnf under [mysqld]"
)

MY_CDC_QUERY_FAILED = (
    "Could not query CDC-related server variables. Ensure the user has "
    "REPLICATION CLIENT privilege:\n"
    "  GRANT REPLICATION CLIENT ON *.* TO '{user}'@'%';\n"
    "  FLUSH PRIVILEGES;"
)


# ── MySQL — JDBC ───────────────────────────────────────────────────────────────

MY_DRIVER_MISSING = (
    "mysql-connector-python is not installed. Install it with:\n"
    "  pip install mysql-connector-python\n"
    "Minimum recommended version: 8.0.x (matches MySQL 8.0 server protocol)"
)

MY_DRIVER_VERSION_WARN = (
    "mysql-connector-python version {version} may not be compatible with "
    "MySQL 8.0+. Upgrade with: pip install --upgrade mysql-connector-python"
)


# ── MongoDB — Connectivity ─────────────────────────────────────────────────────

MG_TCP_UNREACHABLE = SHARED_TCP_UNREACHABLE

MG_AUTH_FAILED = (
    "Authentication failed. Verify the username, password, and authSource are correct. "
    "MongoDB authenticates against a specific database (default: admin). "
    "Check the user exists: db.getSiblingDB('admin').getUser('{user}')\n"
    "If using SCRAM-SHA-256 (default since MongoDB 4.0), ensure the driver supports it: "
    "pip install 'pymongo[srv]>=4.0'"
)

MG_SSL_WARN = (
    "TLS status could not be determined. If TLS is required, add tls=True and "
    "tlsCAFile=/path/to/ca.pem to the connection URI, and ensure the server has "
    "net.tls.mode: requireTLS in mongod.conf."
)


# ── MongoDB — Permissions ──────────────────────────────────────────────────────

MG_READ_ACCESS_MISSING = (
    "The user does not have read access on the target database. CDC connectors "
    "need to read collections during initial snapshot. Fix:\n"
    "  use {db}\n"
    "  db.grantRolesToUser('{user}', [{{ role: 'read', db: '{db}' }}])"
)

MG_CHANGE_STREAM_MISSING = (
    "The user lacks the 'changeStream' privilege or 'read' role required to open "
    "a change stream on the database. Fix:\n"
    "  use admin\n"
    "  db.grantRolesToUser('{user}', [\n"
    "    {{ role: 'read', db: '{db}' }},\n"
    "    {{ role: 'clusterMonitor', db: 'admin' }}\n"
    "  ])"
)

MG_LIST_COLLECTIONS_MISSING = (
    "The user cannot list collections, which is required for schema discovery. "
    "Grant the 'listCollections' action or the 'read' role:\n"
    "  use {db}\n"
    "  db.grantRolesToUser('{user}', [{{ role: 'read', db: '{db}' }}])"
)

MG_PERMISSIONS_QUERY_FAILED = (
    "Could not query user roles — the user may not have 'usersInfo' privilege "
    "on the admin database. Try connecting as an admin and running:\n"
    "  use admin\n"
    "  db.getUser('{user}')"
)


# ── MongoDB — CDC ──────────────────────────────────────────────────────────────

MG_NOT_REPLICA_SET = (
    "Change streams require a replica set or sharded cluster — they are not "
    "available on standalone mongod instances. Current topology: {value}.\n"
    "To convert a standalone to a single-node replica set (development only):\n"
    "  1. Add 'replication.replSetName: rs0' to mongod.conf and restart.\n"
    "  2. Connect and run: rs.initiate()\n"
    "For production, provision a proper three-node replica set."
)

MG_OPLOG_SIZE_WARN = (
    "The oplog window is shorter than recommended (current: ~{value} hours). "
    "A small oplog risks losing change events during connector downtime. "
    "Recommended minimum: 24 hours.\n"
    "Fix (requires replica set admin):\n"
    "  db.adminCommand({{ replSetResizeOplog: 1, size: 51200 }})  -- 50 GB in MB"
)

MG_CHANGE_STREAM_DISABLED = (
    "Change streams are not available on this deployment. Ensure the server is "
    "running MongoDB 3.6+ and is part of a replica set or sharded cluster. "
    "Standalone instances do not support change streams."
)

MG_CDC_QUERY_FAILED = (
    "Could not query replication status. The user may lack the 'clusterMonitor' "
    "role required to run rs.status() and db.adminCommand(). Fix:\n"
    "  use admin\n"
    "  db.grantRolesToUser('{user}', [{{ role: 'clusterMonitor', db: 'admin' }}])"
)


# ── MongoDB — JDBC (driver) ────────────────────────────────────────────────────

MG_DRIVER_MISSING = (
    "pymongo is not installed. Install it with:\n"
    "  pip install 'pymongo[srv]>=4.0'\n"
    "The [srv] extra is required for mongodb+srv:// connection strings and "
    "SCRAM-SHA-256 authentication (default since MongoDB 4.0).\n"
    "Minimum recommended version: 4.x (supports MongoDB 4.4+ change stream features)"
)

MG_DRIVER_VERSION_WARN = (
    "pymongo version {version} is older than the recommended minimum (4.0). "
    "Older versions lack full change stream support and SCRAM-SHA-256 auth. "
    "Upgrade with: pip install --upgrade 'pymongo[srv]'"
)


# ── Redshift — Connectivity ────────────────────────────────────────────────────

RS_TCP_UNREACHABLE = SHARED_TCP_UNREACHABLE

RS_AUTH_FAILED = (
    "Authentication failed. Verify the username and password are correct. "
    "Redshift uses database-level credentials — check that the user exists: "
    "SELECT usename FROM pg_user WHERE usename = '{user}';\n"
    "Also confirm the cluster's VPC security group allows inbound traffic on "
    "port {port} from this client IP, and that Enhanced VPC Routing is not "
    "blocking the connection."
)

RS_SSL_WARN = (
    "SSL status could not be queried. Redshift requires SSL by default on most "
    "cluster configurations. Add sslmode=require to the connection string and "
    "ensure the cluster parameter group has require_ssl=true."
)


# ── Redshift — Permissions ─────────────────────────────────────────────────────

RS_REPLICATION_MISSING = (
    "The user does not have the 'replication' system privilege required for "
    "creating a replication slot or using logical replication. Fix:\n"
    "  ALTER USER {user} WITH CREATEUSER;  -- grants full admin\n"
    "Or grant the minimum required privilege:\n"
    "  GRANT USAGE ON SCHEMA pg_catalog TO {user};\n"
    "  ALTER USER {user} REPLICATION;"
)

RS_SUPERUSER_WARN = (
    "The user is not a superuser. Some CDC operations (e.g. creating "
    "publications, reading system tables) may require elevated privileges. "
    "Consider granting the 'rds_superuser' role if running on Redshift Serverless, "
    "or ALTER USER {user} CREATEUSER; on provisioned clusters."
)

RS_CONNECT_PRIVILEGE_MISSING = (
    "The user lacks CONNECT privilege on the database. Fix:\n"
    "  GRANT CONNECT ON DATABASE {db} TO {user};"
)

RS_SCHEMA_ACCESS_MISSING = (
    "The user cannot access the target schema. CDC connectors need to read "
    "table data and metadata during snapshot. Fix:\n"
    "  GRANT USAGE ON SCHEMA {schema} TO {user};\n"
    "  GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {user};\n"
    "  ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO {user};"
)

RS_PERMISSIONS_QUERY_FAILED = (
    "Could not query user privileges from pg_user / information_schema. "
    "The user may lack SELECT on system catalog tables. Run as a superuser:\n"
    "  GRANT SELECT ON pg_catalog.pg_user TO {user};"
)


# ── Redshift — CDC ─────────────────────────────────────────────────────────────

RS_NOT_LOGICAL_REPLICATION = (
    "Logical replication is not enabled on this Redshift cluster. "
    "Redshift supports logical replication via the 'logical replication' "
    "parameter group setting (Redshift Serverless) or the enable_logical_replication "
    "cluster parameter (provisioned).\n"
    "For provisioned clusters:\n"
    "  1. Create or modify a parameter group: enable_logical_replication = true\n"
    "  2. Reboot the cluster to apply.\n"
    "For Serverless: set LOGICAL_REPLICATION = ON in the namespace settings."
)

RS_WAL_SENDER_TIMEOUT_WARN = (
    "wal_sender_timeout is set to {value}, which may cause replication connections "
    "to drop under load. Recommended minimum: 60s.\n"
    "Fix: ALTER SYSTEM SET wal_sender_timeout = '60s';"
)

RS_CDC_QUERY_FAILED = (
    "Could not query Redshift replication configuration. The user may lack "
    "SELECT on pg_settings or pg_replication_slots. Fix:\n"
    "  GRANT SELECT ON pg_catalog.pg_settings TO {user};\n"
    "  GRANT SELECT ON pg_catalog.pg_replication_slots TO {user};"
)


# ── Redshift — JDBC ────────────────────────────────────────────────────────────

RS_DRIVER_MISSING = (
    "redshift-connector is not installed. Install it with:\n"
    "  pip install redshift-connector\n"
    "Alternatively, psycopg2 can connect to Redshift but lacks Redshift-specific "
    "features (IAM auth, Data API). Minimum recommended: redshift-connector>=2.1"
)

RS_DRIVER_VERSION_WARN = (
    "redshift-connector version {version} may be outdated. "
    "Upgrade with: pip install --upgrade redshift-connector"
)
