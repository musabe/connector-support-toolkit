"""
Connector readiness checks for Amazon Redshift (provisioned and Serverless).

CDC mechanism: Redshift logical replication via replication slots (introduced
in Redshift ra3 node types and Serverless). The checks validate what a
CDC connector (e.g. Airbyte Redshift CDC, Fivetran) needs before ingestion.

Redshift is wire-compatible with PostgreSQL so psycopg2 is used as the driver.
The redshift-connector package is also checked as it provides IAM auth support.

Register in runner.CONNECTOR_REGISTRY:
    from .checks.redshift import RedshiftConnector
    CONNECTOR_REGISTRY["redshift"] = RedshiftConnector
"""
from __future__ import annotations

import socket
import time
from typing import Any

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None  # type: ignore

from ..base import BaseConnector
from ..models import Category, CheckResult, Status
from .. import remediation as R

_DEFAULT_PORT = 5439
_DEFAULT_SCHEMA = "public"


class RedshiftConnector(BaseConnector):
    db_type = "redshift"

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    def check_connectivity(self) -> list[CheckResult]:
        results = []
        c = self.config

        if psycopg2 is None:
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="Driver available",
                status=Status.FAIL,
                detail="psycopg2 not installed (required for Redshift connectivity checks)",
                remediation=R.RS_DRIVER_MISSING,
            ))
            return results

        # 1. TCP reachability
        try:
            with socket.create_connection((c.host, c.port), timeout=c.timeout):
                pass
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="TCP reachability",
                status=Status.PASS,
                detail=f"host={c.host} port={c.port}",
            ))
        except OSError as exc:
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="TCP reachability",
                status=Status.FAIL,
                detail=str(exc),
                remediation=R.RS_TCP_UNREACHABLE.format(host=c.host, port=c.port),
            ))
            return results

        # 2. Authenticated connect
        try:
            t0 = time.monotonic()
            conn = psycopg2.connect(
                host=c.host,
                port=c.port,
                dbname=c.db,
                user=c.user,
                password=c.password,
                connect_timeout=c.timeout,
                sslmode="require",
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            self._conn = conn
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="Authenticated connect",
                status=Status.PASS,
                detail=f"latency={latency_ms}ms",
            ))
        except Exception as exc:
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="Authenticated connect",
                status=Status.FAIL,
                detail=str(exc),
                remediation=R.RS_AUTH_FAILED.format(user=c.user, port=c.port),
            ))
            return results

        # 3. SSL
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()"
                )
                row = cur.fetchone()
                ssl_on = bool(row and row[0])
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="SSL",
                status=Status.PASS,
                detail=f"in use: {'yes' if ssl_on else 'no'}",
            ))
        except Exception as exc:
            try:
                self._conn.rollback()
            except Exception:
                pass
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="SSL",
                status=Status.WARN,
                detail=str(exc),
                remediation=R.RS_SSL_WARN,
            ))

        # 4. Redshift server version
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT version()")
                version_str = cur.fetchone()[0]
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="Server version",
                status=Status.PASS,
                detail=version_str[:80],
            ))
        except Exception as exc:
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="Server version",
                status=Status.WARN,
                detail=str(exc),
            ))

        return results

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def check_permissions(self) -> list[CheckResult]:
        results = []
        c = self.config

        try:
            with self._conn.cursor() as cur:
                # superuser and replication flags
                cur.execute(
                    "SELECT usecreatedb, usesuper, usereplication "
                    "FROM pg_user WHERE usename = current_user"
                )
                row = cur.fetchone()
                _, is_super, has_replication = row if row else (False, False, False)

            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Replication privilege",
                status=Status.PASS if has_replication else Status.FAIL,
                detail=f"usereplication={has_replication}",
                remediation=None if has_replication else R.RS_REPLICATION_MISSING.format(
                    user=c.user,
                ),
            ))
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Superuser status",
                status=Status.PASS if is_super else Status.WARN,
                detail="superuser" if is_super else "Not superuser — some CDC setup steps may require elevated privileges",
                remediation=None if is_super else R.RS_SUPERUSER_WARN.format(user=c.user),
            ))
        except Exception as exc:
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Replication privilege",
                status=Status.FAIL,
                detail=str(exc),
                remediation=R.RS_PERMISSIONS_QUERY_FAILED.format(user=c.user),
            ))

        # CONNECT privilege
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT has_database_privilege(current_user, current_database(), 'CONNECT')"
                )
                can_connect = cur.fetchone()[0]
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Database read access",
                status=Status.PASS if can_connect else Status.FAIL,
                detail=f"CONNECT privilege: {can_connect}",
                remediation=None if can_connect else R.RS_CONNECT_PRIVILEGE_MISSING.format(
                    db=c.db, user=c.user,
                ),
            ))
        except Exception as exc:
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Database read access",
                status=Status.FAIL,
                detail=str(exc),
                remediation=R.RS_PERMISSIONS_QUERY_FAILED.format(user=c.user),
            ))

        # Schema access
        schema = getattr(c, "schema", _DEFAULT_SCHEMA)
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT has_schema_privilege(current_user, %s, 'USAGE')",
                    (schema,),
                )
                has_schema = cur.fetchone()[0]
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Schema access",
                status=Status.PASS if has_schema else Status.FAIL,
                detail=f"USAGE on schema '{schema}': {has_schema}",
                remediation=None if has_schema else R.RS_SCHEMA_ACCESS_MISSING.format(
                    schema=schema, user=c.user,
                ),
            ))
        except Exception as exc:
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Schema access",
                status=Status.WARN,
                detail=str(exc),
                remediation=R.RS_PERMISSIONS_QUERY_FAILED.format(user=c.user),
            ))

        return results

    # ------------------------------------------------------------------
    # CDC
    # ------------------------------------------------------------------

    def check_cdc(self) -> list[CheckResult]:
        results = []
        c = self.config

        try:
            with self._conn.cursor() as cur:
                # Logical replication enabled?
                cur.execute(
                    "SELECT name, setting FROM pg_settings "
                    "WHERE name IN ('enable_logical_replication', 'wal_level')"
                )
                settings = {row[0]: row[1] for row in cur.fetchall()}

                wal_level = settings.get("wal_level", "unknown")
                logical_on = settings.get("enable_logical_replication", "off")

                cdc_ok = wal_level == "logical" or logical_on.lower() in ("on", "true", "1")
                results.append(CheckResult(
                    category=Category.CDC,
                    name="Logical replication",
                    status=Status.PASS if cdc_ok else Status.FAIL,
                    detail=f"wal_level={wal_level} enable_logical_replication={logical_on}",
                    remediation=None if cdc_ok else R.RS_NOT_LOGICAL_REPLICATION,
                ))

                # Replication slots
                cur.execute("SELECT count(*) FROM pg_replication_slots")
                slot_count = cur.fetchone()[0]
                results.append(CheckResult(
                    category=Category.CDC,
                    name="Replication slots",
                    status=Status.PASS,
                    detail=f"active slots={slot_count}",
                ))

                # wal_sender_timeout
                cur.execute("SHOW wal_sender_timeout")
                wst = cur.fetchone()[0]
                wst_disabled = wst in ("0", "0ms", "0s")
                results.append(CheckResult(
                    category=Category.CDC,
                    name="wal_sender_timeout",
                    status=Status.WARN if wst_disabled else Status.PASS,
                    detail=f"wal_sender_timeout={wst}",
                    remediation=R.RS_WAL_SENDER_TIMEOUT_WARN.format(value=wst) if wst_disabled else None,
                ))

        except Exception as exc:
            results.append(CheckResult(
                category=Category.CDC,
                name="CDC configuration",
                status=Status.FAIL,
                detail=str(exc),
                remediation=R.RS_CDC_QUERY_FAILED.format(user=c.user),
            ))

        return results

    # ------------------------------------------------------------------
    # JDBC (driver)
    # ------------------------------------------------------------------

    def check_jdbc(self) -> list[CheckResult]:
        results = []

        # Check redshift-connector (preferred)
        try:
            import redshift_connector
            version = getattr(redshift_connector, "__version__", "unknown")
            results.append(CheckResult(
                category=Category.JDBC,
                name="Driver version (redshift-connector)",
                status=Status.PASS,
                detail=f"redshift-connector=={version}",
            ))
        except ImportError:
            results.append(CheckResult(
                category=Category.JDBC,
                name="Driver version (redshift-connector)",
                status=Status.WARN,
                detail="redshift-connector not installed — IAM auth unavailable",
                remediation=R.RS_DRIVER_MISSING,
            ))

        # Check psycopg2 (fallback driver used for checks)
        if psycopg2 is None:
            results.append(CheckResult(
                category=Category.JDBC,
                name="Driver version (psycopg2)",
                status=Status.FAIL,
                detail="psycopg2 not installed",
                remediation="pip install psycopg2-binary",
            ))
        else:
            version = getattr(psycopg2, "__version__", "unknown")
            results.append(CheckResult(
                category=Category.JDBC,
                name="Driver version (psycopg2)",
                status=Status.PASS,
                detail=f"psycopg2=={version}",
            ))

        return results
