from dataclasses import dataclass


@dataclass
class CheckResult:
    category: str
    name: str
    status: str
    detail: str
