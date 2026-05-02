# Connector Support Toolkit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI tool that runs connectivity, permissions, CDC readiness, and JDBC/driver checks against PostgreSQL or MySQL, printing colored terminal results and optionally saving a JSON report.

**Architecture:** `BaseChecker` is an abstract class subclassed by `PostgresChecker` and `MySQLChecker`, each implementing four check-category methods. `CheckRunner` instantiates the right checker, sequences the four categories, and short-circuits all downstream checks to SKIP when connectivity fails. `Reporter` handles terminal output (rich) and JSON file writing independently of checker logic.

**Tech Stack:** Python 3.8+, psycopg2-binary, mysql-connector-python, rich, pytest, unittest.mock (stdlib)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `requirements.txt` | Create | Third-party dependencies |
| `src/models.py` | Create | `CheckResult` dataclass |
| `src/checkers/__init__.py` | Create | Package marker |
| `src/checkers/base.py` | Create | `BaseChecker` abstract class |
| `src/checkers/postgres.py` | Create | `PostgresChecker` — all 4 check categories |
| `src/checkers/mysql.py` | Create | `MySQLChecker` — all 4 check categories |
| `src/runner.py` | Create | `CheckRunner` — orchestration + cascade logic |
| `src/reporter.py` | Create | `Reporter` — terminal (rich) + JSON output |
| `src/connector_check.py` | Modify | CLI entry point (argparse) |
| `tests/test_models.py` | Create | Unit tests for `CheckResult` and `BaseChecker` |
| `tests/test_reporter.py` | Create | Unit tests for `Reporter` |
| `tests/test_runner.py` | Create | Unit tests for `CheckRunner` |
| `tests/test_postgres_checker.py` | Create | Unit tests for `PostgresChecker` (mocked DB) |
| `tests/test_mysql_checker.py` | Create | Unit tests for `MySQLChecker` (mocked DB) |
| `tests/test_cli.py` | Create | Unit tests for CLI entry point |
| `tests/test_checks.py` | Modify | Replace stub with index comment |
| `docker/docker-compose.yml` | Modify | Postgres + MySQL with CDC flags enabled |

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `src/checkers/__init__.py`

- [ ] **Step 1: Create `requirements.txt`**

```
psycopg2-binary>=2.9
mysql-connector-python>=8.0
rich>=13.0
pytest>=7.0
```

- [ ] **Step 2: Create `src/checkers/__init__.py`** (empty file)

- [ ] **Step 3: Commit**

```bash
git add requirements.txt src/checkers/__init__.py
git commit -m "chore: add dependencies and checkers package"
```

---

### Task 2: CheckResult model

**Files:**
- Create: `src/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_models.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.models'`

- [ ] **Step 3: Implement `CheckResult`**

Create `src/models.py`:

```python
from dataclasses import dataclass


@dataclass
class CheckResult:
    category: str
    name: str
    status: str
    detail: str
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_models.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: add CheckResult model"
```

---

### Task 3: BaseChecker abstract class

**Files:**
- Create: `src/checkers/base.py`
- Modify: `tests/test_models.py` (append BaseChecker tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_models.py::test_base_checker_cannot_be_instantiated_directly -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `BaseChecker`**

Create `src/checkers/base.py`:

```python
from abc import ABC, abstractmethod
from typing import List

from src.models import CheckResult


class BaseChecker(ABC):
    def __init__(self, host: str, port: int, db: str, user: str, password: str):
        self.host = host
        self.port = port
        self.db = db
        self.user = user
        self.password = password
        self._conn = None

    @abstractmethod
    def check_connectivity(self) -> List[CheckResult]: ...

    @abstractmethod
    def check_permissions(self) -> List[CheckResult]: ...

    @abstractmethod
    def check_cdc(self) -> List[CheckResult]: ...

    @abstractmethod
    def check_jdbc(self) -> List[CheckResult]: ...

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
```

- [ ] **Step 4: Run all model tests**

```bash
pytest tests/test_models.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/checkers/base.py tests/test_models.py
git commit -m "feat: add BaseChecker abstract class"
```

---

### Task 4: Reporter

**Files:**
- Create: `src/reporter.py`
- Create: `tests/test_reporter.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reporter.py`:

```python
import json
import os
import tempfile
from io import StringIO

from rich.console import Console

from src.models import CheckResult
from src.reporter import Reporter


def _reporter_with_buffer():
    buf = StringIO()
    reporter = Reporter(console=Console(file=buf, highlight=False))
    return reporter, buf


def test_terminal_output_shows_category_header():
    reporter, buf = _reporter_with_buffer()
    reporter.print_terminal([CheckResult('connectivity', 'TCP reachability', 'PASS', 'host=localhost')])
    assert 'CONNECTIVITY' in buf.getvalue()


def test_terminal_output_shows_check_name_and_status():
    reporter, buf = _reporter_with_buffer()
    reporter.print_terminal([CheckResult('connectivity', 'TCP reachability', 'PASS', 'host=localhost')])
    output = buf.getvalue()
    assert 'PASS' in output
    assert 'TCP reachability' in output


def test_terminal_output_groups_by_category():
    reporter, buf = _reporter_with_buffer()
    results = [
        CheckResult('connectivity', 'TCP reachability', 'PASS', ''),
        CheckResult('connectivity', 'SSL', 'PASS', ''),
        CheckResult('permissions', 'Replication', 'WARN', ''),
    ]
    reporter.print_terminal(results)
    output = buf.getvalue()
    assert output.index('CONNECTIVITY') < output.index('PERMISSIONS')


def test_json_report_structure():
    reporter, _ = _reporter_with_buffer()
    results = [
        CheckResult('connectivity', 'TCP reachability', 'PASS', 'host=localhost'),
        CheckResult('cdc', 'wal_level', 'FAIL', 'found: replica'),
    ]
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        path = f.name
    try:
        reporter.write_json(results, host='localhost', db_type='postgres', output_file=path)
        with open(path) as f:
            report = json.load(f)
        assert report['host'] == 'localhost'
        assert report['db_type'] == 'postgres'
        assert report['summary']['passed'] == 1
        assert report['summary']['failed'] == 1
        assert report['summary']['warned'] == 0
        assert len(report['checks']) == 2
        assert 'timestamp' in report
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_reporter.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.reporter'`

- [ ] **Step 3: Implement `Reporter`**

Create `src/reporter.py`:

```python
import json
from datetime import datetime, timezone
from typing import List, Optional

from rich.console import Console

from src.models import CheckResult

_STATUS_BADGE = {
    'PASS': '[green]✔ PASS[/green]',
    'WARN': '[yellow]⚠ WARN[/yellow]',
    'FAIL': '[red]✗ FAIL[/red]',
    'SKIP': '[dim]– SKIP[/dim]',
}


class Reporter:
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def print_terminal(self, results: List[CheckResult]) -> None:
        current_category = None
        for result in results:
            if result.category != current_category:
                current_category = result.category
                self.console.print(f'\n[bold][{current_category.upper()}][/bold]')
            badge = _STATUS_BADGE.get(result.status, result.status)
            self.console.print(f'  {badge}  {result.name:<30} {result.detail}')

    def write_json(self, results: List[CheckResult], host: str, db_type: str, output_file: str) -> None:
        key_map = {'PASS': 'passed', 'WARN': 'warned', 'FAIL': 'failed', 'SKIP': 'skipped'}
        summary = {'passed': 0, 'warned': 0, 'failed': 0, 'skipped': 0}
        for r in results:
            key = key_map.get(r.status)
            if key:
                summary[key] += 1
        report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'host': host,
            'db_type': db_type,
            'summary': summary,
            'checks': [
                {'category': r.category, 'name': r.name, 'status': r.status, 'detail': r.detail}
                for r in results
            ],
        }
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_reporter.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/reporter.py tests/test_reporter.py
git commit -m "feat: add Reporter for terminal and JSON output"
```

---

### Task 5: CheckRunner + checker stubs

**Files:**
- Create: `src/runner.py`
- Create: `src/checkers/postgres.py` (stub — full implementation in Task 6)
- Create: `src/checkers/mysql.py` (stub — full implementation in Task 7)
- Create: `tests/test_runner.py`

- [ ] **Step 1: Create stub checkers so runner.py can import them**

Create `src/checkers/postgres.py`:

```python
from typing import List
from src.checkers.base import BaseChecker
from src.models import CheckResult


class PostgresChecker(BaseChecker):
    def check_connectivity(self) -> List[CheckResult]: return []
    def check_permissions(self) -> List[CheckResult]: return []
    def check_cdc(self) -> List[CheckResult]: return []
    def check_jdbc(self) -> List[CheckResult]: return []
```

Create `src/checkers/mysql.py`:

```python
from typing import List
from src.checkers.base import BaseChecker
from src.models import CheckResult


class MySQLChecker(BaseChecker):
    def check_connectivity(self) -> List[CheckResult]: return []
    def check_permissions(self) -> List[CheckResult]: return []
    def check_cdc(self) -> List[CheckResult]: return []
    def check_jdbc(self) -> List[CheckResult]: return []
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_runner.py`:

```python
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
```

- [ ] **Step 3: Run to verify failure**

```bash
pytest tests/test_runner.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.runner'`

- [ ] **Step 4: Implement `CheckRunner`**

Create `src/runner.py`:

```python
from typing import List, Optional

from src.checkers.mysql import MySQLChecker
from src.checkers.postgres import PostgresChecker
from src.models import CheckResult


class CheckRunner:
    def __init__(self, db_type: str, host: str, port: int, db: str, user: str, password: str,
                 skip: Optional[List[str]] = None):
        self.skip = skip or []
        self.host = host
        self.db_type = db_type
        if db_type == 'postgres':
            self.checker = PostgresChecker(host, port, db, user, password)
        elif db_type == 'mysql':
            self.checker = MySQLChecker(host, port, db, user, password)
        else:
            raise ValueError(f'Unknown db_type: {db_type}')

    def run(self) -> List[CheckResult]:
        results: List[CheckResult] = []

        if 'connectivity' not in self.skip:
            conn_results = self.checker.check_connectivity()
            results.extend(conn_results)
            if any(r.status == 'FAIL' for r in conn_results):
                for category in ('permissions', 'cdc', 'jdbc'):
                    if category not in self.skip:
                        results.append(CheckResult(
                            category, 'All checks', 'SKIP', 'Skipped — connectivity failed',
                        ))
                self.checker.close()
                return results

        for category, method in (
            ('permissions', self.checker.check_permissions),
            ('cdc', self.checker.check_cdc),
            ('jdbc', self.checker.check_jdbc),
        ):
            if category not in self.skip:
                results.extend(method())

        self.checker.close()
        return results
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_runner.py -v
```

Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add src/runner.py src/checkers/postgres.py src/checkers/mysql.py tests/test_runner.py
git commit -m "feat: add CheckRunner with connectivity-fail cascade and checker stubs"
```

---

### Task 6: PostgresChecker — full implementation

**Files:**
- Modify: `src/checkers/postgres.py`
- Create: `tests/test_postgres_checker.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_postgres_checker.py`:

```python
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
    cur.fetchone.return_value = (True,)  # SSL in use
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
    # fetchone call order: SSL (connectivity) → rolreplication → has_db_privilege → rolsuper
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
    # fetchone order: SSL → wal_level → (used_slots, max_slots) → wal_sender_timeout
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
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_postgres_checker.py -v
```

Expected: Most tests fail — stubs return empty lists

- [ ] **Step 3: Implement `PostgresChecker`**

Replace `src/checkers/postgres.py` with:

```python
import socket
import time
from typing import List

import psycopg2

from src.checkers.base import BaseChecker
from src.models import CheckResult


class PostgresChecker(BaseChecker):

    def check_connectivity(self) -> List[CheckResult]:
        results: List[CheckResult] = []

        try:
            sock = socket.create_connection((self.host, self.port), timeout=5)
            sock.close()
            results.append(CheckResult(
                'connectivity', 'TCP reachability', 'PASS',
                f'host={self.host} port={self.port}',
            ))
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            results.append(CheckResult('connectivity', 'TCP reachability', 'FAIL', str(e)))
            return results

        try:
            start = time.monotonic()
            self._conn = psycopg2.connect(
                host=self.host, port=self.port, dbname=self.db,
                user=self.user, password=self.password,
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            results.append(CheckResult(
                'connectivity', 'Authenticated connect', 'PASS', f'latency={latency_ms}ms',
            ))
        except psycopg2.OperationalError as e:
            results.append(CheckResult('connectivity', 'Authenticated connect', 'FAIL', str(e)))
            return results

        try:
            with self._conn.cursor() as cur:
                cur.execute('SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()')
                row = cur.fetchone()
                ssl = row[0] if row else False
            results.append(CheckResult(
                'connectivity', 'SSL', 'PASS', f'in use: {"yes" if ssl else "no"}',
            ))
        except Exception as e:
            results.append(CheckResult('connectivity', 'SSL', 'WARN', str(e)))

        return results

    def check_permissions(self) -> List[CheckResult]:
        results: List[CheckResult] = []
        if self._conn is None:
            return results

        try:
            with self._conn.cursor() as cur:
                cur.execute('SELECT rolreplication FROM pg_roles WHERE rolname = current_user')
                row = cur.fetchone()
                has_repl = row[0] if row else False
            results.append(CheckResult(
                'permissions', 'Replication privilege',
                'PASS' if has_repl else 'FAIL',
                'rolreplication=true' if has_repl else 'User lacks replication privilege',
            ))
        except Exception as e:
            results.append(CheckResult('permissions', 'Replication privilege', 'FAIL', str(e)))

        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT has_database_privilege(current_user, current_database(), 'CONNECT')"
                )
                row = cur.fetchone()
                has_access = row[0] if row else False
            results.append(CheckResult(
                'permissions', 'Database read access',
                'PASS' if has_access else 'FAIL',
                'CONNECT privilege granted' if has_access else 'No CONNECT privilege on database',
            ))
        except Exception as e:
            results.append(CheckResult('permissions', 'Database read access', 'FAIL', str(e)))

        try:
            with self._conn.cursor() as cur:
                cur.execute('SELECT rolsuper FROM pg_roles WHERE rolname = current_user')
                row = cur.fetchone()
                is_super = row[0] if row else False
            results.append(CheckResult(
                'permissions', 'Superuser status',
                'PASS' if is_super else 'WARN',
                'superuser=true' if is_super
                else 'Not superuser — CDC setup may require elevated privileges',
            ))
        except Exception as e:
            results.append(CheckResult('permissions', 'Superuser status', 'WARN', str(e)))

        return results

    def check_cdc(self) -> List[CheckResult]:
        results: List[CheckResult] = []
        if self._conn is None:
            return results

        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT setting FROM pg_settings WHERE name = 'wal_level'")
                row = cur.fetchone()
                wal_level = row[0] if row else 'unknown'
            results.append(CheckResult(
                'cdc', 'wal_level',
                'PASS' if wal_level == 'logical' else 'FAIL',
                'logical' if wal_level == 'logical'
                else f'wal_level={wal_level} (must be logical)',
            ))
        except Exception as e:
            results.append(CheckResult('cdc', 'wal_level', 'FAIL', str(e)))

        try:
            with self._conn.cursor() as cur:
                cur.execute('''
                    SELECT
                        (SELECT count(*) FROM pg_replication_slots) AS used_slots,
                        (SELECT setting::int FROM pg_settings WHERE name = 'max_replication_slots') AS max_slots
                ''')
                row = cur.fetchone()
                used, max_slots = (row[0], row[1]) if row else (0, 0)
            available = max_slots - used
            results.append(CheckResult(
                'cdc', 'Replication slots',
                'PASS' if available > 0 else 'FAIL',
                f'{used}/{max_slots} used'
                + ('' if available > 0 else ' — no slots available'),
            ))
        except Exception as e:
            results.append(CheckResult('cdc', 'Replication slots', 'FAIL', str(e)))

        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT setting FROM pg_settings WHERE name = 'wal_sender_timeout'")
                row = cur.fetchone()
                timeout = row[0] if row else 'unknown'
            results.append(CheckResult('cdc', 'wal_sender_timeout', 'PASS', str(timeout)))
        except Exception as e:
            results.append(CheckResult('cdc', 'wal_sender_timeout', 'WARN', str(e)))

        return results

    def check_jdbc(self) -> List[CheckResult]:
        results: List[CheckResult] = []

        try:
            version_str = psycopg2.__version__.split()[0]
            parts = version_str.split('.')
            major, minor = int(parts[0]), int(parts[1])
            if (major, minor) < (2, 9):
                results.append(CheckResult(
                    'jdbc', 'Driver version', 'WARN',
                    f'psycopg2=={version_str} — upgrade to >=2.9 to avoid asyncio issues on Python 3.10+',
                ))
            else:
                results.append(CheckResult('jdbc', 'Driver version', 'PASS', f'psycopg2=={version_str}'))
        except Exception as e:
            results.append(CheckResult('jdbc', 'Driver version', 'FAIL', str(e)))

        results.append(CheckResult(
            'jdbc', 'Common issues reference', 'PASS',
            'Connection refused: check host/port/firewall. '
            'SSL handshake: set sslmode=require or sslmode=disable. '
            'Auth failure: verify pg_hba.conf allows md5/scram-sha-256.',
        ))

        return results
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_postgres_checker.py -v
```

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/checkers/postgres.py tests/test_postgres_checker.py
git commit -m "feat: implement PostgresChecker with all four check categories"
```

---

### Task 7: MySQLChecker — full implementation

**Files:**
- Modify: `src/checkers/mysql.py`
- Create: `tests/test_mysql_checker.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mysql_checker.py`:

```python
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
    # fetchone order: SSL → log_bin → binlog_format → binlog_row_image → gtid_mode
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
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_mysql_checker.py -v
```

Expected: Most tests fail — stubs return empty lists

- [ ] **Step 3: Implement `MySQLChecker`**

Replace `src/checkers/mysql.py` with:

```python
import socket
import time
from typing import List

import mysql.connector

from src.checkers.base import BaseChecker
from src.models import CheckResult


class MySQLChecker(BaseChecker):

    def check_connectivity(self) -> List[CheckResult]:
        results: List[CheckResult] = []

        try:
            sock = socket.create_connection((self.host, self.port), timeout=5)
            sock.close()
            results.append(CheckResult(
                'connectivity', 'TCP reachability', 'PASS',
                f'host={self.host} port={self.port}',
            ))
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            results.append(CheckResult('connectivity', 'TCP reachability', 'FAIL', str(e)))
            return results

        try:
            start = time.monotonic()
            self._conn = mysql.connector.connect(
                host=self.host, port=self.port, database=self.db,
                user=self.user, password=self.password,
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            results.append(CheckResult(
                'connectivity', 'Authenticated connect', 'PASS', f'latency={latency_ms}ms',
            ))
        except mysql.connector.Error as e:
            results.append(CheckResult('connectivity', 'Authenticated connect', 'FAIL', str(e)))
            return results

        try:
            cur = self._conn.cursor()
            cur.execute("SHOW STATUS LIKE 'Ssl_cipher'")
            row = cur.fetchone()
            cur.close()
            ssl = bool(row and row[1])
            results.append(CheckResult(
                'connectivity', 'SSL', 'PASS', f'in use: {"yes" if ssl else "no"}',
            ))
        except Exception as e:
            results.append(CheckResult('connectivity', 'SSL', 'WARN', str(e)))

        return results

    def check_permissions(self) -> List[CheckResult]:
        results: List[CheckResult] = []
        if self._conn is None:
            return results

        try:
            cur = self._conn.cursor()
            cur.execute('SHOW GRANTS FOR current_user()')
            grants = [row[0] for row in cur.fetchall()]
            cur.close()

            has_repl = any(
                'REPLICATION SLAVE' in g or 'REPLICATION CLIENT' in g or 'ALL PRIVILEGES' in g
                for g in grants
            )
            results.append(CheckResult(
                'permissions', 'Replication privilege',
                'PASS' if has_repl else 'FAIL',
                'REPLICATION SLAVE granted' if has_repl
                else 'User lacks REPLICATION SLAVE privilege',
            ))

            has_select = any('SELECT' in g or 'ALL PRIVILEGES' in g for g in grants)
            results.append(CheckResult(
                'permissions', 'Database read access',
                'PASS' if has_select else 'FAIL',
                'SELECT granted' if has_select else 'No SELECT privilege',
            ))
        except Exception as e:
            results.append(CheckResult('permissions', 'Replication privilege', 'FAIL', str(e)))

        return results

    def _show_variable(self, name: str):
        cur = self._conn.cursor()
        cur.execute('SHOW GLOBAL VARIABLES LIKE %s', (name,))
        row = cur.fetchone()
        cur.close()
        return row[1] if row else None

    def check_cdc(self) -> List[CheckResult]:
        results: List[CheckResult] = []
        if self._conn is None:
            return results

        for var_name, expected in (
            ('log_bin', 'ON'),
            ('binlog_format', 'ROW'),
            ('binlog_row_image', 'FULL'),
        ):
            try:
                value = self._show_variable(var_name)
                status = 'PASS' if value == expected else 'FAIL'
                detail = expected if status == 'PASS' else f'{var_name}={value} (must be {expected})'
                results.append(CheckResult('cdc', var_name, status, detail))
            except Exception as e:
                results.append(CheckResult('cdc', var_name, 'FAIL', str(e)))

        try:
            gtid = self._show_variable('gtid_mode')
            results.append(CheckResult(
                'cdc', 'gtid_mode',
                'PASS' if gtid == 'ON' else 'WARN',
                f'gtid_mode={gtid}'
                + ('' if gtid == 'ON' else ' — GTID recommended for reliable CDC'),
            ))
        except Exception as e:
            results.append(CheckResult('cdc', 'gtid_mode', 'WARN', str(e)))

        return results

    def check_jdbc(self) -> List[CheckResult]:
        results: List[CheckResult] = []

        try:
            version_str = mysql.connector.__version__
            major = int(version_str.split('.')[0])
            if major < 8:
                results.append(CheckResult(
                    'jdbc', 'Driver version', 'WARN',
                    f'mysql-connector-python=={version_str} — upgrade to >=8.0 for full SSL and auth plugin support',
                ))
            else:
                results.append(CheckResult(
                    'jdbc', 'Driver version', 'PASS',
                    f'mysql-connector-python=={version_str}',
                ))
        except Exception as e:
            results.append(CheckResult('jdbc', 'Driver version', 'FAIL', str(e)))

        results.append(CheckResult(
            'jdbc', 'Common issues reference', 'PASS',
            'Connection refused: check host/port/firewall. '
            'SSL handshake: set ssl_disabled=True or provide ssl_ca. '
            'Auth plugin: add auth_plugin=mysql_native_password if caching_sha2_password not supported.',
        ))

        return results
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_mysql_checker.py -v
```

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/checkers/mysql.py tests/test_mysql_checker.py
git commit -m "feat: implement MySQLChecker with all four check categories"
```

---

### Task 8: CLI entry point

**Files:**
- Modify: `src/connector_check.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_cli.py::test_cli_runs_checks_and_prints -v
```

Expected: FAIL — `src.connector_check` has no `main` function

- [ ] **Step 3: Implement CLI**

Replace `src/connector_check.py` with:

```python
import sys
import argparse
from typing import List, Optional


def _check_dependencies(db_type: str) -> None:
    if db_type == 'postgres':
        try:
            import psycopg2
        except ImportError:
            print('Error: psycopg2 not installed. Run: pip install psycopg2-binary')
            sys.exit(1)
    elif db_type == 'mysql':
        try:
            import mysql.connector
        except ImportError:
            print('Error: mysql-connector-python not installed. Run: pip install mysql-connector-python')
            sys.exit(1)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description='Validate database connector readiness')
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--db', required=True)
    parser.add_argument('--user', required=True)
    parser.add_argument('--password', required=True)
    parser.add_argument('--db-type', required=True, choices=['postgres', 'mysql'])
    parser.add_argument('--output-file', default=None)
    parser.add_argument('--skip', default='')
    args = parser.parse_args(argv)

    skip = [s.strip() for s in args.skip.split(',') if s.strip()]

    _check_dependencies(args.db_type)

    from src.runner import CheckRunner
    from src.reporter import Reporter

    runner = CheckRunner(args.db_type, args.host, args.port, args.db, args.user, args.password, skip=skip)
    reporter = Reporter()

    results = runner.run()
    reporter.print_terminal(results)

    if args.output_file:
        reporter.write_json(results, host=args.host, db_type=args.db_type, output_file=args.output_file)


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run CLI tests**

```bash
pytest tests/test_cli.py -v
```

Expected: 4 passed

- [ ] **Step 5: Run the full test suite**

```bash
pytest tests/ -v --ignore=tests/test_checks.py
```

Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/connector_check.py tests/test_cli.py
git commit -m "feat: implement CLI entry point with argparse"
```

---

### Task 9: Docker Compose for local integration testing

**Files:**
- Modify: `docker/docker-compose.yml`

- [ ] **Step 1: Write `docker-compose.yml`**

Replace `docker/docker-compose.yml` with:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: demo
      POSTGRES_PASSWORD: demo
      POSTGRES_DB: test
    ports:
      - "5432:5432"
    command: >
      postgres
        -c wal_level=logical
        -c max_replication_slots=10
        -c max_wal_senders=10

  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: demo
      MYSQL_DATABASE: test
      MYSQL_USER: demo
      MYSQL_PASSWORD: demo
    ports:
      - "3306:3306"
    command: >
      --log-bin=mysql-bin
      --binlog-format=ROW
      --binlog-row-image=FULL
      --gtid-mode=ON
      --enforce-gtid-consistency=ON
```

- [ ] **Step 2: Commit**

```bash
git add docker/docker-compose.yml
git commit -m "chore: configure docker-compose for integration testing with CDC flags"
```

---

### Task 10: Clean up stub files

**Files:**
- Modify: `tests/test_checks.py`

- [ ] **Step 1: Replace the stub with an index comment**

Replace `tests/test_checks.py` with:

```python
# Tests are organized by module:
# tests/test_models.py            — CheckResult, BaseChecker
# tests/test_reporter.py          — Reporter
# tests/test_runner.py            — CheckRunner
# tests/test_postgres_checker.py  — PostgresChecker
# tests/test_mysql_checker.py     — MySQLChecker
# tests/test_cli.py               — CLI entry point
```

- [ ] **Step 2: Run the complete test suite one final time**

```bash
pytest tests/ -v
```

Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_checks.py
git commit -m "chore: replace test_checks stub with module index"
```
