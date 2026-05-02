import sys
import pytest
from unittest.mock import MagicMock, patch

from src.models import CheckResult

_SAMPLE = [
    CheckResult('connectivity', 'TCP reachability', 'PASS', 'host=localhost'),
    CheckResult('cdc', 'wal_level', 'FAIL', 'replica'),
]

_BASE_ARGS = [
    '--host', 'localhost',
    '--port', '5432',
    '--db', 'testdb',
    '--user', 'admin',
    '--password', 'secret',
    '--db-type', 'postgres',
]


@patch('src.connector_check.Reporter')
@patch('src.connector_check.CheckRunner')
def test_cli_runs_checks_and_prints(MockRunner, MockReporter):
    mock_runner = MagicMock()
    mock_runner.run.return_value = _SAMPLE
    MockRunner.return_value = mock_runner
    mock_reporter = MagicMock()
    MockReporter.return_value = mock_reporter

    from src.connector_check import main
    main(_BASE_ARGS)

    MockRunner.assert_called_once_with('postgres', 'localhost', 5432, 'testdb', 'admin', 'secret', skip=[])
    mock_runner.run.assert_called_once()
    mock_reporter.print_terminal.assert_called_once_with(_SAMPLE)


@patch('src.connector_check.Reporter')
@patch('src.connector_check.CheckRunner')
def test_cli_writes_json_when_output_file_given(MockRunner, MockReporter):
    mock_runner = MagicMock()
    mock_runner.run.return_value = _SAMPLE
    MockRunner.return_value = mock_runner
    mock_reporter = MagicMock()
    MockReporter.return_value = mock_reporter

    from src.connector_check import main
    main(_BASE_ARGS + ['--output-file', 'report.json'])

    mock_reporter.write_json.assert_called_once_with(
        _SAMPLE, host='localhost', db_type='postgres', output_file='report.json',
    )


@patch('src.connector_check.Reporter')
@patch('src.connector_check.CheckRunner')
def test_cli_passes_skip_categories(MockRunner, MockReporter):
    mock_runner = MagicMock()
    mock_runner.run.return_value = []
    MockRunner.return_value = mock_runner
    MockReporter.return_value = MagicMock()

    from src.connector_check import main
    main(_BASE_ARGS + ['--skip', 'cdc,jdbc'])

    MockRunner.assert_called_once_with(
        'postgres', 'localhost', 5432, 'testdb', 'admin', 'secret', skip=['cdc', 'jdbc'],
    )


def test_check_dependencies_exits_on_missing_psycopg2(monkeypatch):
    monkeypatch.setitem(sys.modules, 'psycopg2', None)
    from src.connector_check import _check_dependencies
    with pytest.raises(SystemExit) as exc:
        _check_dependencies('postgres')
    assert exc.value.code == 1
