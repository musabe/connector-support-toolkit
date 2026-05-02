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
