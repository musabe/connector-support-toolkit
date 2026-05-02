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
