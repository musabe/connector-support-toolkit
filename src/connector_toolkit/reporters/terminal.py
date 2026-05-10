from __future__ import annotations

from typing import Optional
from rich.console import Console
from rich.text import Text

from ..models import Category, RunReport, Status
from .base import BaseReporter

_STATUS_STYLE: dict[Status, tuple[str, str]] = {
    Status.PASS: ("✔", "green"),
    Status.WARN: ("⚠", "yellow"),
    Status.FAIL: ("✘", "red"),
    Status.SKIP: ("–", "dim"),
}


class TerminalReporter(BaseReporter):
    reporter_type = "terminal"

    def __init__(self, console: Optional[Console] = None) -> None:
        self._console = console or Console()

    def report(self, run: RunReport) -> None:
        results_by_category: dict[Category, list] = {}
        for r in run.results:
            results_by_category.setdefault(r.category, []).append(r)

        for category, checks in results_by_category.items():
            self._console.print(f"\n[bold][{category.value.upper()}][/bold]")
            for check in checks:
                icon, style = _STATUS_STYLE[check.status]
                line = Text()
                line.append(f"  {icon} ", style=style)
                line.append(f"{check.status.value:<6}", style=f"bold {style}")
                line.append(f"  {check.name:<32}")
                if check.detail:
                    line.append(check.detail, style="dim")
                self._console.print(line)
                if check.remediation and check.status in (Status.FAIL, Status.WARN):
                    self._console.print(
                        f"         [dim]→ {check.remediation}[/dim]"
                    )

        s = run.summary
        self._console.print()
        self._console.print(
            f"[bold]Summary[/bold]  "
            f"[green]✔ {s.passed} passed[/green]  "
            f"[yellow]⚠ {s.warned} warned[/yellow]  "
            f"[red]✘ {s.failed} failed[/red]  "
            f"[dim]– {s.skipped} skipped[/dim]"
        )
