"""Step 3.3 — how many bets a book really contains, and when to stop.

Two spreads that share a leg are not two bets. Forex made this concrete earlier
in the project: twelve currency pairs resolve to eight independent directions,
so a book holding `EURUSD~GBPUSD` beside `AUDUSD~NZDUSD` is more concentrated
than its position count suggests, and a screen that counts them as independent
tests overstates its own significance. Nothing in the pipeline measured this.

Three things are checked here, cheapest first, because the cheap one catches
most of it:

    shared legs        two relationships naming the same instrument. No
                       statistics needed and no sample size required.

    effective bets     the participation ratio of the spread correlation
                       matrix, which answers "this book holds N positions; how
                       many independent things is it betting on?" A book of
                       five spreads that turns out to hold two bets is sized as
                       though it holds five, which is the usual way a
                       diversified-looking book takes a concentrated loss.

    exposure caps      per relationship and for the book, gross and net. Net
                       exposure reuses the definition from `hedge.py` so the
                       screen gate and the risk layer cannot drift apart.

The drawdown kill switch is a pure function of an equity curve, separated from
everything above so it can be checked against a curve whose answer is known by
hand.

    python risk.py --book XLP~XLB:index,ALL~TRV:equity
    python risk.py --book XLP~XLB:index:etf,ALL~TRV:equity:equity
    python risk.py --book EURUSD~GBPUSD:forex,AUDUSD~NZDUSD:forex,USDNOK~USDZAR:forex
    python risk.py --book XLP~XLB:index,SPY~DIA:index --max-book-net 0.5 --json

Exit codes: 0 the book passes every cap, 3 it breaches one, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

import paths

paths.ensure_code_importable()

import costs as cost_model                                        # noqa: E402
import hedge as hg                                                # noqa: E402
import pair_report as pr                                          # noqa: E402
import strategy as sig                                            # noqa: E402
import triallog                                                   # noqa: E402

UserError = pr.UserError
DEFAULT_LOG = paths.LOGS / "risk.csv"


@dataclass
class Relationship:
    """One spread in the book, with the numbers the risk layer needs."""

    a: str
    b: str
    asset_class: str
    beta: float
    spread_returns: pd.Series
    broker: str = ""
    equity_net: pd.Series | None = None

    @property
    def name(self) -> str:
        return f"{self.a}~{self.b}"

    @property
    def legs(self) -> set:
        return {self.a, self.b}

    def net_exposure(self) -> float:
        """Net over gross exposure, from the leg weights (1, -beta).

        Delegated to `hedge.Estimate` rather than recomputed, so there is one
        definition of neutrality in the project. A second copy of this formula
        is how the screen came to admit a position that was 72% net long.
        """
        return hg.net_exposure(self.beta)

    def gross_exposure(self) -> float:
        """Units of instrument per unit of spread exposure.

        Always one: the weights (1, -beta) are divided by (1 + |beta|)
        throughout the engine. Stated explicitly because a book's gross is the
        sum of these and the reader should not have to infer the normalisation.
        """
        return 1.0


def shared_legs(book: list) -> list:
    """Every pair of relationships that name the same instrument.

    The cheap check, and the one that catches most concentration. It needs no
    sample and cannot be wrong about the sample it did not have.
    """
    found = []
    for i, first in enumerate(book):
        for second in book[i + 1:]:
            common = first.legs & second.legs
            if common:
                found.append((first.name, second.name, sorted(common)))
    return found


def correlation_matrix(book: list) -> pd.DataFrame:
    """Correlation of spread returns, on the bars every relationship shares.

    Aligned on the intersection rather than filled, because a filled return is
    a return that did not happen and it biases every correlation towards zero,
    which is the direction that makes a book look safer than it is.
    """
    frame = pd.DataFrame({r.name: r.spread_returns for r in book}).dropna()
    if frame.empty or len(frame) < 2:
        raise UserError("the relationships in this book share too few bars to "
                        "correlate; check the timeframes and date ranges match")
    return frame.corr()


def effective_bets(corr: pd.DataFrame) -> float:
    """How many independent things the book is betting on.

    The participation ratio of the correlation matrix eigenvalues,
    `(sum L)^2 / sum(L^2)`. It equals N when the spreads are uncorrelated and
    falls towards 1 as they become the same bet. Preferred to counting
    eigenvalues above a cutoff, because a cutoff invents a threshold nobody
    measured and this does not.
    """
    values = np.linalg.eigvalsh(corr.to_numpy(float))
    values = np.clip(values, 0.0, None)
    denom = float(np.sum(values ** 2))
    if denom <= 0:
        return float("nan")
    return float(np.sum(values) ** 2 / denom)


def worst_correlation(corr: pd.DataFrame) -> tuple:
    """The most correlated distinct pair in the book, by absolute value."""
    best = ("", "", 0.0)
    names = list(corr.columns)
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            value = float(corr.loc[first, second])
            if abs(value) > abs(best[2]):
                best = (first, second, value)
    return best


def drawdown_breach(equity_bps: np.ndarray, limit_bps: float) -> tuple:
    """First bar at which drawdown from the running peak exceeds `limit_bps`.

    Returns `(bar, depth)`, or `(-1, worst)` when the limit is never breached.
    A kill switch that only reports the worst drawdown is not a kill switch; it
    has to say *when*, because the point of the rule is that trading stops there
    and everything after it never happened.
    """
    if limit_bps <= 0:
        raise ValueError("the drawdown limit must be positive")
    equity = np.asarray(equity_bps, dtype=float)
    if equity.size == 0:
        return -1, 0.0
    peak = np.maximum.accumulate(equity)
    drawdown = equity - peak
    breached = np.flatnonzero(drawdown <= -limit_bps)
    if breached.size:
        bar = int(breached[0])
        return bar, float(drawdown[bar])
    return -1, float(drawdown.min())


@dataclass
class Verdict:
    """What the caps say about this book."""

    breaches: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.breaches

    def add(self, message: str) -> None:
        self.breaches.append(message)


def bet_share(corr: pd.DataFrame) -> float:
    """Effective bets as a share of positions held.

    A book of N relationships contains at most N bets, and exactly N only if no
    two of them move together at all — which no real book manages. So an
    absolute floor near N is a cap nothing can clear, and the scale-free
    question is the useful one: of the positions being carried, what share are
    distinct bets?
    """
    n = len(corr)
    if n <= 0:
        return float("nan")
    return effective_bets(corr) / n


def check_caps(book: list, corr: pd.DataFrame, *, max_net: float,
               max_book_net: float, max_correlation: float,
               min_effective_bets: float, min_bet_share: float = 0.0) -> Verdict:
    """Every cap in one place, so a breach is a line rather than a judgement."""
    verdict = Verdict()
    for r in book:
        net = r.net_exposure()
        if net > max_net:
            verdict.add(f"{r.name} is {net:.0%} net exposed, above the "
                        f"{max_net:.0%} cap, so most of its risk is directional")

    # Positions are added as signed weights: two spreads sharing a long leg add
    # exposure, and one long against one short cancels. The book's net is the
    # sum, not the average, which is what makes a book of neutral-looking
    # relationships able to be directional in total.
    book_net = sum(r.net_exposure() for r in book) / max(1, len(book))
    if book_net > max_book_net:
        verdict.add(f"the book averages {book_net:.0%} net exposure, above the "
                    f"{max_book_net:.0%} cap")

    first, second, value = worst_correlation(corr)
    if first and abs(value) > max_correlation:
        verdict.add(f"{first} and {second} have spread correlation {value:+.2f}, "
                    f"beyond the {max_correlation:.2f} cap: they are close to "
                    "one position held twice")

    bets = effective_bets(corr)
    # Printed to four places rather than two: at three relationships the value
    # can sit at 2.9998, and a message reading "3.00 bets, below the 3 required"
    # looks like a bug in the gate rather than a fact about the book.
    if math.isfinite(bets) and bets < min_effective_bets:
        verdict.add(f"{len(book)} relationships contain only {bets:.4f} "
                    f"independent bets, below the {min_effective_bets:g} required")
    share = bet_share(corr)
    if math.isfinite(share) and share < min_bet_share:
        verdict.add(f"only {share:.0%} of the positions are distinct bets, "
                    f"below the {min_bet_share:.0%} required: the book is more "
                    "concentrated than its position count suggests")
    return verdict


def spread_returns(prices: pd.DataFrame, *, fit_window: int, rehedge_every: int,
                   use_log: bool) -> tuple:
    """Bar-to-bar change in the spread the strategy would have been holding.

    Refit on the same trailing window and cadence as the strategy, so the
    correlation is between the things actually traded rather than between two
    static regressions that nobody holds.
    """
    n = len(prices)
    px = np.log(prices) if use_log else prices
    values = px.to_numpy(float)
    series = np.full(n, np.nan)
    fit = None
    last_beta = float("nan")
    for t in range(fit_window, n):
        if fit is None or t - fit.fitted_at >= rehedge_every:
            refit = sig.fit_relationship(prices.iloc[t - fit_window:t],
                                         use_log=use_log, at=t)
            fit = refit if refit is not None else fit
        if fit is None:
            continue
        last_beta = fit.beta
        # Normalised by gross, matching how the engine accrues returns, so a
        # correlation here is a correlation between things of comparable size.
        series[t] = ((values[t, 0] - fit.beta * values[t, 1])
                     / (1.0 + abs(fit.beta)))
    spread = pd.Series(series, index=prices.index).diff()
    return spread, last_beta


def parse_book(text: str, timeframe: str) -> list:
    """`XLP~XLB:index,ALL~TRV:equity` into instructions to load.

    The asset class is per relationship and not optional, for the same reason
    the rest of the pipeline demands it: guessing it silently reads the wrong
    series and the mistake is invisible in the output.
    """
    entries = []
    for piece in text.split(","):
        piece = piece.strip()
        if not piece:
            continue
        if ":" not in piece:
            raise UserError(f"{piece!r} needs an asset class, as in "
                            f"{piece}:index")
        parts = piece.split(":")
        if len(parts) == 2:
            pair, asset_class, broker = parts[0], parts[1], ""
        elif len(parts) == 3:
            pair, asset_class, broker = parts
        else:
            raise UserError(f"{piece!r} should read A~B:asset_class, or "
                            f"A~B:asset_class:broker to include it in the "
                            "drawdown check")
        if "~" not in pair:
            raise UserError(f"{pair!r} is not a relationship; write it as A~B")
        a, b = (s.strip().upper() for s in pair.split("~", 1))
        if not a or not b:
            raise UserError(f"{pair!r} is missing a leg")
        if a == b:
            raise UserError(f"{pair!r} names the same instrument twice")
        entries.append((a, b, asset_class.strip().lower(), timeframe,
                        broker.strip()))

    # Relationships are keyed by name when the correlation matrix is built, so
    # a repeated name would silently collapse two columns into one and the
    # matrix would describe a smaller book than the one handed in.
    names = [f"{a}~{b}" for a, b, _, _, _ in entries]
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated:
        raise UserError(f"{', '.join(repeated)} appears more than once. A book "
                        "holds each relationship once; size is sizing's job, "
                        "not the book's.")
    if len(entries) < 2:
        raise UserError("a book needs at least two relationships; there is "
                        "nothing to diversify with one")
    return entries


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="risk", description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sel = p.add_argument_group("selection")
    sel.add_argument("--book", required=True,
                     help="comma-separated A~B:asset_class entries")
    sel.add_argument("-t", "--timeframe", default="1d")
    sel.add_argument("--start", default=None)
    sel.add_argument("--end", default=None)

    struct = p.add_argument_group("structure - choose once")
    struct.add_argument("--price", default="log", choices=("log", "raw"))
    struct.add_argument("--fit-window", type=int, default=250)
    struct.add_argument("--rehedge-every", type=int, default=5)

    replay = p.add_argument_group("replay - only used when an entry names a broker")
    replay.add_argument("--entry-z", type=float, default=2.0)
    replay.add_argument("--exit-z", type=float, default=0.5)
    replay.add_argument("--stop-z", type=float, default=4.0)
    replay.add_argument("--max-holding-bars", type=int, default=20)
    replay.add_argument("--warmup", type=int, default=260)
    replay.add_argument("--lag", type=int, default=1)
    replay.add_argument("--costs-dir", default=str(cost_model.DEFAULT_COSTS))

    caps = p.add_argument_group("caps")
    caps.add_argument("--max-net-exposure", type=float, default=0.35,
                      help="per relationship, net over gross; the same "
                           "definition the screen gate uses")
    caps.add_argument("--max-book-net", type=float, default=0.35,
                      help="average net exposure across the book")
    caps.add_argument("--max-correlation", type=float, default=0.70,
                      help="beyond this two spreads are one position held twice")
    caps.add_argument("--min-effective-bets", type=float, default=1.5,
                      help="independent bets the book must contain at all; a "
                           "portfolio-construction minimum, not a concentration "
                           "test. A book of N can never exceed N")
    caps.add_argument("--min-bet-share", type=float, default=0.60,
                      help="effective bets as a share of positions held; this is "
                           "the concentration test, and unlike the absolute "
                           "floor it does not tighten as the book grows")
    caps.add_argument("--max-drawdown-bps", type=float, default=1000.0,
                      help="kill switch depth, used when an equity curve is given")

    out = p.add_argument_group("output")
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--log", default=str(DEFAULT_LOG))
    out.add_argument("--no-log", action="store_true")
    out.add_argument("--json", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    return p


def load_book(entries: list, args) -> list:
    book = []
    for a, b, asset_class, timeframe, broker in entries:
        loader = types.SimpleNamespace(
            symbols=f"{a},{b}", asset_class=asset_class, timeframe=timeframe,
            source=None, start=args.start, end=args.end, store=args.store)
        prices = pr.load_prices(loader)
        if len(prices) <= args.fit_window:
            raise UserError(f"{a}~{b} has {len(prices)} bars, not enough for a "
                            f"{args.fit_window}-bar fit window")
        series, beta = spread_returns(prices, fit_window=args.fit_window,
                                      rehedge_every=args.rehedge_every,
                                      use_log=args.price == "log")
        if not math.isfinite(beta):
            raise UserError(f"{a}~{b} has no usable hedge ratio on a "
                            f"{args.fit_window}-bar window")
        equity = None
        if broker:
            # The kill switch needs an equity curve, and an equity curve needs a
            # replay with real costs. Without a broker the book can still be
            # checked for concentration; the drawdown rule simply has nothing to
            # be applied to, and says so rather than passing silently.
            import backtest as bt

            # `--costs-dir` exists so a run can be pointed at a different set of
            # broker numbers. Reading the default location instead made the flag
            # silently do nothing, which is worse than not offering it.
            profile = cost_model.load_profile(
                Path(args.costs_dir) / f"{broker}.json")
            if not profile:
                raise UserError(f"no cost profile named {broker!r} for {a}~{b}")
            params = sig.SignalParams(
                entry_z=args.entry_z, exit_z=args.exit_z, stop_z=args.stop_z,
                max_holding_bars=args.max_holding_bars,
                fit_window=args.fit_window, rehedge_every=args.rehedge_every,
                use_log=args.price == "log")
            nights = cost_model.nights_per_bar(asset_class, timeframe)
            result = bt.run_backtest(prices, profile, params,
                                     warmup=args.warmup, bars_per_night=nights,
                                     lag=args.lag)
            equity = pd.Series(result.equity_net, index=prices.index)
        book.append(Relationship(a=a, b=b, asset_class=asset_class, beta=beta,
                                 spread_returns=series, broker=broker,
                                 equity_net=equity))
    return book


def book_equity(book: list) -> pd.Series | None:
    """Equity of the book, equally weighted, on bars every leg shares.

    Equal weights because sizing is `sizing.py`'s job and guessing at it here
    would make the drawdown a statement about weights nobody chose.
    """
    curves = {r.name: r.equity_net for r in book if r.equity_net is not None}
    if len(curves) != len(book) or not curves:
        return None
    frame = pd.DataFrame(curves).dropna()
    if frame.empty:
        return None
    return frame.mean(axis=1)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))

    book = load_book(parse_book(args.book, args.timeframe), args)
    corr = correlation_matrix(book)
    bets = effective_bets(corr)

    log(f"book of {len(book)} relationships  {args.timeframe}  "
        f"{len(corr)} x {len(corr)} correlation on shared bars")
    log("")
    log(f"  {'relationship':<16} {'class':<9} {'beta':>7} {'net':>6}  cap")
    for r in book:
        net = r.net_exposure()
        mark = "ok" if net <= args.max_net_exposure else "OVER"
        log(f"  {r.name:<16} {r.asset_class:<9} {r.beta:+7.3f} {net:6.0%}  {mark}")

    log("")
    shared = shared_legs(book)
    if shared:
        for first, second, common in shared:
            log(f"  SHARED LEG: {first} and {second} both hold "
                f"{', '.join(common)}")
    else:
        log("  no relationship shares a leg with another")

    log("")
    log("  spread correlation")
    header = "".join(f"{name[:10]:>12}" for name in corr.columns)
    log(f"  {'':<16}{header}")
    for name in corr.index:
        row = "".join(f"{corr.loc[name, other]:12.2f}" for other in corr.columns)
        log(f"  {name[:16]:<16}{row}")

    log("")
    log(f"  {len(book)} relationships contain {bets:.4f} independent bets "
        f"({bet_share(corr):.0%} of the positions held)")
    first, second, value = worst_correlation(corr)
    if first:
        log(f"  most correlated: {first} and {second} at {value:+.2f}")

    equity = book_equity(book)
    breach_bar, depth = (-1, float("nan"))
    log("")
    if equity is None:
        log("  drawdown kill switch not evaluated: no equity curve.")
        log("    Name a broker on every entry to build one, as in "
            "XLP~XLB:index:etf")
    else:
        breach_bar, depth = drawdown_breach(equity.to_numpy(float),
                                            args.max_drawdown_bps)
        if breach_bar >= 0:
            log(f"  KILL SWITCH FIRES at {equity.index[breach_bar]:%Y-%m-%d}, "
                f"{depth:,.0f} bps below the running peak, against a "
                f"{args.max_drawdown_bps:,.0f} limit")
            log("    Everything after that date is a trade the rule says was "
                "never placed.")
        else:
            log(f"  drawdown kill switch never fires: worst is {depth:,.0f} bps "
                f"against a {args.max_drawdown_bps:,.0f} limit")

    verdict = check_caps(book, corr, max_net=args.max_net_exposure,
                         max_book_net=args.max_book_net,
                         max_correlation=args.max_correlation,
                         min_effective_bets=args.min_effective_bets,
                         min_bet_share=args.min_bet_share)
    if breach_bar >= 0:
        verdict.add(f"the book's drawdown reaches {depth:,.0f} bps on "
                    f"{equity.index[breach_bar]:%Y-%m-%d}, past the "
                    f"{args.max_drawdown_bps:,.0f} kill-switch limit")
    log("")
    if verdict.ok:
        log("  BOOK ACCEPTED - every cap holds")
    else:
        log("  BOOK REFUSED")
        for breach in verdict.breaches:
            log(f"    - {breach}")

    if not args.no_log:
        row = {
            "run": 0, "run_utc": triallog.stamp(),
            "book": ",".join(r.name for r in book),
            "timeframe": args.timeframe,
            "start": args.start or "", "end": args.end or "",
            "relationships": len(book),
            "effective_bets": round(bets, 4),
            "bet_share": round(bet_share(corr), 4),
            "min_bet_share": args.min_bet_share,
            "worst_correlation": round(value, 4) if first else None,
            "shared_legs": len(shared),
            "max_net_exposure": args.max_net_exposure,
            "max_correlation": args.max_correlation,
            "min_effective_bets": args.min_effective_bets,
            "max_drawdown_bps": args.max_drawdown_bps,
            "kill_switch_bar": (None if breach_bar < 0
                                else str(equity.index[breach_bar].date())),
            "kill_switch_depth_bps": (None if not math.isfinite(depth)
                                      else round(depth, 1)),
            "accepted": "yes" if verdict.ok else "no",
            "breaches": "; ".join(verdict.breaches) or None,
        }
        try:
            run = triallog.append(Path(args.log), row)
        except triallog.SchemaChanged as exc:
            raise UserError(str(exc)) from exc
        log(f"  run #{run} logged to {Path(args.log)}")

    if args.json:
        print(json.dumps({
            "relationships": [{"name": r.name, "asset_class": r.asset_class,
                               "beta": r.beta, "net_exposure": r.net_exposure()}
                              for r in book],
            "effective_bets": bets,
            "bet_share": bet_share(corr),
            "worst_correlation": {"a": first, "b": second, "value": value},
            "shared_legs": [{"a": f, "b": s, "common": c} for f, s, c in shared],
            "kill_switch": {
                "limit_bps": args.max_drawdown_bps,
                "fires_on": (None if breach_bar < 0
                             else str(equity.index[breach_bar].date())),
                "depth_bps": (None if not math.isfinite(depth) else depth),
                "evaluated": equity is not None,
            },
            "accepted": verdict.ok,
            "breaches": verdict.breaches,
        }, indent=2, default=str))

    return 0 if verdict.ok else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
