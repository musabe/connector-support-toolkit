"""
Tests for CheckResult dataclass and BaseConnector ABC.
Replaces the old test_models.py (which imported from src.models / src.checkers.base).
"""
from __future__ import annotations

import pytest

from connector_toolkit.models import Category, CheckResult, RunConfig, Status
from connector_toolkit.base import BaseConnector


# ── CheckResult ───────────────────────────────────────────────────────────────

class TestCheckResult:
    def test_fields_stored_correctly(self):
        r = CheckResult(
            category=Category.CONNECTIVITY,
            name="TCP reachability",
            status=Status.PASS,
            detail="host=localhost port=5432",
        )
        assert r.category == Category.CONNECTIVITY
        assert r.name == "TCP reachability"
        assert r.status == Status.PASS
        assert r.detail == "host=localhost port=5432"

    def test_remediation_defaults_to_none(self):
        r = CheckResult(category=Category.CDC, name="wal_level", status=Status.FAIL)
        assert r.remediation is None

    def test_remediation_stored_when_provided(self):
        r = CheckResult(
            category=Category.CDC,
            name="wal_level",
            status=Status.FAIL,
            remediation="ALTER SYSTEM SET wal_level = logical;",
        )
        assert "ALTER SYSTEM" in r.remediation

    def test_all_valid_statuses_accepted(self):
        for status in Status:
            r = CheckResult(category=Category.CONNECTIVITY, name="test", status=status)
            assert r.status == status

    def test_all_valid_categories_accepted(self):
        for category in Category:
            r = CheckResult(category=category, name="test", status=Status.PASS)
            assert r.category == category

    def test_passed_helper(self):
        assert CheckResult(category=Category.CONNECTIVITY, name="t", status=Status.PASS).passed()
        assert not CheckResult(category=Category.CONNECTIVITY, name="t", status=Status.FAIL).passed()

    def test_failed_helper(self):
        assert CheckResult(category=Category.CONNECTIVITY, name="t", status=Status.FAIL).failed()
        assert not CheckResult(category=Category.CONNECTIVITY, name="t", status=Status.PASS).failed()

    def test_to_dict_excludes_none_remediation(self):
        r = CheckResult(category=Category.CONNECTIVITY, name="TCP", status=Status.PASS, detail="ok")
        d = r.to_dict()
        assert "remediation" not in d

    def test_to_dict_includes_remediation_when_set(self):
        r = CheckResult(
            category=Category.CONNECTIVITY, name="TCP", status=Status.FAIL,
            remediation="fix it",
        )
        assert r.to_dict()["remediation"] == "fix it"


# ── BaseConnector ABC ─────────────────────────────────────────────────────────

class TestBaseConnector:
    def test_cannot_be_instantiated_directly(self):
        config = RunConfig(
            host="localhost", port=5432, db="db",
            user="u", password="p", db_type="postgres",
        )
        with pytest.raises(TypeError):
            BaseConnector(config)

    def test_subclass_without_all_methods_raises(self):
        class IncompleteConnector(BaseConnector):
            pass  # does not implement any abstract methods

        config = RunConfig(
            host="localhost", port=5432, db="db",
            user="u", password="p", db_type="postgres",
        )
        with pytest.raises(TypeError):
            IncompleteConnector(config)

    def test_subclass_with_all_methods_instantiates(self):
        class CompleteConnector(BaseConnector):
            db_type = "test"
            def check_connectivity(self): return []
            def check_permissions(self): return []
            def check_cdc(self): return []
            def check_jdbc(self): return []

        config = RunConfig(
            host="localhost", port=5432, db="db",
            user="u", password="p", db_type="test",
        )
        c = CompleteConnector(config)
        assert c.config.host == "localhost"
