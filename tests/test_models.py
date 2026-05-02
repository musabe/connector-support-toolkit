from src.models import CheckResult


def test_check_result_fields():
    result = CheckResult(
        category='connectivity',
        name='TCP reachability',
        status='PASS',
        detail='host=localhost port=5432',
    )
    assert result.category == 'connectivity'
    assert result.name == 'TCP reachability'
    assert result.status == 'PASS'
    assert result.detail == 'host=localhost port=5432'


def test_check_result_valid_statuses():
    for status in ('PASS', 'WARN', 'FAIL', 'SKIP'):
        r = CheckResult('connectivity', 'test', status, '')
        assert r.status == status


import pytest
from src.checkers.base import BaseChecker


def test_base_checker_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BaseChecker('localhost', 5432, 'db', 'user', 'pass')


def test_base_checker_subclass_must_implement_all_methods():
    class IncompleteChecker(BaseChecker):
        pass

    with pytest.raises(TypeError):
        IncompleteChecker('localhost', 5432, 'db', 'user', 'pass')
