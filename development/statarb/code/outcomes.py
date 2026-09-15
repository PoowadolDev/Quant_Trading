"""Step 3.1 — what actually happens to a trade, against what was predicted.

Every edge number in this project comes from one formula:

    expected move = (entry_z - exit_z) * sigma_eq

`pair_report.py` prints it, `feasibility.py` divides it by cost to reach a
verdict, and both gates depend on it. It has never been compared with what a
trade earned. The comparison is unkind: on the six pairs that have ever been
candidates it over-predicts realised gross per trade by 10x to 68x where it has
the sign right at all, and has the sign wrong on the other three.

Two errors stack, and this script separates them.

The first is the *scale*. The reports fit one OU process to the whole in-sample
half. The strategy refits every few bars on a trailing window, so the spread it
trades has a shorter memory and a smaller sigma — smaller by 1.4x to 5.7x on
the pairs measured. An expected move computed from the static fit describes a
trade nobody places.

The second is *completion*. The formula gives the payoff of a trade that opens
at `entry_z` and runs to `exit_z`. Some trades do not: they hit the stop, they
run out of holding period, the monitor closes them, or the sample ends. Nothing
in the pipeline has ever counted how often that happens or what those exits
cost, and the backtest reports a win rate without reporting the average win and
the average loss separately — so the assumption of full completion has never
been visible, let alone checked.

    python outcomes.py -s XLP,XLB -a index --broker etf
    python outcomes.py -s XLP,XLB -a index --broker etf --entry-z 1.5,2.0,2.5
    python outcomes.py -s ALL,TRV -a equity --broker equity --json

The replay is `backtest.run_backtest`, unchanged and uncopied. A second replay
would be a second set of bugs, and the point of this script is to describe the
trades the backtest actually makes rather than trades of its own.

Exit codes: 0 the prediction is within tolerance of what was realised, 3 it is
not, 2 usage error, 1 runtime error.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

import paths

paths.ensure_code_importable()

import backtest as bt                                             # noqa: E402
import costs as cost_model                                        # noqa: E402
import pair_report as pr                                          # noqa: E402
import strategy as sig                                            # noqa: E402
import triallog                                                   # noqa: E402

UserError = pr.UserError
DEFAULT_LOG = paths.LOGS / "outcomes.csv"

#: How a position ended. `TARGET` is the only one the expected-move formula
#: describes; every other category is a trade the formula does not model.
TARGET, STOP, TIME, SAMPLE_END, OTHER = (
    "target", "stop", "holding limit", "end of sample", "other")

REASON_CATEGORY = {
    sig.EXIT_TARGET: TARGET,
    sig.EXIT_STOP: STOP,
    sig.EXIT_TIME: TIME,
}


def categorise(reason: str) -> str:
    """Which kind of ending a recorded exit reason describes.

    Matched against the strategy's own constants rather than by reading the
    prose, for the reason the health monitor was fixed for: text written for a
    human is not a data field, and parsing it turns a wording change into a
    silent behaviour change.
    """
    if reason in REASON_CATEGORY:
        return REASON_CATEGORY[reason]
    if reason.startswith("exit: end of the sample"):
        return SAMPLE_END
    return OTHER


@dataclass
class Outcomes:
    """Everything measured about one configuration's trades."""

    trades: int
    by_category: dict                          # category -> count
    gross_by_category: dict                    # category -> total gross bps
    wins: int
    losses: int
    avg_win_bps: float
    avg_loss_bps: float
    avg_gross_bps: float
    median_gross_bps: float
    bars_held: list = field(default_factory=list)
    gross_total_bps: float = 0.0

    @property
    def completion_rate(self) -> float:
        """Share of finished trades that reached the exit threshold.

        This is the number the expected-move formula silently assumes is 1.0.
        """
        finished = self.trades - self.by_category.get(SAMPLE_END, 0)
        if finished <= 0:
            return float("nan")
        return self.by_category.get(TARGET, 0) / finished

    @property
    def win_loss_ratio(self) -> float:
        if not math.isfinite(self.avg_loss_bps) or self.avg_loss_bps == 0:
            return float("inf")
        return abs(self.avg_win_bps / self.avg_loss_bps)

    def reconstruct_gross(self) -> float:
        """Total gross rebuilt from the category breakdown.

        It must equal the engine's own gross figure. If the two disagree, this
        script has lost trades somewhere and every number above it is wrong.
        """
        return float(sum(self.gross_by_category.values()))


def measure(trades: list) -> Outcomes:
    """Classify finished trades. No prices, no fitting — arithmetic only."""
    by_category: dict = {}
    gross_by_category: dict = {}
    gross = []
    held = []
    for t in trades:
        cat = categorise(t.exit_reason)
        by_category[cat] = by_category.get(cat, 0) + 1
        gross_by_category[cat] = gross_by_category.get(cat, 0.0) + t.gross_bps
        gross.append(t.gross_bps)
        held.append(t.bars_held)

    arr = np.array(gross, dtype=float)
    wins = arr[arr > 0]
    losses = arr[arr <= 0]
    return Outcomes(
        trades=len(trades),
        by_category=by_category,
        gross_by_category=gross_by_category,
        wins=int(wins.size),
        losses=int(losses.size),
        avg_win_bps=float(wins.mean()) if wins.size else 0.0,
        avg_loss_bps=float(losses.mean()) if losses.size else 0.0,
        avg_gross_bps=float(arr.mean()) if arr.size else float("nan"),
        median_gross_bps=float(np.median(arr)) if arr.size else float("nan"),
        bars_held=held,
        gross_total_bps=float(arr.sum()) if arr.size else 0.0,
    )


def predicted_move_bps(entry_z: float, exit_z: float, sigma_eq: float) -> float:
    """The pipeline's expected move, in basis points, stated in one place.

    Written here rather than imported so that a change to the formula shows up
    as a failing verification check instead of as a quietly different number.
    """
    return (entry_z - exit_z) * sigma_eq * 1e4


def traded_sigma(prices: pd.DataFrame, params: sig.SignalParams, *,
                 step: int = 25) -> tuple[float, float]:
    """Median sigma_eq and half-life as the *strategy* sees them.

    The reports fit once on the in-sample half. The strategy refits on a
    trailing window every few bars, so the spread it scores has its own scale.
    `sig.fit_relationship` is the same function the strategy calls, so this
    cannot drift away from what is actually traded.
    """
    window = params.fit_window
    sigmas, half_lives = [], []
    for t in range(window, len(prices) + 1, max(1, step)):
        fit = sig.fit_relationship(prices.iloc[t - window:t],
                                   use_log=params.use_log, at=t)
        if fit is None:
            continue
        sigmas.append(fit.sigma_eq)
        # The AR(1) coefficient is not returned, so recover the half-life from
        # the residual scale the same fit implies.
        half_lives.append(_half_life_from(prices.iloc[t - window:t], fit,
                                          use_log=params.use_log))
    if not sigmas:
        return float("nan"), float("nan")
    finite = [h for h in half_lives if math.isfinite(h)]
    return float(np.median(sigmas)), float(np.median(finite)) if finite else float("nan")


def _half_life_from(window: pd.DataFrame, fit: sig.Fit, *, use_log: bool) -> float:
    """Half-life of the spread this fit defines, on the window it was fitted to."""
    px = np.log(window) if use_log else window
    a, b = window.columns
    spread = px[a].to_numpy(float) - fit.beta * px[b].to_numpy(float) - fit.alpha
    s0, s1 = spread[:-1], spread[1:]
    ar = float(np.polyfit(s0, s1, 1)[0])
    if not (0.0 < ar < 1.0):
        return float("nan")
    return math.log(2) / -math.log(ar)


@dataclass
class Comparison:
    """Predicted against realised, for one configuration."""

    entry_z: float
    exit_z: float
    sigma_static_bps: float
    sigma_traded_bps: float
    half_life_static: float
    half_life_traded: float
    predicted_static_bps: float
    predicted_traded_bps: float
    realised_bps: float
    outcomes: Outcomes

    @property
    def overstatement(self) -> float:
        """How many times larger the generous prediction is than the result.

        Infinite when the realised figure is zero or the wrong sign, because
        there is no ratio to quote and reporting one would flatter the model.
        """
        if not math.isfinite(self.realised_bps) or self.realised_bps <= 0:
            return float("inf")
        return self.predicted_traded_bps / self.realised_bps


def compare(prices: pd.DataFrame, profile: dict, params: sig.SignalParams, *,
            static_sigma: float, static_half_life: float, warmup: int,
            bars_per_night: float, lag: int) -> Comparison:
    """Run one configuration and place its prediction beside its result."""
    result = bt.run_backtest(prices, profile, params, warmup=warmup,
                             bars_per_night=bars_per_night, lag=lag)
    outcomes = measure(result.trades)
    sigma_traded, hl_traded = traded_sigma(prices, params)
    return Comparison(
        entry_z=params.entry_z, exit_z=params.exit_z,
        sigma_static_bps=static_sigma * 1e4,
        sigma_traded_bps=sigma_traded * 1e4,
        half_life_static=static_half_life,
        half_life_traded=hl_traded,
        predicted_static_bps=predicted_move_bps(params.entry_z, params.exit_z,
                                                static_sigma),
        predicted_traded_bps=predicted_move_bps(params.entry_z, params.exit_z,
                                                sigma_traded),
        realised_bps=outcomes.avg_gross_bps,
        outcomes=outcomes,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="outcomes", description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sel = p.add_argument_group("selection")
    sel.add_argument("-s", "--symbols", required=True)
    sel.add_argument("-a", "--asset-class", default="forex",
                     help="one class for both legs, or one per leg")
    sel.add_argument("-t", "--timeframe", default="1d")
    sel.add_argument("--source", default=None)
    sel.add_argument("--start", default=None)
    sel.add_argument("--end", default=None)

    struct = p.add_argument_group("structure - choose once")
    struct.add_argument("--price", default="log", choices=("log", "raw"))
    struct.add_argument("--hedge-source", default="rolling",
                        choices=("static", "rolling"))

    search = p.add_argument_group("searched - every value is a trial")
    search.add_argument("--entry-z", default="2.0",
                        help="one value or a comma-separated list; each is a trial")
    search.add_argument("--exit-z", type=float, default=0.5)
    search.add_argument("--stop-z", type=float, default=4.0)
    search.add_argument("--max-holding-bars", type=int, default=20)
    search.add_argument("--min-bars-between-trades", type=int, default=0)
    search.add_argument("--fit-window", type=int, default=250)
    search.add_argument("--rehedge-every", type=int, default=5)
    search.add_argument("--split", type=float, default=0.70)
    search.add_argument("--warmup", type=int, default=260)

    given = p.add_argument_group("given by reality")
    given.add_argument("--broker", required=True)
    given.add_argument("--costs-dir", default=str(cost_model.DEFAULT_COSTS))
    given.add_argument("--bars-per-night", type=float, default=None,
                       help="nights of financing per bar; defaults to the asset class and timeframe, which is 1.45 for a daily equity bar and 1.0 only for crypto")
    given.add_argument("--lag", type=int, default=1)

    judge = p.add_argument_group("judgement")
    judge.add_argument("--max-overstatement", type=float, default=3.0,
                       help="how many times the prediction may exceed the realised "
                            "mean before the configuration is reported as a "
                            "failure of the model rather than of the pair")

    out = p.add_argument_group("output")
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--log", default=str(DEFAULT_LOG))
    out.add_argument("--no-log", action="store_true")
    out.add_argument("--json", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    return p


def parse_levels(text: str, flag: str) -> list[float]:
    values = []
    for piece in text.split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            values.append(float(piece))
        except ValueError as exc:
            raise UserError(f"{flag} takes numbers, got {piece!r}") from exc
    if not values:
        raise UserError(f"{flag} needs at least one value")
    return values


def show(comparisons: list, log) -> None:
    log(f"  {'entry':>6} {'trades':>7} {'target':>7} {'stop':>6} {'time':>6} "
        f"{'other':>6} {'done':>6} {'avg win':>9} {'avg loss':>9} {'w/l':>6}")
    for c in comparisons:
        o = c.outcomes
        log(f"  {c.entry_z:6.2f} {o.trades:7d} "
            f"{o.by_category.get(TARGET, 0):7d} {o.by_category.get(STOP, 0):6d} "
            f"{o.by_category.get(TIME, 0):6d} "
            f"{o.by_category.get(OTHER, 0) + o.by_category.get(SAMPLE_END, 0):6d} "
            f"{o.completion_rate:6.0%} {o.avg_win_bps:+9.1f} {o.avg_loss_bps:+9.1f} "
            f"{o.win_loss_ratio:6.2f}")

    log("")
    log(f"  {'entry':>6} {'sig static':>11} {'sig traded':>11} {'predicted':>10} "
        f"{'realised':>9} {'over by':>9}")
    for c in comparisons:
        over = ("sign wrong" if not math.isfinite(c.overstatement)
                else f"{c.overstatement:.1f}x")
        log(f"  {c.entry_z:6.2f} {c.sigma_static_bps:11.0f} {c.sigma_traded_bps:11.0f} "
            f"{c.predicted_traded_bps:10.0f} {c.realised_bps:+9.1f} {over:>9}")


def append_log(path: Path, args, pair: str, c: Comparison) -> int:
    o = c.outcomes
    row = {
        "run": 0,
        "run_utc": triallog.stamp(),
        "pair": pair,
        "timeframe": args.timeframe,
        "broker": args.broker,
        "start": args.start or "", "end": args.end or "",
        "bars_per_night": args.bars_per_night, "warmup": args.warmup,
        "entry_z": round(c.entry_z, 4),
        "exit_z": round(c.exit_z, 4),
        "stop_z": round(args.stop_z, 4),
        "max_holding_bars": args.max_holding_bars,
        "fit_window": args.fit_window,
        "trades": o.trades,
        "target": o.by_category.get(TARGET, 0),
        "stop": o.by_category.get(STOP, 0),
        "holding_limit": o.by_category.get(TIME, 0),
        "other": o.by_category.get(OTHER, 0) + o.by_category.get(SAMPLE_END, 0),
        "completion_rate": round(o.completion_rate, 4),
        "avg_win_bps": round(o.avg_win_bps, 2),
        "avg_loss_bps": round(o.avg_loss_bps, 2),
        "sigma_static_bps": round(c.sigma_static_bps, 1),
        "sigma_traded_bps": round(c.sigma_traded_bps, 1),
        "predicted_bps": round(c.predicted_traded_bps, 1),
        "realised_bps": round(c.realised_bps, 2),
        "overstatement": (None if not math.isfinite(c.overstatement)
                          else round(c.overstatement, 2)),
    }
    try:
        return triallog.append(Path(path), row)
    except triallog.SchemaChanged as exc:
        raise UserError(str(exc)) from exc


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))

    profile_path = Path(args.costs_dir) / f"{args.broker}.json"
    profile = cost_model.load_profile(profile_path)
    if not profile:
        raise UserError(f"no cost profile at {profile_path}; run costs.py add first")

    prices = pr.load_prices(args)
    if args.bars_per_night is None:
        # One definition of how many nights a bar costs, in costs.py, rather
        # than a 1.0 that silently undercharges every asset class but crypto.
        first_class = args.asset_class.split(",")[0].strip().lower()
        args.bars_per_night = cost_model.nights_per_bar(first_class, args.timeframe)
    if args.warmup >= len(prices):
        raise UserError(f"--warmup {args.warmup} leaves no bars to trade")

    # The static fit the reports use, so the two predictions sit side by side.
    split = int(len(prices) * args.split)
    static = pr.fit_pair(prices, split=split, use_log=args.price == "log",
                         entry_z=2.0, exit_z=args.exit_z, cost_bps=0.0)

    pair = " ~ ".join(prices.columns)
    log(f"{pair}  {args.timeframe}  {len(prices):,} bars  broker {args.broker}")

    comparisons = []
    for entry_z in parse_levels(args.entry_z, "--entry-z"):
        try:
            params = sig.SignalParams(
                entry_z=entry_z, exit_z=args.exit_z, stop_z=args.stop_z,
                max_holding_bars=args.max_holding_bars,
                min_bars_between_trades=args.min_bars_between_trades,
                hedge_source=args.hedge_source, fit_window=args.fit_window,
                rehedge_every=args.rehedge_every, use_log=args.price == "log")
        except ValueError as exc:
            raise UserError(f"entry-z {entry_z:g}: {exc}") from exc
        comparisons.append(compare(prices, profile, params,
                                   static_sigma=static.sigma_eq,
                                   static_half_life=static.half_life,
                                   warmup=args.warmup,
                                   bars_per_night=args.bars_per_night,
                                   lag=args.lag))

    show(comparisons, log)

    hl_s, hl_t = static.half_life, comparisons[0].half_life_traded
    if math.isfinite(hl_s) and math.isfinite(hl_t) and hl_t > 0:
        log("")
        log(f"  half-life: {hl_s:.1f} bars as fitted by the report, "
            f"{hl_t:.1f} as traded ({hl_s / hl_t:.1f}x)")

    worst = max(comparisons, key=lambda c: c.overstatement)
    ok = worst.overstatement <= args.max_overstatement
    log("")
    if ok:
        log(f"  PREDICTION HOLDS - the expected move is within "
            f"{args.max_overstatement:g}x of the realised mean everywhere")
    else:
        over = ("has the wrong sign" if not math.isfinite(worst.overstatement)
                else f"is {worst.overstatement:.1f}x too large")
        log(f"  PREDICTION FAILS - at entry {worst.entry_z:g} the expected move "
            f"{over}. Any edge computed from it is not describing this trade.")

    if not args.no_log:
        for c in comparisons:
            run = append_log(Path(args.log), args, pair, c)
        log(f"  {len(comparisons)} row(s) logged to {Path(args.log)}, last run #{run}")

    if args.json:
        print(json.dumps({
            "pair": pair,
            "bars": len(prices),
            "configurations": [{
                "entry_z": c.entry_z,
                "exit_z": c.exit_z,
                "sigma_static_bps": c.sigma_static_bps,
                "sigma_traded_bps": c.sigma_traded_bps,
                "half_life_static": c.half_life_static,
                "half_life_traded": c.half_life_traded,
                "predicted_bps": c.predicted_traded_bps,
                "realised_bps": c.realised_bps,
                "overstatement": (None if not math.isfinite(c.overstatement)
                                  else c.overstatement),
                "trades": c.outcomes.trades,
                "by_category": c.outcomes.by_category,
                "completion_rate": c.outcomes.completion_rate,
                "avg_win_bps": c.outcomes.avg_win_bps,
                "avg_loss_bps": c.outcomes.avg_loss_bps,
            } for c in comparisons],
        }, indent=2, default=str))

    return 0 if ok else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
