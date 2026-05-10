"""
YAML config loader for connector-support-toolkit.

Responsibilities
----------------
1. Read a YAML file from disk.
2. Interpolate ${VAR} and ${VAR:-default} references against os.environ.
3. Validate required fields and types.
4. Merge with CLI-supplied overrides (CLI wins).
5. Return a RunConfig ready for runner.run().

Design decisions
----------------
- No third-party schema library (pydantic, cerberus) — keeps dependencies minimal.
- Interpolation uses a simple regex rather than a custom YAML loader, so the
  file stays valid YAML that any editor can parse and highlight.
- Numeric casting (port, timeout) happens after interpolation so ${DB_PORT:-5432}
  works transparently.
- ConfigError is a plain Exception subclass; callers can catch it to produce
  clean error messages without tracebacks.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

from .models import Category, RunConfig


# ── Exceptions ────────────────────────────────────────────────────────────────

class ConfigError(Exception):
    """Raised for any config loading, interpolation, or validation failure."""


# ── Interpolation ─────────────────────────────────────────────────────────────

_ENV_RE = re.compile(r"\$\{([^}]+)\}")


def _interpolate_value(value: str) -> str:
    """
    Replace ${VAR} and ${VAR:-default} placeholders in *value* with their
    environment variable values.

    Raises ConfigError if a variable has no default and is not set.
    """
    def _replace(match: re.Match) -> str:
        expr = match.group(1)
        if ":-" in expr:
            var, default = expr.split(":-", 1)
            return os.environ.get(var.strip(), default)
        var = expr.strip()
        if var not in os.environ:
            raise ConfigError(
                f"Environment variable '${{{var}}}' is referenced in the config "
                f"file but is not set. Either export the variable or provide a "
                f"default: ${{{var}:-your_default_here}}"
            )
        return os.environ[var]

    return _ENV_RE.sub(_replace, value)


def _interpolate(obj: Any) -> Any:
    """Recursively interpolate env vars in all string values of a parsed YAML object."""
    if isinstance(obj, str):
        return _interpolate_value(obj)
    if isinstance(obj, dict):
        return {k: _interpolate(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_interpolate(item) for item in obj]
    return obj  # int, float, bool, None — pass through unchanged


# ── Loading ───────────────────────────────────────────────────────────────────

def load(path: str | Path) -> dict:
    """
    Load and interpolate a YAML config file.

    Returns the raw dict (before RunConfig conversion) so callers can merge
    CLI overrides before constructing RunConfig.

    Raises ConfigError on any IO, parse, or interpolation failure.
    """
    if yaml is None:
        raise ConfigError(
            "PyYAML is not installed. Install it with: pip install pyyaml"
        )

    p = Path(path)
    if not p.exists():
        raise ConfigError(f"Config file not found: {p}")

    try:
        raw = yaml.safe_load(p.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse config file '{p}': {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(
            f"Config file '{p}' must contain a YAML mapping at the top level, "
            f"got {type(raw).__name__}."
        )

    try:
        return _interpolate(raw)
    except ConfigError:
        raise
    except Exception as exc:
        raise ConfigError(f"Interpolation error in '{p}': {exc}") from exc


# ── Validation and casting ────────────────────────────────────────────────────

_REQUIRED = ("host", "port", "db", "user", "password", "db_type")
_VALID_DB_TYPES = ("postgres", "mysql")
_VALID_CATEGORIES = {c.value for c in Category}


def _require(data: dict, key: str) -> Any:
    val = data.get(key)
    if val is None or (isinstance(val, str) and not val.strip()):
        raise ConfigError(
            f"Required field '{key}' is missing or empty in the config file."
        )
    return val


def _cast_int(data: dict, key: str, default: int) -> int:
    val = data.get(key, default)
    try:
        return int(val)
    except (TypeError, ValueError):
        raise ConfigError(
            f"Field '{key}' must be an integer (got {val!r})."
        )


def _parse_skip(data: dict) -> list[Category]:
    raw = data.get("skip", [])
    if not isinstance(raw, list):
        raise ConfigError("Field 'skip' must be a YAML list.")
    result = []
    for item in raw:
        if item not in _VALID_CATEGORIES:
            raise ConfigError(
                f"Invalid skip category '{item}'. "
                f"Valid values: {', '.join(sorted(_VALID_CATEGORIES))}"
            )
        result.append(Category(item))
    return result


def validate(data: dict) -> None:
    """Raise ConfigError if any required field is missing or invalid."""
    for key in _REQUIRED:
        _require(data, key)

    db_type = data["db_type"]
    if db_type not in _VALID_DB_TYPES:
        raise ConfigError(
            f"Invalid db_type '{db_type}'. "
            f"Valid values: {', '.join(_VALID_DB_TYPES)}"
        )

    _cast_int(data, "port", 5432)
    _cast_int(data, "timeout", 10)
    _parse_skip(data)


# ── Public API ────────────────────────────────────────────────────────────────

def to_run_config(data: dict, overrides: Optional[dict] = None) -> RunConfig:
    """
    Convert an interpolated config dict to a RunConfig, applying CLI overrides.

    Parameters
    ----------
    data:
        Dict returned by load(). Must be pre-validated.
    overrides:
        Dict of CLI-supplied values. Only non-None values override the file.
        Keys match RunConfig field names (e.g. "host", "port", "db_type").

    Returns
    -------
    RunConfig
    """
    merged = dict(data)
    if overrides:
        for key, val in overrides.items():
            if val is not None:
                merged[key] = val

    return RunConfig(
        host=str(merged["host"]),
        port=_cast_int(merged, "port", 5432),
        db=str(merged["db"]),
        user=str(merged["user"]),
        password=str(merged["password"]),
        db_type=str(merged["db_type"]),
        skip=_parse_skip(merged),
        output_file=merged.get("output_file") or None,
        timeout=_cast_int(merged, "timeout", 10),
    )


def load_config(path: str | Path, overrides: Optional[dict] = None) -> RunConfig:
    """
    Convenience function: load → interpolate → validate → merge → RunConfig.

    This is the single call site for production use in cli.py.
    """
    data = load(path)
    validate(data)
    return to_run_config(data, overrides)
