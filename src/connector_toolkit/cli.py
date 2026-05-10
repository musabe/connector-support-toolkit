from __future__ import annotations

import argparse
import sys

from .models import Category, RunConfig
from . import runner
from .config import ConfigError, load_config


def _parse_skip(value: str) -> list[Category]:
    if not value:
        return []
    names = [v.strip() for v in value.split(",")]
    try:
        return [Category(n) for n in names if n]
    except ValueError as e:
        valid = ", ".join(c.value for c in Category)
        print(f"Invalid --skip value: {e}. Valid categories: {valid}", file=sys.stderr)
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="connector-check",
        description="Validate database connector readiness (connectivity, permissions, CDC, JDBC).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub = p.add_subparsers(dest="command")

    # ── run (default) ─────────────────────────────────────────────────────────
    run_p = sub.add_parser(
        "run",
        help="Run connector readiness checks (default when no subcommand given).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Config file:\n"
            "  Use --config toolkit.yml to load connection settings from a YAML file.\n"
            "  CLI flags always override config file values.\n"
            "  Env var interpolation: ${VAR} or ${VAR:-default}.\n"
            "  Copy toolkit.example.yml as a starting point."
        ),
    )
    _add_run_args(run_p)

    # ── compare ───────────────────────────────────────────────────────────────
    cmp_p = sub.add_parser(
        "compare",
        help="Diff two JSON reports produced by --output-file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  connector-check compare before.json after.json\n"
            "  connector-check compare before.json after.json --output-file diff.json\n\n"
            "Both reports must be from the same db_type and produced with --output-file."
        ),
    )
    cmp_p.add_argument("before", metavar="BEFORE", help="Path to the earlier JSON report")
    cmp_p.add_argument("after",  metavar="AFTER",  help="Path to the later JSON report")
    cmp_p.add_argument(
        "--output-file",
        default=None,
        dest="output_file",
        metavar="PATH",
        help="Write diff as JSON to this path instead of terminal output",
    )

    return p


def _add_run_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="Path to a YAML config file. CLI flags override file values.",
    )
    p.add_argument("--host",     default=None)
    p.add_argument("--port",     default=None, type=int)
    p.add_argument("--db",       default=None)
    p.add_argument("--user",     default=None)
    p.add_argument("--password", default=None)
    p.add_argument(
        "--db-type",
        default=None,
        dest="db_type",
        choices=list(runner.CONNECTOR_REGISTRY),
        metavar="DB_TYPE",
        help=f"One of: {', '.join(runner.CONNECTOR_REGISTRY)}",
    )
    p.add_argument(
        "--skip",
        default=None,
        metavar="CATEGORIES",
        help="Comma-separated categories to skip: connectivity,permissions,cdc,jdbc",
    )
    p.add_argument(
        "--output-file",
        default=None,
        dest="output_file",
        metavar="PATH",
        help="Write JSON report to this path instead of terminal output",
    )
    p.add_argument(
        "--timeout",
        default=None,
        type=int,
        metavar="SECONDS",
        help="Connection timeout in seconds (default: 10)",
    )


def _build_config_from_args(args: argparse.Namespace) -> RunConfig:
    missing = [
        flag for flag, val in [
            ("--host", args.host), ("--port", args.port), ("--db", args.db),
            ("--user", args.user), ("--password", args.password),
            ("--db-type", args.db_type),
        ] if val is None
    ]
    if missing:
        print(
            f"error: the following arguments are required when --config is not used: "
            f"{', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)

    return RunConfig(
        host=args.host,
        port=args.port,
        db=args.db,
        user=args.user,
        password=args.password,
        db_type=args.db_type,
        skip=_parse_skip(args.skip or ""),
        output_file=args.output_file,
        timeout=args.timeout or 10,
    )


def _run_command(args: argparse.Namespace) -> None:
    if args.config:
        cli_overrides = {
            k: v for k, v in {
                "host":        args.host,
                "port":        args.port,
                "db":          args.db,
                "user":        args.user,
                "password":    args.password,
                "db_type":     args.db_type,
                "output_file": args.output_file,
                "timeout":     args.timeout,
                "skip": (
                    [s.strip() for s in args.skip.split(",") if s.strip()]
                    if args.skip else None
                ),
            }.items() if v is not None
        }
        try:
            run_config = load_config(args.config, overrides=cli_overrides)
        except ConfigError as exc:
            print(f"Config error: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        run_config = _build_config_from_args(args)

    report = runner.run(run_config)
    sys.exit(runner.exit_code(report))


def _compare_command(args: argparse.Namespace) -> None:
    from .diff import DiffError, diff_reports, load_report
    from .reporters.diff_reporter import DiffJsonReporter, DiffTerminalReporter

    try:
        before = load_report(args.before)
        before["_source_path"] = args.before
        after  = load_report(args.after)
        after["_source_path"]  = args.after
        diff = diff_reports(before, after)
    except DiffError as exc:
        print(f"Diff error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.output_file:
        DiffJsonReporter().report(diff, output_file=args.output_file)
    else:
        DiffTerminalReporter().report(diff)

    sys.exit(1 if diff.regressions else 0)


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    known_subcommands = {"run", "compare"}
    if not argv or argv[0].startswith("-") or argv[0] not in known_subcommands:
        argv = ["run"] + list(argv)

    args = build_parser().parse_args(argv)

    if args.command == "compare":
        _compare_command(args)
    else:
        _run_command(args)


if __name__ == "__main__":
    main()
