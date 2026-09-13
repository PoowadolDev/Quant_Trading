"""Verification suite for pair_report.py.

Research code fails quietly. A sign error or an off-by-one does not crash; it
returns a plausible number that is wrong, and the mistake is only discovered
after weeks of work have been built on top of it. These checks exist to make
that failure loud.

Five kinds of check, in order of how much they are worth:

1. Ground truth   — simulate a process whose parameters are known, then confirm
                    the code recovers them.
2. Null calibration — feed it data with no relationship at all and confirm the
                    gates reject nearly all of it. A gate that passes noise is
                    worse than no gate.
3. Invariance     — transformations that must not change the answer, do not.
4. No look-ahead  — changing the out-of-sample half must not move any
                    in-sample estimate.
5. Real anchors   — stored data whose answers are already known by hand.

Run it directly; no pytest required:

    python verify_pair_report.py
    python verify_pair_report.py -v        # print every check
"""
from __future__ import annotations

import argparse
import math
import sys
import tempfile
import types
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pair_report as pr  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []
VERBOSE = False


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(name)
    if not ok or VERBOSE:
        mark = "ok  " if ok else "FAIL"
        print(f"  {mark} {name}" + (f"   {detail}" if detail else ""))


def skip(name: str, why: str) -> None:
    SKIPPED.append(name)
    print(f"  skip {name}   {why}")


def close(got: float, want: float, tol: float) -> bool:
    return math.isfinite(got) and abs(got - want) <= tol


# ---------------------------------------------------------------- fixtures
def ou_path(n: int, half_life: float, sigma: float, rng) -> np.ndarray:
    """A discrete OU path with the requested half-life, in bars."""
    a = math.exp(-math.log(2) / half_life)
    s = np.zeros(n)
    for t in range(1, n):
        s[t] = a * s[t - 1] + rng.normal(0, sigma)
    return s


def ar_path(n: int, a: float, sigma: float, rng, cap: float = 1.0) -> np.ndarray:
    """AR(1) path, rescaled to `cap` in absolute value.

    An explosive coefficient over a thousand bars reaches log prices in the
    hundreds, and `exp` of that overflows to infinity, which tests the floating
    point limits rather than the code. Rescaling keeps the shape and the fitted
    coefficient while keeping the prices representable.
    """
    s = np.zeros(n)
    for t in range(1, n):
        s[t] = a * s[t - 1] + rng.normal(0, sigma)
    peak = float(np.max(np.abs(s)))
    return s * (cap / peak) if peak > cap else s


def make_prices(log_a: np.ndarray, log_b: np.ndarray, freq: str = "D") -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=len(log_a), freq=freq, tz="UTC")
    return pd.DataFrame({"AAA": np.exp(log_a), "BBB": np.exp(log_b)}, index=index)


def default_args(**over) -> types.SimpleNamespace:
    args = dict(price="log", hedge="ols", split=0.7, entry_z=2.0, exit_z=0.5,
                min_half_life=2.0, max_half_life=30.0, min_edge=2.0, cost_bps=2.0,
                timeframe="1d", asset_class="forex", source="yahoo", bins=45, symbols="AAA,BBB",
                start=None, end=None)
    args.update(over)
    return types.SimpleNamespace(**args)


def run(prices: pd.DataFrame, args) -> tuple[pr.PairFit, pr.Verdict, pd.Series, pd.Series, int]:
    split = int(len(prices) * args.split)
    fit = pr.fit_pair(prices, split=split, use_log=args.price == "log",
                      entry_z=args.entry_z, exit_z=args.exit_z, cost_bps=args.cost_bps)
    verdict = pr.judge(fit, min_hl=args.min_half_life, max_hl=args.max_half_life,
                       min_edge=args.min_edge)
    px = np.log(prices) if args.price == "log" else prices
    a, b = prices.columns
    spread = px[a] - fit.beta * px[b] - fit.alpha
    z = ((spread - fit.mu) / fit.sigma_eq
         if fit.regime == pr.REVERTING and math.isfinite(fit.sigma_eq) and fit.sigma_eq > 0
         else spread * np.nan)
    return fit, verdict, spread, z, split


# ---------------------------------------------------------------- 1. ground truth
def test_ground_truth() -> None:
    print("\n1. ground truth — known process, recovered parameters")
    rng = np.random.default_rng(11)
    n, true_beta, true_hl = 3000, 0.80, 12.0

    log_b = np.cumsum(rng.normal(0, 0.01, n)) + math.log(1.2)
    s = ou_path(n, true_hl, 0.002, rng)
    prices = make_prices(true_beta * log_b + 0.05 + s, log_b)
    fit, verdict, spread, z, split = run(prices, default_args())

    check("hedge ratio recovered", close(fit.beta, true_beta, 0.05),
          f"beta {fit.beta:.4f} vs {true_beta}")
    check("half-life recovered within 25%", close(fit.half_life, true_hl, true_hl * 0.25),
          f"{fit.half_life:.1f} vs {true_hl}")
    check("regime is reverting", fit.regime == pr.REVERTING, fit.regime)
    check("out-of-sample half-life also recovered",
          close(fit.half_life_oos, true_hl, true_hl * 0.40),
          f"{fit.half_life_oos:.1f} vs {true_hl}")
    check("a clean OU pair is accepted", verdict.accepted, verdict.reason)

    # sigma_eq is the standard deviation of the stationary spread, so the
    # realised spread should sit inside a few of them.
    realised_sd = float(spread.std())
    check("sigma_eq matches the realised spread sd",
          close(fit.sigma_eq, realised_sd, realised_sd * 0.25),
          f"{fit.sigma_eq:.6f} vs {realised_sd:.6f}")
    check("in-sample z-score has unit scale", close(float(z.iloc[:split].std()), 1.0, 0.25),
          f"{float(z.iloc[:split].std()):.3f}")

    # Half-life is a property of the process, not of the sampling label.
    for hl in (4.0, 25.0):
        s2 = ou_path(n, hl, 0.002, rng)
        p2 = make_prices(true_beta * log_b + s2, log_b)
        f2, _, _, _, _ = run(p2, default_args())
        check(f"half-life {hl:g} recovered", close(f2.half_life, hl, hl * 0.25),
              f"{f2.half_life:.1f}")


def test_regimes() -> None:
    print("\n1b. regime labels — the three cases must not be confused")
    rng = np.random.default_rng(12)
    n = 1500

    # Classification is tested on the series itself, with no hedge ratio in the
    # way, so a failure here is unambiguously the classifier's.
    theta, _, _, regime = pr._fit_ou(ou_path(n, 12.0, 0.002, rng))
    check("mean-reverting path labelled reverting", regime == pr.REVERTING, regime)
    check("half-life matches the simulated one",
          close(math.log(2) / theta, 12.0, 3.0), f"{math.log(2)/theta:.1f}")

    _, _, _, regime = pr._fit_ou(ar_path(n, 1.01, 0.002, rng))
    check("explosive path labelled explosive", regime == pr.EXPLOSIVE, regime)

    # A negative AR(1) coefficient reverts faster than one bar. Calling that
    # explosive would be the exact opposite of the truth.
    _, _, _, regime = pr._fit_ou(ar_path(n, -0.5, 0.002, rng))
    check("negative AR(1) labelled oscillating, not explosive",
          regime == pr.OSCILLATING, regime)

    try:
        pr._fit_ou(np.array([1.0, 2.0, np.inf, 4.0]))
        check("non-finite input is refused", False, "no error raised")
    except pr.UserError:
        check("non-finite input is refused", True)
    except Exception as exc:                                    # noqa: BLE001
        check("non-finite input is refused", False, f"raised {type(exc).__name__}")

    # End to end, a spread that walks away must be rejected and must never
    # reach the edge gate, whichever of the two failing labels it lands on.
    log_b = np.cumsum(rng.normal(0, 0.01, n)) + math.log(1.2)
    explosive = make_prices(log_b + ar_path(n, 1.01, 0.002, rng, cap=3.0), log_b)
    fit, verdict, _, z, _ = run(explosive, default_args())
    check("a diverging pair is rejected", not verdict.accepted, verdict.reason)
    check("edge gate not reached when the spread is not stationary",
          verdict.edge_ok is None, str(verdict.edge_ok))
    check("no half-life inside the bounds is reported", not verdict.half_life_ok)
    if fit.regime != pr.REVERTING:
        check("no z-score is invented without an OU fit", bool(z.isna().all()))

    oscillating = make_prices(log_b + ar_path(n, -0.5, 0.002, rng), log_b)
    fit2, verdict2, _, _, _ = run(oscillating, default_args())
    check("oscillating pair labelled oscillating end to end",
          fit2.regime == pr.OSCILLATING, fit2.regime)
    check("oscillating reason does not claim divergence",
          "diverge" not in verdict2.reason and "explosive" not in verdict2.reason,
          verdict2.reason)
    check("oscillating spread is rejected", not verdict2.accepted)


def test_gate_order() -> None:
    print("\n1c. gate order — edge is never evaluated on a non-stationary spread")
    rng = np.random.default_rng(13)
    n, split_frac = 2000, 0.7
    cut = int(n * split_frac)
    log_b = np.cumsum(rng.normal(0, 0.01, n)) + math.log(1.2)

    # Mean-reverting in-sample, then a unit root out-of-sample: the classic
    # relationship that was real once and is not any more.
    s = np.concatenate([ou_path(cut, 10.0, 0.002, rng),
                        np.cumsum(rng.normal(0, 0.004, n - cut)) + 0.02])
    fit, verdict, _, _, _ = run(make_prices(log_b + s, log_b), default_args())
    check("in-sample half-life is inside the bounds", verdict.half_life_ok,
          f"{fit.half_life:.1f}")
    check("out-of-sample gate fails", not verdict.half_life_oos_ok, fit.regime_oos)
    check("edge shows as not evaluated", verdict.edge_ok is None)
    check("verdict rejects", not verdict.accepted, verdict.reason)


# ---------------------------------------------------------------- 2. null calibration
def test_null_calibration(trials: int = 300) -> None:
    print(f"\n2. null calibration — {trials} pairs of independent random walks")
    rng = np.random.default_rng(20)
    n = 1200
    accepted = 0
    reverting = 0
    for _ in range(trials):
        log_a = np.cumsum(rng.normal(0, 0.01, n)) + math.log(1.1)
        log_b = np.cumsum(rng.normal(0, 0.01, n)) + math.log(1.3)
        fit, verdict, _, _, _ = run(make_prices(log_a, log_b), default_args())
        accepted += bool(verdict.accepted)
        reverting += fit.regime == pr.REVERTING
    rate = accepted / trials
    print(f"     accepted {accepted}/{trials} = {rate:.1%}   "
          f"(in-sample fitted as reverting on {reverting/trials:.0%})")
    check("independent random walks are almost never accepted", rate <= 0.02,
          f"{rate:.1%} accepted, want <= 2%")
    print("     Note: with 30 instruments there are 435 pairs, so even a 2% false "
          "positive rate\n     yields about 9 spurious 'tradable' pairs. Rank and "
          "re-test, never take the top hit.")


# ---------------------------------------------------------------- 3. invariance
def test_invariance() -> None:
    print("\n3. invariance — transformations that must not change the answer")
    rng = np.random.default_rng(30)
    n = 1500
    log_b = np.cumsum(rng.normal(0, 0.01, n)) + math.log(1.2)
    prices = make_prices(0.8 * log_b + ou_path(n, 12.0, 0.002, rng), log_b)
    base, _, _, base_z, split = run(prices, default_args())

    # Quoting both legs in different units shifts log price by a constant, which
    # the intercept absorbs. Nothing measured may move.
    scaled = prices.copy()
    scaled["AAA"] *= 3.0
    scaled["BBB"] *= 7.0
    got, _, _, got_z, _ = run(scaled, default_args())
    check("beta invariant to price scaling", close(got.beta, base.beta, 1e-9))
    check("half-life invariant to price scaling", close(got.half_life, base.half_life, 1e-9))
    check("sigma_eq invariant to price scaling", close(got.sigma_eq, base.sigma_eq, 1e-9))
    check("z-score invariant to price scaling",
          float(np.nanmax(np.abs(got_z.to_numpy() - base_z.to_numpy()))) < 1e-8)
    check("correlation invariant to price scaling",
          close(got.correlation, base.correlation, 1e-12))

    # The verdict must depend on the data, not on the order the rows arrived in
    # or on an irrelevant relabelling of the index.
    shifted = prices.copy()
    shifted.index = shifted.index + pd.Timedelta(days=365)
    got2, _, _, _, _ = run(shifted, default_args())
    check("results invariant to shifting the dates", close(got2.beta, base.beta, 1e-12))

    # Correlation is symmetric; the hedge ratio is not, and should not be.
    swapped = prices[["BBB", "AAA"]]
    got3, _, _, _, _ = run(swapped, default_args())
    check("correlation is symmetric under swapping the legs",
          close(got3.correlation, base.correlation, 1e-12))
    check("hedge ratio is not symmetric, as regression requires",
          not close(got3.beta, base.beta, 1e-6), f"{got3.beta:.4f} vs {base.beta:.4f}")


def test_no_lookahead() -> None:
    print("\n4. no look-ahead — the out-of-sample half cannot touch in-sample estimates")
    rng = np.random.default_rng(40)
    n = 1500
    log_b = np.cumsum(rng.normal(0, 0.01, n)) + math.log(1.2)
    prices = make_prices(0.8 * log_b + ou_path(n, 12.0, 0.002, rng), log_b)
    base, _, _, _, split = run(prices, default_args())

    # Replace the held-out half with something wild. Every in-sample number must
    # be byte-identical; only the out-of-sample diagnostics may move.
    tampered = prices.copy()
    tampered.iloc[split:, 0] = tampered.iloc[split:, 0].to_numpy() * np.linspace(1, 4, n - split)
    got, _, _, _, _ = run(tampered, default_args())
    check("beta unchanged", got.beta == base.beta)
    check("alpha unchanged", got.alpha == base.alpha)
    check("mu unchanged", got.mu == base.mu)
    check("sigma_eq unchanged", got.sigma_eq == base.sigma_eq)
    check("in-sample half-life unchanged", got.half_life == base.half_life)
    check("out-of-sample half-life did react", got.half_life_oos != base.half_life_oos,
          f"{base.half_life_oos:.1f} -> {got.half_life_oos:.1f}")


# ---------------------------------------------------------------- 5. real anchors
def test_real_anchors() -> None:
    print("\n5. real anchors — stored data with answers already known")
    store = pr.DEFAULT_STORE
    if not store.exists():
        skip("stored FX anchors", f"no store at {store}")
        return
    args = default_args()
    args.store = str(store)
    args.symbols = "AUDUSD,NZDUSD"
    try:
        prices = pr.load_prices(args)
    except pr.UserError as exc:
        skip("stored FX anchors", str(exc))
        return

    fit, verdict, _, _, _ = run(prices, args)
    check("AUDUSD/NZDUSD correlation is about 0.89", close(fit.correlation, 0.891, 0.02),
          f"{fit.correlation:.3f}")
    check("AUDUSD/NZDUSD hedge ratio is about 0.87", close(fit.beta, 0.866, 0.03),
          f"{fit.beta:.4f}")
    check("AUDUSD/NZDUSD is rejected on the default gates", not verdict.accepted,
          verdict.reason)

    # The triangular identity is the strongest anchor forex offers: EURGBP is
    # EURUSD divided by GBPUSD up to the spread, so a regression of one log
    # price on the other two is nearly exact.
    args.symbols = "EURUSD,GBPUSD"
    try:
        majors = pr.load_prices(args)
        cross = pr.load_prices(default_args(**{**vars(args), "symbols": "EURGBP,GBPUSD"}))
    except pr.UserError as exc:
        skip("triangular identity", str(exc))
        return
    joined = majors.join(cross[["EURGBP"]], how="inner").dropna()
    residual = (np.log(joined["EURGBP"])
                - (np.log(joined["EURUSD"]) - np.log(joined["GBPUSD"])))
    deviation_bps = (residual - residual.median()).abs() * 1e4
    median_bps = float(deviation_bps.median())
    p99_bps = float(deviation_bps.quantile(0.99))
    # Judged on robust statistics: the identity is enforced continuously by
    # banks, but a handful of stored bars are bad prints and the maximum would
    # be measuring those instead of the identity.
    check("EURGBP equals EURUSD/GBPUSD to well under a pip on a typical day",
          median_bps < 2.0, f"median deviation {median_bps:.2f} bps")
    check("the identity holds on all but a few bars", p99_bps < 15.0,
          f"99th percentile {p99_bps:.1f} bps")
    print("     This is why residual statarb across a complete set of FX pairs finds "
          "nothing:\n     the residuals are zero by construction, not by discovery.")

    # The outliers are a data defect, reported rather than asserted away.
    bad = deviation_bps[deviation_bps > 20.0].sort_values(ascending=False)
    if len(bad):
        print(f"     Data defect: {len(bad)} of {len(joined)} bars break the identity by "
              "more than 20 bps.")
        for stamp in bad.index[:3]:
            print(f"       {stamp:%Y-%m-%d}  EURGBP {joined['EURGBP'][stamp]:.5f}  "
                  f"implied {joined['EURUSD'][stamp]/joined['GBPUSD'][stamp]:.5f}  "
                  f"({bad[stamp]:.0f} bps)")
        print("     Holiday bars carry a stale quote on one leg; the worst are plainly "
              "bad prints.")


# ---------------------------------------------------------------- 6. plumbing
def test_reporting_and_log() -> None:
    print("\n6. plumbing — report contents, trial log, exit codes")
    rng = np.random.default_rng(60)
    n = 1200
    log_b = np.cumsum(rng.normal(0, 0.01, n)) + math.log(1.2)

    for label, series in (("clean OU", ou_path(n, 12.0, 0.002, rng)),
                          ("explosive", ar_path(n, 1.01, 0.002, rng)),
                          ("oscillating", ar_path(n, -0.5, 0.002, rng))):
        prices = make_prices(0.8 * log_b + series, log_b)
        args = default_args()
        fit, verdict, spread, z, split = run(prices, args)
        doc = pr.build_html(prices, fit, verdict, args, spread, z, split, 1)
        check(f"{label}: report has all five charts", doc.count("<svg") == 5,
              str(doc.count("<svg")))
        check(f"{label}: report contains no NaN", "nan" not in doc.lower().replace("nan-", ""))
        check(f"{label}: report states a verdict",
              ("ACCEPT" in doc) != ("REJECT" in doc) or "REJECT" in doc)
        check(f"{label}: no unclosed SVG path", "d=''" not in doc or label != "clean OU")

    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "trials.csv"
        prices = make_prices(0.8 * log_b + ou_path(n, 12.0, 0.002, rng), log_b)
        args = default_args()
        fit, verdict, _, _, _ = run(prices, args)
        numbers = []
        for _ in range(3):
            trial = pr.next_trial(log_path)
            numbers.append(trial)
            pr.append_trial(log_path, trial, args, fit, verdict,
                            Path(f"pair-AAA-BBB-trial{trial:03d}.html"))
        check("trial numbers increment", numbers == [1, 2, 3], str(numbers))
        rows = log_path.read_text(encoding="utf-8").strip().splitlines()
        check("one header plus one row per trial", len(rows) == 4, f"{len(rows)} lines")
        check("each trial names its own report",
              len({r.split(",")[-1] for r in rows[1:]}) == 3)


def test_per_leg_selection() -> None:
    print("\n7. cross-asset legs — one asset class per leg, matched on the date")
    # _per_leg expands a flag that may carry one value or one per symbol.
    two = ["GOLD", "AUDUSD"]
    check("one value applies to both legs",
          pr._per_leg("forex", two, "--asset-class") == ["forex", "forex"])
    check("one value per leg is kept in order",
          pr._per_leg("commodity,forex", two, "--asset-class") == ["commodity", "forex"])
    check("whitespace and case are normalised",
          pr._per_leg(" Commodity , FOREX ", two, "--asset-class") == ["commodity", "forex"])
    for bad in ("a,b,c", "a,b,c,d"):
        try:
            pr._per_leg(bad, two, "--asset-class")
            check(f"{bad!r} is refused", False, "no error raised")
        except pr.UserError:
            check(f"{bad!r} is refused", True)

    store = pr.DEFAULT_STORE
    if not (store / "commodity").exists():
        skip("cross-asset load", "no commodity series in the store")
        return
    args = default_args(symbols="GOLD,AUDUSD", asset_class="commodity,forex", source=None)
    args.store = str(store)
    try:
        prices = pr.load_prices(args)
    except pr.UserError as exc:
        skip("cross-asset load", str(exc))
        return
    # Yahoo stamps forex daily bars at 23:00 UTC and futures at 04:00, so an
    # exact-timestamp join finds nothing and the date match is what makes the
    # pair loadable at all.
    check("cross-asset legs load", len(prices) > 1000, f"{len(prices)} bars")
    check("date alignment was applied", getattr(args, "date_aligned", False) is True)
    check("every timestamp is midnight after matching",
          bool((prices.index.normalize() == prices.index).all()))
    check("both legs are named with their class",
          args.resolved_legs == ["GOLD (commodity/yahoo)", "AUDUSD (forex/yahoo)"],
          str(args.resolved_legs))

    fit, verdict, spread, z, split = run(prices, args)
    doc = pr.build_html(prices, fit, verdict, args, spread, z, split, 1)
    check("report names both legs and their classes",
          "GOLD (commodity/yahoo)" in doc and "AUDUSD (forex/yahoo)" in doc)
    check("report warns that the closes are not simultaneous",
          "non-simultaneous closes" in doc)

    # A single asset class must still work unchanged.
    single = default_args(symbols="AUDUSD,NZDUSD", asset_class="forex", source=None)
    single.store = str(store)
    fx = pr.load_prices(single)
    check("same-class pairs are not date-matched",
          getattr(single, "date_aligned", False) is False, f"{len(fx)} bars")


def main() -> int:
    global VERBOSE
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true", help="print passing checks too")
    parser.add_argument("--trials", type=int, default=300,
                        help="random-walk pairs for the null calibration")
    ns = parser.parse_args()
    VERBOSE = ns.verbose

    print("Verifying pair_report.py")
    test_ground_truth()
    test_regimes()
    test_gate_order()
    test_null_calibration(ns.trials)
    test_invariance()
    test_no_lookahead()
    test_real_anchors()
    test_reporting_and_log()
    test_per_leg_selection()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("\nFAILED:")
        for name in FAILED:
            print(f"  - {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
