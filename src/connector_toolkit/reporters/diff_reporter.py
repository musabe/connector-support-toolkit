"""
Reporters for ReportDiff output.

DiffTerminalReporter — colour-coded terminal summary of changes.
DiffJsonReporter     — writes the full diff as a JSON file or stdout.
"""
from __future__ import annotations

import json
import sys
from typing import Optional

from rich.console import Console

from ..diff import CheckDelta, ReportDiff


class DiffTerminalReporter:
    def __init__(self, console: Optional[Console] = None) -> None:
        self._console = console or Console()

    def report(self, diff: ReportDiff) -> None:
        c = self._console

        c.print(f"\n[bold]Comparing reports[/bold]")
        c.print(f"  before  {diff.before_path}  ({diff.before_timestamp[:19]})")
        c.print(f"  after   {diff.after_path}  ({diff.after_timestamp[:19]})")
        c.print(f"  db_type {diff.db_type}  |  "
                f"host: {diff.before_host} → {diff.after_host}\n")

        if not diff.deltas:
            c.print("[green]No changes — both reports are identical.[/green]\n")
            self._print_summary(diff)
            return

        # Regressions first — most important
        if diff.regressions:
            c.print(f"[bold red]Regressions ({len(diff.regressions)})[/bold red]")
            for d in diff.regressions:
                self._print_delta(d)

        if diff.improvements:
            c.print(f"\n[bold green]Improvements ({len(diff.improvements)})[/bold green]")
            for d in diff.improvements:
                self._print_delta(d)

        if diff.added:
            c.print(f"\n[bold]New checks ({len(diff.added)})[/bold]")
            for d in diff.added:
                self._print_delta(d)

        if diff.removed:
            c.print(f"\n[bold]Removed checks ({len(diff.removed)})[/bold]")
            for d in diff.removed:
                self._print_delta(d)

        c.print()
        self._print_summary(diff)

    def _print_delta(self, d: CheckDelta) -> None:
        c = self._console
        before_str = d.before or "—"
        after_str  = d.after  or "—"

        status_color = {
            "PASS": "green", "WARN": "yellow",
            "FAIL": "red",   "SKIP": "dim",
        }
        b_col = status_color.get(before_str, "white")
        a_col = status_color.get(after_str,  "white")

        c.print(
            f"  [{b_col}]{before_str}[/{b_col}] → [{a_col}]{after_str}[/{a_col}]"
            f"  [dim]{d.category}[/dim]  {d.name}"
        )
        if d.detail_after:
            c.print(f"           detail: {d.detail_after}", style="dim")
        if d.remediation and d.after == "FAIL":
            c.print(f"           → {d.remediation}", style="dim")

    def _print_summary(self, diff: ReportDiff) -> None:
        c = self._console
        bs = diff.summary_before
        as_ = diff.summary_after
        d = diff.summary_delta

        def _fmt(label: str, before: int, after: int, delta: int, color: str) -> str:
            sign = "+" if delta > 0 else ""
            delta_str = f"({sign}{delta})" if delta != 0 else ""
            return f"[{color}]{label}: {before}→{after} {delta_str}[/{color}]"

        c.print(
            "[bold]Summary delta[/bold]  "
            + _fmt("passed",  bs.get("passed",  0), as_.get("passed",  0), d.passed,  "green")
            + "  "
            + _fmt("warned",  bs.get("warned",  0), as_.get("warned",  0), d.warned,  "yellow")
            + "  "
            + _fmt("failed",  bs.get("failed",  0), as_.get("failed",  0), d.failed,  "red")
            + "  "
            + _fmt("skipped", bs.get("skipped", 0), as_.get("skipped", 0), d.skipped, "dim")
        )

        if diff.regressions:
            c.print(
                f"\n[bold red]⚠  {len(diff.regressions)} regression(s) detected.[/bold red]"
            )
        elif not diff.deltas:
            c.print("\n[green]✔  No regressions.[/green]")
        else:
            c.print("\n[green]✔  No regressions.[/green]")


class DiffJsonReporter:
    def report(self, diff: ReportDiff, output_file: Optional[str] = None) -> None:
        payload = json.dumps(diff.to_dict(), indent=2)
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(payload)
            print(f"Diff written to {output_file}")
        else:
            sys.stdout.write(payload + "\n")
