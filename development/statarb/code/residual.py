"""Stage 0 of RESIDUAL.md — does the equity residual revert at all?

This is a measurement, not a strategy. It answers one question, cheaply, before
any portfolio machinery is built: after a factor model absorbs the common
movement in a universe of returns, does what is left mean-revert more often than
chance?

The construction follows Avellaneda & Lee (2010) and §2.1 of the plan:

    r_t   = Λ F_t + ε_t        factor model on *returns*
    X_t   = Σ ε                the residual accumulated over the test window
    dX_t  = θ(μ − X_t) dt + σ dB_t

`X_t` is the tradable object. The test is whether `X_t` rejects a unit root more
often than the same pipeline achieves on data with no time structure.

**The residual is measured out of sample, and that is not a detail.** Loadings
come from the trailing `--pca-window` bars; the residual is then accumulated over
the `--ou-window` bars that come *after* them. Fitting and testing on the same
bars — which is how the paper presents it — breaks the measurement twice over:

* Cumulated OLS residuals must return to zero at the end of the window they were
  fitted on, so `X_t` becomes a Brownian bridge, and a bridge looks
  mean-reverting by construction. Measured here, that lifts the shuffled null's
  rejection rate from the nominal 5% to 8.2%.
* Sixteen fitted parameters on a sixty-bar window absorb the very deviation the
  residual is supposed to contain. Measured here, the in-sample lift over null
  is +0.3% at t = 0.84; the same data measured forward gives +2.1% at t = 5.27.

So the in-sample version simultaneously inflates the null and erases the signal.
Forward residuals also happen to be what a live implementation would hold, so
the honest measurement and the tradable one are the same object.

**The null is load-bearing.** It is computed on every run and cannot be switched
off. The shuffle permutes the date index **jointly across all names**, leaving
the contemporaneous covariance matrix untouched — so PCA still finds the same
factors and a residual is still a residual — while destroying serial dependence.
Shuffling each name independently would also destroy the cross-sectional
structure, leaving PCA to fit noise, which tests a different and easier question.

**The unit of evidence is the window, not the name.** The 160 residuals inside
one window share a single factor estimate and are cross-sectionally correlated,
so counting them as 160 independent tests understates the error by roughly the
square root of the universe size. The lift is therefore paired per window and its
standard error taken across windows.

    python residual.py
    python residual.py --factors 5 --step 21
    python residual.py --min-bars 3000 --json

Exit codes: 0 the residual reverts by more than two standard errors; 3 it does
not, which is the kill criterion in §4 of the plan and means stop; 2 usage error.
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
from marketdata import Instrument, ParquetStore, aligned_panel      # noqa: E402

UserError = pr.UserError
DEFAULT_LOG = paths.LOGS / "residual.csv"

#: A lift smaller than this many standard errors is not evidence. The project
#: already prints `mean/standard error` on every backtest and treats anything
#: below 2 as indistinguishable from zero; the same bar applies here rather than
#: a second, laxer one invented for this script.
MIN_T = 2.0

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from statsmodels.tsa.stattools import adfuller                  # noqa: E402


# ------------------------------------------------------------------ loading

def load_panel(store_path: Path, asset_class: str, timeframe: str,
               min_bars: int, source: str | None) -> pd.DataFrame:
    """Every stored series of one class with enough history, on common dates.

    `min_bars` is applied to each series *before* the join, not after. A name
    with a short history would otherwise truncate the common index for everyone
    else — this project holds two such names right now (`EQR` at 14 bars and
    `AVB`, both taken over and no longer listed), and either one alone would cut
    a twenty-year panel to a fortnight.
    """
    root = Path(store_path) / asset_class
    if not root.is_dir():
        raise UserError(f"no {asset_class} series in the store at {store_path}")

    frames, skipped = {}, 0
    store = ParquetStore(Path(store_path))
    for path in sorted(root.glob(f"*/{timeframe}/*.parquet")):
        symbol, src = path.parts[-3], path.stem
        if source and src != source:
            continue
        frame = store.read(Instrument(symbol, asset_class=asset_class, source=src,
                                      timeframe=timeframe))
        if frame is None or len(frame) < min_bars:
            skipped += 1
            continue
        frames[symbol] = frame

    if len(frames) < 3:
        raise UserError(
            f"only {len(frames)} {asset_class} series have {min_bars:,}+ bars at "
            f"{timeframe}; a factor model needs a universe, not a handful. "
            f"Lower --min-bars or download more names."
        )

    panel = aligned_panel(frames, field="close").dropna(how="any")
    panel.attrs["skipped"] = skipped
    return panel


# ------------------------------------------------------------------ the model

def eigenportfolios(window: np.ndarray, n_factors: int) -> tuple[np.ndarray, np.ndarray]:
    """Factor weights from the correlation matrix of one window of returns.

    Returns the mask of usable names and the weight matrix that turns their
    returns into factor returns.

    The decomposition is of the **correlation** matrix, not the covariance
    matrix. Without that standardisation the highest-variance names dominate the
    factors purely by being volatile, and their residuals come back smallest — an
    artefact that ranks names by volatility while appearing to rank them by
    signal. Each eigenvector entry is then divided by the name's own volatility,
    so a factor is a portfolio of risk-equalised positions rather than of dollar
    amounts.
    """
    sd = window.std(axis=0, ddof=1)
    # A name that never moved in the window carries no information and would
    # divide by zero. Held out of the decomposition, not quietly set to zero.
    sd = np.where(sd > 0, sd, np.nan)
    standardised = (window - window.mean(axis=0)) / sd

    usable = np.isfinite(standardised).all(axis=0)
    if usable.sum() <= n_factors:
        raise UserError(f"only {int(usable.sum())} usable names in a window, which "
                        f"cannot support {n_factors} factors")

    corr = np.corrcoef(standardised[:, usable], rowvar=False)
    top = np.linalg.eigh(corr)[1][:, ::-1][:, :n_factors]   # eigh sorts ascending
    return usable, top / sd[usable][:, None]


def forward_residuals(returns: np.ndarray, end: int, pca_window: int,
                      ou_window: int, n_factors: int) -> np.ndarray:
    """Residual returns over the bars *after* the window the model was fitted on.

    Both the factor weights and the loadings come from `returns[end -
    pca_window:end]`; they are then applied unchanged to `returns[end:end +
    ou_window]`. Nothing from the test window informs the model, so the residual
    carries no constraint to return to zero and the ADF test faces its nominal
    null.
    """
    window = returns[end - pca_window:end]
    usable, weights = eigenportfolios(window, n_factors)

    design = np.column_stack([window[:, usable] @ weights, np.ones(len(window))])
    loadings, *_ = np.linalg.lstsq(design, window, rcond=None)

    forward = returns[end:end + ou_window]
    forward_design = np.column_stack([forward[:, usable] @ weights,
                                      np.ones(len(forward))])
    return forward - forward_design @ loadings


def score_window(residual_returns: np.ndarray, adf_lags: int,
                 level: float) -> list[dict]:
    """OU fit and unit-root test on each name's accumulated residual."""
    accumulated = np.cumsum(residual_returns, axis=0)
    out = []
    for i in range(accumulated.shape[1]):
        series = accumulated[:, i]
        if not np.isfinite(series).all():
            continue
        try:
            theta, _mu, _sigma, regime = pr._fit_ou(series)
        except UserError:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            stat, pvalue, *_ = adfuller(series, maxlag=adf_lags, autolag=None,
                                        regression="c")
        out.append({
            "regime": regime,
            "half_life": math.log(2) / theta if theta > 0 else float("nan"),
            "adf_stat": float(stat),
            "adf_p": float(pvalue),
            "rejects": bool(pvalue < level),
        })
    return out


def sweep(returns: np.ndarray, args) -> list[list[dict]]:
    """Walk the panel forward, scoring every name in each window.

    One inner list per window, because the window is the unit the verdict is
    computed on.
    """
    windows = []
    last = len(returns) - args.ou_window
    for end in range(args.pca_window, last + 1, args.step):
        residuals = forward_residuals(returns, end, args.pca_window,
                                      args.ou_window, args.factors)
        scored = score_window(residuals, args.adf_lags, args.level)
        if scored:
            windows.append(scored)
    if not windows:
        raise UserError(
            f"no window fitted: {len(returns):,} return rows cannot supply a "
            f"{args.pca_window}-bar fit window plus a {args.ou_window}-bar "
            f"forward window. Lower --pca-window or --min-bars."
        )
    return windows


def shuffled(returns: np.ndarray, seed: int) -> np.ndarray:
    """The same rows in a different order — one permutation for all names.

    Permuting the dates jointly keeps every contemporaneous correlation exactly
    as it was, so the factor model has the same thing to find, and removes only
    the ordering, which is the sole thing the OU fit and the ADF test read.
    """
    rng = np.random.default_rng(seed)
    return returns[rng.permutation(len(returns))]


# ------------------------------------------------------------------ reporting

def window_shares(windows: list[list[dict]]) -> np.ndarray:
    """Rejection share within each window."""
    return np.array([np.mean([r["rejects"] for r in w]) for w in windows])


def summarise(windows: list[list[dict]]) -> dict:
    rows = [r for w in windows for r in w]
    p = np.array([r["adf_p"] for r in rows])
    half = np.array([r["half_life"] for r in rows])
    finite = half[np.isfinite(half)]
    regimes = [r["regime"] for r in rows]
    return {
        "windows": len(windows),
        "observations": len(rows),
        "reject_share": float(np.mean(p < 0.05)),
        "median_p": float(np.median(p)),
        "reverting_share": float(np.mean([g == pr.REVERTING for g in regimes])),
        "explosive_share": float(np.mean([g == pr.EXPLOSIVE for g in regimes])),
        "half_life_p25": float(np.percentile(finite, 25)) if finite.size else float("nan"),
        "half_life_median": float(np.median(finite)) if finite.size else float("nan"),
        "half_life_p75": float(np.percentile(finite, 75)) if finite.size else float("nan"),
    }


def paired_lift(real: np.ndarray, null: np.ndarray) -> tuple[float, float, float]:
    """Mean per-window lift, its standard error, and the ratio of the two.

    Paired because both are measured on the same windows, so the window-to-window
    variation — which is large, since whole years are calm or turbulent together
    — cancels instead of being charged to the difference.
    """
    n = min(len(real), len(null))
    difference = real[:n] - null[:n]
    if n < 2:
        raise UserError("at least two windows are needed for a standard error; "
                        "lower --step or --pca-window")
    se = float(difference.std(ddof=1) / math.sqrt(n))
    mean = float(difference.mean())

    # Both sides are shares, so a spread below floating-point noise is zero, not
    # a very small number. Dividing by it produced a t of 1.0e16 on a constant
    # lift -- an overwhelming result manufactured entirely by rounding. There is
    # no reading of that number that is evidence: windows that all return an
    # identical share mean the two sweeps were handed the same input, which is
    # a defect to find rather than a result to report.
    if se < 1e-12:
        raise UserError(
            f"every one of the {n} windows produced the same lift of {mean:+.4%}, "
            "which real data does not do. The real and shuffled sweeps are seeing "
            "the same input — check that the permutation is reaching the returns."
        )
    return mean, se, mean / se


def show(real: dict, null: dict, log) -> None:
    log("")
    log(f"  {'':28s} {'real':>10s} {'shuffled':>10s} {'lift':>10s}")
    rows = [
        ("residuals tested", "observations", "{:,.0f}"),
        ("unit root rejected at 5%", "reject_share", "{:.1%}"),
        ("median ADF p-value", "median_p", "{:.3f}"),
        ("OU regime is reverting", "reverting_share", "{:.1%}"),
        ("OU regime is explosive", "explosive_share", "{:.1%}"),
        ("half-life, 25th pct (bars)", "half_life_p25", "{:.1f}"),
        ("half-life, median (bars)", "half_life_median", "{:.1f}"),
        ("half-life, 75th pct (bars)", "half_life_p75", "{:.1f}"),
    ]
    for label, key, fmt in rows:
        a, b = real[key], null[key]
        if key == "observations":
            lift = ""
        elif fmt.endswith("%}"):
            lift = f"{a - b:+.1%}"
        elif key == "median_p":
            lift = f"{a - b:+.3f}"
        else:
            lift = f"{a - b:+.1f}"
        log(f"  {label:28s} {fmt.format(a):>10s} {fmt.format(b):>10s} {lift:>10s}")


def append_log(path: Path, args, panel: pd.DataFrame, real: dict, null: dict,
               mean: float, se: float, t: float, passed: bool) -> int:
    row = {"run": 0,
           "run_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "asset_class": args.asset_class, "timeframe": args.timeframe,
           "names": panel.shape[1], "bars": panel.shape[0],
           "start": f"{panel.index[0]:%Y-%m-%d}", "end": f"{panel.index[-1]:%Y-%m-%d}",
           "factors": args.factors, "pca_window": args.pca_window,
           "ou_window": args.ou_window, "step": args.step, "level": args.level,
           "null_draws": args.null_draws, "seed": args.seed,
           "windows": real["windows"], "observations": real["observations"],
           "reject_share": round(real["reject_share"], 4),
           "null_reject_share": round(null["reject_share"], 4),
           "lift": round(mean, 5), "lift_se": round(se, 5), "lift_t": round(t, 3),
           "half_life_median": round(real["half_life_median"], 3),
           "reverting_share": round(real["reverting_share"], 4),
           "passed": "yes" if passed else "no"}
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
    p = argparse.ArgumentParser(prog="residual", description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sel = p.add_argument_group("selection")
    sel.add_argument("-a", "--asset-class", default="equity")
    sel.add_argument("-t", "--timeframe", default="1d")
    sel.add_argument("--source", default=None, help="restrict to one feed")
    sel.add_argument("--min-bars", type=int, default=5000,
                     help="a series shorter than this is left out of the panel "
                          "rather than truncating the common index for every "
                          "other name")

    struct = p.add_argument_group("structure - choose once, not per run")
    struct.add_argument("--pca-window", type=int, default=252,
                        help="bars the factor model is estimated on")
    struct.add_argument("--ou-window", type=int, default=60,
                        help="bars after the fit window over which the residual "
                             "is accumulated and tested")
    struct.add_argument("--step", type=int, default=63,
                        help="bars between windows. The default exceeds "
                             "--ou-window so the tested residuals do not "
                             "overlap, which keeps each window a near-"
                             "independent observation")
    struct.add_argument("--adf-lags", type=int, default=1,
                        help="fixed ADF lag order. Fixed rather than chosen by "
                             "AIC because the choice moves the rejection rate "
                             "by well under a percentage point and autolag "
                             "makes the sweep several times slower")

    search = p.add_argument_group("searched - every value is a trial")
    search.add_argument("--factors", type=int, default=15,
                        help="principal components removed before the residual")
    search.add_argument("--level", type=float, default=0.05)
    search.add_argument("--null-draws", type=int, default=3,
                        help="permutations averaged into the null, so the floor "
                             "is not one lucky shuffle")
    search.add_argument("--seed", type=int, default=0)

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
    if args.factors < 1:
        raise UserError("--factors must be at least 1")
    if args.ou_window < 20:
        raise UserError("--ou-window below 20 bars leaves the unit-root test with "
                        "almost no power, so a null result would say nothing")
    if args.factors >= args.pca_window:
        raise UserError("--factors must be fewer than --pca-window bars, or the "
                        "loading regression has no degrees of freedom")
    if args.null_draws < 1:
        raise UserError("--null-draws must be at least 1; the null is what makes "
                        "the real number readable")
    if not 0.0 < args.level < 0.5:
        raise UserError("--level must be between 0 and 0.5")

    panel = load_panel(Path(args.store), args.asset_class, args.timeframe,
                       args.min_bars, args.source)
    returns = np.diff(np.log(panel.to_numpy(float)), axis=0)

    log(f"{args.asset_class} residual reversion   {panel.shape[1]} names   "
        f"{panel.shape[0]:,} common bars   "
        f"{panel.index[0]:%Y-%m-%d} to {panel.index[-1]:%Y-%m-%d}")
    log(f"  {args.factors} factors fitted on {args.pca_window} bars, residual "
        f"accumulated over the {args.ou_window} bars after, stepped {args.step}"
        + (f", {panel.attrs['skipped']} series below {args.min_bars:,} bars left out"
           if panel.attrs.get("skipped") else ""))

    real_windows = sweep(returns, args)
    null_windows = [sweep(shuffled(returns, args.seed + d), args)
                    for d in range(args.null_draws)]

    real = summarise(real_windows)
    null = summarise([w for draw in null_windows for w in draw])

    real_shares = window_shares(real_windows)
    null_shares = np.mean([window_shares(d)[:len(real_shares)]
                           for d in null_windows], axis=0)
    mean, se, t = paired_lift(real_shares, null_shares)

    show(real, null, log)
    passed = t > MIN_T

    log("")
    log(f"  lift {mean:+.2%} +/- {se:.2%} per window over {real['windows']} windows, "
        f"t = {t:.2f}")
    log(f"  null averaged over {args.null_draws} permutations")
    log("")
    if passed:
        log(f"  REVERTS — the residual rejects a unit root more often than the same")
        log(f"  pipeline on shuffled dates, by {t:.1f} standard errors. The premise of")
        log(f"  RESIDUAL.md survives Stage 0.")
        log(f"  This is not an edge. It says the object exists, not that trading it")
        log(f"  pays: Stage 1 measures whether the aggregate signal is positive gross,")
        log(f"  and §1.3 of the plan says financing is what has killed every candidate.")
    else:
        log(f"  DOES NOT REVERT — the lift over the shuffled null is {mean:+.2%} against a")
        log(f"  standard error of {se:.2%}, so it is indistinguishable from zero at the")
        log(f"  two-error bar this project applies to every other mean it reports.")
        log(f"  This is the Stage 0 kill criterion in RESIDUAL.md §4. Stop rather than")
        log(f"  tuning --factors until it passes: every such value is a trial, and the")
        log(f"  deflation benchmark in Step 4 grows with the log of the trial count.")

    if args.json:
        print(json.dumps({"names": panel.shape[1], "bars": panel.shape[0],
                          "factors": args.factors, "real": real, "null": null,
                          "lift": mean, "lift_se": se, "lift_t": t,
                          "passed": passed}, indent=2, default=str))

    if not args.no_log:
        run = append_log(Path(args.log), args, panel, real, null, mean, se, t, passed)
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
