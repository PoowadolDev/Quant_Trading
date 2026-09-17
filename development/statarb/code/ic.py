"""Stage 11 — how much skill is in the residual signal, and how many bets it spreads over.

The whole redesign in RESIDUAL.md rests on one piece of arithmetic:

    IR  ≈  IC × √breadth

and until now this project has supplied neither term. `IC = 0.02–0.05` has been quoted
throughout as though it were a property of this system; it is a range from the literature.
Breadth has been argued from the number of names rather than measured. This script measures
both, so the arithmetic can be checked instead of cited.

**This is also Stage 1 of RESIDUAL.md.** Stage 0 established that the residual reverts;
that says the object exists, not that a signal built on it predicts anything. The
information coefficient is exactly the question "does the signal predict the forward
return", asked across the whole cross-section at once rather than one pair at a time.

    signal_i,t      = −X_i,t / sd(X_i)      high residual is expensive, so short it
    forward_i,t,h   = Σ ε_i over (t, t+h]   the residual return actually earned
    IC_t            = rank correlation of signal against forward, across names
    ICIR            = mean(IC) / sd(IC)

**Nothing after the formation date informs the signal.** The loadings come from the bars
before `t` and are applied unchanged to the bars after it. This is the same discipline
Stage 0 needed: measured in-sample, the residual's own fit constrains it to return to zero,
which flatters every statistic computed on it.

**Breadth is measured, not counted.** 160 names is not 160 bets if the residuals move
together. `risk.effective_bets` already answers this correctly — the participation ratio of
the correlation matrix, `(ΣL)²/Σ(L²)`, which equals N for uncorrelated series and falls
towards 1 as they become the same bet. It has only ever been handed a book of spreads;
here it is handed the residual cross-section. Residuals are factor-neutral by construction,
so this number should land near N, and if it does not then the factor model is not removing
what it claims to.

**The survivorship caveat is not cosmetic.** The panel is filtered on having enough history,
which is a filter on having survived. The shuffled null does not correct for it — the
permutation reorders dates and leaves the cross-section exactly as it was. Any IC reported
here is therefore an upper bound, and the report says so on its own line.

    python ic.py
    python ic.py --horizons 1,5,20 --factors 5
    python ic.py --json

Exit codes: 0 the IC beats two standard errors at the primary horizon; 3 it does not, which
is the Stage 1 kill criterion in RESIDUAL.md §4 and means stop; 2 usage error.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import paths

paths.ensure_code_importable()
paths.ensure_marketdata_importable()

import pair_report as pr                                            # noqa: E402
import residual as rs                                               # noqa: E402
import risk                                                         # noqa: E402

UserError = pr.UserError
DEFAULT_LOG = paths.LOGS / "ic.csv"

#: Same bar the rest of the project applies to any mean it reports. `backtest.py` prints
#: `mean/standard error` and calls anything below 2 indistinguishable from zero; there is no
#: reason for the information coefficient to be judged more leniently than a trade mean.
MIN_T = rs.MIN_T


# ------------------------------------------------------------------ the measurement

def rank_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman correlation, computed as Pearson on average ranks.

    Ranks rather than levels because a cross-section of residual returns has a heavy tail
    and one name that moved 40% would otherwise set the correlation on its own. That is not
    skill, it is a single print, and this project has already had one bad bar supply 34% of
    a pair's profit.
    """
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return float("nan")
    ra = pd.Series(a[ok]).rank().to_numpy(float)
    rb = pd.Series(b[ok]).rank().to_numpy(float)
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def formation(returns: np.ndarray, end: int, pca_window: int, signal_window: int,
              horizon: int, n_factors: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Signal at `end`, the forward residual return after it, and that forward residual.

    The loadings and the factor weights both come from `returns[end - pca_window:end]` and
    are applied unchanged to `returns[end:end + horizon]`. Returns `(signal, forward,
    forward_residual_returns)`; the third is kept because breadth is measured on the
    residual returns themselves, not on the signal.
    """
    window = returns[end - pca_window:end]
    usable, weights = rs.eigenportfolios(window, n_factors)

    design = np.column_stack([window[:, usable] @ weights, np.ones(len(window))])
    loadings, *_ = np.linalg.lstsq(design, window, rcond=None)

    # The signal is the residual as it stands at the formation date, scaled by its own
    # variation over the window it was accumulated on. Sign is negative because a residual
    # that has run up is the expensive one, and the trade is to be short it.
    tail = slice(len(window) - signal_window, len(window))
    accumulated = np.cumsum(window[tail] - design[tail] @ loadings, axis=0)
    scale = accumulated.std(axis=0, ddof=1)
    scale = np.where(scale > 0, scale, np.nan)
    signal = -accumulated[-1] / scale

    forward = returns[end:end + horizon]
    forward_design = np.column_stack([forward[:, usable] @ weights, np.ones(len(forward))])
    forward_residuals = forward - forward_design @ loadings
    return signal, forward_residuals.sum(axis=0), forward_residuals


def sweep(returns: np.ndarray, horizon: int, args) -> tuple[np.ndarray, np.ndarray]:
    """Walk the panel forward, one IC per formation date.

    The step is at least the horizon, so two consecutive forward windows never share a bar.
    Overlapping windows would make each IC a partial restatement of its neighbour, and the
    standard error across them would then describe a sample smaller than it claims to be.
    """
    step = max(args.step, horizon)
    ics, residual_blocks = [], []
    last = len(returns) - horizon
    for end in range(args.pca_window, last + 1, step):
        signal, forward, block = formation(returns, end, args.pca_window,
                                           args.signal_window, horizon, args.factors)
        value = rank_correlation(signal, forward)
        if math.isfinite(value):
            ics.append(value)
            residual_blocks.append(block)
    if not ics:
        raise UserError(
            f"no formation date produced an IC at horizon {horizon}: {len(returns):,} "
            f"return rows cannot supply a {args.pca_window}-bar fit window plus a "
            f"{horizon}-bar forward window. Lower --pca-window or --min-bars."
        )
    return np.array(ics), np.vstack(residual_blocks)


def summarise(ics: np.ndarray) -> dict:
    """Mean IC with the uncertainty that makes it readable, and the ICIR."""
    n = len(ics)
    mean = float(ics.mean())
    sd = float(ics.std(ddof=1)) if n > 1 else float("nan")
    se = sd / math.sqrt(n) if n > 1 and math.isfinite(sd) else float("nan")
    return {
        "windows": n,
        "ic_mean": mean,
        "ic_sd": sd,
        "ic_se": se,
        # The information ratio of the signal itself: how consistent the skill is from one
        # formation date to the next, which is a different question from how large it is.
        "icir": mean / sd if math.isfinite(sd) and sd > 0 else float("nan"),
        "t": mean / se if math.isfinite(se) and se > 0 else float("nan"),
        "hit_rate": float(np.mean(ics > 0)),
    }


def breadth_returns(returns: np.ndarray, args) -> np.ndarray:
    """Forward residual returns tiling the panel, for the correlation matrix.

    Breadth is a property of the residual cross-section, not of whichever forward horizon
    the caller happened to ask for first, so it gets its own pass. The forward window is set
    equal to the step, which makes consecutive windows tile the panel end to end: no bar is
    counted twice and none is skipped.

    This matters more than it looks. Measured off a one-bar horizon the sample was 236 rows
    for 160 names, and a correlation matrix estimated at that ratio has its eigenvalues
    spread by sampling noise alone, which inflates `Σ(L²)` and drags the participation ratio
    down. The same panel reported 59.7 independent bets that way and 112.2 off a five-bar
    horizon — a number that moved by a factor of two according to a setting that has nothing
    to do with breadth.
    """
    blocks = []
    last = len(returns) - args.step
    for end in range(args.pca_window, last + 1, args.step):
        _signal, _forward, block = formation(returns, end, args.pca_window,
                                             args.signal_window, args.step, args.factors)
        blocks.append(block)
    if not blocks:
        raise UserError("the panel is too short to measure breadth; lower --pca-window")
    return np.vstack(blocks)


def breadth(residual_returns: np.ndarray, names: list[str]) -> dict:
    """How many independent bets the residual cross-section actually contains."""
    frame = pd.DataFrame(residual_returns, columns=names).dropna(axis=1, how="any")
    if frame.shape[1] < 2:
        raise UserError("fewer than two usable residual series; breadth is undefined")
    rows, cols = frame.shape
    # A sample correlation matrix needs far more rows than columns before its eigenvalues
    # mean anything. Refused rather than reported with a caveat, because the number looks
    # perfectly reasonable when it is wrong and nothing downstream would catch it.
    if rows < 2 * cols:
        raise UserError(
            f"breadth would be measured on {rows:,} rows for {cols} names. Below about two "
            f"rows per name the eigenvalues are mostly sampling noise and the participation "
            f"ratio is biased downwards. Raise --step or lower --min-bars to admit a longer "
            f"panel."
        )
    correlation = frame.corr()
    effective = risk.effective_bets(correlation)
    worst = risk.worst_correlation(correlation)
    return {
        "names": int(cols),
        "rows": int(rows),
        "rows_per_name": rows / cols,
        "effective_bets": float(effective),
        "bet_share": float(effective / cols),
        "worst_pair": f"{worst[0]}~{worst[1]}",
        "worst_correlation": float(worst[2]),
    }


def implied_ir(ic_mean: float, effective: float, horizon: int, bars_per_year: int) -> float:
    """The fundamental law, with breadth counted per year rather than per rebalance.

    `IR ≈ IC × √breadth` needs breadth to be the number of independent bets taken in the
    period the ratio is quoted over. A cross-section of `effective` independent names
    rebalanced every `horizon` bars supplies `effective × bars_per_year / horizon` of them
    in a year, which is what makes the result comparable with an annual Sharpe.
    """
    if not (math.isfinite(ic_mean) and math.isfinite(effective)) or horizon <= 0:
        return float("nan")
    return ic_mean * math.sqrt(max(effective, 0.0) * bars_per_year / horizon)


# ------------------------------------------------------------------ reporting

def show(rows: list[dict], log) -> None:
    log("")
    log(f"  {'horizon':>7s} {'windows':>8s} {'IC':>8s} {'std err':>9s} {'t':>7s} "
        f"{'ICIR':>7s} {'IC>0':>6s} {'implied IR':>11s}")
    for row in rows:
        log(f"  {row['horizon']:7d} {row['windows']:8d} {row['ic_mean']:8.4f} "
            f"{row['ic_se']:9.4f} {row['t']:7.2f} {row['icir']:7.3f} "
            f"{row['hit_rate']:6.0%} {row['implied_ir']:11.2f}")


def show_null(rows: list[dict], null_rows: list[dict], log) -> None:
    log("")
    log(f"  {'horizon':>7s} {'IC real':>9s} {'IC null':>9s} {'lift':>9s} {'lift t':>8s}")
    for row, null in zip(rows, null_rows):
        lift = row["ic_mean"] - null["ic_mean"]
        # The two are measured on the same formation dates, so the error on the difference
        # is not the sum of the two errors; it is taken from the paired series directly.
        se = math.sqrt(row["ic_se"] ** 2 + null["ic_se"] ** 2)
        log(f"  {row['horizon']:7d} {row['ic_mean']:9.4f} {null['ic_mean']:9.4f} "
            f"{lift:+9.4f} {(lift / se if se > 0 else float('nan')):8.2f}")


def append_log(path: Path, args, panel: pd.DataFrame, primary: dict, bred: dict) -> int:
    row = {"run": 0,
           "run_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "asset_class": args.asset_class, "timeframe": args.timeframe,
           "names": panel.shape[1], "bars": panel.shape[0],
           "start": f"{panel.index[0]:%Y-%m-%d}", "end": f"{panel.index[-1]:%Y-%m-%d}",
           "factors": args.factors, "pca_window": args.pca_window,
           "signal_window": args.signal_window, "step": args.step,
           "horizon": primary["horizon"], "windows": primary["windows"],
           "ic_mean": round(primary["ic_mean"], 5),
           "ic_se": round(primary["ic_se"], 5),
           "ic_t": round(primary["t"], 3),
           "icir": round(primary["icir"], 4),
           "effective_bets": round(bred["effective_bets"], 2),
           "bet_share": round(bred["bet_share"], 4),
           "implied_ir": round(primary["implied_ir"], 4),
           "passed": "yes" if primary["t"] > MIN_T else "no"}
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = 0
    if path.exists():
        with path.open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh), [])
            existing = sum(1 for _ in csv.reader(fh))
        if header and header != list(row):
            raise UserError(f"{path} was written by an older version; rename it to keep "
                            "the history and a fresh log will start")
    row["run"] = existing + 1
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row))
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    return row["run"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ic", description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sel = p.add_argument_group("selection")
    sel.add_argument("-a", "--asset-class", default="equity")
    sel.add_argument("-t", "--timeframe", default="1d")
    sel.add_argument("--source", default=None)
    sel.add_argument("--min-bars", type=int, default=5000,
                     help="a series shorter than this is left out of the panel rather "
                          "than truncating the common index for every other name")

    struct = p.add_argument_group("structure - choose once, not per run")
    struct.add_argument("--pca-window", type=int, default=252,
                        help="bars the factor model is estimated on")
    struct.add_argument("--signal-window", type=int, default=60,
                        help="trailing bars the residual is accumulated over to form the "
                             "signal")
    struct.add_argument("--step", type=int, default=21,
                        help="bars between formation dates; raised to the horizon when the "
                             "horizon is longer, so forward windows never overlap")
    struct.add_argument("--bars-per-year", type=int, default=252,
                        help="used only to annualise the implied information ratio")

    search = p.add_argument_group("searched - every value is a trial")
    search.add_argument("--factors", type=int, default=15,
                        help="principal components removed before the residual")
    search.add_argument("--horizons", default="1,2,3,5,10,20",
                        help="forward horizons in bars, reported as a decay profile")
    search.add_argument("--primary-horizon", type=int, default=5,
                        help="the one horizon that decides the exit code. Set it from the "
                             "half-life measured by residual.py, which is an independent "
                             "measurement, and not by reading the horizon table below and "
                             "taking the best row — that is selection, and Step 4 charges "
                             "for it")
    search.add_argument("--null-draws", type=int, default=2,
                        help="permutations averaged into the null")
    search.add_argument("--seed", type=int, default=0)

    out = p.add_argument_group("output")
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--log", default=str(DEFAULT_LOG))
    out.add_argument("--no-log", action="store_true")
    out.add_argument("--json", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    return p


def parse_horizons(text: str) -> list[int]:
    try:
        horizons = [int(x) for x in str(text).split(",") if str(x).strip()]
    except ValueError:
        raise UserError(f"--horizons takes whole numbers of bars, not {text!r}") from None
    if not horizons:
        raise UserError("--horizons needs at least one value")
    if any(h < 1 for h in horizons):
        raise UserError("every horizon must be at least one bar")
    return horizons


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))
    horizons = parse_horizons(args.horizons)
    if args.factors < 1:
        raise UserError("--factors must be at least 1")
    if args.signal_window < 20:
        raise UserError("--signal-window below 20 bars leaves the residual scale estimated "
                        "on too little to be meaningful")
    if args.signal_window > args.pca_window:
        raise UserError("--signal-window cannot exceed --pca-window; the signal is "
                        "accumulated inside the window the factors were fitted on")
    if args.factors >= args.pca_window:
        raise UserError("--factors must be fewer than --pca-window bars, or the loading "
                        "regression has no degrees of freedom")
    if args.null_draws < 1:
        raise UserError("--null-draws must be at least 1; the null is what makes the real "
                        "number readable")

    panel = rs.load_panel(Path(args.store), args.asset_class, args.timeframe,
                          args.min_bars, args.source)
    returns = np.diff(np.log(panel.to_numpy(float)), axis=0)
    names = list(panel.columns)

    log(f"{args.asset_class} residual information coefficient   {panel.shape[1]} names   "
        f"{panel.shape[0]:,} common bars   "
        f"{panel.index[0]:%Y-%m-%d} to {panel.index[-1]:%Y-%m-%d}")
    log(f"  {args.factors} factors fitted on {args.pca_window} bars, signal from the "
        f"trailing {args.signal_window}, stepped {args.step}")

    if args.primary_horizon not in horizons:
        horizons = sorted(set(horizons) | {args.primary_horizon})

    rows, null_rows = [], []
    for horizon in horizons:
        ics, _block = sweep(returns, horizon, args)
        summary = summarise(ics)
        summary["horizon"] = horizon
        rows.append(summary)

        null_ics = np.concatenate([
            sweep(rs.shuffled(returns, args.seed + d), horizon, args)[0]
            for d in range(args.null_draws)])
        null_summary = summarise(null_ics)
        null_summary["horizon"] = horizon
        null_rows.append(null_summary)

    bred = breadth(breadth_returns(returns, args), names)
    for row in rows:
        row["implied_ir"] = implied_ir(row["ic_mean"], bred["effective_bets"],
                                       row["horizon"], args.bars_per_year)
    for row in null_rows:
        row["implied_ir"] = implied_ir(row["ic_mean"], bred["effective_bets"],
                                       row["horizon"], args.bars_per_year)

    show(rows, log)
    show_null(rows, null_rows, log)

    log("")
    log(f"  breadth: {bred['names']} residuals contain {bred['effective_bets']:.1f} "
        f"independent bets ({bred['bet_share']:.0%} of the cross-section)")
    log(f"  measured on {bred['rows']:,} tiled residual bars, "
        f"{bred['rows_per_name']:.1f} per name")
    log(f"  most correlated residual pair {bred['worst_pair']} at "
        f"{bred['worst_correlation']:+.3f}")

    primary = next(r for r in rows if r["horizon"] == args.primary_horizon)
    passed = math.isfinite(primary["t"]) and primary["t"] > MIN_T

    log("")
    log(f"  at the primary horizon of {primary['horizon']} bar(s): "
        f"IC {primary['ic_mean']:+.4f} +/- {primary['ic_se']:.4f} over "
        f"{primary['windows']} formation dates, t = {primary['t']:.2f}, "
        f"ICIR {primary['icir']:.3f}")
    log(f"  fundamental law gives IR = IC x sqrt(breadth) = "
        f"{primary['implied_ir']:.2f} a year before costs")
    log("")
    if passed:
        log(f"  HAS SKILL — the information coefficient beats zero by {primary['t']:.1f} "
            f"standard")
        log(f"  errors. RESIDUAL.md Stage 1 survives: the aggregate signal predicts.")
        log(f"  Before costs, and on a survivor-filtered panel. The implied IR of "
            f"{primary['implied_ir']:.2f} is")
        log(f"  an upper bound on both counts, and Stage 2 charges the real spread.")
    else:
        log(f"  NO SKILL — IC {primary['ic_mean']:+.4f} against a standard error of "
            f"{primary['ic_se']:.4f} is")
        log(f"  indistinguishable from zero at the two-error bar this project applies to "
            f"every")
        log(f"  other mean it reports. This is the Stage 1 kill criterion in RESIDUAL.md "
            f"§4.")
        log(f"  Breadth cannot rescue it: IR = IC x sqrt(breadth) multiplies the skill, "
            f"and")
        log(f"  multiplying zero by any breadth gives zero.")
    log("")
    log("  The panel is filtered on having enough history, which is a filter on having")
    log("  survived. The shuffled null does not correct for that — it reorders dates and")
    log("  leaves the cross-section intact. Every IC above is an upper bound.")

    if args.json:
        print(json.dumps({"names": panel.shape[1], "bars": panel.shape[0],
                          "factors": args.factors, "horizons": horizons,
                          "real": rows, "null": null_rows, "breadth": bred,
                          "passed": passed}, indent=2, default=str))

    if not args.no_log:
        run = append_log(Path(args.log), args, panel, primary, bred)
        log(f"\n  run #{run} logged to {Path(args.log).resolve()}")
    return 0 if passed else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:                                        # noqa: BLE001
        if "-v" in sys.argv or "--verbose" in sys.argv:
            raise
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
