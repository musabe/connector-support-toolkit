import pytest
from unittest.mock import MagicMock, patch
import psycopg2

from src.checkers.postgres import PostgresChecker


def _checker():
    return PostgresChecker('localhost', 5432, 'testdb', 'user', 'pass')


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


# --- Connectivity ---

@patch('src.checkers.postgres.psycopg2.connect')
@patch('src.checkers.postgres.socket.create_connection')
def test_connectivity_pass(mock_sock, mock_connect):
    mock_sock.return_value = MagicMock()
    conn, cur = _mock_conn()
    mock_connect.return_value = conn
    cur.fetchone.return_value = (True,)
    results = _checker().check_connectivity()
    assert all(r.status != 'FAIL' for r in results)
    assert any('TCP' in r.name for r in results)
    assert any('SSL' in r.name for r in results)


@patch('src.checkers.postgres.socket.create_connection')
def test_connectivity_tcp_fail(mock_sock):
    mock_sock.side_effect = ConnectionRefusedError('Connection refused')
    results = _checker().check_connectivity()
    assert results[0].status == 'FAIL'
    assert 'TCP' in results[0].name


@patch('src.checkers.postgres.psycopg2.connect')
@patch('src.checkers.postgres.socket.create_connection')
def test_connectivity_auth_fail(mock_sock, mock_connect):
    mock_sock.return_value = MagicMock()
    mock_connect.side_effect = psycopg2.OperationalError('password authentication failed')
    results = _checker().check_connectivity()
    auth = next(r for r in results if 'connect' in r.name.lower())
    assert auth.status == 'FAIL'


# --- Permissions ---

@patch('src.checkers.postgres.psycopg2.connect')
@patch('src.checkers.postgres.socket.create_connection')
def test_permissions_replication_pass(mock_sock, mock_connect):
    conn, cur = _mock_conn()
    mock_sock.return_value = MagicMock()
    mock_connect.return_value = conn
    cur.fetchone.side_effect = [(True,), (True,), (True,), (False,)]
    checker = _checker()
    checker.check_connectivity()
    results = checker.check_permissions()
    repl = next(r for r in results if 'Replication' in r.name)
    assert repl.status == 'PASS'


@patch('src.checkers.postgres.psycopg2.connect')
@patch('src.checkers.postgres.socket.create_connection')
def test_permissions_no_replication_fails(mock_sock, mock_connect):
    conn, cur = _mock_conn()
    mock_sock.return_value = MagicMock()
    mock_connect.return_value = conn
    cur.fetchone.side_effect = [(True,), (False,), (True,), (False,)]
    checker = _checker()
    checker.check_connectivity()
    results = checker.check_permissions()
    repl = next(r for r in results if 'Replication' in r.name)
    assert repl.status == 'FAIL'


@patch('src.checkers.postgres.psycopg2.connect')
@patch('src.checkers.postgres.socket.create_connection')
def test_permissions_not_superuser_warns(mock_sock, mock_connect):
    conn, cur = _mock_conn()
    mock_sock.return_value = MagicMock()
    mock_connect.return_value = conn
    cur.fetchone.side_effect = [(True,), (True,), (True,), (False,)]
    checker = _checker()
    checker.check_connectivity()
    results = checker.check_permissions()
    superuser = next(r for r in results if 'Superuser' in r.name)
    assert superuser.status == 'WARN'


# --- CDC ---

@patch('src.checkers.postgres.psycopg2.connect')
@patch('src.checkers.postgres.socket.create_connection')
def test_cdc_wal_level_logical_passes(mock_sock, mock_connect):
    conn, cur = _mock_conn()
    mock_sock.return_value = MagicMock()
    mock_connect.return_value = conn
    cur.fetchone.side_effect = [(True,), ('logical',), (1, 10), ('5000ms',)]
    checker = _checker()
    checker.check_connectivity()
    results = checker.check_cdc()
    wal = next(r for r in results if 'wal_level' in r.name)
    assert wal.status == 'PASS'


@patch('src.checkers.postgres.psycopg2.connect')
@patch('src.checkers.postgres.socket.create_connection')
def test_cdc_wal_level_not_logical_fails(mock_sock, mock_connect):
    conn, cur = _mock_conn()
    mock_sock.return_value = MagicMock()
    mock_connect.return_value = conn
    cur.fetchone.side_effect = [(True,), ('replica',), (0, 10), ('5000ms',)]
    checker = _checker()
    checker.check_connectivity()
    results = checker.check_cdc()
    wal = next(r for r in results if 'wal_level' in r.name)
    assert wal.status == 'FAIL'


@patch('src.checkers.postgres.psycopg2.connect')
@patch('src.checkers.postgres.socket.create_connection')
def test_cdc_no_slots_available_fails(mock_sock, mock_connect):
    conn, cur = _mock_conn()
    mock_sock.return_value = MagicMock()
    mock_connect.return_value = conn
    cur.fetchone.side_effect = [(True,), ('logical',), (3, 3), ('5000ms',)]
    checker = _checker()
    checker.check_connectivity()
    results = checker.check_cdc()
    slots = next(r for r in results if 'slot' in r.name.lower())
    assert slots.status == 'FAIL'
    assert 'no slots available' in slots.detail


# --- JDBC ---

def test_jdbc_returns_results():
    results = _checker().check_jdbc()
    assert len(results) >= 1
    assert any('Driver' in r.name for r in results)
    assert all(r.status in ('PASS', 'WARN', 'FAIL') for r in results)
