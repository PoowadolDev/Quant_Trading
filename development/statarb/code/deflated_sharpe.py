"""Step 4.2 — a Sharpe ratio that knows how many tries it took to find.

A Sharpe selected as the best of many attempts is biased upward, and the bias
grows with the number of attempts and with how much they varied. Searching
enough configurations produces an impressive Sharpe from pure noise; the number
itself carries no memory of the search that produced it.

Two corrections, in order:

    Probabilistic Sharpe Ratio   the probability that the true Sharpe exceeds a
                                 benchmark, given the sample length and the
                                 shape of the return distribution. Pair-trade
                                 returns are skewed and fat-tailed, so assuming
                                 normality here is the difference between a
                                 correction and a decoration.

    Deflated Sharpe Ratio        the same probability, but against a benchmark
                                 raised to the Sharpe the *best of N trials*
                                 would reach under the null. That benchmark is
                                 the expected maximum of N draws, which grows
                                 with N and with the spread between trials.

`--trials` is the whole point, and this project has logged every run since its
first day for exactly this. An honest count includes cells that were run and
discarded: `thresholds.py` evaluates five entry thresholds per call, and each is
a trial whether or not anyone looked at it.

    python deflated_sharpe.py -s NUE,STLD -a equity --broker equity
    python deflated_sharpe.py -s XLP,XLB -a index --broker etf --trials 400
    python deflated_sharpe.py -s RSG,WM -a equity --broker equity --count-trials

Exit codes: 0 the Sharpe survives deflation, 3 it does not, 2 usage error.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.stats import norm

import paths

paths.ensure_code_importable()

import costs as cost_model                                        # noqa: E402
import pair_report as pr                                          # noqa: E402
import outcomes as oc                                             # noqa: E402
import strategy as sig                                            # noqa: E402
import triallog                                                   # noqa: E402

UserError = pr.UserError
DEFAULT_LOG = paths.LOGS / "deflated_sharpe.csv"

#: Euler-Mascheroni, in the expected-maximum formula below.
EULER = 0.5772156649015329


def sharpe(returns: np.ndarray) -> float:
    """Sharpe of a return series, per observation, not annualised.

    Annualising is a separate decision and it belongs to whoever is comparing
    strategies, not here. Deflation works on the per-observation figure, and
    scaling it first would have to be undone.
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size < 2:
        return float("nan")
    sd = float(np.std(r, ddof=1))
    return float(np.mean(r)) / sd if sd > 0 else float("nan")


def moments(returns: np.ndarray) -> tuple:
    """Skew and kurtosis, the non-normality the correction needs.

    Kurtosis is returned raw rather than in excess form: 3.0 is the normal
    value. The formula below subtracts one from it, and mixing the two
    conventions is a silent way to get a plausible wrong answer.
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = r.size
    if n < 4:
        return 0.0, 3.0
    sd = float(np.std(r, ddof=0))
    if sd <= 0:
        return 0.0, 3.0
    z = (r - r.mean()) / sd
    return float(np.mean(z ** 3)), float(np.mean(z ** 4))


def probabilistic_sharpe(observed: float, benchmark: float, n: int,
                         skew: float, kurtosis: float) -> float:
    """Probability the true Sharpe exceeds `benchmark`.

    The denominator is the standard error of a Sharpe estimate when returns are
    not normal. Negative skew and fat tails both widen it, which lowers the
    probability — correctly, because a Sharpe earned with occasional large
    losses is less certain than the same number earned smoothly.
    """
    if n < 2 or not math.isfinite(observed):
        return float("nan")
    variance = 1.0 - skew * observed + (kurtosis - 1.0) / 4.0 * observed ** 2
    if variance <= 0:
        return float("nan")
    z = (observed - benchmark) * math.sqrt(n - 1) / math.sqrt(variance)
    return float(norm.cdf(z))


def expected_max_sharpe(trials: int, trial_sd: float) -> float:
    """Sharpe the best of `trials` independent attempts reaches under the null.

    The expected maximum of N standard normals, scaled by how much the trials
    actually varied. With one trial the benchmark is zero: nothing was selected,
    so there is nothing to deflate.
    """
    if trials <= 1 or trial_sd <= 0:
        return 0.0
    a = norm.ppf(1.0 - 1.0 / trials)
    b = norm.ppf(1.0 - 1.0 / (trials * math.e))
    return float(trial_sd * ((1.0 - EULER) * a + EULER * b))


#: Logs whose rows are *strategy configurations* — something with a Sharpe that
#: could have been selected. Deflation charges for the search over those.
#:
#: `screens.csv` and `cointegration.csv` are deliberately absent. They record
#: statistical tests, not backtests: screening 1,192 pairs is 1,192 chances to
#: reject a null, which is what `multiple_testing.py` corrects for, and not 1,192
#: Sharpe ratios anyone could have picked. Charging one correction for the other
#: inflates the benchmark with tests that were never candidates.
#: `deflated_sharpe` is deliberately absent from its own list. Running this
#: script is not trying another strategy configuration — it is measuring the one
#: already chosen. Counting its own rows made the benchmark climb on every run:
#: the same pair deflated against 78 trials, then 82, then 83, so asking the
#: question twice gave two answers and the later one was always harsher. A
#: measurement must not change what it measures.
STRATEGY_LOGS = ("backtests", "outcomes", "thresholds", "sizing", "trials")


def is_trial_log(path: Path) -> bool:
    """Whether a file in the log directory records runs at all.

    `screen.py --dump` writes one row per tested pair into the same directory.
    Those rows are the output of a single run, not separate runs, and counting
    them put the trial count at 1,464 when the real figure was under a hundred.
    A trial log carries a `run` or `trial` column; a dump carries neither.
    """
    stem = path.name.split(".")[0].split("-")[0]
    if stem not in STRATEGY_LOGS:
        return False
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh), [])
    except OSError:
        return False
    return bool({"run", "trial"} & set(header))


def count_trials(logs_dir: Path) -> tuple:
    """How many strategy configurations this project has logged.

    A sweep writes one row per cell, so this counts configurations tried rather
    than commands typed. Archives count: a trial does not stop having happened
    because its log was renamed after a schema change.
    """
    total, per_file = 0, {}
    for path in sorted(logs_dir.glob("*.csv")) + sorted(logs_dir.glob("*.csv.bak")):
        if not is_trial_log(path):
            continue
        try:
            with path.open(newline="", encoding="utf-8") as fh:
                rows = max(0, sum(1 for _ in csv.reader(fh)) - 1)
        except OSError:
            continue
        per_file[path.name] = rows
        total += rows
    return total, per_file


@dataclass
class Verdict:
    """One strategy's Sharpe, before and after it is charged for the search."""

    pair: str
    observations: int
    observed: float
    skew: float
    kurtosis: float
    trials: int
    trial_sd: float
    benchmark: float
    psr: float
    dsr: float
    level: float

    @property
    def survives(self) -> bool:
        return math.isfinite(self.dsr) and self.dsr >= 1.0 - self.level

    def reason(self) -> str:
        if not math.isfinite(self.observed):
            return "there are too few returns to form a Sharpe ratio"
        if self.observed <= 0:
            return (f"the Sharpe is {self.observed:+.3f} before any correction, so "
                    "there is nothing for the search to have inflated")
        if self.benchmark >= self.observed:
            return (f"the best of {self.trials:,} trials would reach "
                    f"{self.benchmark:.3f} on noise alone, and this reached "
                    f"{self.observed:.3f}")
        return (f"{self.dsr:.1%} probability the true Sharpe beats what "
                f"{self.trials:,} trials would produce by chance")


def assess(returns: np.ndarray, *, pair: str, trials: int, trial_sd: float,
           level: float) -> Verdict:
    """Everything above applied to one return series."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    sr = sharpe(r)
    sk, ku = moments(r)
    benchmark = expected_max_sharpe(trials, trial_sd)
    return Verdict(
        pair=pair, observations=int(r.size), observed=sr, skew=sk, kurtosis=ku,
        trials=trials, trial_sd=trial_sd, benchmark=benchmark,
        psr=probabilistic_sharpe(sr, 0.0, r.size, sk, ku),
        dsr=probabilistic_sharpe(sr, benchmark, r.size, sk, ku),
        level=level)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="deflated_sharpe",
                                description=__doc__.splitlines()[0],
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
    struct.add_argument("--fit-window", type=int, default=250)
    struct.add_argument("--rehedge-every", type=int, default=5)
    struct.add_argument("--per", default="trade", choices=("trade", "bar"),
                        help="Sharpe of per-trade returns or of the bar-by-bar "
                             "equity change. Trades are fewer and fatter-tailed")

    search = p.add_argument_group("searched - every value is a trial")
    search.add_argument("--entry-z", type=float, default=2.0)
    search.add_argument("--exit-z", type=float, default=0.5)
    search.add_argument("--stop-z", type=float, default=4.0)
    search.add_argument("--max-holding-bars", type=int, default=20)
    search.add_argument("--warmup", type=int, default=260)

    deflate = p.add_argument_group("deflation")
    deflate.add_argument("--trials", type=int, default=None,
                         help="configurations tried to find this one; counted "
                              "from the logs when not given")
    deflate.add_argument("--count-trials", action="store_true",
                         help="print what each log contributed to the count")
    deflate.add_argument("--trial-sd", type=float, default=None,
                         help="spread of Sharpe across those trials; measured "
                              "from an entry-threshold sweep when not given")
    deflate.add_argument("--sweep", default="1.0,1.5,2.0,2.5,3.0",
                         help="thresholds swept to measure the trial spread")
    deflate.add_argument("--level", type=float, default=0.05,
                         help="a deflated Sharpe above 1 - level survives")

    given = p.add_argument_group("given by reality")
    given.add_argument("--broker", required=True)
    given.add_argument("--costs-dir", default=str(cost_model.DEFAULT_COSTS))
    given.add_argument("--bars-per-night", type=float, default=None)
    given.add_argument("--lag", type=int, default=1)

    out = p.add_argument_group("output")
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--log", default=str(DEFAULT_LOG))
    out.add_argument("--no-log", action="store_true")
    out.add_argument("--json", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    return p


def returns_for(px, profile, params, args) -> np.ndarray:
    import backtest as bt

    result = bt.run_backtest(px, profile, params, warmup=args.warmup,
                             bars_per_night=args.bars_per_night, lag=args.lag)
    if args.per == "trade":
        return np.array([t.net_bps for t in result.trades], dtype=float)
    return np.diff(np.concatenate([[0.0], result.equity_net]))


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    warnings.filterwarnings("ignore")
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))

    if not 0 < args.level < 1:
        raise UserError(f"--level {args.level:g} is a probability between 0 and 1")
    if args.trials is not None and args.trials < 1:
        raise UserError(f"--trials {args.trials} is a count of configurations tried")
    if args.trial_sd is not None and args.trial_sd < 0:
        # This one fails in the dangerous direction. `expected_max_sharpe`
        # returns zero for a non-positive spread, so a negative value deflates
        # against a benchmark of zero — no deflation at all, reported as though
        # the Sharpe had survived one.
        raise UserError(f"--trial-sd {args.trial_sd:g} is a standard deviation. "
                        "A negative value deflates against a benchmark of zero, "
                        "which is the same as not deflating at all.")
    sweep_levels = oc.parse_levels(args.sweep, "--sweep")

    profile = cost_model.load_profile(Path(args.costs_dir) / f"{args.broker}.json")
    if not profile:
        raise UserError(f"no cost profile named {args.broker!r}")

    px = pr.load_prices(args)
    if args.bars_per_night is None:
        first = args.asset_class.split(",")[0].strip().lower()
        args.bars_per_night = cost_model.nights_per_bar(first, args.timeframe)

    def params_at(entry_z: float) -> sig.SignalParams:
        return sig.SignalParams(
            entry_z=entry_z, exit_z=args.exit_z, stop_z=args.stop_z,
            max_holding_bars=args.max_holding_bars,
            hedge_source=args.hedge_source, fit_window=args.fit_window,
            rehedge_every=args.rehedge_every, use_log=args.price == "log")

    try:
        base = params_at(args.entry_z)
    except ValueError as exc:
        raise UserError(str(exc)) from exc

    pair = " ~ ".join(px.columns)
    returns = returns_for(px, profile, base, args)
    if returns.size < 2:
        raise UserError(f"{pair} produced {returns.size} return(s); a Sharpe needs "
                        "at least two")

    # --- how many trials, and how much did they vary
    trials, per_file = args.trials, {}
    if trials is None:
        trials, per_file = count_trials(paths.LOGS)
        trials = max(trials, 1)

    trial_sd = args.trial_sd
    sweep_sharpes = []
    if trial_sd is None:
        for value in sweep_levels:
            try:
                p_i = params_at(value)
            except ValueError:
                continue
            r_i = returns_for(px, profile, p_i, args)
            s_i = sharpe(r_i)
            if math.isfinite(s_i):
                sweep_sharpes.append(s_i)
        trial_sd = (float(np.std(sweep_sharpes, ddof=1))
                    if len(sweep_sharpes) > 1 else 0.0)

    verdict = assess(returns, pair=pair, trials=trials, trial_sd=trial_sd,
                     level=args.level)

    log(f"{pair}  {args.timeframe}  {len(px):,} bars  per {args.per}  "
        f"broker {args.broker}")
    log(f"  {verdict.observations} return(s)   Sharpe {verdict.observed:+.4f}   "
        f"skew {verdict.skew:+.2f}   kurtosis {verdict.kurtosis:.2f}")
    log("")
    log(f"  trials counted        {trials:8,d}   configurations logged by this project")
    if args.count_trials and per_file:
        for name, rows in sorted(per_file.items(), key=lambda kv: -kv[1]):
            if rows:
                log(f"     {name:<34s} {rows:5,d}")
    log(f"  spread across trials  {trial_sd:8.4f}   "
        + (f"from {len(sweep_sharpes)} swept threshold(s): "
           + ", ".join(f"{v:+.3f}" for v in sweep_sharpes)
           if sweep_sharpes else "given"))
    log(f"  benchmark Sharpe      {verdict.benchmark:8.4f}   the best of "
        f"{trials:,} trials under the null")
    log("")
    log(f"  probabilistic Sharpe  {verdict.psr:8.1%}   probability the true "
        "Sharpe beats zero")
    log(f"  deflated Sharpe       {verdict.dsr:8.1%}   probability it beats the "
        "benchmark above")
    log("")
    if verdict.survives:
        log(f"  SURVIVES DEFLATION — {verdict.reason()}")
    else:
        log(f"  DOES NOT SURVIVE — {verdict.reason()}")
        if math.isfinite(verdict.psr) and verdict.psr >= 1 - args.level:
            log("  Note the gap: the Sharpe is convincing on its own and stops "
                "being so once the search behind it is charged for.")

    if not args.no_log:
        row = {
            "run": 0, "run_utc": triallog.stamp(), "pair": pair,
            "timeframe": args.timeframe, "broker": args.broker,
            "start": args.start or "", "end": args.end or "", "per": args.per,
            "entry_z": args.entry_z, "exit_z": args.exit_z,
            "observations": verdict.observations,
            "sharpe": round(verdict.observed, 6),
            "skew": round(verdict.skew, 4),
            "kurtosis": round(verdict.kurtosis, 4),
            "trials": trials,
            "trial_sd": round(trial_sd, 6),
            "benchmark": round(verdict.benchmark, 6),
            "psr": round(verdict.psr, 6) if math.isfinite(verdict.psr) else None,
            "dsr": round(verdict.dsr, 6) if math.isfinite(verdict.dsr) else None,
            "level": args.level,
            "verdict": "survives" if verdict.survives else "deflated away",
        }
        try:
            run = triallog.append(Path(args.log), row)
        except triallog.SchemaChanged as exc:
            raise UserError(str(exc)) from exc
        log(f"  run #{run} logged to {Path(args.log)}")

    if args.json:
        print(json.dumps({
            "pair": pair, "observations": verdict.observations,
            "sharpe": verdict.observed, "skew": verdict.skew,
            "kurtosis": verdict.kurtosis, "trials": trials,
            "trial_sd": trial_sd, "benchmark": verdict.benchmark,
            "psr": verdict.psr, "dsr": verdict.dsr,
            "survives": verdict.survives, "reason": verdict.reason(),
        }, indent=2, default=str))

    return 0 if verdict.survives else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
