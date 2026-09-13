"""Every path the statarb scripts use, resolved in one place.

Each script used to work out where the store, the reports and the logs lived
from its own location. That worked until the directory was reorganised, at
which point every script had to be edited. One module now owns the answer.

Layout:

    statarb/
      plan/       the plan and its per-step splits
      code/       these scripts
      costs/      broker cost profiles, one JSON per broker
      logs/       trial logs, one row per run
      worklog/    write-ups of what was done, for a human to read
      studies/    output produced by the scripts
        pairs/        pair_report.py
        backtests/    backtest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent
ROOT = CODE.parent
DEVELOPMENT = ROOT.parent

PLAN = ROOT / "plan"
COSTS = ROOT / "costs"
LOGS = ROOT / "logs"
WORKLOG = ROOT / "worklog"
STUDIES = ROOT / "studies"
PAIR_STUDIES = STUDIES / "pairs"
BACKTEST_STUDIES = STUDIES / "backtests"

MARKETDATA = DEVELOPMENT / "marketdata"
STORE = MARKETDATA / "store"

TRIALS = LOGS / "trials.csv"
BACKTEST_LOG = LOGS / "backtests.csv"


def ensure_marketdata_importable() -> None:
    """Put the marketdata package on the import path.

    It is a sibling directory rather than an installed package, so the scripts
    reach it by path. Called at import time by everything that reads the store.
    """
    if str(MARKETDATA) not in sys.path:
        sys.path.insert(0, str(MARKETDATA))


def ensure_code_importable() -> None:
    """Let the scripts import each other when run from any directory."""
    if str(CODE) not in sys.path:
        sys.path.insert(0, str(CODE))
