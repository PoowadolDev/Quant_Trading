"""Market data pipeline: fetch OHLCV history, store it as Parquet, inspect and validate it.

    from marketdata import Instrument, ParquetStore

    store = ParquetStore("store")
    df = store.read(Instrument("EURUSD", "forex", "yahoo", "1d"))

The command line entry point lives in :mod:`marketdata.cli`.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .instruments import (
    ASSET_CLASSES,
    DEFAULT_SOURCE,
    OHLCV,
    SOURCES,
    UNIVERSES,
    Instrument,
    resolve_instruments,
    to_source_symbol,
)
from .feeds import BinanceFeed, DataFeed, FeedError, YahooFeed, get_feed, normalise
from .store import ParquetStore, aligned_panel, gap_pct, log_returns, select, series_label
from .validate import Issue, SeriesReport, validate_frame, validate_selection
from .report import build_report
from .util import UserError, parse_date

__all__ = [
    "__version__",
    # instruments
    "Instrument", "resolve_instruments", "to_source_symbol",
    "ASSET_CLASSES", "SOURCES", "DEFAULT_SOURCE", "UNIVERSES", "OHLCV",
    # feeds
    "DataFeed", "YahooFeed", "BinanceFeed", "get_feed", "normalise", "FeedError",
    # store
    "ParquetStore", "select", "series_label", "aligned_panel", "gap_pct", "log_returns",
    # validation
    "validate_frame", "validate_selection", "Issue", "SeriesReport",
    # report
    "build_report",
    # util
    "parse_date", "UserError",
]
