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
