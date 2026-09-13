"""Step 1a — record what a broker actually charges, once, in one place.

Every later step reads these numbers instead of carrying a guess in a script.
Forex needs three terms and the third is the one that decides a mean-reversion
trade: spread, commission, and swap charged every night a position is held.

    python costs.py add --broker demo --symbol USDZAR --spread-pips 25 \
        --swap-long -8.5 --swap-short 3.2 --swap-unit points-per-lot
    python costs.py add --broker ig --symbol USDZAR --spread-pips 25 \
        --swap-long -8.5 --swap-short 3.2 --from-broker-sheet
    python costs.py show --broker demo
    python costs.py show --broker demo -s USDNOK,USDZAR --holding-bars 7
    python costs.py remove --broker demo --symbol USDZAR

Exit codes: 0 success, 2 usage error, 1 runtime error.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import paths

paths.ensure_marketdata_importable()

from marketdata import Instrument, ParquetStore  # noqa: E402

DEFAULT_STORE = paths.STORE
DEFAULT_COSTS = paths.COSTS

#: Nights of financing charged on the weekly rollover day. Most brokers book
#: Saturday and Sunday on Wednesday, so a Wednesday hold costs three nights.
TRIPLE_SWAP_WEEKDAY = 2                      # Monday is 0


class UserError(Exception):
    """Bad input from the command line. Reported without a traceback."""


def pip_size(symbol: str) -> float:
    """Yen quotes go to two decimals, everything else to four."""
    return 0.01 if symbol.upper().endswith("JPY") or symbol.upper().startswith("JPY") else 0.0001


@dataclass
class SymbolCost:
    """What one leg costs, in the units the broker quotes them in."""

    symbol: str
    asset_class: str = "forex"
    spread_pips: float = 0.0
    commission_bps: float = 0.0              # per side, on notional
    swap_long: float = 0.0
    swap_short: float = 0.0
    swap_unit: str = "points-per-lot"        # or percent-per-annum, bps-per-night
    session_widening: float = 1.0            # multiple applied in thin hours
    rollover_widening: float = 1.0           # multiple applied around 17:00 New York
    price: float | None = None               # quote level used for the conversion
    estimated: bool = True
    updated: str = ""

    # -- conversions ------------------------------------------------------
    def spread_bps(self) -> float:
        """Half-turn spread cost in basis points of notional.

        Crossing the spread once costs half of it, because the quoted spread is
        the round trip between bid and ask. That halving applies to every asset
        class; only the conversion into basis points differs, since forex is
        quoted in pips and everything else is given in basis points already.
        """
        if self.asset_class != "forex":
            return self.spread_pips / 2.0
        if not self.price:
            raise UserError(f"{self.symbol}: no price level, cannot convert pips to bps")
        return self.spread_pips * pip_size(self.symbol) / self.price * 1e4 / 2.0

    def carry_bps(self, direction: str) -> float:
        """Financing for one night, in basis points, signed.

        Negative is a cost, positive is a credit. Brokers quote swap so that a
        negative number debits the account, and that sign is preserved here.
        """
        quoted = self.swap_long if direction == "long" else self.swap_short
        if self.swap_unit == "bps-per-night":
            return quoted
        if self.swap_unit == "percent-per-annum":
            return quoted * 1e4 / 100.0 / 365.0
        if self.swap_unit == "points-per-lot":
            if not self.price:
                raise UserError(f"{self.symbol}: no price level, cannot convert swap points")
            return quoted * pip_size(self.symbol) / self.price * 1e4
        raise UserError(f"{self.symbol}: unknown swap unit {self.swap_unit!r}")

    def entry_exit_bps(self) -> float:
        """One leg, in and out: two spread crossings and two commissions."""
        return 2 * self.spread_bps() + 2 * self.commission_bps


@dataclass
class LegPlan:
    """How one leg of the spread is traded, for costing purposes."""

    symbol: str
    direction: str                            # long or short


def load_profile(path: Path) -> dict[str, SymbolCost]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: SymbolCost(**v) for k, v in raw.get("symbols", {}).items()}


def save_profile(path: Path, symbols: dict[str, SymbolCost]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"broker": path.stem,
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "symbols": {k: asdict(v) for k, v in sorted(symbols.items())}}
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")


def price_level(symbol: str, asset_class: str, store: Path) -> float | None:
    """Latest stored close, used to turn pips and swap points into basis points."""
    try:
        frame = ParquetStore(store).read(Instrument(symbol, asset_class=asset_class))
        if frame is None or frame.empty:
            return None
        return float(frame["close"].iloc[-1])
    except Exception:                                             # noqa: BLE001
        return None


def round_trip(costs: dict[str, SymbolCost], legs: list[LegPlan],
               holding_bars: float, bars_per_night: float = 1.0) -> dict:
    """Total cost of opening and closing a spread held for `holding_bars` bars."""
    nights = holding_bars * bars_per_night
    transaction = 0.0
    carry = 0.0
    detail = []
    for leg in legs:
        cost = costs.get(leg.symbol)
        if cost is None:
            raise UserError(f"no cost profile for {leg.symbol}; add it first")
        entry_exit = cost.entry_exit_bps()
        per_night = cost.carry_bps(leg.direction)
        transaction += entry_exit
        carry += per_night * nights
        detail.append({"symbol": leg.symbol, "direction": leg.direction,
                       "entry_exit_bps": entry_exit, "carry_bps_per_night": per_night,
                       "carry_bps_total": per_night * nights,
                       "estimated": cost.estimated})
    # Carry is signed: a credit reduces the bill, a debit increases it. The
    # total is expressed as a cost, so a positive carry credit subtracts.
    total = transaction - carry
    return {"transaction_bps": transaction, "carry_bps": carry, "nights": nights,
            "total_bps": total, "legs": detail,
            "estimated": any(d["estimated"] for d in detail)}


# ---------------------------------------------------------------- cli
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="costs", description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--costs-dir", default=str(DEFAULT_COSTS), help="where profiles are kept")
    p.add_argument("--store", default=str(DEFAULT_STORE), help="store used for price levels")
    sub = p.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="record or replace one symbol's costs")
    add.add_argument("--broker", required=True)
    add.add_argument("--symbol", required=True)
    add.add_argument("-a", "--asset-class", default="forex")
    add.add_argument("--spread-pips", type=float, required=True,
                     help="quoted bid-ask spread in pips; bps for non-forex")
    add.add_argument("--commission-bps", type=float, default=0.0, help="per side")
    add.add_argument("--swap-long", type=float, default=0.0,
                     help="financing for a long position, negative is a debit")
    add.add_argument("--swap-short", type=float, default=0.0)
    add.add_argument("--swap-unit", default="points-per-lot",
                     choices=("points-per-lot", "percent-per-annum", "bps-per-night"))
    add.add_argument("--session-widening", type=float, default=1.0,
                     help="spread multiple in thin hours")
    add.add_argument("--rollover-widening", type=float, default=1.0,
                     help="spread multiple around 17:00 New York")
    add.add_argument("--price", type=float, default=None,
                     help="quote level for conversions; taken from the store if unset")
    add.add_argument("--from-broker-sheet", action="store_true",
                     help="these numbers were read off the broker's contract "
                          "specification; without this flag they are recorded as an "
                          "estimate and every report that uses them says so")

    show = sub.add_parser("show", help="print a profile and the round-trip cost")
    show.add_argument("--broker", required=True)
    show.add_argument("-s", "--symbols", default=None,
                      help="legs to cost, comma separated; all symbols if unset")
    show.add_argument("--directions", default="long,short",
                      help="direction per leg, in the same order as --symbols")
    show.add_argument("--holding-bars", type=float, default=1.0)
    show.add_argument("--bars-per-night", type=float, default=1.0,
                      help="1.0 for daily bars, 1/24 for hourly")
    show.add_argument("--json", action="store_true")

    rm = sub.add_parser("remove", help="delete one symbol from a profile")
    rm.add_argument("--broker", required=True)
    rm.add_argument("--symbol", required=True)

    sub.add_parser("list", help="list known broker profiles")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    costs_dir = Path(args.costs_dir)

    if args.command == "list":
        profiles = sorted(costs_dir.glob("*.json"))
        if not profiles:
            print(f"no profiles in {costs_dir}")
            return 0
        for path in profiles:
            symbols = load_profile(path)
            flag = " (estimated)" if any(c.estimated for c in symbols.values()) else ""
            print(f"{path.stem:12s} {len(symbols)} symbols{flag}")
        return 0

    path = costs_dir / f"{args.broker}.json"
    symbols = load_profile(path)

    if args.command == "add":
        price = args.price or price_level(args.symbol, args.asset_class, Path(args.store))
        entry = SymbolCost(
            symbol=args.symbol.upper(), asset_class=args.asset_class,
            spread_pips=args.spread_pips, commission_bps=args.commission_bps,
            swap_long=args.swap_long, swap_short=args.swap_short,
            swap_unit=args.swap_unit, session_widening=args.session_widening,
            rollover_widening=args.rollover_widening, price=price,
            estimated=not args.from_broker_sheet,
            updated=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        if price is None:
            raise UserError(f"no price level for {args.symbol}; pass --price")
        symbols[entry.symbol] = entry
        save_profile(path, symbols)
        print(f"{entry.symbol}: spread {entry.spread_bps():.2f} bps per crossing, "
              f"carry long {entry.carry_bps('long'):+.2f} / short "
              f"{entry.carry_bps('short'):+.2f} bps per night"
              + ("   ESTIMATED" if entry.estimated else ""))
        print(f"saved to {path}")
        return 0

    if args.command == "remove":
        if args.symbol.upper() not in symbols:
            raise UserError(f"{args.symbol} is not in {path}")
        del symbols[args.symbol.upper()]
        save_profile(path, symbols)
        print(f"removed {args.symbol.upper()} from {path}")
        return 0

    # show
    if not symbols:
        raise UserError(f"no profile at {path}; add symbols first")
    names = ([s.strip().upper() for s in args.symbols.split(",")] if args.symbols
             else sorted(symbols))
    directions = [d.strip().lower() for d in args.directions.split(",")]
    if len(directions) == 1:
        directions *= len(names)
    if len(directions) != len(names):
        raise UserError("--directions must give one value or one per symbol")

    print(f"broker {args.broker}   {len(symbols)} symbols on file")
    print(f"{'symbol':10s} {'spread':>9s} {'commission':>11s} {'carry long':>11s} "
          f"{'carry short':>12s}  source")
    for name in names:
        cost = symbols.get(name)
        if cost is None:
            raise UserError(f"no cost profile for {name}")
        print(f"{name:10s} {cost.spread_bps():8.2f}b {cost.commission_bps:10.2f}b "
              f"{cost.carry_bps('long'):+10.2f}b {cost.carry_bps('short'):+11.2f}b  "
              f"{'estimated' if cost.estimated else 'broker sheet'}")

    legs = [LegPlan(n, d) for n, d in zip(names, directions)]
    total = round_trip(symbols, legs, args.holding_bars, args.bars_per_night)
    if args.json:
        print(json.dumps(total, indent=2))
        return 0
    print(f"\nheld {args.holding_bars:g} bars = {total['nights']:.1f} nights, "
          f"{' and '.join(f'{leg.direction} {leg.symbol}' for leg in legs)}")
    print(f"  transaction   {total['transaction_bps']:8.2f} bps   both legs, in and out")
    print(f"  carry         {-total['carry_bps']:8.2f} bps   financing over the hold")
    print(f"  total         {total['total_bps']:8.2f} bps")
    if total["estimated"]:
        print("  NOTE: at least one leg is an estimate, not a broker sheet")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:                                       # noqa: BLE001
        if "-v" in sys.argv or "--verbose" in sys.argv:
            raise
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
