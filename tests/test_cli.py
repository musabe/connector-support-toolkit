"""
Tests for CLI argument parsing, flag wiring, and driver dependency check.
Replaces the old test_cli.py (which imported from src.connector_check).
"""
from __future__ import annotations

import sys
import pytest
from unittest.mock import MagicMock, patch

from connector_toolkit.cli import build_parser, _parse_skip, main
from connector_toolkit.models import Category


# ── Argument parsing ──────────────────────────────────────────────────────────

_BASE_ARGS = [
    "run",
    "--host", "localhost",
    "--port", "5432",
    "--db", "testdb",
    "--user", "admin",
    "--password", "secret",
    "--db-type", "postgres",
]


class TestArgParsing:
    def test_required_flags_parsed(self):
        args = build_parser().parse_args(_BASE_ARGS)
        assert args.host == "localhost"
        assert args.port == 5432
        assert args.db == "testdb"
        assert args.user == "admin"
        assert args.password == "secret"
        assert args.db_type == "postgres"

    def test_port_cast_to_int(self):
        args = build_parser().parse_args(_BASE_ARGS)
        assert isinstance(args.port, int)

    def test_skip_default_is_none(self):
        args = build_parser().parse_args(_BASE_ARGS)
        assert args.skip is None

    def test_output_file_default_is_none(self):
        args = build_parser().parse_args(_BASE_ARGS)
        assert args.output_file is None

    def test_timeout_default_is_none(self):
        args = build_parser().parse_args(_BASE_ARGS)
        assert args.timeout is None

    def test_output_file_parsed(self):
        args = build_parser().parse_args(_BASE_ARGS + ["--output-file", "report.json"])
        assert args.output_file == "report.json"

    def test_skip_parsed(self):
        args = build_parser().parse_args(_BASE_ARGS + ["--skip", "cdc,jdbc"])
        assert args.skip == "cdc,jdbc"

    def test_timeout_parsed(self):
        args = build_parser().parse_args(_BASE_ARGS + ["--timeout", "30"])
        assert args.timeout == 30


# ── _parse_skip helper ────────────────────────────────────────────────────────

class TestParseSkip:
    def test_empty_string_returns_empty_list(self):
        assert _parse_skip("") == []

    def test_single_category(self):
        assert _parse_skip("cdc") == [Category.CDC]

    def test_multiple_categories(self):
        result = _parse_skip("cdc,jdbc")
        assert Category.CDC in result
        assert Category.JDBC in result

    def test_whitespace_stripped(self):
        result = _parse_skip("cdc, jdbc")
        assert Category.CDC in result
        assert Category.JDBC in result

    def test_invalid_category_exits(self):
        with pytest.raises(SystemExit):
            _parse_skip("notacat")


# ── main() integration ────────────────────────────────────────────────────────

class TestMain:
    def _mock_report(self):
        from connector_toolkit.models import RunReport, RunConfig, Summary
        from datetime import datetime, timezone
        config = RunConfig(
            host="localhost", port=5432, db="testdb",
            user="admin", password="secret", db_type="postgres",
        )
        return RunReport(
            config=config,
            results=[],
            summary=Summary(passed=1),
            timestamp=datetime.now(timezone.utc),
        )

    def test_main_calls_runner_run(self):
        mock_report = self._mock_report()
        with patch("connector_toolkit.cli.runner.run", return_value=mock_report) as mock_run, \
             patch("connector_toolkit.cli.runner.exit_code", return_value=0), \
             pytest.raises(SystemExit):
            main(_BASE_ARGS)
        mock_run.assert_called_once()

    def test_main_passes_skip_categories(self):
        mock_report = self._mock_report()
        with patch("connector_toolkit.cli.runner.run", return_value=mock_report) as mock_run, \
             patch("connector_toolkit.cli.runner.exit_code", return_value=0), \
             pytest.raises(SystemExit):
            main(_BASE_ARGS + ["--skip", "cdc,jdbc"])
        config_used = mock_run.call_args[0][0]
        assert Category.CDC in config_used.skip
        assert Category.JDBC in config_used.skip

    def test_main_passes_output_file(self):
        mock_report = self._mock_report()
        with patch("connector_toolkit.cli.runner.run", return_value=mock_report) as mock_run, \
             patch("connector_toolkit.cli.runner.exit_code", return_value=0), \
             pytest.raises(SystemExit):
            main(_BASE_ARGS + ["--output-file", "report.json"])
        config_used = mock_run.call_args[0][0]
        assert config_used.output_file == "report.json"

    def test_main_passes_timeout(self):
        mock_report = self._mock_report()
        with patch("connector_toolkit.cli.runner.run", return_value=mock_report) as mock_run, \
             patch("connector_toolkit.cli.runner.exit_code", return_value=0), \
             pytest.raises(SystemExit):
            main(_BASE_ARGS + ["--timeout", "30"])
        config_used = mock_run.call_args[0][0]
        assert config_used.timeout == 30

    def test_main_exits_with_runner_exit_code(self):
        mock_report = self._mock_report()
        with patch("connector_toolkit.cli.runner.run", return_value=mock_report), \
             patch("connector_toolkit.cli.runner.exit_code", return_value=2), \
             pytest.raises(SystemExit) as exc:
            main(_BASE_ARGS)
        assert exc.value.code == 2

    def test_main_missing_required_args_exits(self):
        with pytest.raises(SystemExit):
            main(["--host", "localhost"])  # missing port, db, user, password, db-type
