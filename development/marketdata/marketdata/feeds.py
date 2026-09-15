"""Market data sources. Every feed returns the same normalised OHLCV frame."""

from __future__ import annotations

import lzma
import struct
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor

import numpy as np
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
        start = self._clamp_to_lookback(inst, fetch_tf, start)
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
                {"open": "first", "high": "max", "low": "min", "close": "last",
                 "volume": "sum"}
            )
            # Summing volume over an empty period yields 0 rather than NaN, so a
            # row for a period the market never traded is not all-NaN and
            # survives dropna(how="all"). Resampling an index session into 4h
            # slots that way fabricated a bar for every night and weekend: 73% of
            # the output was placeholders. The close is the honest test of
            # whether anything happened.
            df = df[df["close"].notna()]

        return normalise(df)

    def _clamp_to_lookback(self, inst: Instrument, interval: str,
                           start: pd.Timestamp) -> pd.Timestamp:
        """Pull the start forward to what the source will actually serve.

        Asking beyond the limit does not return a short frame: it returns an
        empty one, and the caller sees a successful download of zero rows. The
        start is therefore moved inside the window, a day clear of the boundary,
        and the truncation is logged rather than discovered later.
        """
        cap = self._MAX_LOOKBACK_DAYS.get(interval)
        if cap is None:
            return start
        now = pd.Timestamp.now(tz="UTC")
        requested = (now - start).days
        if requested <= cap - 1:
            return start
        clamped = now - pd.Timedelta(days=cap - 1)
        LOG.warning(
            "%s: Yahoo serves at most %dd of %s bars, asked for %dd — starting from %s",
            inst.symbol, cap, interval, requested, clamped.date(),
        )
        return clamped


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


#: pandas offset aliases for every timeframe the project uses.
_RESAMPLE_RULE = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
                  "1h": "1h", "4h": "4h", "1d": "1D", "1w": "1W"}


class DukascopyFeed(DataFeed):
    """Dukascopy tick history, aggregated into bars. Forex and CFDs.

    Why this exists: Yahoo serves seven days of one-minute forex bars and no
    volume at all, because there is no central FX exchange for it to report. A
    week is not enough to test anything — the one pair that has ever reached the
    replay in this project did so on 2,817 bars of a single week, which is a
    finding about the mechanism and not about the pair.

    Dukascopy publishes its own broker feed as one LZMA-compressed file per
    instrument per hour, going back to 2003 for the majors. Each record is
    twenty bytes: milliseconds into the hour, ask and bid in points, and ask and
    bid volume in millions.

        >IIIff  ->  (ms_offset, ask_points, bid_points, ask_volume, bid_volume)

    Bars are built from the **mid** price, so the OHLC is a real traded range
    rather than one side of the book, and the spread is available separately
    rather than baked into every bar. Volume is the tick count, which is a
    genuine measure of activity — unlike the zeros Yahoo returns.

    This is one broker's book, not a consolidated tape. Two brokers disagree on
    forex prices at the tick level, so never splice a Dukascopy series into a
    Yahoo one; the store keeps them in separate files for exactly that reason.
    """

    name = "dukascopy"

    _BASE = "https://datafeed.dukascopy.com/datafeed"
    _RECORD = struct.Struct(">IIIff")
    # The host rate-limits hard: eight concurrent workers earn 503s and dropped
    # connections within a minute. Two with a pause between them is slower per
    # file and far faster overall, because nothing has to be retried.
    _WORKERS = 2
    _PAUSE = 0.15
    _SESSION_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                        "Accept": "*/*",
                        "Referer": "https://www.dukascopy.com/"}
    _RETRY_STATUS = (429, 500, 502, 503, 504)

    #: Quotes arrive as integers in points. Yen crosses and metals carry three
    #: decimals, everything else five. A wrong exponent here does not fail, it
    #: silently produces prices off by a factor of a hundred.
    _THREE_DECIMAL = ("JPY", "XAU", "XAG")

    def _point(self, symbol: str) -> float:
        return 1e-3 if any(t in symbol.upper() for t in self._THREE_DECIMAL) else 1e-5

    def _hour_url(self, symbol: str, hour: pd.Timestamp) -> str:
        # Months are zero-indexed in the path: 00 is January.
        return (f"{self._BASE}/{symbol}/{hour.year:04d}/{hour.month - 1:02d}/"
                f"{hour.day:02d}/{hour.hour:02d}h_ticks.bi5")

    def _fetch_hour(self, session: requests.Session, symbol: str,
                    hour: pd.Timestamp, retries: int) -> np.ndarray | None:
        """Ticks for one hour as an (n, 3) array of (epoch_ms, ask, bid), or None.

        A missing file is the normal case, not an error: the market is closed at
        weekends and on holidays, and Dukascopy returns 404 or an empty body for
        those hours.
        """
        url = self._hour_url(symbol, hour)

        def fetch():
            time.sleep(self._PAUSE)
            r = session.get(url, timeout=60)
            # A busy server answers 503 rather than dropping the connection, and
            # `raise_for_status` outside the retried call would turn a transient
            # refusal into a failed download. Raise inside, so it is retried.
            if r.status_code in self._RETRY_STATUS:
                raise requests.HTTPError(f"{r.status_code} from dukascopy", response=r)
            return r

        response = with_retries(
            fetch, retries=max(retries, 5), delay=2.0,
            label=f"dukascopy {symbol} {hour:%Y-%m-%d %H}h")
        if response.status_code == 404 or not response.content:
            return None
        response.raise_for_status()
        try:
            raw = lzma.LZMADecompressor().decompress(response.content)
        except lzma.LZMAError as exc:
            raise FeedError(f"dukascopy {symbol} {hour:%Y-%m-%d %H}h is not "
                            f"readable: {exc}") from exc
        if not raw:
            return None
        n = len(raw) // self._RECORD.size
        out = np.empty((n, 3), dtype=float)
        base_ms = hour.value // 1_000_000
        for i in range(n):
            ms, ask, bid, _, _ = self._RECORD.unpack_from(raw, i * self._RECORD.size)
            out[i] = (base_ms + ms, ask, bid)
        return out

    def history(self, inst: Instrument, start: pd.Timestamp, end: pd.Timestamp,
                retries: int = 3) -> pd.DataFrame:
        symbol = to_source_symbol(inst)
        hours = pd.date_range(start.floor("h"), end.ceil("h"), freq="h", tz="UTC")
        if not len(hours):
            return empty_ohlcv()

        LOG.info("dukascopy %s: %d hour file(s) at roughly %.1fs each, about "
                 "%.0f minute(s)", symbol, len(hours), 2.6,
                 len(hours) * 2.6 / 60 / self._WORKERS)

        # One session, kept open. Without connection reuse this host drops about
        # a third of requests on connect; with it, almost none.
        session = requests.Session()
        session.headers.update(self._SESSION_HEADERS)
        adapter = requests.adapters.HTTPAdapter(pool_connections=self._WORKERS,
                                                pool_maxsize=self._WORKERS)
        session.mount("https://", adapter)
        try:
            with ThreadPoolExecutor(max_workers=self._WORKERS) as pool:
                chunks = list(pool.map(
                    lambda h: self._fetch_hour(session, symbol, h, retries), hours))
        finally:
            session.close()

        ticks = [c for c in chunks if c is not None and len(c)]
        if not ticks:
            return empty_ohlcv()
        arr = np.vstack(ticks)

        point = self._point(symbol)
        mid = (arr[:, 1] + arr[:, 2]) / 2.0 * point
        index = pd.to_datetime(arr[:, 0], unit="ms", utc=True)
        series = pd.Series(mid, index=index).sort_index()

        rule = _RESAMPLE_RULE.get(inst.timeframe)
        if rule is None:
            raise UserError(f"dukascopy cannot build {inst.timeframe!r} bars; "
                            f"known: {', '.join(sorted(_RESAMPLE_RULE))}")
        bars = series.resample(rule, label="left", closed="left").ohlc()
        # Tick count is the honest volume for a decentralised market: it counts
        # quote updates, which is activity. Traded size is not published.
        bars["volume"] = series.resample(rule, label="left",
                                         closed="left").count().astype(float)
        bars = bars[bars["close"].notna()]
        return normalise(bars)


_FEEDS: dict[str, DataFeed] = {"yahoo": YahooFeed(), "binance": BinanceFeed(),
                               "dukascopy": DukascopyFeed()}


def get_feed(name: str) -> DataFeed:
    try:
        return _FEEDS[name]
    except KeyError:
        raise UserError(
            f"unknown source {name!r}; expected one of {', '.join(sorted(_FEEDS))}"
        ) from None
