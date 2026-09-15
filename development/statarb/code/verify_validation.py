"""Step 4.5 — prove the validation layer is not lying.

The same treatment the other four suites give the rest of the pipeline. This one
matters more than most, because a validation layer that is wrong does not merely
give a wrong answer — it gives false confidence in every answer above it.

The checks that carry weight:

    Benjamini-Hochberg   against a set worked out by hand, and against the two
                         boundaries: everything significant, nothing significant.

    the bootstrap        on independent random walks the mean rejection count
                         must land on `N x level`, because expectation is linear
                         whatever the dependence. This is the check that caught
                         a wrong claim in `multiple_testing.py` itself, which
                         reported an "effective tests" figure as an expected
                         count. It is not one.

    block resampling     the resample must keep each series' own serial
                         correlation and destroy every relation between series.
                         Both halves are checked, because a resample that keeps
                         nothing under-states the noise floor and one that keeps
                         too much over-states it.

    no aggregation       no function may return a single combined score. The
                         study this plan cites found a composite had no forward
                         relationship, and the temptation to build one is strong
                         enough to be worth a failing test.

    python verify_validation.py
    python verify_validation.py -v --trials 2000
"""
from __future__ import annotations

import argparse
import ast
import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cointegration as ci                                        # noqa: E402
import deflated_sharpe as ds                                      # noqa: E402
import multiple_testing as mt                                     # noqa: E402
import overfit as of                                              # noqa: E402
import purged_cv as pc                                            # noqa: E402
import risk as rk                                                 # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []
VERBOSE = False


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(name)
    if not ok or VERBOSE:
        print(("  ok   " if ok else "  FAIL ") + name + (f"   {detail}" if detail else ""))


def close(got: float, want: float, tol: float) -> bool:
    return math.isfinite(got) and abs(got - want) <= tol


def raises(fn, *args, **kwargs) -> bool:
    try:
        fn(*args, **kwargs)
    except Exception:
        return True
    return False


# ------------------------------------------------- 1. false discovery rate
def test_benjamini_hochberg() -> None:
    print("\n1. Benjamini-Hochberg - controlling the share of the list that is wrong")

    # Worked by hand. N = 5, fdr = 0.10, limits are k/5 * 0.10 = .02 .04 .06 .08 .10
    # sorted p: .001 .008 .039 .041 .900
    #           .001<=.02 yes, .008<=.04 yes, .039<=.06 yes, .041<=.08 yes, .9 no
    # largest k that passes is 4, so the threshold is .041 and four survive.
    p = np.array([0.900, 0.008, 0.041, 0.001, 0.039])
    mask, thr = mt.benjamini_hochberg(p, 0.10)
    check("the hand-worked example gives four survivors", int(mask.sum()) == 4,
          f"{int(mask.sum())}")
    check("and a threshold of the fourth smallest p", close(thr, 0.041, 1e-12),
          f"{thr}")
    check("the survivors are exactly the four smallest",
          set(np.flatnonzero(mask)) == {1, 2, 3, 4})

    check("nothing survives when every p-value is large",
          int(mt.benjamini_hochberg(np.array([0.4, 0.6, 0.9]), 0.10)[0].sum()) == 0)
    check("and the threshold is then not a number",
          not math.isfinite(mt.benjamini_hochberg(np.array([0.4, 0.6]), 0.10)[1]))
    check("everything survives when every p-value is tiny",
          int(mt.benjamini_hochberg(np.array([1e-9, 2e-9, 3e-9]), 0.10)[0].sum()) == 3)
    check("a stricter rate keeps no more than a looser one",
          mt.benjamini_hochberg(p, 0.01)[0].sum()
          <= mt.benjamini_hochberg(p, 0.20)[0].sum())
    check("it is never stricter than the raw level on the smallest p-value",
          mt.benjamini_hochberg(np.array([0.001, 0.9]), 0.10)[0][0])
    check("an empty set of p-values does not raise",
          mt.benjamini_hochberg(np.array([]), 0.10)[0].size == 0)
    check("a rate of zero is refused", raises(mt.benjamini_hochberg, p, 0.0))
    check("a rate of one is refused", raises(mt.benjamini_hochberg, p, 1.0))
    check("a negative rate is refused", raises(mt.benjamini_hochberg, p, -0.1))

    # Under a complete null every discovery is false, so BH must find almost
    # nothing. Averaged over many draws its false discovery rate is below fdr.
    rng = np.random.default_rng(3)
    found = [int(mt.benjamini_hochberg(rng.uniform(size=200), 0.10)[0].sum())
             for _ in range(300)]
    check("under a complete null it names almost nobody",
          float(np.mean(found)) < 2.0, f"mean {np.mean(found):.2f} of 200")

    # With real signal present it must find most of it.
    planted = np.concatenate([rng.uniform(0, 1e-5, 20), rng.uniform(size=180)])
    mask, _ = mt.benjamini_hochberg(planted, 0.10)
    check("with twenty planted discoveries it finds most of them",
          int(mask[:20].sum()) >= 18, f"{int(mask[:20].sum())} of 20")
    check("and few of the rest", int(mask[20:].sum()) <= 4,
          f"{int(mask[20:].sum())} of 180")


# ------------------------------------------------- 2. the null, by simulation
def test_bootstrap_null(trials: int) -> None:
    print("\n2. the bootstrap - what chance alone produces, measured")

    rng = np.random.default_rng(11)
    n, level = 400, 0.05
    # Independent random walks: no relationship anywhere, so the rejection count
    # must centre on N x level. Dependence would widen it, never move the mean.
    hits = 0
    for _ in range(trials):
        y = np.cumsum(rng.normal(0, 0.01, n))
        x = np.cumsum(rng.normal(0, 0.01, n))
        if ci.engle_granger(y, x, trend="c", lags=1).pvalue < level:
            hits += 1
    rate = hits / trials
    tol = 3 * math.sqrt(level * (1 - level) / trials)
    check("the test rejects at its nominal level on independent walks",
          abs(rate - level) <= tol, f"{rate:.2%} against {level:.0%} +-{tol:.2%}")

    counts = np.array([12, 9, 15, 11, 13])
    boot = mt.Bootstrap(replicates=5, rejections=counts, pairs=100, level=0.05)
    check("the bootstrap mean is the mean of its replicates",
          close(boot.mean, 12.0, 1e-12))
    check("its standard error shrinks with the replicate count",
          mt.Bootstrap(5, np.tile(counts, 4), 100, 0.05).standard_error
          < boot.standard_error)
    check("a count no replicate reached has a small p-value",
          boot.p_value_of(99) < 0.2, f"{boot.p_value_of(99):.3f}")
    check("the bootstrap p-value is never exactly zero",
          boot.p_value_of(10_000) > 0.0,
          "a rate of zero claims more than the replicate count supports")
    check("a count every replicate reached has a p-value of one",
          close(boot.p_value_of(0), 1.0, 1e-12))
    check("more extreme observations give smaller p-values",
          boot.p_value_of(15) <= boot.p_value_of(11))


def test_block_resampling() -> None:
    print("\n3. block resampling - keep the series, break the relation")
    rng = np.random.default_rng(5)
    n, block = 4000, 25

    # A strongly autocorrelated series. Blocks must preserve that; drawing single
    # observations would not, and a whiter null is easier to reject, which would
    # understate the noise floor.
    raw = np.zeros(n)
    for t in range(1, n):
        raw[t] = 0.7 * raw[t - 1] + rng.normal(0, 1)

    out = mt.block_bootstrap(raw, block, rng)
    check("the resample is the same length as the original", out.size == n,
          f"{out.size}")

    def ac1(v):
        return float(np.corrcoef(v[:-1], v[1:])[0, 1])

    singles = rng.choice(raw, size=n, replace=True)
    check("block resampling keeps the serial correlation",
          abs(ac1(out) - ac1(raw)) < 0.15,
          f"{ac1(out):.3f} against {ac1(raw):.3f}")
    check("single-observation resampling destroys it, which is why blocks are used",
          abs(ac1(singles)) < 0.1, f"{ac1(singles):.3f}")
    check("a longer block keeps more of it",
          abs(ac1(mt.block_bootstrap(raw, 200, rng)) - ac1(raw))
          <= abs(ac1(mt.block_bootstrap(raw, 2, rng)) - ac1(raw)) + 0.02)

    # Two series resampled with independent draws must end up unrelated.
    other = np.zeros(n)
    for t in range(1, n):
        other[t] = 0.7 * other[t - 1] + rng.normal(0, 1)
    a = mt.block_bootstrap(raw, block, rng)
    b = mt.block_bootstrap(other, block, rng)
    check("two independently resampled series are unrelated",
          abs(float(np.corrcoef(a, b)[0, 1])) < 0.2,
          f"{float(np.corrcoef(a, b)[0, 1]):.3f}")
    check("a block shorter than one bar is refused",
          raises(mt.block_bootstrap, raw, 0, rng))
    check("a block longer than the series does not raise",
          mt.block_bootstrap(raw, n * 2, rng).size == n)


# ------------------------------------------------- 4. counting the tests
def test_effective_tests() -> None:
    print("\n4. effective tests - how many independent things were tried")
    rng = np.random.default_rng(13)
    n = 900
    index = pd.date_range("2015-01-01", periods=n, freq="D", tz="UTC")

    independent = pd.DataFrame(
        {f"p{i}": rng.normal(0, 1, n) for i in range(6)}, index=index)
    check("six independent spreads are six tests",
          close(mt.effective_tests(independent), 6.0, 0.5),
          f"{mt.effective_tests(independent):.2f}")

    one = rng.normal(0, 1, n)
    identical = pd.DataFrame({f"p{i}": one * (i + 1) for i in range(6)}, index=index)
    check("six copies of one spread are one test",
          close(mt.effective_tests(identical), 1.0, 0.05),
          f"{mt.effective_tests(identical):.3f}")

    f1, f2 = rng.normal(0, 1, n), rng.normal(0, 1, n)
    from_two = pd.DataFrame({"a": f1, "b": f2, "c": f1 + f2,
                             "d": f1 - f2, "e": 2 * f1 + f2}, index=index)
    got = mt.effective_tests(from_two)
    check("five spreads built from two factors are not five tests", got < 4.0,
          f"{got:.2f}")
    check("and not one either", got > 1.5, f"{got:.2f}")
    check("a single spread is one test",
          close(mt.effective_tests(independent[["p0"]]), 1.0, 1e-12))
    check("too few shared bars is refused",
          raises(mt.effective_tests, independent.iloc[:5]))
    check("it uses the same definition the risk layer uses",
          close(mt.effective_tests(independent),
                rk.effective_bets(independent.corr()), 1e-12))


# ------------------------------------------------- 5. deflation
def test_deflated_sharpe() -> None:
    print("\n5. deflated Sharpe - charging a result for the search behind it")
    rng = np.random.default_rng(17)

    check("a flat series has no Sharpe", not math.isfinite(ds.sharpe(np.ones(50))))
    check("one observation is not enough",
          not math.isfinite(ds.sharpe(np.array([1.0]))))
    check("Sharpe is mean over deviation",
          close(ds.sharpe(np.array([1.0, 2.0, 3.0])),
                2.0 / float(np.std([1.0, 2.0, 3.0], ddof=1)), 1e-12))
    check("scaling every return leaves it unchanged",
          close(ds.sharpe(np.array([1.0, 2.0, 3.0])),
                ds.sharpe(np.array([10.0, 20.0, 30.0])), 1e-12))

    normal = rng.normal(0, 1, 200_000)
    sk, ku = ds.moments(normal)
    check("a normal sample has no skew", abs(sk) < 0.05, f"{sk:+.4f}")
    check("and kurtosis of three, not zero", close(ku, 3.0, 0.1), f"{ku:.3f}")

    r = rng.normal(0.05, 1.0, 500)
    v1 = ds.assess(r, pair="A~B", trials=1, trial_sd=0.3, level=0.05)
    check("one trial deflates against a benchmark of zero",
          close(v1.benchmark, 0.0, 1e-12))
    check("and the deflated Sharpe then equals the probabilistic one",
          close(v1.dsr, v1.psr, 1e-12))
    check("trials with no spread deflate against zero as well",
          close(ds.expected_max_sharpe(1000, 0.0), 0.0, 1e-12))
    check("more trials raise the benchmark",
          ds.expected_max_sharpe(1000, 0.3) > ds.expected_max_sharpe(10, 0.3))
    check("a wider spread between trials raises it too",
          ds.expected_max_sharpe(100, 0.6) > ds.expected_max_sharpe(100, 0.3))
    check("the benchmark is never negative", ds.expected_max_sharpe(2, 0.3) >= 0.0)

    v_few = ds.assess(r, pair="A~B", trials=5, trial_sd=0.3, level=0.05)
    v_many = ds.assess(r, pair="A~B", trials=5000, trial_sd=0.3, level=0.05)
    check("the same series survives fewer trials more easily",
          v_few.dsr > v_many.dsr, f"{v_few.dsr:.3f} against {v_many.dsr:.3f}")
    check("a long search can deflate a real-looking Sharpe to nothing",
          v_many.dsr < 0.5)

    strong = rng.normal(0.30, 1.0, 3000)
    check("a strong Sharpe on a long sample survives a modest search",
          ds.assess(strong, pair="A~B", trials=50, trial_sd=0.1,
                    level=0.05).survives)
    losing = rng.normal(-0.10, 1.0, 1000)
    check("a negative Sharpe never survives",
          not ds.assess(losing, pair="A~B", trials=2, trial_sd=0.01,
                        level=0.05).survives)
    check("and says so plainly",
          "nothing for the search" in ds.assess(
              losing, pair="A~B", trials=2, trial_sd=0.01, level=0.05).reason())

    flat = ds.probabilistic_sharpe(0.2, 0.0, 500, skew=0.0, kurtosis=3.0)
    fat = ds.probabilistic_sharpe(0.2, 0.0, 500, skew=-1.0, kurtosis=9.0)
    check("negative skew and fat tails lower the probabilistic Sharpe",
          fat < flat, f"{fat:.4f} against {flat:.4f}")
    check("a longer sample raises it",
          ds.probabilistic_sharpe(0.2, 0.0, 2000, 0.0, 3.0)
          > ds.probabilistic_sharpe(0.2, 0.0, 200, 0.0, 3.0))
    check("a Sharpe exactly at the benchmark is a coin flip",
          close(ds.probabilistic_sharpe(0.2, 0.2, 500, 0.0, 3.0), 0.5, 1e-9))

    logs = HERE.parent / "logs"
    dump = logs / "dump-equities.csv"
    if dump.exists():
        check("a per-pair dump is not counted as a trial log",
              not ds.is_trial_log(dump))
    screens = logs / "screens.csv"
    if screens.exists():
        check("a screen log is not counted as a strategy trial",
              not ds.is_trial_log(screens))


# ------------------------------------------------- 6. overfitting
def test_overfit() -> None:
    print("\n6. CSCV - was the winner chosen, or did it get lucky?")
    rng = np.random.default_rng(19)
    rows, cols = 1200, 8
    labels = [f"c{i}" for i in range(cols)]

    check("the relative rank of the worst column is below the midpoint",
          of.logit(1, 8) < 0)
    check("and of the best, above it", of.logit(8, 8) > 0)
    check("the middle rank sits near zero", abs(of.logit(4.5, 8)) < 0.2)
    check("a single column has no rank to take", not math.isfinite(of.logit(1, 1)))

    noise = rng.normal(0, 1, (rows, cols))
    r_noise = of.cscv(noise, 10, labels)
    check("a sweep over noise is called overfit",
          r_noise.pbo > 0.35, f"PBO {r_noise.pbo:.2f}")
    check("its median log-odds are not positive",
          r_noise.median_logit <= 0.0, f"{r_noise.median_logit:+.3f}")


    real = rng.normal(0, 1, (rows, cols))
    real[:, 3] += 0.35
    r_real = of.cscv(real, 10, labels)
    check("a sweep with a genuine edge is not called overfit",
          r_real.pbo < 0.10, f"PBO {r_real.pbo:.3f}")
    check("and the same column wins nearly every split",
          max(r_real.chosen_counts().values()) >= 0.9 * r_real.splits)
    check("noise is called overfit more often than a real edge",
          r_noise.pbo > r_real.pbo)
    check("and a real edge ranks better out of sample than noise does",
          r_real.median_logit > r_noise.median_logit,
          f"{r_real.median_logit:+.2f} against {r_noise.median_logit:+.2f}")

    check("the split count is blocks-choose-half", r_real.splits == 252,
          f"{r_real.splits}")
    check("an odd block count is refused", raises(of.cscv, noise, 9, labels))
    check("too few blocks is refused", raises(of.cscv, noise, 2, labels))
    check("a single configuration is refused",
          raises(of.cscv, noise[:, :1], 10, ["c0"]))
    check("a sample too short for the blocks is refused",
          raises(of.cscv, noise[:8], 10, labels))


# ------------------------------------------------- 7. leakage
def test_purging() -> None:
    print("\n7. purged k-fold - not handing the answer across the boundary")
    n = 1000
    check("training rows inside the test fold are always excluded",
          not set(pc.training_index(n, 400, 500, horizon=0, embargo=0))
          & set(range(400, 501)))
    check("a row whose window reaches the test fold is purged",
          395 not in set(pc.training_index(n, 400, 500, horizon=10, embargo=0)))
    check("a row whose window stops short of it is kept",
          380 in set(pc.training_index(n, 400, 500, horizon=10, embargo=0)))
    check("the embargo drops rows just after the fold",
          505 not in set(pc.training_index(n, 400, 500, horizon=0, embargo=20)))
    check("and keeps rows beyond the margin",
          530 in set(pc.training_index(n, 400, 500, horizon=0, embargo=20)))
    check("a longer horizon never keeps more rows",
          pc.training_index(n, 400, 500, horizon=50, embargo=0).size
          <= pc.training_index(n, 400, 500, horizon=5, embargo=0).size)
    check("a negative horizon is refused",
          raises(pc.training_index, n, 400, 500, horizon=-1, embargo=0))
    check("fewer than two folds is refused", raises(pc.fold_bounds, 100, 1))
    check("folds cover every observation exactly once",
          sum(hi - lo + 1 for lo, hi in pc.fold_bounds(1000, 7)) == 1000)

    # Purging shown to do something, on data where the overlap is constructed
    # rather than hoped for. Labels are a rolling sum over a long window, so
    # neighbouring rows share most of their outcome.
    rng = np.random.default_rng(23)
    horizon, size = 200, 2000
    steps = rng.normal(0, 1, size + horizon)
    label = np.array([steps[i:i + horizon].sum() for i in range(size)])
    feature = label + rng.normal(0, 0.5, size)

    scored = pc.run(feature, label, folds=10, horizon=horizon, embargo=0)
    rows_plain = float(np.mean(scored["plain"].trained_on))
    rows_purged = float(np.mean(scored["purged"].trained_on))
    # Ten folds of 200 rows, horizon 200: purging drops about one horizon on
    # each side of the test fold, so roughly 400 of 2,000 rows go. That is the
    # derived figure; an earlier version asserted a quarter, which was a guess.
    removed = 1.0 - rows_purged / rows_plain
    check("purging removes about a horizon either side of each fold",
          0.10 < removed < 0.35, f"{removed:.1%} removed")
    check("which is far more than the default no-op case",
          removed > 0.05, f"{removed:.1%}")
    check("both regimes still score every fold",
          scored["plain"].usable_folds == 10 and scored["purged"].usable_folds == 10)
    check("the plain score on overlapping labels is high",
          scored["plain"].mean > 0.5, f"{scored['plain'].mean:.3f}")
    check("a longer embargo never keeps more training rows",
          float(np.mean(pc.run(feature, label, folds=10, horizon=horizon,
                               embargo=100)["purged + embargo"].trained_on))
          <= rows_purged)


# ------------------------------------------------- 8. what it must not do
def test_no_aggregation() -> None:
    print("\n5. the gates stay separate")
    modules = ("multiple_testing", "deflated_sharpe", "overfit", "purged_cv")
    source = "".join((HERE / f"{m}.py").read_text(encoding="utf-8") for m in modules)
    names = {n.name for m in modules
             for n in ast.walk(ast.parse(
                 (HERE / f"{m}.py").read_text(encoding="utf-8")))
             if isinstance(n, ast.FunctionDef)}
    banned = {"score", "composite", "overall", "combined", "aggregate",
              "total_score", "quality_score"}
    check("no function pretends to be a single combined score",
          not (names & banned), f"found {sorted(names & banned)}")
    check("the population and individual verdicts are reported separately",
          "population:" in source and "individuals:" in source)
    check("the docstring records that effective tests is not an expected count",
          "does not reduce the expected count" in source)

    for name in ("pair_report", "backtest", "cointegration", "hedge", "health",
                 "strategy", "costs", "outcomes", "thresholds", "sizing"):
        path = HERE / f"{name}.py"
        if not path.exists():
            continue
        imported = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                imported.add(node.module.split(".")[0])
        check(f"{name}.py does not import Step 4",
              not ({"multiple_testing", "deflated_sharpe", "overfit",
                    "purged_cv"} & imported))


def main() -> int:
    global VERBOSE
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--trials", type=int, default=600,
                        help="random-walk pairs for the calibration check")
    ns = parser.parse_args()
    VERBOSE = ns.verbose

    print("Verifying multiple_testing.py, deflated_sharpe.py, "
          "overfit.py and purged_cv.py")
    test_benjamini_hochberg()
    test_bootstrap_null(ns.trials)
    test_block_resampling()
    test_effective_tests()
    test_deflated_sharpe()
    test_overfit()
    test_purging()
    test_no_aggregation()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("\nFAILED:")
        for name in FAILED:
            print(f"  - {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
