import pytest
from unittest.mock import MagicMock, patch

from src.models import CheckResult
from src.runner import CheckRunner


def _make_checker_mock(connectivity_status='PASS'):
    checker = MagicMock()
    checker.check_connectivity.return_value = [
        CheckResult('connectivity', 'TCP reachability', connectivity_status, ''),
    ]
    checker.check_permissions.return_value = [
        CheckResult('permissions', 'Replication', 'PASS', ''),
    ]
    checker.check_cdc.return_value = [
        CheckResult('cdc', 'wal_level', 'PASS', 'logical'),
    ]
    checker.check_jdbc.return_value = [
        CheckResult('jdbc', 'Driver version', 'PASS', '2.9.9'),
    ]
    return checker


@patch('src.runner.PostgresChecker')
def test_runner_runs_all_categories(MockChecker):
    mock = _make_checker_mock()
    MockChecker.return_value = mock
    runner = CheckRunner('postgres', 'localhost', 5432, 'db', 'user', 'pass')
    results = runner.run()
    assert len(results) == 4
    assert mock.check_connectivity.called
    assert mock.check_permissions.called
    assert mock.check_cdc.called
    assert mock.check_jdbc.called


@patch('src.runner.PostgresChecker')
def test_runner_skips_downstream_on_connectivity_fail(MockChecker):
    mock = _make_checker_mock(connectivity_status='FAIL')
    MockChecker.return_value = mock
    runner = CheckRunner('postgres', 'localhost', 5432, 'db', 'user', 'pass')
    results = runner.run()
    skipped = [r for r in results if r.status == 'SKIP']
    assert len(skipped) == 3
    assert not mock.check_permissions.called
    assert not mock.check_cdc.called
    assert not mock.check_jdbc.called


@patch('src.runner.PostgresChecker')
def test_runner_skip_flag_excludes_category(MockChecker):
    mock = _make_checker_mock()
    MockChecker.return_value = mock
    runner = CheckRunner('postgres', 'localhost', 5432, 'db', 'user', 'pass', skip=['cdc'])
    runner.run()
    assert not mock.check_cdc.called
    assert mock.check_permissions.called


@patch('src.runner.MySQLChecker')
def test_runner_uses_mysql_checker(MockChecker):
    mock = _make_checker_mock()
    MockChecker.return_value = mock
    runner = CheckRunner('mysql', 'localhost', 3306, 'db', 'user', 'pass')
    runner.run()
    MockChecker.assert_called_once_with('localhost', 3306, 'db', 'user', 'pass')


def test_runner_raises_on_unknown_db_type():
    with pytest.raises(ValueError, match='Unknown db_type'):
        CheckRunner('oracle', 'localhost', 1521, 'db', 'user', 'pass')
