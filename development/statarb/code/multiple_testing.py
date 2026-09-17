"""Step 4.1 — how many tests were really run, and how many rejections chance gives.

`screen.py` prints a line like this:

    equities, within sector   1,192 pairs   144 cointegrated   noise would give about 59

and this project has been reading 144-against-59 as a large excess. That reading
assumes 1,192 independent tests. They are not independent. They are built from
252 instruments, so `NUE~STLD`, `NUE~CLF` and `STLD~CLF` share legs and share
their errors, and the same instruments are tested in overlapping windows. The
true number of independent tests is smaller — the question is how much smaller,
and whether the excess survives knowing.

Three estimates, reported side by side rather than reconciled:

    naive             N x level. What the screen prints today, kept so the
                      difference is visible rather than asserted.

    effective tests   the participation ratio of the spread correlation matrix,
                      `(sum L)^2 / sum(L^2)`. The same statistic `risk.py` uses
                      to count independent bets in a book.

                      **It does not reduce the expected count**, and this script
                      first claimed it did. The expected number of rejections is
                      `N x level` however correlated the tests are, because
                      expectation is linear and every test still rejects with
                      probability `level` under the null. What dependence inflates
                      is the *variance* of the count. The effective number belongs
                      in the family-wise threshold instead, and that is where it
                      is now used. The bootstrap below is what caught the mistake.

    bootstrap         resample each instrument independently under the null,
                      keeping its own serial correlation and destroying every
                      cross-instrument relationship, then re-run the screen and
                      count rejections. This is the honest answer and the slow
                      one; the other two exist to be checked against it.

And a fourth thing, which is a different question and a more useful one:
**Benjamini-Hochberg**. "Which pairs have p below 0.05" controls the chance of
one false positive. "Which pairs survive at a false discovery rate of 10%"
controls the share of the reported set that is wrong, which is what matters when
the set is the output of a search.

    python multiple_testing.py --dump logs/dump-equities.csv
    python multiple_testing.py --dump logs/dump-fx.csv --bootstrap 200
    python multiple_testing.py --dump logs/dump-equities.csv --fdr 0.10 --json

Exit codes: 0 the excess survives correction, 3 it does not, 2 usage error.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import types
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import paths

paths.ensure_code_importable()
paths.ensure_marketdata_importable()

import cointegration as ci                                        # noqa: E402
import pair_report as pr                                          # noqa: E402
import risk as rk                                                 # noqa: E402
import triallog                                                   # noqa: E402

UserError = pr.UserError
DEFAULT_LOG = paths.LOGS / "multiple_testing.csv"


def read_dump(path: Path) -> pd.DataFrame:
    """One row per tested pair, as `screen.py --dump` writes it."""
    if not path.exists():
        raise UserError(f"no dump at {path}. Produce one with: "
                        f"python screen.py -u <universe> --dump {path}")
    frame = pd.read_csv(path)
    for column in ("a", "b", "pvalue"):
        if column not in frame.columns:
            raise UserError(f"{path} has no {column!r} column; it was not written "
                            "by screen.py --dump")
    frame = frame[np.isfinite(frame["pvalue"])]
    if frame.empty:
        raise UserError(f"{path} contains no finite p-values")
    return frame


def benjamini_hochberg(pvalues: np.ndarray, fdr: float) -> tuple:
    """Which p-values survive at a false discovery rate of `fdr`.

    Sort ascending; find the largest k where `p_k <= k/N * fdr`; everything up
    to k is a discovery. Returns the boolean mask and the p-value threshold.

    This answers a different question from "p < 0.05". That controls the chance
    of a single false positive anywhere. This controls the *share of the
    reported set* that is wrong, which is the question a screen is asking:
    of the pairs I am about to look at, how many are noise?
    """
    if not 0 < fdr < 1:
        raise UserError(f"--fdr {fdr:g} is a rate between 0 and 1")
    p = np.asarray(pvalues, dtype=float)
    n = p.size
    if n == 0:
        return np.zeros(0, dtype=bool), float("nan")
    order = np.argsort(p)
    ranked = p[order]
    limits = (np.arange(1, n + 1) / n) * fdr
    under = np.flatnonzero(ranked <= limits)
    if under.size == 0:
        return np.zeros(n, dtype=bool), float("nan")
    cutoff_rank = under[-1]
    threshold = float(ranked[cutoff_rank])
    return p <= threshold, threshold


def effective_tests(spreads: pd.DataFrame) -> float:
    """How many independent tests a set of correlated spreads amounts to.

    The participation ratio of the correlation matrix eigenvalues, which equals
    N when the spreads are independent and falls towards 1 as they become the
    same test. Delegated to `risk.effective_bets` rather than recomputed: a
    second copy of this formula is how two parts of this project came to
    disagree about neutrality.
    """
    if spreads.shape[1] < 2:
        return float(spreads.shape[1])
    frame = spreads.dropna()
    if len(frame) < 10:
        raise UserError("the spreads share too few bars to correlate")
    return rk.effective_bets(frame.corr())


def build_spreads(frame: pd.DataFrame, args, limit: int) -> pd.DataFrame:
    """Spread returns for a sample of the tested pairs.

    Sampled rather than exhaustive: the correlation matrix of 1,192 spreads is
    1.4 million entries and its participation ratio is stable long before that.
    The sample is deterministic given the seed, and the count is reported so the
    estimate can be repeated.
    """
    rng = np.random.default_rng(args.seed)
    rows = frame if len(frame) <= limit else frame.iloc[
        rng.choice(len(frame), size=limit, replace=False)]

    series: dict = {}
    for _, row in rows.iterrows():
        a, b = str(row["a"]), str(row["b"])
        sel = types.SimpleNamespace(
            symbols=f"{a},{b}", asset_class=args.asset_class,
            timeframe=args.timeframe, source=None, start=args.start,
            end=args.end, store=args.store)
        try:
            px = pr.load_prices(sel)
        except UserError:
            continue
        lp = np.log(px)
        beta = float(row["beta"]) if np.isfinite(row.get("beta", np.nan)) else 1.0
        spread = lp[a] - beta * lp[b]
        series[f"{a}~{b}"] = spread.diff()
    if not series:
        raise UserError("none of the sampled pairs could be loaded")
    return pd.DataFrame(series)


def block_bootstrap(returns: np.ndarray, block: int,
                    rng: np.random.Generator) -> np.ndarray:
    """One resample that keeps serial correlation and destroys everything else.

    Drawing single observations would destroy each series' own autocorrelation
    as well, and a white-noise null is easier to reject than the real one — it
    would understate how often chance produces a rejection. Blocks keep the
    within-series structure and break only the relationship *between* series,
    which is the null being tested.
    """
    n = returns.size
    if block < 1:
        raise UserError("the bootstrap block length must be at least one bar")
    starts = rng.integers(0, max(1, n - block), size=math.ceil(n / block))
    out = np.concatenate([returns[s:s + block] for s in starts])
    return out[:n]


@dataclass
class Bootstrap:
    """What chance alone produced, measured rather than assumed."""

    replicates: int
    rejections: np.ndarray
    pairs: int
    level: float

    @property
    def mean(self) -> float:
        return float(np.mean(self.rejections))

    @property
    def std(self) -> float:
        return float(np.std(self.rejections, ddof=1)) if len(self.rejections) > 1 \
            else float("nan")

    @property
    def standard_error(self) -> float:
        return self.std / math.sqrt(len(self.rejections)) if len(self.rejections) else float("nan")

    def p_value_of(self, observed: int) -> float:
        """How often chance alone produced at least `observed` rejections.

        The +1 in numerator and denominator is deliberate: a bootstrap p-value of
        exactly zero claims more than the replicate count can support.
        """
        if not len(self.rejections):
            return float("nan")
        at_least = int(np.sum(self.rejections >= observed))
        return (at_least + 1) / (len(self.rejections) + 1)


def run_bootstrap(frame: pd.DataFrame, args, log) -> Bootstrap | None:
    """Re-screen resampled data with every real relationship destroyed."""
    if args.bootstrap <= 0:
        return None

    symbols = sorted(set(frame["a"]) | set(frame["b"]))
    prices: dict = {}
    for sym in symbols:
        sel = types.SimpleNamespace(
            symbols=f"{sym},{symbols[0] if sym != symbols[0] else symbols[1]}",
            asset_class=args.asset_class, timeframe=args.timeframe, source=None,
            start=args.start, end=args.end, store=args.store)
        try:
            px = pr.load_prices(sel)
        except UserError:
            continue
        prices[sym] = np.log(px[sym].to_numpy(float))

    usable = [(str(r["a"]), str(r["b"])) for _, r in frame.iterrows()
              if str(r["a"]) in prices and str(r["b"]) in prices]
    if not usable:
        raise UserError("no tested pair could be reloaded for the bootstrap")

    rng = np.random.default_rng(args.seed)
    length = min(len(v) for v in prices.values())
    diffs = {k: np.diff(v[-length:]) for k, v in prices.items()}

    log(f"  bootstrapping {args.bootstrap} replicate(s) over {len(usable)} pair(s) "
        f"and {len(prices)} instrument(s), block {args.block} bars")
    counts = []
    for _ in range(args.bootstrap):
        # Each instrument is resampled with its own generator draw, so no two
        # share a path. That is the null: same individual behaviour, no relation.
        fake = {k: np.concatenate([[0.0], block_bootstrap(v, args.block, rng)]).cumsum()
                for k, v in diffs.items()}
        hits = 0
        for a, b in usable:
            y, x = fake[a], fake[b]
            if ci.engle_granger(y, x, trend="c", lags=args.lags).pvalue < args.level:
                hits += 1
        counts.append(hits)
    return Bootstrap(replicates=args.bootstrap, rejections=np.array(counts),
                     pairs=len(usable), level=args.level)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="multiple_testing",
                                description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    src = p.add_argument_group("input")
    src.add_argument("--dump", required=True,
                     help="per-pair rows from `screen.py --dump`")
    src.add_argument("-a", "--asset-class", default="equity")
    src.add_argument("-t", "--timeframe", default="1d")
    src.add_argument("--start", default=None)
    src.add_argument("--end", default=None)

    gates = p.add_argument_group("correction")
    gates.add_argument("--level", type=float, default=0.05,
                       help="the level the screen tested at")
    gates.add_argument("--fdr", type=float, default=0.10,
                       help="false discovery rate for Benjamini-Hochberg")
    gates.add_argument("--effective-sample", type=int, default=120,
                       help="pairs sampled for the correlation estimate; the "
                            "participation ratio settles well before the full set")
    gates.add_argument("--bootstrap", type=int, default=0,
                       help="replicates under the null; 0 skips it. This is the "
                            "honest estimate and the slow one")
    gates.add_argument("--block", type=int, default=20,
                       help="bootstrap block length in bars, which preserves each "
                            "instrument's own serial correlation")
    gates.add_argument("--lags", default=1,
                       type=lambda v: int(v) if str(v).isdigit() else v)
    gates.add_argument("--seed", type=int, default=1)

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
    warnings.filterwarnings("ignore")
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))

    if not 0 < args.level < 1:
        raise UserError(f"--level {args.level:g} is a probability between 0 and 1")
    if args.bootstrap < 0:
        raise UserError(f"--bootstrap {args.bootstrap} is a count of replicates. "
                        "Use 0 to skip it; a negative number skipped it silently "
                        "while looking like a request for it.")
    if args.effective_sample < 2:
        raise UserError(f"--effective-sample {args.effective_sample} cannot form a "
                        "correlation matrix. It needs at least two pairs, and "
                        "below that the estimate was quietly dropped instead.")

    frame = read_dump(Path(args.dump))
    p = frame["pvalue"].to_numpy(float)
    n = p.size
    observed = int(np.sum(p < args.level))

    log(f"{Path(args.dump).name}  {n:,} tested pair(s)  level {args.level:g}")
    log(f"  observed rejections   {observed:4d}")
    log("")

    expected_count = n * args.level
    binomial_sd = math.sqrt(n * args.level * (1 - args.level))
    log(f"  expected rejections   {expected_count:6.1f}   "
        f"= {n:,} x {args.level:g}, and dependence does not change this")
    log(f"  if independent, s.d.  {binomial_sd:6.2f}")

    n_eff = float("nan")
    try:
        spreads = build_spreads(frame, args, args.effective_sample)
        ratio = effective_tests(spreads) / spreads.shape[1]
        n_eff = ratio * n
        instruments = len(set(frame["a"]) | set(frame["b"]))
        measured = effective_tests(spreads)
        sidak = 1.0 - (1.0 - args.level) ** (1.0 / max(n_eff, 1.0))
        log("")
        log(f"  effective tests       {n_eff:6,.0f}   "
            f"from {measured:.1f} independent of {spreads.shape[1]} sampled pair(s)")
        log(f"  family-wise threshold {sidak:6.4f}   Sidak on the effective count: "
            f"a pair needs p below this")
        # Spreads of K instruments live in a K-dimensional space, so the
        # effective count cannot exceed the instrument count however many pairs
        # were formed. Stated as a check, because a number above it would mean
        # the estimate is wrong rather than the screen being broad.
        if n_eff > instruments:
            log(f"     WARNING: {n_eff:.0f} effective tests from {instruments} "
                "instruments is impossible; the estimate is wrong")
        else:
            log(f"     {instruments} instruments bound it from above, and it is "
                "below that")
    except UserError as exc:
        log(f"  effective (correlation)  not computed: {exc}")

    log("")
    boot = run_bootstrap(frame, args, log)
    if boot is not None:
        inflation = boot.std / binomial_sd if binomial_sd else float("nan")
        log(f"  bootstrap mean        {boot.mean:6.1f}   against {expected_count:.1f} "
            "expected; these should agree, and that is the check")
        log(f"  bootstrap s.d.        {boot.std:6.2f}   against {binomial_sd:.2f} "
            f"if independent — dependence widens it {inflation:.1f}x")
        log(f"  {boot.replicates} replicate(s), standard error of the mean "
            f"{boot.standard_error:.2f}")

    survivors, threshold = benjamini_hochberg(p, args.fdr)
    log("")
    log(f"  Benjamini-Hochberg at a {args.fdr:.0%} false discovery rate: "
        f"{int(survivors.sum())} survivor(s)"
        + (f", p <= {threshold:.5f}" if math.isfinite(threshold) else ""))
    if survivors.sum():
        keep = frame[survivors].sort_values("pvalue")
        for _, r in keep.head(10).iterrows():
            log(f"     {r['a']}~{r['b']:<10s} p {r['pvalue']:.5f}")

    # The verdict uses the strongest estimate available, because a correction
    # that is not applied is not a correction.
    # A point comparison against the mean is not a test. Six rejections against
    # 4.8 expected reads as an excess and happens 39% of the time by chance; the
    # bootstrap p-value is the only one of these numbers that answers the
    # question, so it decides whenever it exists.
    excess_p = boot.p_value_of(observed) if boot is not None else float("nan")
    expected = boot.mean if boot is not None else expected_count
    source = "bootstrap" if boot is not None else "N x level"

    # Two questions, and they are allowed to disagree. Collapsing them into one
    # verdict produced the sentence "NO EXCESS - 6 rejections against 0.2
    # expected", which is self-contradictory and was the first thing this script
    # printed. Report them separately, because the pair of answers is more
    # informative than either.
    excess = (excess_p < args.level if math.isfinite(excess_p)
              else observed > expected + 2 * binomial_sd)
    named = bool(survivors.sum())
    log("")
    log(f"  population: {'EXCESS' if excess else 'NO EXCESS'} — {observed} "
        f"rejections against {expected:.1f} expected by the {source} estimate"
        + (f", bootstrap p = {excess_p:.3f}" if math.isfinite(excess_p) else ""))
    log(f"  individuals: {int(survivors.sum())} pair(s) survive a "
        f"{args.fdr:.0%} false discovery rate")
    log("")
    if excess and named:
        log("  There is more here than chance, and the pairs carrying it can be "
            "named. That is a population statement plus a shortlist, not a "
            "recommendation of anything on it.")
    elif excess and not named:
        log("  There is more here than chance, but no individual pair is strong "
            "enough to name at this false discovery rate. The excess is spread "
            "thinly across the population — real as an aggregate, untradeable as "
            "a list.")
    elif named and not excess:
        log("  No population excess, yet a pair clears the rate. Treat it as a "
            "single result that has not been corroborated by the rest of its "
            "universe.")
    else:
        log("  The screen found what chance alone would find, and named nobody. "
            "Nothing below the first gate is evidence.")
    survives = excess and named

    if not args.no_log:
        row = {
            "run": 0, "run_utc": triallog.stamp(),
            "dump": Path(args.dump).name, "asset_class": args.asset_class,
            "timeframe": args.timeframe, "pairs": n, "level": args.level,
            "observed": observed,
            "expected_count": round(expected_count, 2),
            "binomial_sd": round(binomial_sd, 3),
            "effective_tests": None if not math.isfinite(n_eff) else round(n_eff, 1),
            "sidak_threshold": (None if not math.isfinite(n_eff) else
                                round(1 - (1 - args.level) ** (1 / max(n_eff, 1)), 6)),
            "bootstrap_sd": None if boot is None else round(boot.std, 3),
            "bootstrap_replicates": 0 if boot is None else boot.replicates,
            "expected_bootstrap": None if boot is None else round(boot.mean, 2),
            "bootstrap_p": (None if boot is None or not math.isfinite(excess_p)
                            else round(excess_p, 4)),
            "fdr": args.fdr,
            "bh_survivors": int(survivors.sum()),
            "bh_threshold": None if not math.isfinite(threshold) else round(threshold, 6),
            "verdict": "excess" if survives else "no excess",
        }
        try:
            run = triallog.append(Path(args.log), row)
        except triallog.SchemaChanged as exc:
            raise UserError(str(exc)) from exc
        log(f"  run #{run} logged to {Path(args.log)}")

    if args.json:
        print(json.dumps({
            "pairs": n, "observed": observed, "level": args.level,
            "expected_count": expected_count,
            "effective_tests": None if not math.isfinite(n_eff) else n_eff,
            "expected_bootstrap": None if boot is None else boot.mean,
            "bootstrap_p": None if not math.isfinite(excess_p) else excess_p,
            "bh_survivors": int(survivors.sum()),
            "bh_threshold": None if not math.isfinite(threshold) else threshold,
            "survives": survives,
        }, indent=2, default=str))

    return 0 if survives else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
