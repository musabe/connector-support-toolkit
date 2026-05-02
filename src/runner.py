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
