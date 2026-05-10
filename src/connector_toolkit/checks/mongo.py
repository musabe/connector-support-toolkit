from __future__ import annotations

import socket
import time
from typing import Any

try:
    import pymongo
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, OperationFailure
except ImportError:
    pymongo = None  # type: ignore
    MongoClient = None  # type: ignore
    ConnectionFailure = Exception  # type: ignore
    OperationFailure = Exception  # type: ignore

from ..base import BaseConnector
from ..models import Category, CheckResult, Status
from .. import remediation as R

# Minimum oplog window (hours) before we emit a WARN
_MIN_OPLOG_HOURS = 24


class MongoConnector(BaseConnector):
    """
    Connector readiness checks for MongoDB replica sets and sharded clusters.

    CDC mechanism: MongoDB change streams (requires replica set or sharded cluster,
    MongoDB 3.6+). The checks here validate everything a change-stream-based
    connector (e.g. Debezium MongoDB, Airbyte MongoDB CDC) needs before it can
    run reliably.

    Register in runner.CONNECTOR_REGISTRY:
        from .checks.mongo import MongoConnector
        CONNECTOR_REGISTRY["mongo"] = MongoConnector
    """

    db_type = "mongo"

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    def check_connectivity(self) -> list[CheckResult]:
        results = []
        c = self.config

        if pymongo is None:
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="Driver available",
                status=Status.FAIL,
                detail="pymongo not installed",
                remediation=R.MG_DRIVER_MISSING,
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
                remediation=R.MG_TCP_UNREACHABLE.format(host=c.host, port=c.port),
            ))
            return results

        # 2. Authenticated connect + hello handshake
        try:
            uri = (
                f"mongodb://{c.user}:{c.password}@{c.host}:{c.port}/{c.db}"
                f"?authSource=admin&serverSelectionTimeoutMS={c.timeout * 1000}"
            )
            t0 = time.monotonic()
            client = MongoClient(uri)
            # hello forces an actual network round-trip
            info = client.admin.command("hello")
            latency_ms = int((time.monotonic() - t0) * 1000)
            self._conn = client
            self._hello = info
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="Authenticated connect",
                status=Status.PASS,
                detail=f"latency={latency_ms}ms",
            ))
        except ConnectionFailure as exc:
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="Authenticated connect",
                status=Status.FAIL,
                detail=str(exc),
                remediation=R.MG_AUTH_FAILED.format(user=c.user),
            ))
            return results
        except Exception as exc:
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="Authenticated connect",
                status=Status.FAIL,
                detail=str(exc),
                remediation=R.MG_AUTH_FAILED.format(user=c.user),
            ))
            return results

        # 3. TLS
        try:
            tls_on = self._hello.get("isWritablePrimary") is not None
            # Check if the connection used TLS via server status
            status_doc = client.admin.command("serverStatus", tcmallocVerbosity=0)
            tls_info = status_doc.get("security", {}).get("SSLServerSubjectName", "")
            tls_active = bool(tls_info)
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="TLS",
                status=Status.PASS,
                detail=f"in use: {'yes' if tls_active else 'no'}",
            ))
        except Exception as exc:
            results.append(CheckResult(
                category=Category.CONNECTIVITY,
                name="TLS",
                status=Status.WARN,
                detail=str(exc),
                remediation=R.MG_SSL_WARN,
            ))

        return results

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def check_permissions(self) -> list[CheckResult]:
        results = []
        c = self.config
        client: Any = self._conn

        # 1. Read access on target database
        try:
            db = client[c.db]
            collections = db.list_collection_names()
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Database read access",
                status=Status.PASS,
                detail=f"listCollections returned {len(collections)} collections",
            ))
        except OperationFailure as exc:
            code = getattr(exc, "code", None)
            if code == 13:  # Unauthorized
                results.append(CheckResult(
                    category=Category.PERMISSIONS,
                    name="Database read access",
                    status=Status.FAIL,
                    detail=str(exc),
                    remediation=R.MG_READ_ACCESS_MISSING.format(
                        db=c.db, user=c.user,
                    ),
                ))
            else:
                results.append(CheckResult(
                    category=Category.PERMISSIONS,
                    name="Database read access",
                    status=Status.FAIL,
                    detail=str(exc),
                    remediation=R.MG_LIST_COLLECTIONS_MISSING.format(
                        db=c.db, user=c.user,
                    ),
                ))
        except Exception as exc:
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Database read access",
                status=Status.FAIL,
                detail=str(exc),
                remediation=R.MG_PERMISSIONS_QUERY_FAILED.format(user=c.user),
            ))

        # 2. Change stream privilege (open a stream and immediately close it)
        try:
            db = client[c.db]
            with db.watch([], max_await_time_ms=1) as stream:
                pass
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Change stream access",
                status=Status.PASS,
                detail="opened and closed successfully",
            ))
        except OperationFailure as exc:
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Change stream access",
                status=Status.FAIL,
                detail=str(exc),
                remediation=R.MG_CHANGE_STREAM_MISSING.format(
                    db=c.db, user=c.user,
                ),
            ))
        except Exception as exc:
            results.append(CheckResult(
                category=Category.PERMISSIONS,
                name="Change stream access",
                status=Status.WARN,
                detail=f"Unexpected error opening change stream: {exc}",
                remediation=R.MG_CHANGE_STREAM_MISSING.format(
                    db=c.db, user=c.user,
                ),
            ))

        return results

    # ------------------------------------------------------------------
    # CDC
    # ------------------------------------------------------------------

    def check_cdc(self) -> list[CheckResult]:
        results = []
        c = self.config
        client: Any = self._conn

        # 1. Replica set topology (change streams require RS or sharded)
        try:
            rs_status = client.admin.command("replSetGetStatus")
            topology = "replica_set"
            rs_ok = rs_status.get("ok") == 1
            results.append(CheckResult(
                category=Category.CDC,
                name="Replica set topology",
                status=Status.PASS if rs_ok else Status.FAIL,
                detail=f"topology={topology} set={rs_status.get('set', 'unknown')}",
                remediation=None if rs_ok else R.MG_NOT_REPLICA_SET.format(
                    value="standalone"
                ),
            ))
        except OperationFailure as exc:
            # replSetGetStatus fails on standalone with code 76
            results.append(CheckResult(
                category=Category.CDC,
                name="Replica set topology",
                status=Status.FAIL,
                detail="Not a replica set member — change streams unavailable",
                remediation=R.MG_NOT_REPLICA_SET.format(value="standalone"),
            ))
            # No point checking oplog if not a replica set
            results.append(CheckResult(
                category=Category.CDC,
                name="Oplog window",
                status=Status.SKIP,
                detail="Skipped — requires replica set",
            ))
            return results
        except Exception as exc:
            results.append(CheckResult(
                category=Category.CDC,
                name="Replica set topology",
                status=Status.FAIL,
                detail=str(exc),
                remediation=R.MG_CDC_QUERY_FAILED.format(user=c.user),
            ))
            return results

        # 2. Oplog window estimate
        try:
            local_db = client["local"]
            oplog = local_db["oplog.rs"]
            first = oplog.find_one(sort=[("$natural", 1)])   # 1  = ASCENDING
            last = oplog.find_one(sort=[("$natural", -1)])  # -1 = DESCENDING

            if first and last:
                first_ts = first["ts"].as_datetime()
                last_ts = last["ts"].as_datetime()
                window_hours = (last_ts - first_ts).total_seconds() / 3600
                oplog_ok = window_hours >= _MIN_OPLOG_HOURS
                results.append(CheckResult(
                    category=Category.CDC,
                    name="Oplog window",
                    status=Status.PASS if oplog_ok else Status.WARN,
                    detail=f"window={window_hours:.1f}h (min recommended: {_MIN_OPLOG_HOURS}h)",
                    remediation=None if oplog_ok else R.MG_OPLOG_SIZE_WARN.format(
                        value=f"{window_hours:.1f}",
                    ),
                ))
            else:
                results.append(CheckResult(
                    category=Category.CDC,
                    name="Oplog window",
                    status=Status.WARN,
                    detail="Oplog appears empty — no events yet",
                ))
        except Exception as exc:
            results.append(CheckResult(
                category=Category.CDC,
                name="Oplog window",
                status=Status.WARN,
                detail=str(exc),
                remediation=R.MG_CDC_QUERY_FAILED.format(user=c.user),
            ))

        # 3. Change stream smoke-test at the deployment level
        try:
            with client.watch([], max_await_time_ms=1):
                pass
            results.append(CheckResult(
                category=Category.CDC,
                name="Change stream smoke-test",
                status=Status.PASS,
                detail="Deployment-level change stream opened successfully",
            ))
        except OperationFailure as exc:
            results.append(CheckResult(
                category=Category.CDC,
                name="Change stream smoke-test",
                status=Status.FAIL,
                detail=str(exc),
                remediation=R.MG_CHANGE_STREAM_DISABLED,
            ))
        except Exception as exc:
            results.append(CheckResult(
                category=Category.CDC,
                name="Change stream smoke-test",
                status=Status.WARN,
                detail=str(exc),
                remediation=R.MG_CDC_QUERY_FAILED.format(user=c.user),
            ))

        return results

    # ------------------------------------------------------------------
    # JDBC (driver)
    # ------------------------------------------------------------------

    def check_jdbc(self) -> list[CheckResult]:
        if pymongo is None:
            return [CheckResult(
                category=Category.JDBC,
                name="Driver version",
                status=Status.FAIL,
                detail="pymongo not installed",
                remediation=R.MG_DRIVER_MISSING,
            )]

        version = getattr(pymongo, "version", "unknown")
        try:
            major = int(version.split(".")[0])
        except (ValueError, AttributeError):
            major = 0

        if major < 4:
            return [CheckResult(
                category=Category.JDBC,
                name="Driver version",
                status=Status.WARN,
                detail=f"pymongo=={version}",
                remediation=R.MG_DRIVER_VERSION_WARN.format(version=version),
            )]

        return [CheckResult(
            category=Category.JDBC,
            name="Driver version",
            status=Status.PASS,
            detail=f"pymongo=={version}",
        )]
