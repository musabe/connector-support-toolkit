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
