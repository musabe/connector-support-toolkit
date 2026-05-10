"""Unit tests for the YAML config loader — no filesystem or DB required."""
from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from connector_toolkit.config import (
    ConfigError,
    _interpolate,
    load,
    load_config,
    to_run_config,
    validate,
)
from connector_toolkit.models import Category


# ── Interpolation ─────────────────────────────────────────────────────────────

class TestInterpolation:
    def test_plain_string_unchanged(self):
        assert _interpolate("hello") == "hello"

    def test_simple_var(self, monkeypatch):
        monkeypatch.setenv("DB_HOST", "db.internal")
        assert _interpolate("${DB_HOST}") == "db.internal"

    def test_var_with_default_env_set(self, monkeypatch):
        monkeypatch.setenv("DB_PORT", "5433")
        assert _interpolate("${DB_PORT:-5432}") == "5433"

    def test_var_with_default_env_unset(self, monkeypatch):
        monkeypatch.delenv("DB_PORT", raising=False)
        assert _interpolate("${DB_PORT:-5432}") == "5432"

    def test_missing_var_no_default_raises(self, monkeypatch):
        monkeypatch.delenv("DB_PASSWORD", raising=False)
        with pytest.raises(ConfigError, match="DB_PASSWORD"):
            _interpolate("${DB_PASSWORD}")

    def test_partial_interpolation(self, monkeypatch):
        monkeypatch.setenv("REPORT_DIR", "reports")
        assert _interpolate("${REPORT_DIR:-out}/report.json") == "reports/report.json"

    def test_nested_dict(self, monkeypatch):
        monkeypatch.setenv("DB_HOST", "myhost")
        result = _interpolate({"host": "${DB_HOST}", "port": 5432})
        assert result == {"host": "myhost", "port": 5432}

    def test_list_values(self, monkeypatch):
        monkeypatch.setenv("CAT", "cdc")
        result = _interpolate(["${CAT}", "jdbc"])
        assert result == ["cdc", "jdbc"]

    def test_non_string_passthrough(self):
        assert _interpolate(5432) == 5432
        assert _interpolate(True) is True
        assert _interpolate(None) is None


# ── Validation ────────────────────────────────────────────────────────────────

_VALID_DATA = {
    "host": "localhost",
    "port": "5432",
    "db": "mydb",
    "user": "myuser",
    "password": "secret",
    "db_type": "postgres",
    "timeout": 10,
    "skip": [],
    "output_file": None,
}


class TestValidation:
    def test_valid_data_passes(self):
        validate(dict(_VALID_DATA))

    @pytest.mark.parametrize("missing_key", ["host", "port", "db", "user", "password", "db_type"])
    def test_missing_required_field_raises(self, missing_key):
        data = dict(_VALID_DATA)
        del data[missing_key]
        with pytest.raises(ConfigError, match=missing_key):
            validate(data)

    def test_invalid_db_type_raises(self):
        data = {**_VALID_DATA, "db_type": "oracle"}
        with pytest.raises(ConfigError, match="oracle"):
            validate(data)

    def test_invalid_skip_category_raises(self):
        data = {**_VALID_DATA, "skip": ["notacat"]}
        with pytest.raises(ConfigError, match="notacat"):
            validate(data)

    def test_skip_as_non_list_raises(self):
        data = {**_VALID_DATA, "skip": "cdc"}
        with pytest.raises(ConfigError, match="list"):
            validate(data)

    def test_port_non_integer_raises(self):
        data = {**_VALID_DATA, "port": "not_a_port"}
        with pytest.raises(ConfigError, match="port"):
            validate(data)


# ── to_run_config ─────────────────────────────────────────────────────────────

class TestToRunConfig:
    def test_basic_conversion(self):
        rc = to_run_config(dict(_VALID_DATA))
        assert rc.host == "localhost"
        assert rc.port == 5432
        assert rc.db_type == "postgres"
        assert rc.skip == []
        assert rc.timeout == 10

    def test_port_cast_from_string(self):
        rc = to_run_config({**_VALID_DATA, "port": "5433"})
        assert rc.port == 5433

    def test_skip_converted_to_enum(self):
        rc = to_run_config({**_VALID_DATA, "skip": ["cdc", "jdbc"]})
        assert Category.CDC in rc.skip
        assert Category.JDBC in rc.skip

    def test_cli_override_wins(self):
        rc = to_run_config(dict(_VALID_DATA), overrides={"host": "override-host"})
        assert rc.host == "override-host"

    def test_none_override_does_not_replace(self):
        rc = to_run_config(dict(_VALID_DATA), overrides={"host": None})
        assert rc.host == "localhost"

    def test_output_file_none_when_missing(self):
        rc = to_run_config(dict(_VALID_DATA))
        assert rc.output_file is None


# ── File loading (integration) ────────────────────────────────────────────────

class TestLoadFromFile:
    def _write(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "toolkit.yml"
        p.write_text(textwrap.dedent(content))
        return p

    def test_valid_file_loads(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DB_PASSWORD", "supersecret")
        f = self._write(tmp_path, """
            host: localhost
            port: 5432
            db: testdb
            user: admin
            password: ${DB_PASSWORD}
            db_type: postgres
        """)
        rc = load_config(f)
        assert rc.password == "supersecret"
        assert rc.host == "localhost"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            load(tmp_path / "nonexistent.yml")

    def test_invalid_yaml_raises(self, tmp_path):
        f = tmp_path / "bad.yml"
        f.write_text("key: [unclosed")
        with pytest.raises(ConfigError, match="parse"):
            load(f)

    def test_missing_env_var_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DB_PASSWORD", raising=False)
        f = self._write(tmp_path, """
            host: localhost
            port: 5432
            db: testdb
            user: admin
            password: ${DB_PASSWORD}
            db_type: postgres
        """)
        with pytest.raises(ConfigError, match="DB_PASSWORD"):
            load_config(f)

    def test_cli_override_wins_over_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DB_PASSWORD", "pw")
        f = self._write(tmp_path, """
            host: filehost
            port: 5432
            db: testdb
            user: admin
            password: ${DB_PASSWORD}
            db_type: postgres
        """)
        rc = load_config(f, overrides={"host": "clihost"})
        assert rc.host == "clihost"

    def test_skip_list_parsed_from_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DB_PASSWORD", "pw")
        f = self._write(tmp_path, """
            host: localhost
            port: 5432
            db: testdb
            user: admin
            password: ${DB_PASSWORD}
            db_type: mysql
            skip:
              - jdbc
              - cdc
        """)
        rc = load_config(f)
        assert Category.JDBC in rc.skip
        assert Category.CDC in rc.skip
