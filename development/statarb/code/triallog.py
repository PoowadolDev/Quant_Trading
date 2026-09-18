"""One CSV append, with the guard that stops a log corrupting itself.

Step 1 and Step 2 each grew their own copy of this. The copies agreed until a
column was added to one of them, at which point new values were written under an
old header and every row after that point was silently shifted by one field. The
guard below is the fix, and it lives in one module so there is one copy of it.

A log is a record of what was run. A log that quietly changes meaning half way
down is worse than no log, because it is still believed.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path


class SchemaChanged(Exception):
    """The file on disk was written by a different version of the caller."""


def stamp() -> str:
    """UTC, to the second, in the one format every log in this project uses."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def register(path: Path, campaign: str, trials: int, description: str) -> int:
    """Record that `trials` tests are about to be run, before running them.

    `append` records what happened. This records what is *about* to happen, and the
    difference is the whole point: a trial count reconstructed after a winner is found is
    a count of the tests somebody remembered, and the ones abandoned half way through are
    exactly the ones that inflate the search.

    Every distinct parameter set, universe variant and second-chance assessment is a trial.
    A candidate re-examined for whether it improves a book has been given a second
    opportunity to look good, and the deflated-Sharpe benchmark grows with the logarithm of
    how many opportunities were taken. Registering before the fact is what keeps that
    honest when the assessment finds nothing and nobody would have thought to log it.

    Returns the cumulative registered trial count across the whole file.
    """
    if trials < 0:
        raise ValueError("a campaign cannot register a negative number of trials")

    path = Path(path)
    row = {"run": 0, "run_utc": stamp(), "campaign": campaign,
           "trials": int(trials), "description": description}
    run = append(path, row)

    total = 0
    with path.open(newline="", encoding="utf-8") as fh:
        for line in csv.DictReader(fh):
            try:
                total += int(line["trials"])
            except (KeyError, TypeError, ValueError):
                continue
    return total


def append(path: Path, row: dict) -> int:
    """Add one row, returning its run number.

    `row` must contain a `run` key; its value is replaced with the count of
    rows already present plus one, so run numbers come from the file rather
    than from the caller's memory of it.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if "run" not in row:
        raise ValueError("every logged row needs a 'run' column")

    existing = 0
    if path.exists() and path.stat().st_size > 0:
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            header = next(reader, [])
            existing = sum(1 for _ in reader)
        if header and header != list(row):
            added = [c for c in row if c not in header]
            dropped = [c for c in header if c not in row]
            raise SchemaChanged(
                f"{path} was written by an older version of this script "
                f"(added {added or 'none'}, dropped {dropped or 'none'}). "
                "Rename it to keep the history and a fresh log will start. "
                "Nothing was written for this run.")

    row = dict(row)
    row["run"] = existing + 1
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row))
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    return row["run"]
