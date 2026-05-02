import pytest
from unittest.mock import MagicMock, patch
import mysql.connector

from src.checkers.mysql import MySQLChecker


def _checker():
    return MySQLChecker('localhost', 3306, 'testdb', 'user', 'pass')


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


# --- Connectivity ---

@patch('src.checkers.mysql.mysql.connector.connect')
@patch('src.checkers.mysql.socket.create_connection')
def test_connectivity_pass(mock_sock, mock_connect):
    mock_sock.return_value = MagicMock()
    conn, cur = _mock_conn()
    mock_connect.return_value = conn
    cur.fetchone.return_value = ('Ssl_cipher', 'AES256-SHA')
    results = _checker().check_connectivity()
    assert all(r.status != 'FAIL' for r in results)


@patch('src.checkers.mysql.socket.create_connection')
def test_connectivity_tcp_fail(mock_sock):
    mock_sock.side_effect = ConnectionRefusedError('Connection refused')
    results = _checker().check_connectivity()
    assert results[0].status == 'FAIL'
    assert 'TCP' in results[0].name


@patch('src.checkers.mysql.mysql.connector.connect')
@patch('src.checkers.mysql.socket.create_connection')
def test_connectivity_auth_fail(mock_sock, mock_connect):
    mock_sock.return_value = MagicMock()
    mock_connect.side_effect = mysql.connector.Error('Access denied')
    results = _checker().check_connectivity()
    auth = next(r for r in results if 'connect' in r.name.lower())
    assert auth.status == 'FAIL'


# --- Permissions ---

@patch('src.checkers.mysql.mysql.connector.connect')
@patch('src.checkers.mysql.socket.create_connection')
def test_permissions_replication_pass(mock_sock, mock_connect):
    conn, cur = _mock_conn()
    mock_sock.return_value = MagicMock()
    mock_connect.return_value = conn
    cur.fetchone.return_value = ('Ssl_cipher', 'AES256-SHA')
    cur.fetchall.return_value = [("GRANT ALL PRIVILEGES ON *.* TO 'user'@'localhost'",)]
    checker = _checker()
    checker.check_connectivity()
    results = checker.check_permissions()
    repl = next(r for r in results if 'Replication' in r.name)
    assert repl.status == 'PASS'


@patch('src.checkers.mysql.mysql.connector.connect')
@patch('src.checkers.mysql.socket.create_connection')
def test_permissions_no_replication_fails(mock_sock, mock_connect):
    conn, cur = _mock_conn()
    mock_sock.return_value = MagicMock()
    mock_connect.return_value = conn
    cur.fetchone.return_value = ('Ssl_cipher', 'AES256-SHA')
    cur.fetchall.return_value = [("GRANT SELECT ON *.* TO 'user'@'localhost'",)]
    checker = _checker()
    checker.check_connectivity()
    results = checker.check_permissions()
    repl = next(r for r in results if 'Replication' in r.name)
    assert repl.status == 'FAIL'


# --- CDC ---

@patch('src.checkers.mysql.mysql.connector.connect')
@patch('src.checkers.mysql.socket.create_connection')
def test_cdc_correct_settings_pass(mock_sock, mock_connect):
    conn, cur = _mock_conn()
    mock_sock.return_value = MagicMock()
    mock_connect.return_value = conn
    cur.fetchone.side_effect = [
        ('Ssl_cipher', 'AES256-SHA'),
        ('log_bin', 'ON'),
        ('binlog_format', 'ROW'),
        ('binlog_row_image', 'FULL'),
        ('gtid_mode', 'ON'),
    ]
    checker = _checker()
    checker.check_connectivity()
    results = checker.check_cdc()
    log_bin = next(r for r in results if 'log_bin' in r.name)
    assert log_bin.status == 'PASS'


@patch('src.checkers.mysql.mysql.connector.connect')
@patch('src.checkers.mysql.socket.create_connection')
def test_cdc_binlog_off_fails(mock_sock, mock_connect):
    conn, cur = _mock_conn()
    mock_sock.return_value = MagicMock()
    mock_connect.return_value = conn
    cur.fetchone.side_effect = [
        ('Ssl_cipher', 'AES256-SHA'),
        ('log_bin', 'OFF'),
        ('binlog_format', 'ROW'),
        ('binlog_row_image', 'FULL'),
        ('gtid_mode', 'OFF'),
    ]
    checker = _checker()
    checker.check_connectivity()
    results = checker.check_cdc()
    log_bin = next(r for r in results if 'log_bin' in r.name)
    assert log_bin.status == 'FAIL'


# --- JDBC ---

def test_jdbc_returns_results():
    results = _checker().check_jdbc()
    assert any('Driver' in r.name for r in results)
    assert all(r.status in ('PASS', 'WARN', 'FAIL') for r in results)
