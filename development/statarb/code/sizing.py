"""Step 3.4 — how much to hold, from the growth rate rather than from Sharpe.

Sharpe is leverage-invariant: doubling every position doubles the return and
doubles the volatility, and the ratio does not move. It therefore cannot answer
the sizing question at all, and a strategy chosen on Sharpe has had nothing said
about how much of it to hold.

What does answer it is the time-average growth rate. Holding leverage `f` on a
strategy whose per-trade log return has mean `mu` and variance `sigma^2` grows
the account at

    g(f) = f * mu - f^2 * sigma^2 / 2

which is maximised at `f = mu / sigma^2`. Growth, unlike the arithmetic mean, is
what a single account compounding through time actually experiences: the
subtraction of `sigma^2 / 2` is the cost of volatility to a path, not a risk
preference (`research/paper/portfolio_sizing/0902.2965`).

**The estimate is the problem, not the formula.** Every parameter in this
project has moved by a factor of several across windows: hedge ratios from
+0.079 to +1.343, half-lives by up to 15x. Full-Kelly leverage on `mu` estimated
from seventy-five trades is a way to lose an account while being right on
average. So `mu` is replaced by a lower confidence bound,

    mu_adjusted = mu - k * sigma / sqrt(n)

where `k` is a stated confidence level and `sigma / sqrt(n)` is the standard
error of the mean. Nothing here is a fudge factor: `k` is a number the operator
states and the rest is measured. When the sample is small the bound is far below
the point estimate and the size falls accordingly, which is the intended
behaviour rather than a side effect.

`mu` and `sigma` come from the realised per-trade returns of a replay, never from
the OU closed form, because that form over-predicts the realised move by 10x to
68x on every pair this project has tested. `outcomes.py` measures the same trades
and explains why the two differ; this script only needs their returns.

    python sizing.py -s XLP,XLB -a index --broker etf --equity 100000
    python sizing.py -s ALL,TRV -a equity --broker equity --confidence 1.0
    python sizing.py -s XLP,XLB -a index --broker etf --json

Exit codes: 0 a positive size is justified, 3 the honest size is zero,
2 usage error.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import paths

paths.ensure_code_importable()

import costs as cost_model                                        # noqa: E402
import pair_report as pr                                          # noqa: E402
import strategy as sig                                            # noqa: E402
import triallog                                                   # noqa: E402

UserError = pr.UserError
DEFAULT_LOG = paths.LOGS / "sizing.csv"


def growth_rate(leverage: float, mu: float, sigma: float) -> float:
    """Time-average growth of an account held at `leverage`.

    `mu` and `sigma` are per trade, in log terms. The `sigma^2 / 2` term is the
    gap between the average outcome and the outcome of a single path, and it is
    why a strategy with a positive mean can still ruin an account held at the
    wrong size.
    """
    return leverage * mu - 0.5 * (leverage ** 2) * (sigma ** 2)


def growth_optimal_leverage(mu: float, sigma: float) -> float:
    """The leverage that maximises growth: `mu / sigma^2`.

    Negative when the mean is negative, which is the correct answer and is
    reported rather than clamped — a negative optimum means the strategy should
    be traded the other way round or not at all, and hiding it behind a zero
    loses that information.
    """
    if not (math.isfinite(mu) and math.isfinite(sigma)) or sigma <= 0:
        return float("nan")
    return mu / (sigma ** 2)


def lower_bound_mean(mu: float, sigma: float, n: int, confidence: float) -> float:
    """`mu` discounted by the uncertainty in its own estimate.

    The standard error of a mean is `sigma / sqrt(n)`, so `k` standard errors
    below the estimate is a bound that gets tighter as evidence accumulates and
    stays honest when it does not. With seventy-five trades and a per-trade
    standard deviation several times the mean, this is a large haircut. It is
    supposed to be.
    """
    if n <= 0 or not math.isfinite(sigma) or sigma < 0:
        return float("nan")
    return mu - confidence * sigma / math.sqrt(n)


@dataclass
class Size:
    """What one relationship should be held at, and why."""

    pair: str
    trades: int
    mu_bps: float
    sigma_bps: float
    mu_lower_bps: float
    confidence: float
    full_leverage: float
    bounded_leverage: float
    capped_leverage: float
    max_leverage: float
    equity: float

    @property
    def notional(self) -> float:
        """Gross exposure in account currency, at the capped leverage."""
        return max(0.0, self.capped_leverage) * self.equity

    @property
    def growth_full(self) -> float:
        return growth_rate(self.full_leverage, self.mu_bps / 1e4,
                           self.sigma_bps / 1e4) * 1e4

    @property
    def growth_capped(self) -> float:
        return growth_rate(self.capped_leverage, self.mu_bps / 1e4,
                           self.sigma_bps / 1e4) * 1e4

    @property
    def justified(self) -> bool:
        return self.capped_leverage > 0.0

    def reason(self) -> str:
        if self.mu_bps <= 0:
            return ("the realised mean is not positive, so no size is justified "
                    "at any leverage")
        if self.mu_lower_bps <= 0:
            return (f"the mean is +{self.mu_bps:.1f} bps per trade but its "
                    f"{self.confidence:g}-standard-error lower bound is "
                    f"{self.mu_lower_bps:+.1f}, so {self.trades} trades do not "
                    "establish that it is positive at all")
        if self.bounded_leverage > self.max_leverage:
            return (f"growth-optimal leverage is {self.bounded_leverage:.2f} "
                    f"after the uncertainty haircut, capped at "
                    f"{self.max_leverage:g}")
        return (f"leverage {self.capped_leverage:.2f} from a bounded mean of "
                f"{self.mu_lower_bps:+.1f} bps against a per-trade deviation of "
                f"{self.sigma_bps:.1f}")


def size_from_trades(pair: str, gross_bps: list, *, confidence: float,
                     max_leverage: float, equity: float) -> Size:
    """Everything above, applied to one set of realised per-trade returns.

    Separated from the command line so the verification suite can hand it
    returns whose right answer is known by hand.
    """
    arr = np.asarray(list(gross_bps), dtype=float)
    arr = arr[np.isfinite(arr)]
    n = int(arr.size)
    if n < 2:
        raise UserError(f"{pair} has {n} finished trade(s); a mean and a "
                        "deviation need at least two, and a size worth trusting "
                        "needs far more")
    mu_bps = float(arr.mean())
    sigma_bps = float(arr.std(ddof=1))
    mu_lower_bps = lower_bound_mean(mu_bps, sigma_bps, n, confidence)

    full = growth_optimal_leverage(mu_bps / 1e4, sigma_bps / 1e4)
    bounded = growth_optimal_leverage(mu_lower_bps / 1e4, sigma_bps / 1e4)
    capped = 0.0 if not math.isfinite(bounded) else min(max(bounded, 0.0),
                                                        max_leverage)
    return Size(pair=pair, trades=n, mu_bps=mu_bps, sigma_bps=sigma_bps,
                mu_lower_bps=mu_lower_bps, confidence=confidence,
                full_leverage=full, bounded_leverage=bounded,
                capped_leverage=capped, max_leverage=max_leverage,
                equity=equity)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sizing", description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sel = p.add_argument_group("selection")
    sel.add_argument("-s", "--symbols", required=True)
    sel.add_argument("-a", "--asset-class", default="forex")
    sel.add_argument("-t", "--timeframe", default="1d")
    sel.add_argument("--source", default=None)
    sel.add_argument("--start", default=None)
    sel.add_argument("--end", default=None)

    struct = p.add_argument_group("structure - choose once")
    struct.add_argument("--price", default="log", choices=("log", "raw"))
    struct.add_argument("--hedge-source", default="rolling",
                        choices=("static", "rolling"))

    search = p.add_argument_group("searched - every value is a trial")
    search.add_argument("--entry-z", type=float, default=2.0)
    search.add_argument("--exit-z", type=float, default=0.5)
    search.add_argument("--stop-z", type=float, default=4.0)
    search.add_argument("--max-holding-bars", type=int, default=20)
    search.add_argument("--fit-window", type=int, default=250)
    search.add_argument("--rehedge-every", type=int, default=5)
    search.add_argument("--warmup", type=int, default=260)

    size = p.add_argument_group("sizing")
    size.add_argument("--equity", type=float, default=100_000.0,
                      help="account value the size is expressed against")
    size.add_argument("--confidence", type=float, default=1.0,
                      help="standard errors to subtract from the estimated mean "
                           "before sizing on it; 0 is full Kelly on the point "
                           "estimate, which no sample in this project supports")
    size.add_argument("--max-leverage", type=float, default=1.0,
                      help="hard cap, applied after the uncertainty haircut")

    given = p.add_argument_group("given by reality")
    given.add_argument("--broker", required=True)
    given.add_argument("--costs-dir", default=str(cost_model.DEFAULT_COSTS))
    given.add_argument("--bars-per-night", type=float, default=None,
                       help="nights of financing per bar; defaults to the asset class and timeframe, which is 1.45 for a daily equity bar and 1.0 only for crypto")
    given.add_argument("--lag", type=int, default=1)
    given.add_argument("--net", action="store_true",
                       help="size on net returns after cost and financing rather "
                            "than on gross; the honest choice, and off by default "
                            "only so gross and net can be compared")

    out = p.add_argument_group("output")
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--log", default=str(DEFAULT_LOG))
    out.add_argument("--no-log", action="store_true")
    out.add_argument("--json", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))

    profile_path = Path(args.costs_dir) / f"{args.broker}.json"
    profile = cost_model.load_profile(profile_path)
    if not profile:
        raise UserError(f"no cost profile at {profile_path}; run costs.py add first")
    estimated = any(c.estimated for c in profile.values())

    # A flag that takes a number will be given a wrong one eventually, and two of
    # these turn the script into the opposite of itself: a negative confidence
    # adds the uncertainty back on instead of taking it off, and produced full
    # leverage on a pair every other test in this project rejects.
    if args.equity <= 0:
        raise UserError(f"--equity {args.equity:g} is not an account. Size is "
                        "expressed against equity, so it must be positive.")
    if args.confidence < 0:
        raise UserError(f"--confidence {args.confidence:g} would add the "
                        "uncertainty to the estimated mean rather than take it "
                        "off, sizing up on exactly the evidence that is weakest. "
                        "Use 0 for the point estimate itself.")
    if args.max_leverage < 0:
        raise UserError(f"--max-leverage {args.max_leverage:g} is not a cap. "
                        "Use 0 to forbid a position entirely.")

    prices = pr.load_prices(args)
    if args.bars_per_night is None:
        # One definition of how many nights a bar costs, in costs.py, rather
        # than a 1.0 that silently undercharges every asset class but crypto.
        first_class = args.asset_class.split(",")[0].strip().lower()
        args.bars_per_night = cost_model.nights_per_bar(first_class, args.timeframe)
    if args.warmup >= len(prices):
        raise UserError(f"--warmup {args.warmup} leaves no bars to trade")

    try:
        params = sig.SignalParams(
            entry_z=args.entry_z, exit_z=args.exit_z, stop_z=args.stop_z,
            max_holding_bars=args.max_holding_bars,
            hedge_source=args.hedge_source, fit_window=args.fit_window,
            rehedge_every=args.rehedge_every, use_log=args.price == "log")
    except ValueError as exc:
        raise UserError(str(exc)) from exc

    import backtest as bt

    result = bt.run_backtest(prices, profile, params, warmup=args.warmup,
                             bars_per_night=args.bars_per_night, lag=args.lag)
    pair = " ~ ".join(prices.columns)
    basis = "net" if args.net else "gross"
    returns = [(t.net_bps if args.net else t.gross_bps) for t in result.trades]

    size = size_from_trades(pair, returns, confidence=args.confidence,
                            max_leverage=args.max_leverage, equity=args.equity)

    log(f"{pair}  {args.timeframe}  {len(prices):,} bars  sizing on {basis} returns")
    log(f"  {size.trades} trades   mean {size.mu_bps:+.1f} bps   "
        f"deviation {size.sigma_bps:.1f} bps   "
        f"standard error {size.sigma_bps / math.sqrt(size.trades):.1f}")
    log("")
    log(f"  {'leverage':<26} {'value':>8}  {'growth/trade':>13}")
    log(f"  {'growth-optimal on the mean':<26} {size.full_leverage:8.2f}  "
        f"{size.growth_full:+13.2f} bps")
    log(f"  {f'after a {args.confidence:g} s.e. haircut':<26} "
        f"{size.bounded_leverage:8.2f}")
    log(f"  {f'after the {args.max_leverage:g}x cap':<26} "
        f"{size.capped_leverage:8.2f}  {size.growth_capped:+13.2f} bps")
    log("")
    if size.justified:
        log(f"  SIZE {size.notional:,.0f} of gross exposure on "
            f"{size.equity:,.0f} of equity")
    else:
        log("  SIZE ZERO")
    log(f"    {size.reason()}")
    if estimated:
        log("  NOTE: the cost profile is an estimate, not a broker sheet")

    if not args.no_log:
        row = {
            "run": 0, "run_utc": triallog.stamp(), "pair": pair,
            "timeframe": args.timeframe, "broker": args.broker, "basis": basis,
            "start": args.start or "", "end": args.end or "",
            "bars_per_night": args.bars_per_night, "warmup": args.warmup,
            "entry_z": args.entry_z, "exit_z": args.exit_z,
            "stop_z": args.stop_z, "max_holding_bars": args.max_holding_bars,
            "fit_window": args.fit_window,
            "trades": size.trades,
            "mu_bps": round(size.mu_bps, 3),
            "sigma_bps": round(size.sigma_bps, 3),
            "mu_lower_bps": round(size.mu_lower_bps, 3),
            "confidence": size.confidence,
            "full_leverage": round(size.full_leverage, 4),
            "bounded_leverage": round(size.bounded_leverage, 4),
            "capped_leverage": round(size.capped_leverage, 4),
            "max_leverage": size.max_leverage,
            "equity": size.equity,
            "notional": round(size.notional, 2),
        }
        try:
            run = triallog.append(Path(args.log), row)
        except triallog.SchemaChanged as exc:
            raise UserError(str(exc)) from exc
        log(f"  run #{run} logged to {Path(args.log)}")

    if args.json:
        print(json.dumps({
            "pair": pair, "basis": basis, "trades": size.trades,
            "mu_bps": size.mu_bps, "sigma_bps": size.sigma_bps,
            "mu_lower_bps": size.mu_lower_bps, "confidence": size.confidence,
            "full_leverage": size.full_leverage,
            "bounded_leverage": size.bounded_leverage,
            "capped_leverage": size.capped_leverage,
            "notional": size.notional, "equity": size.equity,
            "justified": size.justified, "reason": size.reason(),
        }, indent=2, default=str))

    return 0 if size.justified else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
