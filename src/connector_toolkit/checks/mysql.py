from __future__ import annotations

import socket
import time

try:
    import mysql.connector
except ImportError:
    mysql = None  # type: ignore

from ..base import BaseConnector
from ..models import Category, CheckResult, Status
from .. import remediation as R


class MySQLConnector(BaseConnector):
    db_type = "mysql"

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    def check_connectivity(self) -> list[CheckResult]:
        results = []
        c = self.config

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
                remediation=R.MY_TCP_UNREACHABLE.format(host=c.host, port=c.port),
            ))
            return results

        # 2. Authenticated connect
        try:
            t0 = time.monotonic()
            conn = mysql.connector.connect(
                host=c.host, port=c.port, database=c.db,
                user=c.user, password=c.password,
                connection_timeout=c.timeout,
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
                remediation=R.MY_AUTH_FAILED.format(user=c.user),
            ))
            return results

        # 3. SSL
        try:
            cur = self._conn.cursor()
            cur.execute("SHOW STATUS LIKE 'Ssl_cipher'")
            row = cur.fetchone()
            ssl_active = bool(row and row[1])
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="SSL",
                status=Status.PASS,
                detail=f"cipher: {row[1] if ssl_active else 'none'}",
            ))
        except Exception as exc:
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="SSL",
                status=Status.WARN,
                detail=str(exc),
                remediation=R.MY_SSL_WARN,
            ))

        return results

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def check_permissions(self) -> list[CheckResult]:
        results = []

        try:
            cur = self._conn.cursor()
            cur.execute("SHOW GRANTS FOR CURRENT_USER()")
            grants = [row[0] for row in cur.fetchall()]
            grant_str = " | ".join(grants)

            has_replication = any(
                "REPLICATION SLAVE" in g or "ALL PRIVILEGES" in g
                for g in grants
            )
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Replication privilege",
                status=Status.PASS if has_replication else Status.FAIL,
                detail=grant_str[:120],
                remediation=None if has_replication else R.MY_REPLICATION_MISSING.format(user=self.config.user),
            ))

            has_read = any(
                "SELECT" in g or "ALL PRIVILEGES" in g
                for g in grants
            )
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Database read access",
                status=Status.PASS if has_read else Status.FAIL,
                detail="SELECT privilege found" if has_read else "No SELECT privilege",
                remediation=None if has_read else R.MY_READ_ACCESS_MISSING.format(db=self.config.db, user=self.config.user),
            ))
        except Exception as exc:
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="SHOW GRANTS",
                status=Status.FAIL,
                detail=str(exc),
                remediation=R.MY_GRANTS_QUERY_FAILED.format(user=self.config.user),
            ))

        return results

    # ------------------------------------------------------------------
    # CDC
    # ------------------------------------------------------------------

    def check_cdc(self) -> list[CheckResult]:
        results = []

        variables = {
            "log_bin": ("ON", Status.FAIL, R.MY_LOG_BIN_DISABLED),
            "binlog_format": ("ROW", Status.FAIL, R.MY_BINLOG_FORMAT_WRONG),
            "binlog_row_image": ("FULL", Status.WARN, R.MY_BINLOG_ROW_IMAGE_WARN),
            "gtid_mode": ("ON", Status.WARN, R.MY_GTID_MODE_WARN),
        }

        try:
            cur = self._conn.cursor()
            for var, (expected, fail_status, fix) in variables.items():
                cur.execute(f"SHOW VARIABLES LIKE '{var}'")
                row = cur.fetchone()
                value = row[1] if row else "N/A"
                ok = value.upper() == expected.upper()
                results.append(CheckResult(
                    category=Category.CDC,
                    name=var,
                    status=Status.PASS if ok else fail_status,
                    detail=f"{var}={value}",
                    remediation=None if ok else fix.format(value=value),
                ))
        except Exception as exc:
            results.append(CheckResult(
                category=Category.CDC,
                name="CDC configuration",
                status=Status.FAIL,
                detail=str(exc),
                remediation=R.MY_CDC_QUERY_FAILED.format(user=self.config.user),
            ))

        return results

    # ------------------------------------------------------------------
    # JDBC
    # ------------------------------------------------------------------

    def check_jdbc(self) -> list[CheckResult]:
        try:
            import mysql.connector as mc
            version = getattr(mc, "__version__", "unknown")
            return [CheckResult(
                category=Category.JDBC,
                name="Driver version",
                status=Status.PASS,
                detail=f"mysql-connector-python=={version}",
            )]
        except ImportError:
            return [CheckResult(
                category=Category.JDBC,
                name="Driver version",
                status=Status.FAIL,
                detail="mysql-connector-python not installed",
                remediation=R.MY_DRIVER_MISSING,
            )]
