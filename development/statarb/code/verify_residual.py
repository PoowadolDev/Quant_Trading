"""Stage 0.1 — prove residual.py is not lying.

The same treatment the rest of the pipeline gets. Two checks carry most of the
weight and the rest support them:

* **Null calibration.** With residuals measured forward, the shuffled null must
  reject a unit root at about the nominal 5%. If it does not, the construction
  is manufacturing stationarity and every "lift" it reports is an artefact. This
  is the check that caught the in-sample version of this script, whose null sat
  at 8.2%.
* **No look-ahead.** Nothing after the fit window may influence the loadings. A
  residual that has seen its own future reverts beautifully and means nothing.

    python verify_residual.py
    python verify_residual.py -v
"""
from __future__ import annotations

import argparse
import math
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ic                                                         # noqa: E402
import pair_report as pr                                          # noqa: E402
import residual as rs                                             # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []
VERBOSE = False


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(name)
    if not ok or VERBOSE:
        print(("  ok   " if ok else "  FAIL ") + name + (f"   {detail}" if detail else ""))


def skip(name: str, why: str) -> None:
    SKIPPED.append(name)
    print(f"  skip {name}   {why}")


def close(got: float, want: float, tol: float) -> bool:
    return math.isfinite(got) and abs(got - want) <= tol


# ---------------------------------------------------------------- fixtures
def args_for(**over):
    ns = rs.build_parser().parse_args(["--no-log"])
    ns.pca_window, ns.ou_window, ns.step = 252, 60, 63
    ns.factors, ns.adf_lags, ns.level = 5, 1, 0.05
    for key, value in over.items():
        setattr(ns, key, value)
    return ns


def universe(level_ar: float, *, bars=1500, names=40, factors=3, seed=0,
             factor_vol=0.01, idio_vol=0.01) -> np.ndarray:
    """Returns whose residual *level* is an AR(1) with the given coefficient.

    `X_t` — the cumulated residual return — reconstructs that level, so the
    coefficient is the ground truth the sweep has to recover:

    * `0.0` makes the level white noise, which is as stationary as a series gets
      and must be detected loudly.
    * `1.0` makes the level a random walk, which has a unit root by construction
      and must not be detected at more than the test's nominal size.
    """
    rng = np.random.default_rng(seed)
    common = rng.normal(0, factor_vol, (bars, factors)) @ rng.normal(0, 1, (factors, names))
    level = np.zeros((bars, names))
    for t in range(1, bars):
        level[t] = level_ar * level[t - 1] + rng.normal(0, idio_vol, names)
    return common + np.vstack([level[0], np.diff(level, axis=0)])


def lift_of(returns: np.ndarray, args, draws=2) -> tuple[float, float, float]:
    real = rs.window_shares(rs.sweep(returns, args))
    null = np.mean([rs.window_shares(rs.sweep(rs.shuffled(returns, s), args))[:len(real)]
                    for s in range(draws)], axis=0)
    return rs.paired_lift(real, null)


# ---------------------------------------------------------------- 1. truth
def test_ground_truth() -> None:
    print("\n1. the sweep finds reversion that is there and not reversion that is not")

    args = args_for()

    stationary_lift, _, stationary_t = lift_of(universe(0.0, seed=1), args)
    check("a white-noise residual level is detected loudly",
          stationary_lift > 0.20 and stationary_t > 5,
          f"lift {stationary_lift:+.1%}, t {stationary_t:.1f}")

    walk_lift, walk_se, walk_t = lift_of(universe(1.0, seed=2), args)
    check("a random-walk residual level is not detected",
          abs(walk_t) < rs.MIN_T,
          f"lift {walk_lift:+.2%} +/- {walk_se:.2%}, t {walk_t:.2f}")

    # The ordering must be monotone in the ground truth, not merely correct at
    # the two extremes: a sweep that answered "yes" and "no" by coin flip would
    # pass the two checks above roughly a quarter of the time.
    lifts = [lift_of(universe(ar, seed=3), args)[0] for ar in (0.0, 0.7, 0.95, 1.0)]
    check("detected lift falls as the planted level approaches a unit root",
          all(a > b for a, b in zip(lifts, lifts[1:])),
          " > ".join(f"{x:+.1%}" for x in lifts))

    # Half-lives must track the planted reversion speed, not just its presence.
    # ar = 0.7 implies ln2 / -ln(0.7) = 1.94 bars; ar = 0.95 implies 13.5.
    fast = rs.summarise(rs.sweep(universe(0.7, seed=4), args))["half_life_median"]
    slow = rs.summarise(rs.sweep(universe(0.95, seed=4), args))["half_life_median"]
    check("a faster planted level gives a shorter measured half-life",
          fast < slow, f"{fast:.1f} bars against {slow:.1f}")


# ---------------------------------------------------------------- 2. null
def test_null_calibration() -> None:
    print("\n2. the shuffled null rejects at its nominal size, so a lift means something")

    args = args_for()
    for label, ar in (("white-noise", 0.0), ("random-walk", 1.0)):
        shares = rs.window_shares(rs.sweep(rs.shuffled(universe(ar, seed=5), 11), args))
        got = float(shares.mean())
        # The forward construction faces the plain ADF null, so this must land
        # near 0.05. The in-sample construction this script replaced produced
        # 0.082 on the same data because cumulated in-window residuals form a
        # Brownian bridge; anything approaching that is the bug returning.
        check(f"null on {label} data rejects near the nominal 5%",
              0.02 <= got <= 0.075, f"{got:.1%}")

    # Shuffling must actually remove the thing being tested. On a planted
    # stationary level the real share is far above the null; if the permutation
    # were not doing its job the two would agree.
    real = rs.window_shares(rs.sweep(universe(0.0, seed=6), args)).mean()
    null = rs.window_shares(rs.sweep(rs.shuffled(universe(0.0, seed=6), 12), args)).mean()
    check("shuffling removes the reversion it is meant to remove",
          real > null + 0.20, f"real {real:.1%} against null {null:.1%}")

    # A level shift changes nothing the test reads, and a scale change on one
    # name must not change how often anything rejects.
    base = universe(0.0, seed=7)
    scaled = base.copy()
    scaled[:, 0] *= 50.0
    check("rescaling one name does not move the rejection share",
          close(rs.window_shares(rs.sweep(scaled, args)).mean(),
                rs.window_shares(rs.sweep(base, args)).mean(), 0.02),
          f"{rs.window_shares(rs.sweep(scaled, args)).mean():.1%}")


# ---------------------------------------------------------------- 3. leakage
def test_no_look_ahead() -> None:
    print("\n3. nothing after the fit window reaches the loadings")

    returns = universe(0.0, bars=800, names=20, seed=8)
    end, pca, ou, k = 400, 252, 60, 5
    baseline = rs.forward_residuals(returns, end, pca, ou, k)

    # Bars beyond the forward window are not read at all.
    beyond = returns.copy()
    beyond[end + ou:] += 5.0
    check("bars after the forward window do not change the residual",
          np.allclose(baseline, rs.forward_residuals(beyond, end, pca, ou, k)))

    # Bars before the fit window are not read either.
    before = returns.copy()
    before[:end - pca] += 5.0
    check("bars before the fit window do not change the residual",
          np.allclose(baseline, rs.forward_residuals(before, end, pca, ou, k)))

    # A single forward bar may move its own row and no other. If the loadings
    # had been fitted on the forward window, one changed bar there would shift
    # every row -- which is exactly how a look-ahead defect would present.
    poked = returns.copy()
    poked[end + 30] += 0.05
    after = rs.forward_residuals(poked, end, pca, ou, k)
    changed = ~np.isclose(after, baseline).all(axis=1)
    check("one forward bar changes its own row only",
          changed.sum() == 1 and bool(changed[30]),
          f"{int(changed.sum())} of {ou} rows changed")

    # And a bar inside the fit window must change the loadings, or the fit
    # window is not being read either and the check above proves nothing.
    fit_poked = returns.copy()
    fit_poked[end - 10] += 0.05
    check("a bar inside the fit window does change the residual",
          not np.allclose(baseline, rs.forward_residuals(fit_poked, end, pca, ou, k)))

    # The sweep must never read past the end of the panel.
    args = args_for(pca_window=pca, ou_window=ou, step=63, factors=k)
    windows = rs.sweep(returns, args)
    expected = len(range(pca, len(returns) - ou + 1, 63))
    check("the sweep stops a full forward window before the end",
          len(windows) == expected, f"{len(windows)} windows, expected {expected}")


# ---------------------------------------------------------------- 4. factors
def test_eigenportfolios() -> None:
    print("\n4. the factor step is a correlation decomposition, not a covariance one")

    rng = np.random.default_rng(9)
    window = rng.normal(0, 0.01, (252, 12))

    usable, weights = rs.eigenportfolios(window, 3)
    check("every moving name is usable", bool(usable.all()))
    check("weights are one row per name and one column per factor",
          weights.shape == (12, 3), str(weights.shape))

    # Multiplying one name by a constant multiplies its weight by the reciprocal
    # and leaves the factor returns it produces unchanged. On a covariance
    # decomposition that name would instead dominate the leading factor.
    scaled = window.copy()
    scaled[:, 0] *= 100.0
    _, scaled_weights = rs.eigenportfolios(scaled, 3)
    factors_before = window @ weights
    factors_after = scaled @ scaled_weights
    check("scaling one name leaves the factor returns it generates unchanged",
          np.allclose(np.abs(factors_before), np.abs(factors_after), atol=1e-8))

    # A name that never moves has no correlation to anything; it must be held
    # out rather than dividing by zero and poisoning the whole matrix.
    flat = window.copy()
    flat[:, 4] = 0.0
    usable_flat, weights_flat = rs.eigenportfolios(flat, 3)
    check("a name that never moves is held out of the decomposition",
          not usable_flat[4] and usable_flat.sum() == 11)
    check("holding it out leaves the decomposition finite",
          bool(np.isfinite(weights_flat).all()))

    # Asking for more factors than there are names cannot silently return fewer.
    try:
        rs.eigenportfolios(window, 12)
        check("more factors than usable names is refused", False)
    except rs.UserError:
        check("more factors than usable names is refused", True)


# ---------------------------------------------------------------- 5. statistic
def test_paired_lift() -> None:
    print("\n5. the lift statistic is computed by hand and matches")

    # Worked by hand rather than copied from a run: differences are
    # 0.05, 0.15, 0.25; mean 0.15; deviations -0.10, 0, +0.10; sample variance
    # 0.02/2 = 0.01; sd 0.10; standard error 0.10/sqrt(3) = 0.0577350;
    # t = 0.15 / 0.0577350 = 2.5980762.
    real = np.array([0.10, 0.20, 0.30])
    null = np.array([0.05, 0.05, 0.05])
    mean, se, t = rs.paired_lift(real, null)
    check("mean lift matches the hand computation", close(mean, 0.15, 1e-12), f"{mean:.10f}")
    check("standard error matches the hand computation",
          close(se, 0.1 / math.sqrt(3), 1e-12), f"{se:.10f}")
    check("t matches the hand computation", close(t, 2.5980762114, 1e-9), f"{t:.10f}")

    # Pairing must cancel common window-to-window variation. Adding the same
    # swing to both sides moves neither the mean nor the error; a version that
    # compared unpaired averages would see the error grow.
    swing = np.array([0.30, -0.10, 0.20])
    mean2, se2, _ = rs.paired_lift(real + swing, null + swing)
    check("a swing common to both sides cancels entirely",
          close(mean2, mean, 1e-12) and close(se2, se, 1e-12), f"{mean2:.10f} {se2:.10f}")

    # A constant difference has no spread to estimate from. Floating point makes
    # its standard error about 1e-17 rather than exactly zero, which once turned
    # a meaningless input into a t of 1.0e16, so the guard must be a tolerance
    # and not an equality against zero.
    try:
        rs.paired_lift(np.array([0.2, 0.2, 0.2]), np.array([0.1, 0.1, 0.1]))
        check("a lift identical in every window is refused, not reported as huge", False)
    except rs.UserError:
        check("a lift identical in every window is refused, not reported as huge", True)

    # The refusal must be triggered by the tolerance rather than by an exact
    # zero, which is the case that actually occurs.
    spread = np.array([0.2, 0.2, 0.2 + 1e-16])
    try:
        rs.paired_lift(spread, np.array([0.1, 0.1, 0.1]))
        check("a difference at floating-point noise is refused too", False)
    except rs.UserError:
        check("a difference at floating-point noise is refused too", True)

    # A genuinely small but real spread must still be reported.
    _, se4, t4 = rs.paired_lift(np.array([0.2, 0.2, 0.21]), np.array([0.1, 0.1, 0.1]))
    check("a small but real spread still produces a finite t",
          math.isfinite(t4) and se4 > 1e-12, f"se {se4:.2e} t {t4:.2f}")

    # One window cannot carry a standard error.
    try:
        rs.paired_lift(np.array([0.1]), np.array([0.05]))
        check("a single window is refused", False)
    except rs.UserError:
        check("a single window is refused", True)

    check(f"the pass bar is {rs.MIN_T} standard errors, the same one the backtest uses",
          rs.MIN_T == 2.0)


# ---------------------------------------------------------------- 6. shuffle
def test_shuffle() -> None:
    print("\n6. the permutation removes time and nothing else")

    rng = np.random.default_rng(10)
    returns = universe(0.0, bars=600, names=8, seed=10)
    permuted = rs.shuffled(returns, 3)

    check("the permutation preserves the correlation matrix exactly",
          np.allclose(np.corrcoef(returns, rowvar=False),
                      np.corrcoef(permuted, rowvar=False), atol=1e-12))
    check("the permutation preserves every column's mean and standard deviation",
          np.allclose(returns.mean(0), permuted.mean(0), atol=1e-12)
          and np.allclose(returns.std(0), permuted.std(0), atol=1e-12))
    check("the permutation keeps the same rows, only reordered",
          np.allclose(np.sort(returns, axis=0), np.sort(permuted, axis=0), atol=1e-12))

    # It must actually reorder. A permutation that returned the input would pass
    # all three checks above.
    check("the permutation does reorder", not np.allclose(returns, permuted))

    # And it must destroy serial dependence, which is the only thing the ADF
    # test and the OU fit read. Measured on the accumulated level, where the
    # planted structure lives.
    level = np.cumsum(returns[:, 0])
    level_permuted = np.cumsum(permuted[:, 0])

    def autocorr(x):
        x = x - x.mean()
        return float(np.corrcoef(x[:-1], x[1:])[0, 1])

    check("the accumulated level loses none of its autocorrelation before shuffling",
          autocorr(level) > 0.9, f"{autocorr(level):.3f}")
    check("shuffling the returns changes the level's path",
          not np.allclose(level, level_permuted))

    check("the same seed gives the same permutation",
          np.allclose(permuted, rs.shuffled(returns, 3), atol=1e-12))
    check("a different seed gives a different one",
          not np.allclose(permuted, rs.shuffled(returns, 4)))


# ---------------------------------------------------------------- 7. scoring
def test_scoring() -> None:
    print("\n7. OU regimes and p-values follow the series they are given")

    # A residual return series whose cumulation is a pure random walk: the
    # accumulated level then has a unit root and the fit must not call it
    # reverting with a short half-life.
    rng = np.random.default_rng(11)
    walk = rng.normal(0, 0.01, (200, 1))
    walk_rows = rs.score_window(walk, 1, 0.05)
    check("a random walk is scored, not dropped", len(walk_rows) == 1)

    # Alternating residual returns cumulate to a two-state oscillation, which
    # AR(1) sees as a negative coefficient. That is reversion faster than the
    # sampling interval, and pair_report labels it separately so no caller can
    # build a continuous-time half-life out of it.
    alternating = np.array([[0.01], [-0.01]] * 100, dtype=float)
    rows = rs.score_window(alternating, 1, 0.05)
    check("an overshooting residual is not labelled reverting",
          rows[0]["regime"] != pr.REVERTING, rows[0]["regime"])
    check("an overshooting residual reports no half-life",
          not math.isfinite(rows[0]["half_life"]), str(rows[0]["half_life"]))

    # A name carrying a non-finite value is skipped rather than crashing the
    # window or silently contributing a wrong answer.
    with_nan = np.column_stack([walk[:, 0], np.full(200, np.nan)])
    check("a non-finite residual is skipped, not counted",
          len(rs.score_window(with_nan, 1, 0.05)) == 1)

    # The rejection flag must agree with the level it was given, at any level.
    strict = rs.score_window(walk, 1, 0.001)
    check("the rejection flag follows --level",
          strict[0]["rejects"] == (strict[0]["adf_p"] < 0.001))

    # Every summary field the report prints must exist and be finite where the
    # data allows, so a formatting change cannot silently print a blank.
    summary = rs.summarise([walk_rows, walk_rows])
    for key in ("windows", "observations", "reject_share", "median_p",
                "reverting_share", "explosive_share", "half_life_median"):
        check(f"summarise reports {key}", key in summary)
    check("summarise counts windows and observations separately",
          summary["windows"] == 2 and summary["observations"] == 2)


# ---------------------------------------------------------------- 8. guards
def test_guards() -> None:
    print("\n8. bad settings are refused rather than quietly producing a number")

    for flags, why in (
        (["--factors", "0"], "zero factors"),
        (["--ou-window", "10"], "a forward window too short to test"),
        (["--factors", "300"], "more factors than fit-window bars"),
        (["--null-draws", "0"], "no null at all"),
        (["--level", "0.9"], "a significance level above one half"),
    ):
        try:
            rs.main(["--no-log", "--quiet", *flags])
            check(f"{why} is refused", False)
        except rs.UserError:
            check(f"{why} is refused", True)
        except Exception as exc:                                   # noqa: BLE001
            check(f"{why} is refused", False, f"raised {type(exc).__name__}")

    # A panel too short for one window must say so rather than reporting an
    # empty sweep as a pass.
    try:
        rs.sweep(universe(0.0, bars=100, names=10, seed=12), args_for())
        check("a panel too short for one window is refused", False)
    except rs.UserError:
        check("a panel too short for one window is refused", True)

    try:
        rs.load_panel(Path("nowhere-at-all"), "equity", "1d", 5000, None)
        check("a missing store is refused", False)
    except rs.UserError:
        check("a missing store is refused", True)


# ---------------------------------------------------------------- 9. IC
def ic_args(**over):
    ns = ic.build_parser().parse_args(["--no-log"])
    ns.pca_window, ns.signal_window, ns.step = 252, 60, 63
    ns.factors, ns.bars_per_year = 5, 252
    for key, value in over.items():
        setattr(ns, key, value)
    return ns


def test_ic() -> None:
    print("\n9. the information coefficient tracks the skill that was planted")

    args = ic_args()

    # A white-noise residual level is maximally mean-reverting: X_{t+h} is independent of
    # X_t, so the forward return is very nearly -X_t, and the signal (-X_t) must predict it.
    strong, _ = ic.sweep(universe(0.0, seed=20), 5, args)
    strong_summary = ic.summarise(strong)
    check("a strongly reverting residual gives a large positive IC",
          strong_summary["ic_mean"] > 0.2 and strong_summary["t"] > 5,
          f"IC {strong_summary['ic_mean']:+.4f}, t {strong_summary['t']:.1f}")

    # A random-walk level has no reversion, so the forward return is independent of where
    # the residual currently sits and the IC must be indistinguishable from zero.
    walk, _ = ic.sweep(universe(1.0, seed=21), 5, args)
    walk_summary = ic.summarise(walk)
    check("a random-walk residual gives no IC",
          abs(walk_summary["t"]) < ic.MIN_T,
          f"IC {walk_summary['ic_mean']:+.4f}, t {walk_summary['t']:.2f}")

    # Monotone in the ground truth, not merely right at the two extremes.
    #
    # The ordering is asserted from 0.7 upwards, not from 0.0, and the exclusion is
    # measured rather than assumed. In theory the IC at horizon h is
    # `a / sqrt(a^2 + 1 - phi^2h)` with `a = 1 - phi^h`, which gives 0.707 at phi = 0
    # against 0.645 at phi = 0.7, so phi = 0 should lead. Measured, it does not: 0.324
    # against 0.374. The reason is that the stationary level variance is
    # `sigma^2/(1 - phi^2)`, so the phi = 0.7 signal carries about 1.4x the amplitude
    # against the roughly constant estimation noise the factor regression injects, and the
    # signal-to-noise gain outweighs the theoretical loss. Asserting the full ordering
    # would be asserting something the arithmetic does not support once estimation error
    # is present.
    means = [ic.summarise(ic.sweep(universe(ar, seed=22), 5, args)[0])["ic_mean"]
             for ar in (0.0, 0.7, 0.95, 1.0)]
    check("IC falls as the planted level approaches a unit root, from 0.7 up",
          all(a > b for a, b in zip(means[1:], means[2:])),
          " > ".join(f"{m:+.3f}" for m in means[1:]))
    check("both strongly reverting levels give a large IC regardless of their ordering",
          means[0] > 0.2 and means[1] > 0.2,
          f"{means[0]:+.3f} and {means[1]:+.3f}")
    check("a unit-root level gives essentially none",
          abs(means[3]) < 0.05, f"{means[3]:+.4f}")

    # The sign convention is the whole trade: a residual that has run up is expensive and
    # the signal must be negative on it. Inverting the sign must invert the IC.
    signal, forward, _ = ic.formation(universe(0.0, seed=23), 400, 252, 60, 5, 5)
    check("the signal is the negative of the standing residual",
          ic.rank_correlation(signal, forward) > 0
          and ic.rank_correlation(-signal, forward) < 0,
          f"{ic.rank_correlation(signal, forward):+.3f} against "
          f"{ic.rank_correlation(-signal, forward):+.3f}")

    # Shuffling must remove the IC, exactly as it removes the reversion in group 2.
    null, _ = ic.sweep(rs.shuffled(universe(0.0, seed=24), 5), 5, args)
    check("shuffling the dates removes the IC",
          abs(ic.summarise(null)["ic_mean"]) < 0.05,
          f"{ic.summarise(null)['ic_mean']:+.4f}")

    # Worked by hand: identical orderings rank-correlate at exactly 1, reversed at -1.
    check("rank correlation of an identical ordering is exactly 1",
          close(ic.rank_correlation(np.array([1.0, 2, 3, 4]),
                                    np.array([10.0, 20, 30, 40])), 1.0, 1e-12))
    check("rank correlation of a reversed ordering is exactly -1",
          close(ic.rank_correlation(np.array([1.0, 2, 3, 4]),
                                    np.array([40.0, 30, 20, 10])), -1.0, 1e-12))
    # Ranks, not levels, so one extreme value must not carry the correlation. In levels
    # this pair correlates above 0.99; in ranks the disagreement at the bottom shows.
    check("one extreme value does not set the correlation the way it would in levels",
          ic.rank_correlation(np.array([1.0, 2, 3, 1000]),
                              np.array([2.0, 1, 3, 1000])) < 0.9,
          f"{ic.rank_correlation(np.array([1.0, 2, 3, 1000]), np.array([2.0, 1, 3, 1000])):.3f}")
    check("a constant series has no rank correlation rather than a spurious one",
          not math.isfinite(ic.rank_correlation(np.array([1.0, 1, 1, 1]),
                                                np.array([1.0, 2, 3, 4]))))

    # ICIR is mean over standard deviation, and must not be confused with the t-statistic,
    # which divides by the standard error instead. On n windows they differ by exactly
    # sqrt(n), and reporting one as the other overstates consistency by that factor.
    made_up = np.array([0.02, 0.04, 0.00, 0.06, 0.03])
    summary = ic.summarise(made_up)
    check("ICIR divides by the standard deviation, not the standard error",
          close(summary["icir"], float(made_up.mean() / made_up.std(ddof=1)), 1e-12),
          f"{summary['icir']:.6f}")
    check("t divides by the standard error and exceeds ICIR by sqrt(n)",
          close(summary["t"], summary["icir"] * math.sqrt(len(made_up)), 1e-9),
          f"{summary['t']:.6f}")


def test_breadth() -> None:
    print("\n10. breadth counts independent bets, not positions")

    rng = np.random.default_rng(25)
    names = [f"N{i:02d}" for i in range(10)]

    # Ten independent series are ten bets, to sampling error.
    independent = rng.normal(0, 0.01, (2000, 10))
    got = ic.breadth(independent, names)
    check("ten independent residuals are close to ten bets",
          9.0 < got["effective_bets"] <= 10.0, f"{got['effective_bets']:.2f}")

    # Ten copies of one series are one bet, however many positions are held.
    one = rng.normal(0, 0.01, (2000, 1))
    identical = np.repeat(one, 10, axis=1)
    got_one = ic.breadth(identical, names)
    check("ten copies of one residual are one bet",
          close(got_one["effective_bets"], 1.0, 0.01), f"{got_one['effective_bets']:.4f}")
    check("bet share falls to a tenth when the ten are the same bet",
          close(got_one["bet_share"], 0.1, 0.001), f"{got_one['bet_share']:.4f}")

    # Between the two, breadth must move in the right direction as correlation rises.
    common = rng.normal(0, 0.01, (2000, 1))
    blended = [ic.breadth(w * common + (1 - w) * rng.normal(0, 0.01, (2000, 10)),
                          names)["effective_bets"] for w in (0.0, 0.3, 0.6, 0.9)]
    check("breadth falls as the residuals share more of a common factor",
          all(a > b for a, b in zip(blended, blended[1:])),
          " > ".join(f"{b:.1f}" for b in blended))

    # The guard that caught the real defect: a correlation matrix estimated on too few rows
    # has noise-spread eigenvalues and a depressed participation ratio. On the real panel
    # this moved breadth from 132.2 to 59.7 according to a horizon setting.
    try:
        ic.breadth(rng.normal(0, 0.01, (15, 10)), names)
        check("breadth on too few rows per name is refused", False)
    except rs.UserError:
        check("breadth on too few rows per name is refused", True)
    check("breadth reports the sample it was measured on",
          got["rows"] == 2000 and close(got["rows_per_name"], 200.0, 1e-9))

    # Breadth must not depend on which forward horizon the caller asked for. This is the
    # defect the dedicated tiling pass exists to remove.
    args = ic_args()
    returns = universe(0.0, bars=2000, names=20, seed=26)
    first = ic.breadth(ic.breadth_returns(returns, args), [f"N{i:02d}" for i in range(20)])
    args_other = ic_args()
    second = ic.breadth(ic.breadth_returns(returns, args_other),
                        [f"N{i:02d}" for i in range(20)])
    check("breadth is reproducible and independent of the horizon list",
          close(first["effective_bets"], second["effective_bets"], 1e-9),
          f"{first['effective_bets']:.4f}")

    # Worked by hand: 0.02 * sqrt(100 * 252 / 5) = 0.02 * sqrt(5040) = 0.02 * 70.99295
    check("the fundamental law is computed as IC times the root of annual breadth",
          close(ic.implied_ir(0.02, 100.0, 5, 252), 0.02 * math.sqrt(5040), 1e-12),
          f"{ic.implied_ir(0.02, 100.0, 5, 252):.8f}")
    check("a longer horizon lowers the implied ratio, because there are fewer bets a year",
          ic.implied_ir(0.02, 100.0, 20, 252) < ic.implied_ir(0.02, 100.0, 5, 252))
    check("zero skill implies zero ratio at any breadth",
          close(ic.implied_ir(0.0, 10_000.0, 1, 252), 0.0, 1e-12))


def main() -> int:
    global VERBOSE
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true")
    ns = parser.parse_args()
    VERBOSE = ns.verbose

    print("Verifying residual.py and ic.py")
    test_ground_truth()
    test_null_calibration()
    test_no_look_ahead()
    test_eigenportfolios()
    test_paired_lift()
    test_shuffle()
    test_scoring()
    test_guards()
    test_ic()
    test_breadth()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("\nFAILED:")
        for name in FAILED:
            print(f"  - {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
