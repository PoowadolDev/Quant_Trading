"""Shared helpers: date parsing, logging setup, small formatters."""

from __future__ import annotations

import logging
import re
import sys

import pandas as pd

LOG = logging.getLogger("marketdata")

# "30d", "2y", "6mo", "12h", "4w" — optionally written with a leading minus.
_RELATIVE = re.compile(r"^-?(\d+)\s*(h|d|w|mo|y)$", re.IGNORECASE)

_SIMPLE_UNITS = {"h": "h", "d": "D", "w": "W"}


class UserError(Exception):
    """Bad input from the command line. Reported without a traceback."""


def parse_date(value: str | pd.Timestamp | None) -> pd.Timestamp | None:
    """Parse a CLI date into a UTC timestamp.

    Accepts absolute forms ("2024-01-01", "20240101", "2024-01-01 12:00"), the keywords
    "now" and "today", and relative offsets from now ("30d", "6mo", "2y", "12h", "4w").
    Returns None when given None, so "not specified" stays distinguishable from a date.
    """
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")

    text = str(value).strip().lower()
    if not text:
        return None

    now = pd.Timestamp.now(tz="UTC")
    if text == "now":
        return now
    if text == "today":
        return now.normalize()

    match = _RELATIVE.match(text)
    if match:
        amount, unit = int(match.group(1)), match.group(2).lower()
        if unit in _SIMPLE_UNITS:
            return now - pd.Timedelta(f"{amount}{_SIMPLE_UNITS[unit]}")
        if unit == "mo":
            return now - pd.DateOffset(months=amount)
        return now - pd.DateOffset(years=amount)

    try:
        stamp = pd.Timestamp(value)
    except Exception as exc:  # noqa: BLE001 - surfaced as a clean CLI error
        raise UserError(
            f"cannot parse date {value!r}. Use YYYY-MM-DD, YYYYMMDD, 'now', 'today', "
            "or a relative offset such as 30d / 6mo / 2y."
        ) from exc

    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def setup_logging(verbosity: int = 0, quiet: bool = False) -> None:
    """-v gives DEBUG, default is INFO, --quiet drops to WARNING."""
    if quiet:
        level = logging.WARNING
    elif verbosity >= 1:
        level = logging.DEBUG
    else:
        level = logging.INFO

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
    LOG.handlers[:] = [handler]
    LOG.setLevel(level)
    LOG.propagate = False


def human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num_bytes) < 1024 or unit == "GB":
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} GB"


def split_csv(value: str | None) -> list[str]:
    """Split a comma-separated CLI value; tolerate spaces and trailing commas."""
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]
