"""Step 4.4 — cross-validation that does not hand the answer to itself.

Plain k-fold assumes each observation is independent of the others. A trade does
not oblige. A position opened at bar t and held sixteen bars has an outcome that
depends on bars t through t+16, so an observation in the training fold can
overlap a test-fold observation and carry its answer across the boundary. The
model then scores well on data it has effectively seen.

Two corrections, both from Lopez de Prado:

    purging    drop training observations whose outcome window overlaps any test
               observation's window. This removes the direct leak.

    embargo    drop a further margin of training observations immediately after
               the test fold. Serial correlation means a bar just after the test
               window still carries information about it even when the windows
               do not literally overlap.

What this script reports is the *gap*: the same folds scored plain, purged, and
purged with an embargo. A strategy whose score collapses once purging is applied
was being scored on leaked information.

    python purged_cv.py -s NUE,STLD -a equity
    python purged_cv.py -s RSG,WM -a equity --folds 8 --embargo 30
    python purged_cv.py -s XLP,XLB -a index --horizon 400

**Purging is often a no-op, and this script says so rather than implying
otherwise.** With a 20-bar horizon and six folds over seven thousand bars it
removes about sixty training rows out of six thousand, and a score computed on
5,990 rows is indistinguishable from one computed on 6,023. The share purged is
reported for exactly that reason: a correction that removed one percent of the
data has not demonstrated anything by leaving the answer unchanged.

Purging bites when the outcome window is long relative to the fold — many folds,
a long holding period, or both. The demonstration that it works at all lives in
`verify_validation.py`, on synthetic data where the overlap is constructed and
the right answer is known. It cannot be demonstrated from the command line on
real prices, and an earlier version of this script offered a `--plant-leak` flag
that claimed to: the leak it planted was inside each row, which purging is not
for and cannot remove. The flag is gone.

Exit codes: 0 the score survives purging, 3 it does not, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import paths

paths.ensure_code_importable()

import pair_report as pr                                          # noqa: E402
import strategy as sig                                            # noqa: E402
import triallog                                                   # noqa: E402

UserError = pr.UserError
DEFAULT_LOG = paths.LOGS / "purged_cv.csv"


def fold_bounds(n: int, folds: int) -> list:
    """Contiguous test ranges. Time series fold by period, never at random.

    Shuffling rows would put a bar's neighbours on both sides of the split,
    which leaks by construction before any label window is considered.
    """
    if folds < 2:
        raise UserError(f"--folds {folds} must be at least two")
    if n < folds * 2:
        raise UserError(f"{n} observation(s) will not make {folds} folds")
    edges = np.array_split(np.arange(n), folds)
    return [(int(e[0]), int(e[-1])) for e in edges]


def training_index(n: int, test_lo: int, test_hi: int, *, horizon: int,
                   embargo: int) -> np.ndarray:
    """Which observations may be trained on for this test fold.

    An observation at `i` has an outcome window `[i, i + horizon]`. It is purged
    when that window touches the test range at all, and embargoed when it falls
    in the margin just after the test range.
    """
    if horizon < 0 or embargo < 0:
        raise UserError("the horizon and the embargo are counts of bars, not "
                        "negative numbers")
    idx = np.arange(n)
    overlaps = (idx + horizon >= test_lo) & (idx <= test_hi + horizon)
    embargoed = (idx > test_hi) & (idx <= test_hi + embargo)
    inside = (idx >= test_lo) & (idx <= test_hi)
    return idx[~(overlaps | embargoed | inside)]


@dataclass
class Scored:
    """One scoring regime across every fold."""

    name: str
    scores: list
    trained_on: list

    @property
    def mean(self) -> float:
        good = [s for s in self.scores if math.isfinite(s)]
        return float(np.mean(good)) if good else float("nan")

    @property
    def usable_folds(self) -> int:
        return sum(1 for s in self.scores if math.isfinite(s))


def score_fold(feature: np.ndarray, label: np.ndarray, train: np.ndarray,
               test: np.ndarray) -> float:
    """Correlation between a fitted prediction and the truth, out of sample.

    Deliberately the simplest possible model — one coefficient fitted on the
    training rows and applied to the test rows. The question here is whether
    information crosses the fold boundary, and a simple model answers it more
    clearly than one with enough capacity to confuse the issue.
    """
    if train.size < 10 or test.size < 10:
        return float("nan")
    x, y = feature[train], label[train]
    if np.std(x) <= 0 or np.std(y) <= 0:
        return float("nan")
    beta = float(np.polyfit(x, y, 1)[0])
    predicted = beta * feature[test]
    if np.std(predicted) <= 0 or np.std(label[test]) <= 0:
        return float("nan")
    return float(np.corrcoef(predicted, label[test])[0, 1])


def run(feature: np.ndarray, label: np.ndarray, *, folds: int, horizon: int,
        embargo: int) -> dict:
    """Plain, purged, and purged-with-embargo, over the same folds."""
    n = feature.size
    bounds = fold_bounds(n, folds)
    out = {}
    for name, purge, gap in (("plain", False, 0),
                             ("purged", True, 0),
                             ("purged + embargo", True, embargo)):
        scores, sizes = [], []
        for lo, hi in bounds:
            test = np.arange(lo, hi + 1)
            if purge:
                train = training_index(n, lo, hi, horizon=horizon, embargo=gap)
            else:
                train = np.setdiff1d(np.arange(n), test)
            scores.append(score_fold(feature, label, train, test))
            sizes.append(int(train.size))
        out[name] = Scored(name=name, scores=scores, trained_on=sizes)
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="purged_cv", description=__doc__.splitlines()[0],
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
    struct.add_argument("--fit-window", type=int, default=250)
    struct.add_argument("--rehedge-every", type=int, default=5)

    cv = p.add_argument_group("cross-validation")
    cv.add_argument("--folds", type=int, default=6)
    cv.add_argument("--horizon", type=int, default=None,
                    help="bars a trade's outcome depends on; defaults to the "
                         "maximum holding period, which is what the strategy uses")
    cv.add_argument("--max-holding-bars", type=int, default=20)
    cv.add_argument("--embargo", type=int, default=20,
                    help="bars dropped after each test fold, for the serial "
                         "correlation that survives purging")
    cv.add_argument("--min-retained", type=float, default=0.50,
                    help="share of the plain score that must survive purging")

    out = p.add_argument_group("output")
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--log", default=str(DEFAULT_LOG))
    out.add_argument("--no-log", action="store_true")
    out.add_argument("--json", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    return p


def feature_and_label(px, args) -> tuple:
    """The spread's z-score now, and what the spread does over the horizon.

    This is the prediction a mean-reversion strategy is making, stated plainly:
    a spread far from its mean should come back, so today's z should predict the
    move over the next `horizon` bars. Everything the strategy does on top —
    thresholds, stops, sizing — is a way of acting on that one claim, and this
    is the claim being cross-validated.
    """
    a, b = px.columns
    lp = np.log(px) if args.price == "log" else px
    n = len(px)
    window = args.fit_window
    values = lp.to_numpy(float)

    z = np.full(n, np.nan)
    spread = np.full(n, np.nan)
    fit = None
    for t in range(window, n):
        if fit is None or t - fit.fitted_at >= args.rehedge_every:
            refit = sig.fit_relationship(px.iloc[t - window:t],
                                         use_log=args.price == "log", at=t)
            fit = refit if refit is not None else fit
        if fit is None:
            continue
        z[t] = fit.z(values[t, 0], values[t, 1])
        spread[t] = values[t, 0] - fit.beta * values[t, 1]

    horizon = args.horizon if args.horizon is not None else args.max_holding_bars
    forward = np.full(n, np.nan)
    forward[:-horizon] = spread[horizon:] - spread[:-horizon]

    # A high z should be followed by a fall, so the sign is flipped and the
    # feature reads as "how much reversion is predicted".
    feature = -z
    label = forward

    good = np.isfinite(feature) & np.isfinite(label)
    feature, label = feature[good], label[good]

    return feature, label, horizon


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    warnings.filterwarnings("ignore")
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))

    if not 0 <= args.min_retained <= 1:
        raise UserError(f"--min-retained {args.min_retained:g} is a share")
    if args.horizon is not None and args.horizon < 1:
        # A negative horizon reversed the forward-return slice and produced an
        # empty sample, which then reported itself as "too few observations for
        # six folds" — true, and the wrong explanation.
        raise UserError(f"--horizon {args.horizon} counts bars ahead, so it is at "
                        "least one. A negative value emptied the sample and the "
                        "error then blamed the fold count.")
    if args.max_holding_bars < 1:
        raise UserError(f"--max-holding-bars {args.max_holding_bars} counts bars")
    if args.embargo < 0:
        raise UserError(f"--embargo {args.embargo} counts bars, not negative ones")

    px = pr.load_prices(args)
    pair = " ~ ".join(px.columns)
    feature, label, horizon = feature_and_label(px, args)
    if feature.size < args.folds * 4:
        raise UserError(f"{pair} gives {feature.size} usable observation(s), too "
                        f"few for {args.folds} folds")

    scored = run(feature, label, folds=args.folds, horizon=horizon,
                 embargo=args.embargo)

    log(f"{pair}  {args.timeframe}  {len(px):,} bars  "
        f"{feature.size:,} usable observation(s)")
    log(f"  horizon {horizon} bars, {args.folds} folds, "
        f"embargo {args.embargo} bars")
    log("")
    log(f"  {'regime':<20s} {'mean score':>11s} {'folds':>6s} {'trained on':>12s}")
    for name in ("plain", "purged", "purged + embargo"):
        s = scored[name]
        log(f"  {name:<20s} {s.mean:+11.4f} {s.usable_folds:6d} "
            f"{int(np.mean(s.trained_on)):12,d}")

    plain_rows = float(np.mean(scored["plain"].trained_on))
    kept_rows = float(np.mean(scored["purged + embargo"].trained_on))
    removed = 1.0 - kept_rows / plain_rows if plain_rows else float("nan")
    log("")
    log(f"  purging removed {removed:.1%} of the training rows")
    if removed < 0.05:
        log("  At that share the comparison below cannot tell a clean strategy "
            "from a leaky one. Purging bites when the outcome window is long "
            "relative to the fold; raise --folds or --horizon to make it mean "
            "something.")

    plain = scored["plain"].mean
    purged = scored["purged + embargo"].mean
    retained = (purged / plain) if (math.isfinite(plain) and plain > 0) else float("nan")

    log("")
    if math.isfinite(retained):
        log(f"  purging retains {retained:.0%} of the plain score")
    else:
        log("  the plain score is not positive, so there is nothing for purging "
            "to take away")

    leaked = math.isfinite(retained) and retained < args.min_retained
    log("")
    if leaked:
        log(f"  LEAKAGE — the score falls to {retained:.0%} of the unpurged "
            f"figure, below the {args.min_retained:.0%} floor. Whatever this "
            "predicts, it was partly reading its own answer.")
    elif removed < 0.05:
        log("  NOT TESTED — purging removed too little of the training data for "
            "this comparison to mean anything. The score is unchanged because "
            "the data is unchanged.")
    else:
        log("  NO LEAKAGE — the score survives purging and the embargo. That "
            "says the prediction is honest, not that it is large.")

    if not args.no_log:
        row = {
            "run": 0, "run_utc": triallog.stamp(), "pair": pair,
            "timeframe": args.timeframe, "start": args.start or "",
            "end": args.end or "", "observations": int(feature.size),
            "folds": args.folds, "horizon": horizon, "embargo": args.embargo,
            "rows_removed": round(removed, 4) if math.isfinite(removed) else None,
            "plain": round(plain, 6) if math.isfinite(plain) else None,
            "purged": round(scored["purged"].mean, 6)
            if math.isfinite(scored["purged"].mean) else None,
            "purged_embargo": round(purged, 6) if math.isfinite(purged) else None,
            "retained": round(retained, 4) if math.isfinite(retained) else None,
            "min_retained": args.min_retained,
            "verdict": ("leakage" if leaked else
                        "not tested" if removed < 0.05 else "clean"),
        }
        try:
            run_no = triallog.append(Path(args.log), row)
        except triallog.SchemaChanged as exc:
            raise UserError(str(exc)) from exc
        log(f"  run #{run_no} logged to {Path(args.log)}")

    if args.json:
        print(json.dumps({
            "pair": pair, "observations": int(feature.size), "horizon": horizon,
            "folds": args.folds, "embargo": args.embargo,
            "plain": plain, "purged": scored["purged"].mean,
            "purged_embargo": purged, "retained": retained,
            "rows_removed": removed, "leakage": leaked,
        }, indent=2, default=str))

    return 3 if leaked else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
