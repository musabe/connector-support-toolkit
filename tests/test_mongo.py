"""
Unit tests for MongoConnector — no live MongoDB required.

The mock layer stubs out the MongoClient so each check method can be tested
against controlled responses. OperationFailure is also mocked at the module
level so tests run without pymongo installed.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import sys

import pytest

from connector_toolkit.checks.mongo import MongoConnector, _MIN_OPLOG_HOURS
from connector_toolkit.models import Category, RunConfig, Status


# ── Mock OperationFailure so tests run without pymongo installed ───────────────

class _FakeOperationFailure(Exception):
    def __init__(self, message="", code=None):
        super().__init__(message)
        self.code = code


_fake_errors_mod = MagicMock()
_fake_errors_mod.OperationFailure = _FakeOperationFailure
sys.modules.setdefault("pymongo", MagicMock())
sys.modules["pymongo.errors"] = _fake_errors_mod

import connector_toolkit.checks.mongo as _mongo_mod
_mongo_mod.OperationFailure = _FakeOperationFailure

OperationFailure = _FakeOperationFailure


@pytest.fixture
def config():
    return RunConfig(
        host="localhost", port=27017, db="testdb",
        user="demo", password="demo", db_type="mongo",
    )


@pytest.fixture
def connector(config):
    return MongoConnector(config)


def _attach_mock_client(connector) -> MagicMock:
    """Attach a basic MagicMock MongoClient to the connector and return it."""
    client = MagicMock()
    connector._conn = client
    connector._hello = {"isWritablePrimary": True}
    return client


def _make_oplog_client(connector, first_doc, last_doc) -> MagicMock:
    """
    Build a mock MongoClient where client["local"]["oplog.rs"].find_one()
    returns the supplied docs in order. Uses explicit __getitem__ assignment
    so the same object is returned on every subscript access.
    """
    client = MagicMock()
    connector._conn = client
    connector._hello = {"isWritablePrimary": True}

    client.admin.command.side_effect = lambda cmd, *a, **kw: (
        {"ok": 1, "set": "rs0"} if cmd == "replSetGetStatus" else {}
    )

    oplog_mock = MagicMock()
    oplog_mock.find_one.side_effect = [first_doc, last_doc]

    local_mock = MagicMock()
    local_mock.__getitem__ = MagicMock(return_value=oplog_mock)

    client.__getitem__ = MagicMock(return_value=local_mock)

    cs_cm = MagicMock()
    cs_cm.__enter__ = MagicMock(return_value=MagicMock())
    cs_cm.__exit__ = MagicMock(return_value=False)
    client.watch.return_value = cs_cm

    return client


# ── Permissions ────────────────────────────────────────────────────────────────

class TestPermissions:
    def test_read_access_pass(self, connector):
        client = _attach_mock_client(connector)
        client["testdb"].list_collection_names.return_value = ["orders", "users"]
        client["testdb"].watch.return_value.__enter__ = MagicMock(return_value=MagicMock())
        client["testdb"].watch.return_value.__exit__ = MagicMock(return_value=False)

        results = connector.check_permissions()
        read = next(r for r in results if r.name == "Database read access")
        assert read.status == Status.PASS
        assert "2 collections" in read.detail

    def test_read_access_fail_unauthorized(self, connector):
        client = _attach_mock_client(connector)
        err = OperationFailure("not authorized", code=13)
        client["testdb"].list_collection_names.side_effect = err

        results = connector.check_permissions()
        read = next(r for r in results if r.name == "Database read access")
        assert read.status == Status.FAIL
        assert read.remediation is not None
        assert "grantRolesToUser" in read.remediation

    def test_change_stream_access_pass(self, connector):
        client = _attach_mock_client(connector)
        client["testdb"].list_collection_names.return_value = []
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=MagicMock())
        cm.__exit__ = MagicMock(return_value=False)
        client["testdb"].watch.return_value = cm

        results = connector.check_permissions()
        cs = next(r for r in results if r.name == "Change stream access")
        assert cs.status == Status.PASS

    def test_change_stream_access_fail(self, connector):
        client = _attach_mock_client(connector)
        client["testdb"].list_collection_names.return_value = []
        client["testdb"].watch.side_effect = OperationFailure("unauthorized", code=13)

        results = connector.check_permissions()
        cs = next(r for r in results if r.name == "Change stream access")
        assert cs.status == Status.FAIL
        assert cs.remediation is not None


# ── CDC ────────────────────────────────────────────────────────────────────────

class TestCDC:
    def test_replica_set_pass(self, connector):
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=48)
        first_doc = {"ts": MagicMock(as_datetime=MagicMock(return_value=old))}
        last_doc  = {"ts": MagicMock(as_datetime=MagicMock(return_value=now))}
        _make_oplog_client(connector, first_doc, last_doc)

        results = connector.check_cdc()
        topo = next(r for r in results if r.name == "Replica set topology")
        assert topo.status == Status.PASS

    def test_standalone_topology_fails(self, connector):
        client = _attach_mock_client(connector)
        client.admin.command.side_effect = OperationFailure("not running with --replSet", code=76)

        results = connector.check_cdc()
        topo = next(r for r in results if r.name == "Replica set topology")
        assert topo.status == Status.FAIL
        assert "replica set" in topo.remediation.lower()

    def test_oplog_window_warn_when_short(self, connector):
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=2)
        first_doc = {"ts": MagicMock(as_datetime=MagicMock(return_value=old))}
        last_doc  = {"ts": MagicMock(as_datetime=MagicMock(return_value=now))}
        _make_oplog_client(connector, first_doc, last_doc)

        results = connector.check_cdc()
        oplog_result = next(r for r in results if r.name == "Oplog window")
        assert oplog_result.status == Status.WARN
        assert oplog_result.remediation is not None
        assert "replSetResizeOplog" in oplog_result.remediation

    def test_oplog_window_pass_when_sufficient(self, connector):
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=48)
        first_doc = {"ts": MagicMock(as_datetime=MagicMock(return_value=old))}
        last_doc  = {"ts": MagicMock(as_datetime=MagicMock(return_value=now))}
        _make_oplog_client(connector, first_doc, last_doc)

        results = connector.check_cdc()
        oplog_result = next(r for r in results if r.name == "Oplog window")
        assert oplog_result.status == Status.PASS
        assert oplog_result.remediation is None


# ── JDBC ───────────────────────────────────────────────────────────────────────

class TestJDBC:
    def test_pass_when_pymongo_v4(self, connector):
        with patch("connector_toolkit.checks.mongo.pymongo") as mock_py:
            mock_py.version = "4.6.1"
            results = connector.check_jdbc()
        assert results[0].status == Status.PASS

    def test_warn_when_pymongo_v3(self, connector):
        with patch("connector_toolkit.checks.mongo.pymongo") as mock_py:
            mock_py.version = "3.12.0"
            results = connector.check_jdbc()
        assert results[0].status == Status.WARN
        assert results[0].remediation is not None

    def test_fail_when_pymongo_missing(self, connector):
        with patch("connector_toolkit.checks.mongo.pymongo", None):
            results = connector.check_jdbc()
        assert results[0].status == Status.FAIL
        assert "pip install" in results[0].remediation
