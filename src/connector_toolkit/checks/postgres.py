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


def _parse_timeout_ms(value: str) -> int:
    """
    Convert a Postgres GUC timeout string to milliseconds.

    Postgres returns values like: '0', '500ms', '60s', '1min', '2h'.
    Returns 0 if the value represents a disabled timeout.
    """
    import re
    v = value.strip().lower()
    if v == "0":
        return 0
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(ms|s|min|h)?$", v)
    if not m:
        return -1  # unknown format — treat as non-zero (don't warn)
    num = float(m.group(1))
    unit = m.group(2) or "ms"
    return int({
        "ms":  num,
        "s":   num * 1000,
        "min": num * 60_000,
        "h":   num * 3_600_000,
    }[unit])


class PostgresConnector(BaseConnector):
    db_type = "postgres"

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    def check_connectivity(self) -> list[CheckResult]:
        results = []
        c = self.config

        # 1. TCP reachability
        try:
            start = time.monotonic()
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
                remediation=R.PG_TCP_UNREACHABLE.format(host=c.host, port=c.port),
            ))
            return results  # no point continuing

        # 2. Authenticated connect
        try:
            t0 = time.monotonic()
            conn = psycopg2.connect(
                host=c.host, port=c.port, dbname=c.db,
                user=c.user, password=c.password,
                connect_timeout=c.timeout,
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
                remediation=R.PG_AUTH_FAILED.format(db=c.db, user=c.user),
            ))
            return results

        # 3. SSL — use pg_stat_ssl which works on all Postgres versions
        # Fall back gracefully if the view is unavailable (e.g. older builds)
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
            # Roll back the aborted transaction so subsequent checks can proceed
            try:
                self._conn.rollback()
            except Exception:
                pass
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="SSL",
                status=Status.WARN,
                detail=str(exc),
                remediation=R.PG_SSL_WARN,
            ))

        return results

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def check_permissions(self) -> list[CheckResult]:
        results = []

        # Replication privilege
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT rolreplication, rolsuper FROM pg_roles WHERE rolname = current_user"
                )
                row = cur.fetchone()
                rolreplication, rolsuper = row if row else (False, False)

            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Replication privilege",
                status=Status.PASS if rolreplication else Status.FAIL,
                detail=f"rolreplication={rolreplication}",
                remediation=None if rolreplication else R.PG_REPLICATION_MISSING.format(user=self.config.user),
            ))
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Superuser status",
                status=Status.PASS if rolsuper else Status.WARN,
                detail="superuser" if rolsuper else "Not superuser — CDC setup may require elevated privileges",
                remediation=None if rolsuper else R.PG_SUPERUSER_WARN.format(user=self.config.user),
            ))
        except Exception as exc:
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Replication privilege",
                status=Status.FAIL,
                detail=str(exc),
                remediation=R.PG_PERMISSIONS_QUERY_FAILED.format(user=self.config.user),
            ))

        # Database read access
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT has_database_privilege(current_user, current_database(), 'CONNECT')")
                can_connect = cur.fetchone()[0]
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Database read access",
                status=Status.PASS if can_connect else Status.FAIL,
                detail=f"CONNECT privilege: {can_connect}",
                remediation=None if can_connect else R.PG_CONNECT_PRIVILEGE_MISSING.format(db=self.config.db, user=self.config.user),
            ))
        except Exception as exc:
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Database read access",
                status=Status.FAIL,
                detail=str(exc),
                remediation=R.PG_PERMISSIONS_QUERY_FAILED.format(user=self.config.user),
            ))

        return results

    # ------------------------------------------------------------------
    # CDC
    # ------------------------------------------------------------------

    def check_cdc(self) -> list[CheckResult]:
        results = []

        checks = [
            ("wal_level", "logical", Status.FAIL,
             "ALTER SYSTEM SET wal_level = logical; -- requires restart"),
            ("wal_sender_timeout", None, Status.WARN, None),
        ]

        try:
            with self._conn.cursor() as cur:
                # wal_level
                cur.execute("SHOW wal_level")
                wal_level = cur.fetchone()[0]
                results.append(CheckResult(
                    category=Category.CDC,
                    name="wal_level",
                    status=Status.PASS if wal_level == "logical" else Status.FAIL,
                    detail=f"wal_level={wal_level}",
                    remediation=None if wal_level == "logical" else R.PG_WAL_LEVEL_NOT_LOGICAL.format(value=wal_level),
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

                # wal_sender_timeout — warn if disabled (0)
                # Postgres returns values like '0', '60s', '1min', '2h', '500ms'
                cur.execute("SHOW wal_sender_timeout")
                wst = cur.fetchone()[0]
                wst_is_zero = _parse_timeout_ms(wst) == 0
                results.append(CheckResult(
                    category=Category.CDC,
                    name="wal_sender_timeout",
                    status=Status.WARN if wst_is_zero else Status.PASS,
                    detail=f"wal_sender_timeout={wst}",
                    remediation=R.PG_WAL_SENDER_TIMEOUT_WARN.format(value=wst) if wst_is_zero else None,
                ))

        except Exception as exc:
            results.append(CheckResult(
                category=Category.CDC,
                name="CDC configuration",
                status=Status.FAIL,
                detail=str(exc),
                remediation=R.PG_CDC_QUERY_FAILED.format(user=self.config.user),
            ))

        return results

    # ------------------------------------------------------------------
    # JDBC
    # ------------------------------------------------------------------

    def check_jdbc(self) -> list[CheckResult]:
        try:
            import psycopg2 as pg
            version = getattr(pg, "__version__", "unknown")
            return [CheckResult(
                category=Category.JDBC,
                name="Driver version",
                status=Status.PASS,
                detail=f"psycopg2=={version}",
            )]
        except ImportError:
            return [CheckResult(
                category=Category.JDBC,
                name="Driver version",
                status=Status.FAIL,
                detail="psycopg2 not installed",
                remediation=R.PG_DRIVER_MISSING,
            )]
