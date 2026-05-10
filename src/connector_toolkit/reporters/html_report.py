"""
HTML reporter — produces a self-contained single-file HTML report.

The output file embeds all CSS inline and requires no external dependencies,
so it can be shared as an email attachment, saved to S3, or opened directly
in any browser.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Optional

from ..models import RunReport, Status
from .base import BaseReporter

_STATUS_EMOJI = {
    "PASS": "✔",
    "WARN": "⚠",
    "FAIL": "✘",
    "SKIP": "–",
}

_STATUS_COLOR = {
    "PASS": "#1a7f37",
    "WARN": "#bf8700",
    "FAIL": "#cf222e",
    "SKIP": "#6e7781",
}

_STATUS_BG = {
    "PASS": "#dafbe1",
    "WARN": "#fff8c5",
    "FAIL": "#ffebe9",
    "SKIP": "#f6f8fa",
}


def _html_report(run: RunReport) -> str:
    config = run.config
    summary = run.summary
    verbose = config.verbose

    # Mask password
    safe_host = (
        f"{config.db_type}://{config.user}:***@{config.host}:{config.port}/{config.db}"
    )

    # Group results by category
    by_category: dict = {}
    for r in run.results:
        by_category.setdefault(r.category.value, []).append(r)

    # Build check rows
    rows_html = ""
    for category, checks in by_category.items():
        rows_html += f"""
        <tr class="category-header">
          <td colspan="4">{category.upper()}</td>
        </tr>"""
        for check in checks:
            s = check.status.value
            timing = f'<span class="timing">{check.duration_ms}ms</span>' \
                     if verbose and check.duration_ms is not None else ""
            remediation = ""
            if check.remediation and check.status in (Status.FAIL, Status.WARN):
                remediation = f'<div class="remediation">→ {check.remediation}</div>'
            exception = ""
            if verbose and check.exception:
                exception = f'<pre class="exception">{check.exception.strip()}</pre>'

            rows_html += f"""
        <tr class="check-row status-{s.lower()}">
          <td class="status-cell">
            <span class="badge" style="color:{_STATUS_COLOR[s]};background:{_STATUS_BG[s]}">
              {_STATUS_EMOJI[s]} {s}
            </span>
          </td>
          <td class="name-cell">{check.name} {timing}</td>
          <td class="detail-cell">{check.detail or ""}</td>
          <td class="fix-cell">{remediation}{exception}</td>
        </tr>"""

    # Summary bar
    total_timing = (
        f'<span class="total-timing">  {run.total_duration_ms}ms total</span>'
        if run.total_duration_ms is not None else ""
    )

    timestamp = run.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Connector check — {config.host} ({config.db_type})</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          font-size: 14px; color: #1f2328; background: #f6f8fa; padding: 24px; }}
  .card {{ background: #fff; border: 1px solid #d0d7de; border-radius: 8px;
           max-width: 960px; margin: 0 auto; overflow: hidden; }}
  .header {{ padding: 20px 24px; border-bottom: 1px solid #d0d7de; }}
  .header h1 {{ font-size: 18px; font-weight: 600; margin-bottom: 4px; }}
  .header .meta {{ font-size: 12px; color: #656d76; }}
  .summary-bar {{ display: flex; gap: 24px; padding: 14px 24px;
                  border-bottom: 1px solid #d0d7de; background: #f6f8fa; }}
  .summary-item {{ display: flex; align-items: center; gap: 6px;
                   font-size: 13px; font-weight: 500; }}
  .dot {{ width: 10px; height: 10px; border-radius: 50%; }}
  .dot-pass {{ background: #1a7f37; }}
  .dot-warn {{ background: #bf8700; }}
  .dot-fail {{ background: #cf222e; }}
  .dot-skip {{ background: #6e7781; }}
  .total-timing {{ font-size: 12px; color: #656d76; margin-left: auto; align-self: center; }}
  table {{ width: 100%; border-collapse: collapse; }}
  td {{ padding: 8px 16px; vertical-align: top; border-bottom: 1px solid #f0f0f0; }}
  .category-header td {{ background: #f6f8fa; font-weight: 600; font-size: 11px;
                          text-transform: uppercase; letter-spacing: 0.06em;
                          color: #656d76; padding: 10px 16px 6px; }}
  .status-cell {{ width: 100px; white-space: nowrap; }}
  .name-cell {{ width: 220px; font-weight: 500; }}
  .detail-cell {{ color: #656d76; font-family: ui-monospace, monospace; font-size: 12px; }}
  .fix-cell {{ font-size: 12px; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px;
            font-size: 12px; font-weight: 600; }}
  .remediation {{ margin-top: 4px; color: #656d76; font-family: ui-monospace, monospace;
                   white-space: pre-wrap; word-break: break-word; }}
  .exception {{ margin-top: 6px; padding: 8px; background: #fff5f5; border: 1px solid #ffcdd2;
                border-radius: 4px; color: #c62828; font-size: 11px; overflow-x: auto; }}
  .timing {{ font-size: 11px; color: #939fa9; font-weight: 400; margin-left: 4px; }}
  .footer {{ padding: 12px 24px; font-size: 11px; color: #939fa9;
             border-top: 1px solid #d0d7de; background: #f6f8fa; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #0d1117; color: #c9d1d9; }}
    .card {{ background: #161b22; border-color: #30363d; }}
    .header .meta, .detail-cell, .total-timing, .timing {{ color: #8b949e; }}
    .summary-bar, .category-header td, .footer {{ background: #1c2128; }}
    .category-header td {{ color: #8b949e; }}
    td {{ border-bottom-color: #21262d; }}
    .remediation {{ color: #8b949e; }}
  }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <h1>Connector readiness check</h1>
    <div class="meta">{safe_host} &nbsp;·&nbsp; {timestamp}</div>
  </div>
  <div class="summary-bar">
    <div class="summary-item"><span class="dot dot-pass"></span>{summary.passed} passed</div>
    <div class="summary-item"><span class="dot dot-warn"></span>{summary.warned} warned</div>
    <div class="summary-item"><span class="dot dot-fail"></span>{summary.failed} failed</div>
    <div class="summary-item"><span class="dot dot-skip"></span>{summary.skipped} skipped</div>
    {total_timing}
  </div>
  <table>
    {rows_html}
  </table>
  <div class="footer">
    Generated by connector-support-toolkit &nbsp;·&nbsp;
    {len(run.results)} checks across {len(by_category)} categories
  </div>
</div>
</body>
</html>"""


class HtmlReporter(BaseReporter):
    reporter_type = "html"

    def report(self, run: RunReport) -> None:
        html = _html_report(run)
        output_file = run.config.output_file

        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"HTML report written to {output_file}")
        else:
            sys.stdout.write(html + "\n")
