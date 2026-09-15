"""Instrument identity, symbol translation, and the named universes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .util import UserError

ASSET_CLASSES = ("forex", "crypto", "commodity", "index", "equity")
SOURCES = ("yahoo", "binance", "dukascopy")

#: Which feed to use when the caller does not name one.
DEFAULT_SOURCE = {"forex": "yahoo", "crypto": "binance", "commodity": "yahoo",
                  "index": "yahoo", "equity": "yahoo"}

#: Liquid US listings grouped by what they do. Two firms in the same business
#: face the same demand, the same input costs and the same regulation, which is
#: the reason their prices might share a long-run level. Searching across
#: sectors instead would multiply the number of tests without adding any such
#: reason, and the extra tests are all chances to be fooled.
#: Names removed after `marketdata download` returned nothing for them: ANSS,
#: HES, K, MRO, SKX and X were all taken over between 2024 and 2025, so the feed
#: serves no history and any pair holding one would be silently truncated to the
#: shorter leg. A universe is a list of things that can be traded now.
EQUITY_SECTORS = {
    "staples": ["KO", "PEP", "PG", "CL", "KMB", "GIS", "MDLZ", "MO", "PM",
                "HSY", "CAG", "SJM", "CPB", "HRL", "MKC", "CHD", "CLX"],
    "energy": ["XOM", "CVX", "COP", "SLB", "EOG", "PSX", "VLO", "MPC",
               "HAL", "BKR", "OXY", "DVN", "FANG", "APA"],
    "banks": ["JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC",
              "TFC", "FITB", "KEY", "RF", "CFG", "HBAN", "MTB", "ZION"],
    "semis": ["NVDA", "AMD", "INTC", "TXN", "QCOM", "AVGO", "MU", "ADI",
              "LRCX", "AMAT", "KLAC", "NXPI", "MCHP", "ON", "SWKS", "TER"],
    "software": ["MSFT", "ORCL", "CRM", "ADBE", "IBM", "NOW",
                 "INTU", "ADSK", "CDNS", "SNPS", "PTC"],
    "pharma": ["JNJ", "PFE", "MRK", "ABBV", "LLY", "BMY", "AMGN", "GILD",
               "VRTX", "REGN", "BIIB", "ZTS", "VTRS"],
    "payments": ["V", "MA", "AXP", "PYPL", "FIS", "FISV", "GPN"],
    "retail": ["WMT", "TGT", "COST", "HD", "LOW", "DG", "DLTR", "BBY", "KR"],
    "telecom": ["T", "VZ", "TMUS", "LUMN"],
    "autos": ["GM", "F", "APTV", "BWA", "LEA"],
    "airlines": ["DAL", "UAL", "AAL", "LUV", "ALK", "JBLU"],
    "rails": ["UNP", "CSX", "NSC"],
    "truckers": ["ODFL", "JBHT", "CHRW", "XPO", "SAIA"],
    "insurers": ["MET", "PRU", "AFL", "ALL", "TRV", "CB", "HIG", "PGR",
                 "LNC", "GL", "CINF", "WRB"],
    "utilities": ["NEE", "DUK", "SO", "D", "AEP", "EXC", "XEL", "ED",
                  "WEC", "ES", "DTE", "PPL", "CMS", "AEE"],
    "reits": ["SPG", "O", "PLD", "AMT", "CCI", "EQR", "AVB", "PSA",
              "VTR", "WELL", "BXP", "KIM"],
    "homebuilders": ["DHI", "LEN", "PHM", "NVR", "TOL", "KBH", "MTH"],
    "miners": ["NEM", "FCX", "AA", "NUE", "STLD", "CLF", "RS"],
    "chemicals": ["DOW", "LYB", "DD", "PPG", "SHW", "ECL", "ALB", "EMN", "CE"],
    "defense": ["LMT", "NOC", "GD", "RTX", "LHX", "HII", "TXT"],
    "machinery": ["CAT", "DE", "CMI", "PCAR", "ITW", "EMR", "ETN", "PH", "DOV"],
    "media": ["DIS", "CMCSA", "WBD", "PARA", "FOX", "NFLX"],
    "hotels_travel": ["MAR", "HLT", "H", "WH", "CCL", "RCL", "NCLH", "EXPE"],
    "restaurants": ["MCD", "SBUX", "YUM", "CMG", "DRI", "DPZ", "QSR"],
    "apparel": ["NKE", "LULU", "VFC", "RL", "PVH", "TPR"],
    "exchanges": ["CME", "ICE", "NDAQ", "CBOE", "MKTX", "SPGI", "MCO"],
    "asset_managers": ["BLK", "BEN", "TROW", "IVZ", "AMG", "SEIC"],
    "health_providers": ["UNH", "ELV", "CI", "HUM", "CNC", "MOH"],
    "waste": ["WM", "RSG", "WCN"],
}

#: Which sector each symbol belongs to, so a screen can restrict itself.
#:
#: A symbol must appear in exactly one sector. It used to be possible for one to
#: sit in two — `MSFT` was in both `software` and a `majors_tech` grouping — and
#: this dictionary then silently kept whichever came last, so the sector a symbol
#: belonged to depended on the order the sectors happened to be written in. That
#: grouping is gone for a second reason as well: "large technology company" is a
#: size, not a shared driver. `AAPL` and `AMZN` have no common input, customer or
#: regulator, which is precisely the kind of pairing that produced this project's
#: two false candidates.
def _sector_of() -> dict:
    seen: dict = {}
    for sector, symbols in EQUITY_SECTORS.items():
        for symbol in symbols:
            if symbol in seen:
                raise UserError(
                    f"{symbol} is listed in both {seen[symbol]!r} and {sector!r}. "
                    "A symbol belongs to one sector, or the mapping depends on "
                    "the order the sectors are written in."
                )
            seen[symbol] = sector
    return seen


EQUITY_SECTOR_OF = _sector_of()


#: What an index fund is a claim on. Sector funds carry their sector; broad funds
#: carry the market they track.
#:
#: This exists so a screen can refuse to pair two instruments that share no
#: driver. `XLP~XLB` — consumer staples against materials — was this project's
#: best result for a day, and the two have no common cash flow, input, customer
#: or regulator. Nothing in the pipeline could say so, because nothing recorded
#: what an instrument is a claim on.
INDEX_DRIVERS = {
    "SPY": ("us-broad",), "IVV": ("us-broad",), "VOO": ("us-broad",),
    "DIA": ("us-broad",), "QQQ": ("us-broad", "semis", "software"),
    "IWM": ("us-small",), "MDY": ("us-small",),
    "XLP": ("staples",), "XLE": ("energy",), "XLF": ("banks", "insurers"),
    "XLV": ("pharma", "health_providers"), "XLK": ("software", "semis"),
    "XLI": ("machinery", "defense", "rails"), "XLB": ("chemicals", "miners"),
    "XLU": ("utilities",), "XLY": ("retail", "restaurants", "autos"),
    "XLC": ("media", "telecom"), "XLRE": ("reits",),
    "SMH": ("semis",), "SOXX": ("semis",), "KRE": ("banks",),
    "XOP": ("energy",), "OIH": ("energy",), "GDX": ("miners",),
    "XHB": ("homebuilders",), "ITB": ("homebuilders",), "IYT": ("rails", "truckers"),
}

#: Commodities grouped by what moves them.
COMMODITY_DRIVERS = {
    "BRENT": ("oil",), "WTI": ("oil",), "NATGAS": ("gas",),
    "GOLD": ("precious",), "SILVER": ("precious",), "PLATINUM": ("precious",),
    "COPPER": ("industrial-metal",),
    "CORN": ("grain",), "WHEAT": ("grain",), "SOYBEAN": ("grain",),
}


def driver_groups(symbol: str, asset_class: str) -> frozenset:
    """What this instrument is exposed to, as a set of named drivers.

    Two instruments are worth pairing when these overlap. An empty set means
    nothing is known about the instrument, which is treated as "no link" rather
    than "links to everything" — silence is not evidence of a relationship.
    """
    symbol = symbol.upper()
    if asset_class == "equity":
        sector = EQUITY_SECTOR_OF.get(symbol)
        return frozenset((sector,)) if sector else frozenset()
    if asset_class == "index":
        return frozenset(INDEX_DRIVERS.get(symbol, ()))
    if asset_class == "commodity":
        return frozenset(COMMODITY_DRIVERS.get(symbol, ()))
    if asset_class == "forex":
        # A currency pair is exposed to both of its legs. Two pairs sharing a
        # leg move together by construction, which is a real mechanism and the
        # reason twelve pairs resolve to eight independent directions.
        if len(symbol) == 6:
            return frozenset((symbol[:3], symbol[3:]))
        return frozenset()
    if asset_class == "crypto":
        # Everything in this market moves with bitcoin. That is one driver, not
        # a per-coin story, and pretending otherwise is how a screen finds
        # dozens of "relationships" in a single beta.
        return frozenset(("crypto-beta",))
    return frozenset()


def shared_drivers(a: str, b: str, asset_class_a: str,
                   asset_class_b: str | None = None) -> frozenset:
    """Drivers two instruments have in common. Empty means do not pair them."""
    return (driver_groups(a, asset_class_a)
            & driver_groups(b, asset_class_b or asset_class_a))

#: Equity index levels and the funds that track them. The names without a
#: tracking fund are **cash indices and cannot be traded directly** — a real
#: position needs a future, a fund or a contract for difference, each with its
#: own cost and financing. They are here because a relationship is worth
#: measuring on the index itself before deciding what instrument to hold.
INDEX_SYMBOLS = {
    # cash indices, research only
    "SPX": "^GSPC",        # S&P 500
    "NDX": "^NDX",         # Nasdaq 100
    "DJI": "^DJI",         # Dow Jones Industrial Average
    "RUT": "^RUT",         # Russell 2000
    "FTSE": "^FTSE",       # FTSE 100
    "DAX": "^GDAXI",       # DAX 40
    "NIKKEI": "^N225",     # Nikkei 225
    "VIX": "^VIX",         # volatility index, not a price series
    # tracking funds, actually tradable
    "SPY": "SPY", "QQQ": "QQQ", "IWM": "IWM", "DIA": "DIA",
    "EFA": "EFA", "EEM": "EEM",
    # sector funds: different baskets of the same market, which is where pairs
    # trading has historically worked
    "XLF": "XLF", "XLE": "XLE", "XLK": "XLK", "XLV": "XLV", "XLI": "XLI",
    "XLP": "XLP", "XLY": "XLY", "XLU": "XLU", "XLB": "XLB", "XLRE": "XLRE",
    "XLC": "XLC", "GDX": "GDX", "XOP": "XOP", "KRE": "KRE", "SMH": "SMH",
}

#: Which of the above can actually be held.
TRADABLE_INDEX = {"SPY", "QQQ", "IWM", "DIA", "EFA", "EEM",
                  "XLF", "XLE", "XLK", "XLV", "XLI", "XLP", "XLY", "XLU",
                  "XLB", "XLRE", "XLC", "GDX", "XOP", "KRE", "SMH"}

#: Commodities have no natural ticker convention, so the canonical name is a plain
#: word and the map holds the vendor symbol. Every entry is the front-month
#: continuous futures contract, which rolls; see the note in to_source_symbol.
COMMODITY_SYMBOLS = {
    "GOLD": "GC=F",        # COMEX gold, USD per troy ounce
    "SILVER": "SI=F",      # COMEX silver, USD per troy ounce
    "COPPER": "HG=F",      # COMEX copper, USD per pound
    "WTI": "CL=F",         # NYMEX light sweet crude, USD per barrel
    "BRENT": "BZ=F",       # ICE Brent crude, USD per barrel
    "NATGAS": "NG=F",      # NYMEX Henry Hub, USD per MMBtu
}

OHLCV = ["open", "high", "low", "close", "volume"]


@dataclass(frozen=True)
class Instrument:
    """One series to fetch and store.

    `symbol` is canonical and source-agnostic: "EURUSD" for forex, "BTC-USDT" for
    crypto, "GOLD" or "WTI" for commodities.
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
    if inst.source == "dukascopy":
        if inst.asset_class != "forex":
            raise UserError(
                f"dukascopy is wired for forex only here, not {inst.asset_class!r}. "
                "It carries CFDs too, but each needs its own instrument code and "
                "an unverified code silently downloads a different market."
            )
        return inst.symbol                  # EURUSD is already what the feed wants
    if inst.source == "yahoo":
        if inst.asset_class == "forex":
            return f"{inst.symbol}=X"            # EURUSD -> EURUSD=X
        if inst.asset_class == "equity":
            return inst.symbol              # the ticker is already canonical
        if inst.asset_class == "index":
            try:
                return INDEX_SYMBOLS[inst.symbol]
            except KeyError:
                raise UserError(
                    f"unknown index {inst.symbol!r}; known: "
                    f"{', '.join(sorted(INDEX_SYMBOLS))}"
                ) from None
        if inst.asset_class == "commodity":
            # Yahoo has no spot commodity feed, so these are front-month futures.
            # The series is continuous but not roll-adjusted: at each roll the
            # level steps by the spread between contracts. Fine for a study of
            # daily closes, wrong for anything that accumulates the jump.
            try:
                return COMMODITY_SYMBOLS[inst.symbol]
            except KeyError:
                raise UserError(
                    f"unknown commodity {inst.symbol!r}; known: "
                    f"{', '.join(sorted(COMMODITY_SYMBOLS))}"
                ) from None
        return inst.symbol                        # BTC-USD stays as-is
    if inst.source == "binance":
        if inst.asset_class != "crypto":
            raise UserError(
                f"Binance serves crypto only; {inst.symbol} is {inst.asset_class}. "
                "Use --source yahoo for forex and commodities."
            )
        return inst.symbol.replace("-", "")        # BTC-USDT -> BTCUSDT
    raise UserError(f"unknown source {inst.source!r}")


FX_MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"]
FX_CROSSES = ["EURGBP", "EURJPY", "AUDNZD", "GBPJPY", "EURCHF"]
FX_COMMODITY = ["AUDUSD", "USDCAD", "NZDUSD", "AUDNZD"]
CRYPTO_MAJORS = ["BTC-USDT", "ETH-USDT"]
METALS = ["GOLD", "SILVER", "COPPER"]
ENERGY = ["WTI", "BRENT"]
US_INDICES = ["SPX", "NDX", "DJI", "RUT"]
GLOBAL_INDICES = ["FTSE", "DAX", "NIKKEI"]
INDEX_ETFS = ["SPY", "QQQ", "IWM", "DIA"]
SECTOR_ETFS = ["XLF", "XLE", "XLK", "XLV", "XLI", "XLP", "XLY", "XLU",
               "XLB", "XLRE", "XLC", "GDX", "XOP", "KRE", "SMH"]

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
    "metals": {
        "symbols": METALS,
        "asset_class": "commodity",
        "description": "Gold, silver and copper front-month futures",
    },
    "energy": {
        "symbols": ENERGY,
        "asset_class": "commodity",
        "description": "WTI and Brent crude front-month futures",
    },
    "commodities": {
        "symbols": METALS + ENERGY,
        "asset_class": "commodity",
        "description": "Metals and energy — the external anchors for FX pair studies",
    },
    "us-indices": {
        "symbols": US_INDICES,
        "asset_class": "index",
        "description": "S&P 500, Nasdaq 100, Dow and Russell — cash levels, not tradable",
    },
    "global-indices": {
        "symbols": GLOBAL_INDICES,
        "asset_class": "index",
        "description": "FTSE, DAX and Nikkei — cash levels in their own currencies",
    },
    "equities": {
        "symbols": sorted({s for syms in EQUITY_SECTORS.values() for s in syms}),
        "asset_class": "equity",
        "description": "Liquid US listings grouped by sector — the classic pairs universe",
    },
    "eq-staples": {
        "symbols": EQUITY_SECTORS["staples"],
        "asset_class": "equity",
        "description": "Staples sector listings",
    },
    "eq-energy": {
        "symbols": EQUITY_SECTORS["energy"],
        "asset_class": "equity",
        "description": "Energy sector listings",
    },
    "eq-banks": {
        "symbols": EQUITY_SECTORS["banks"],
        "asset_class": "equity",
        "description": "Banks sector listings",
    },
    "eq-semis": {
        "symbols": EQUITY_SECTORS["semis"],
        "asset_class": "equity",
        "description": "Semis sector listings",
    },
    "eq-pharma": {
        "symbols": EQUITY_SECTORS["pharma"],
        "asset_class": "equity",
        "description": "Pharma sector listings",
    },
    "sector-etfs": {
        "symbols": SECTOR_ETFS,
        "asset_class": "index",
        "description": "Sector and industry funds — different baskets, all tradable",
    },
    "index-etfs": {
        "symbols": INDEX_ETFS,
        "asset_class": "index",
        "description": "Funds tracking the US indices — these can actually be held",
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
