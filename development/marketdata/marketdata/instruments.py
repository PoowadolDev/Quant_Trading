"""Instrument identity, symbol translation, and the named universes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .util import UserError

ASSET_CLASSES = ("forex", "crypto")
SOURCES = ("yahoo", "binance")

#: Which feed to use when the caller does not name one.
DEFAULT_SOURCE = {"forex": "yahoo", "crypto": "binance"}

OHLCV = ["open", "high", "low", "close", "volume"]


@dataclass(frozen=True)
class Instrument:
    """One series to fetch and store.

    `symbol` is canonical and source-agnostic: "EURUSD" for forex, "BTC-USDT" for crypto.
    `timeframe` uses Binance-style tokens (1m, 5m, 15m, 1h, 4h, 1d, 1w).
    """

    symbol: str
    asset_class: str
    source: str = "yahoo"
    timeframe: str = "1d"

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        object.__setattr__(self, "asset_class", self.asset_class.strip().lower())
        object.__setattr__(self, "source", self.source.strip().lower())
        object.__setattr__(self, "timeframe", self.timeframe.strip().lower())

        if not self.symbol:
            raise UserError("instrument symbol cannot be empty")
        if self.asset_class not in ASSET_CLASSES:
            raise UserError(
                f"unknown asset class {self.asset_class!r}; expected one of {', '.join(ASSET_CLASSES)}"
            )
        if self.source not in SOURCES:
            raise UserError(
                f"unknown source {self.source!r}; expected one of {', '.join(SOURCES)}"
            )

    def __str__(self) -> str:
        return f"{self.symbol}@{self.source}:{self.timeframe}"

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.asset_class, self.symbol, self.timeframe, self.source)


def to_source_symbol(inst: Instrument) -> str:
    """Translate a canonical symbol into what the source expects."""
    if inst.source == "yahoo":
        if inst.asset_class == "forex":
            return f"{inst.symbol}=X"            # EURUSD -> EURUSD=X
        return inst.symbol                        # BTC-USD stays as-is
    if inst.source == "binance":
        if inst.asset_class != "crypto":
            raise UserError(
                f"Binance serves crypto only; {inst.symbol} is {inst.asset_class}. "
                "Use --source yahoo for forex."
            )
        return inst.symbol.replace("-", "")        # BTC-USDT -> BTCUSDT
    raise UserError(f"unknown source {inst.source!r}")


FX_MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"]
FX_CROSSES = ["EURGBP", "EURJPY", "AUDNZD", "GBPJPY", "EURCHF"]
FX_COMMODITY = ["AUDUSD", "USDCAD", "NZDUSD", "AUDNZD"]
CRYPTO_MAJORS = ["BTC-USDT", "ETH-USDT"]

#: Named symbol sets, so a routine download does not need a hand-typed list.
UNIVERSES: dict[str, dict] = {
    "fx-majors": {
        "symbols": FX_MAJORS,
        "asset_class": "forex",
        "description": "Seven USD majors",
    },
    "fx-crosses": {
        "symbols": FX_CROSSES,
        "asset_class": "forex",
        "description": "Common non-USD crosses",
    },
    "fx-all": {
        "symbols": FX_MAJORS + FX_CROSSES,
        "asset_class": "forex",
        "description": "Majors plus crosses — the currency-factor study universe",
    },
    "fx-commodity": {
        "symbols": FX_COMMODITY,
        "asset_class": "forex",
        "description": "Commodity currencies, the usual cointegration candidates",
    },
    "crypto-majors": {
        "symbols": CRYPTO_MAJORS,
        "asset_class": "crypto",
        "description": "BTC and ETH against USDT",
    },
}


def resolve_instruments(
    symbols: Iterable[str] | None = None,
    universe: str | None = None,
    asset_class: str | None = None,
    source: str | None = None,
    timeframe: str = "1d",
) -> list[Instrument]:
    """Build the instrument list from CLI selection arguments.

    Exactly one of `symbols` or `universe` supplies the names. `asset_class` is required
    with explicit symbols (a universe carries its own), and `source` defaults per class.
    """
    symbols = list(symbols or [])
    if universe:
        if universe not in UNIVERSES:
            raise UserError(
                f"unknown universe {universe!r}. Available: {', '.join(sorted(UNIVERSES))}"
            )
        spec = UNIVERSES[universe]
        symbols = list(spec["symbols"]) + symbols
        asset_class = asset_class or spec["asset_class"]

    if not symbols:
        raise UserError("no symbols selected — pass --symbols or --universe")
    if not asset_class:
        raise UserError("--asset-class is required when symbols are given explicitly")

    chosen_source = source or DEFAULT_SOURCE[asset_class]

    seen: dict[tuple, Instrument] = {}
    for symbol in symbols:
        inst = Instrument(symbol, asset_class, chosen_source, timeframe)
        seen.setdefault(inst.key, inst)          # de-duplicate, keep input order
    return list(seen.values())
