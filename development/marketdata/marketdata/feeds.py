"""Market data sources. Every feed returns the same normalised OHLCV frame."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

import pandas as pd
import requests

from .instruments import OHLCV, Instrument, to_source_symbol
from .util import LOG, UserError


class FeedError(RuntimeError):
    """A source failed in a way retrying will not fix."""


def empty_ohlcv() -> pd.DataFrame:
    index = pd.DatetimeIndex([], tz="UTC", name="timestamp")
    return pd.DataFrame(columns=OHLCV, index=index, dtype=float)


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    """One schema everywhere: UTC index named 'timestamp', sorted, de-duplicated, float."""
    if df.empty:
        return empty_ohlcv()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "timestamp"
    return df[OHLCV].astype(float)


def with_retries(func, *, retries: int = 3, delay: float = 1.0, label: str = ""):
    """Call `func`, retrying transient failures with exponential backoff."""
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return func()
        except (requests.RequestException, TimeoutError, ConnectionError) as exc:
            last = exc
            if attempt == retries:
                break
            wait = delay * (2 ** (attempt - 1))
            LOG.warning("%s failed (%s), retry %d/%d in %.1fs",
                        label or "request", type(exc).__name__, attempt, retries, wait)
            time.sleep(wait)
    raise FeedError(f"{label or 'request'} failed after {retries} attempts: {last}") from last


class DataFeed(ABC):
    """Common interface for every source."""

    name: str = "base"

    @abstractmethod
    def history(self, inst: Instrument, start: pd.Timestamp, end: pd.Timestamp,
                retries: int = 3) -> pd.DataFrame:
        """Return OHLCV history for `inst` between `start` and `end`, both UTC."""


class YahooFeed(DataFeed):
    """Yahoo Finance. Forex, crypto and equities."""

    name = "yahoo"

    # timeframes Yahoo has no native bar for -> (fetch at, resample to)
    _RESAMPLE_FALLBACK = {"4h": ("1h", "4h"), "3d": ("1d", "3D"), "1w": ("1d", "1W")}
    # how far back each interval is available, in days
    _MAX_LOOKBACK_DAYS = {"1m": 7, "2m": 60, "5m": 60, "15m": 60, "30m": 60, "90m": 60, "1h": 730}

    def history(self, inst: Instrument, start: pd.Timestamp, end: pd.Timestamp,
                retries: int = 3) -> pd.DataFrame:
        import yfinance as yf                     # imported lazily; slow to load

        fetch_tf, resample_rule = self._RESAMPLE_FALLBACK.get(
            inst.timeframe, (inst.timeframe, None)
        )
        self._warn_if_beyond_lookback(inst, fetch_tf, start)
        ticker = to_source_symbol(inst)

        raw = with_retries(
            lambda: yf.Ticker(ticker).history(
                start=start, end=end, interval=fetch_tf, auto_adjust=False
            ),
            retries=retries, label=f"yahoo {ticker}",
        )
        if raw is None or raw.empty:
            return empty_ohlcv()

        missing = [c for c in OHLCV if c not in raw.rename(columns=str.lower).columns]
        if missing:
            raise FeedError(f"yahoo {ticker}: response is missing columns {missing}")

        df = raw.rename(columns=str.lower)[OHLCV].astype(float)
        df.index = pd.to_datetime(df.index, utc=True)

        if resample_rule:
            df = df.resample(resample_rule).agg(
                {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
            ).dropna(how="all")

        return normalise(df)

    def _warn_if_beyond_lookback(self, inst: Instrument, interval: str,
                                 start: pd.Timestamp) -> None:
        cap = self._MAX_LOOKBACK_DAYS.get(interval)
        if cap is None:
            return
        requested = (pd.Timestamp.now(tz="UTC") - start).days
        if requested > cap:
            LOG.warning(
                "%s: Yahoo serves at most %dd of %s bars, asked for %dd — expect truncation",
                inst.symbol, cap, interval, requested,
            )


class BinanceFeed(DataFeed):
    """Binance spot klines. Crypto only. Pages through the 1000-bar REST limit."""

    name = "binance"

    _REST = "https://api.binance.com/api/v3/klines"
    _COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
             "quote_volume", "trades", "taker_base_vol", "taker_quote_vol", "ignore"]
    _PAGE_LIMIT = 1000
    _PAGE_PAUSE = 0.25                            # stay inside the request weight budget

    def history(self, inst: Instrument, start: pd.Timestamp, end: pd.Timestamp,
                retries: int = 3) -> pd.DataFrame:
        symbol = to_source_symbol(inst)
        start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
        frames: list[pd.DataFrame] = []

        while start_ms < end_ms:
            params = {
                "symbol": symbol, "interval": inst.timeframe,
                "startTime": start_ms, "endTime": end_ms, "limit": self._PAGE_LIMIT,
            }
            response = with_retries(
                lambda p=params: requests.get(self._REST, params=p, timeout=30),
                retries=retries, label=f"binance {symbol}",
            )
            if response.status_code == 400:
                raise FeedError(f"binance rejected {symbol} {inst.timeframe}: {response.text[:160]}")
            response.raise_for_status()

            batch = response.json()
            if not batch:
                break
            frames.append(pd.DataFrame(batch, columns=self._COLS))
            start_ms = batch[-1][6] + 1            # resume after the last close_time
            if len(batch) < self._PAGE_LIMIT:
                break
            time.sleep(self._PAGE_PAUSE)

        if not frames:
            return empty_ohlcv()

        df = pd.concat(frames, ignore_index=True)
        df.index = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        return normalise(df[OHLCV].astype(float))


_FEEDS: dict[str, DataFeed] = {"yahoo": YahooFeed(), "binance": BinanceFeed()}


def get_feed(name: str) -> DataFeed:
    try:
        return _FEEDS[name]
    except KeyError:
        raise UserError(
            f"unknown source {name!r}; expected one of {', '.join(sorted(_FEEDS))}"
        ) from None
