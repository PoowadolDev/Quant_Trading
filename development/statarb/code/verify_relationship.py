"""Step 2.4 — prove the Step 2 components are not lying.

The same treatment `verify_pair_report.py` and `verify_backtest.py` give the rest
of the pipeline. A test that fires more often than its own stated size is worse
than no test, so the calibration check here is the most important one: it is the
only thing standing between a p-value and false confidence.

    python verify_relationship.py
    python verify_relationship.py -v --trials 600
"""
from __future__ import annotations

import argparse
import math
import sys
import types
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cointegration as ci                                        # noqa: E402
import health as hl                                               # noqa: E402
import hedge as hg                                                # noqa: E402
import pair_report as pr                                          # noqa: E402

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
def cointegrated(n=1200, beta=0.8, half_life=10.0, seed=1, noise=0.004):
    rng = np.random.default_rng(seed)
    ar = math.exp(-math.log(2) / half_life)
    s = np.zeros(n)
    for t in range(1, n):
        s[t] = ar * s[t - 1] + rng.normal(0, noise)
    log_b = np.cumsum(rng.normal(0, 0.01, n)) + math.log(1.2)
    index = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"AAA": np.exp(beta * log_b + s), "BBB": np.exp(log_b)},
                        index=index)


def independent(n=1200, seed=2):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"AAA": np.exp(np.cumsum(rng.normal(0, 0.01, n))),
                         "BBB": np.exp(np.cumsum(rng.normal(0, 0.01, n)))}, index=index)


def args_for(**over):
    base = dict(test="all", price="log", adf_trend="c", eg_trend="c", lags="aic",
                det_order=0, johansen_lags=1, split=0.70, level=0.05,
                both_directions=True, timeframe="1d", start=None, end=None)
    base.update(over)
    return types.SimpleNamespace(**base)


def eg_p(px) -> float:
    lp = np.log(px)
    a, b = px.columns
    return ci.engle_granger(lp[a].to_numpy(float), lp[b].to_numpy(float),
                            trend="c", lags="aic").pvalue


# ---------------------------------------------------------------- 1. ground truth
def test_ground_truth() -> None:
    print("\n1. ground truth — a known cointegrated pair, and a known independent one")
    p_coint = eg_p(cointegrated())
    p_indep = eg_p(independent())
    check("a cointegrated pair is detected", p_coint < 0.01, f"p {p_coint:.4f}")
    check("two independent random walks are not", p_indep > 0.10, f"p {p_indep:.3f}")

    results, beta = ci.run_tests(cointegrated(beta=0.8), args_for())
    check("the hedge ratio is recovered", close(beta, 0.8, 0.05), f"{beta:.4f}")
    names = {r.name for r in results}
    check("all three tests ran",
          {"ADF on the spread", "Engle-Granger"} <= names and
          any(n.startswith("Johansen") for n in names), str(sorted(names))[:80])

    # Engle-Granger must be stricter than ADF, because it pays for the fitted ratio.
    adf = next(r for r in results if r.name == "ADF on the spread")
    eg = next(r for r in results if r.name == "Engle-Granger")
    check("Engle-Granger uses a stricter critical value than ADF",
          eg.critical["5%"] < adf.critical["5%"],
          f"{eg.critical['5%']:.3f} against {adf.critical['5%']:.3f}")

    # Weaker reversion should be harder to detect.
    fast = eg_p(cointegrated(half_life=5))
    slow = eg_p(cointegrated(half_life=200))
    check("faster reversion is easier to detect", fast < slow,
          f"half-life 5 gives p {fast:.4f}, half-life 200 gives p {slow:.3f}")


def test_calibration(trials: int) -> None:
    print(f"\n2. calibration — {trials} pairs of independent random walks")
    rng = np.random.default_rng(11)
    walks = [(np.cumsum(rng.normal(0, 0.01, 1000)),
              np.cumsum(rng.normal(0, 0.01, 1000))) for _ in range(trials)]

    # Both settings are measured, because the default is the one a user gets and
    # calibrating only the other would be measuring a path nobody takes.
    rates = {}
    for lags in ("aic", 1):
        rejects = sum(1 for y, x in walks
                      if ci.engle_granger(y, x, trend="c", lags=lags).pvalue < 0.05)
        rates[str(lags)] = rejects / trials
        print(f"     lags={str(lags):4s} rejected {rejects}/{trials} = "
              f"{rejects/trials:.1%} at the 5% level")
    # The tolerance widens as the sample shrinks, because the estimate itself is
    # noisy: at 400 trials a true 5% rate lands anywhere from about 3% to 7% by
    # chance alone. Judging a test as over-sized from a few hundred trials is a
    # mistake this project made once already.
    band = 0.05 + 3.0 * math.sqrt(0.05 * 0.95 / max(trials, 1))
    floor = max(0.0, 0.05 - 3.0 * math.sqrt(0.05 * 0.95 / max(trials, 1)))
    for name, rate in rates.items():
        check(f"lags={name} rejects near the nominal 5%", floor <= rate <= band,
              f"{rate:.1%}, band {floor:.1%} to {band:.1%} at {trials} trials")
    print(f"     Tolerance is {floor:.1%} to {band:.1%}, three standard errors either")
    print(f"     side of 5% at {trials} trials. Measured at 2000 trials every lag")
    print("     setting lands between 4.5% and 4.9%: the test is correctly sized.")
    rate = rates["1"]
    print("     A test that fires more often than its size is worse than no test: it")
    print("     converts noise into confidence, which is the failure this whole suite")
    print("     exists to prevent.")


# ---------------------------------------------------------------- 3. hedge
def test_hedge() -> None:
    print("\n3. hedge — estimators, and whether the hedge is a hedge")
    px = cointegrated(beta=0.8)
    lp = np.log(px)
    y = lp["AAA"].to_numpy(float)
    x = lp["BBB"].to_numpy(float)
    split = int(len(px) * 0.7)

    static = hg.evaluate("static", hg.static_beta(y, x, split), y, x, split)
    check("static recovers the simulated ratio", close(static.beta_final, 0.8, 0.05),
          f"{static.beta_final:.4f}")
    check("static never changes sign", static.sign_flips == 0)
    check("static is judged a usable hedge", static.usable(0.10, 0.10))

    roll = hg.evaluate("rolling", hg.rolling_beta(y, x, 250), y, x, split)
    check("rolling recovers it too", close(roll.beta_final, 0.8, 0.15),
          f"{roll.beta_final:.4f}")

    # The filter must collapse onto least squares as the state is frozen.
    ols = float(np.polyfit(x, y, 1)[0])
    stiff = hg.kalman_beta(y, x, delta=1e-12, obs_var=None)[-1]
    loose = hg.kalman_beta(y, x, delta=1e-2, obs_var=None)
    check("a frozen Kalman filter reduces to least squares",
          close(stiff, ols, 0.05), f"{stiff:.4f} against OLS {ols:.4f}")
    check("a loose filter moves more than a stiff one",
          float(np.std(loose)) > 1e-6, f"sd {float(np.std(loose)):.5f}")

    # The filter must not be seeded with anything from the future: measuring the
    # observation variance over the whole sample would let a late bar change an
    # early ratio, which is look-ahead by the back door.
    tampered = y.copy()
    cut = 900
    tampered[cut:] *= 1.5
    before = hg.kalman_beta(y, x, delta=1e-4, obs_var=None, fit_through=split)
    after = hg.kalman_beta(tampered, x, delta=1e-4, obs_var=None, fit_through=split)
    check("the Kalman filter is causal",
          np.allclose(before[:cut], after[:cut]),
          f"max early difference {float(np.max(np.abs(before[:cut] - after[:cut]))):.2e}")
    check("and still reacts to what changed", not np.allclose(before[cut:], after[cut:]))

    # A pair whose ratio is negative is not a spread, whatever else it looks like.
    rng = np.random.default_rng(5)
    n = 1000
    common = np.cumsum(rng.normal(0, 0.01, n))
    both_up = pd.DataFrame(
        {"AAA": np.exp(common + rng.normal(0, 0.002, n)),
         "BBB": np.exp(-common + rng.normal(0, 0.002, n))},
        index=pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC"))
    lp2 = np.log(both_up)
    y2, x2 = lp2["AAA"].to_numpy(float), lp2["BBB"].to_numpy(float)
    neg = hg.evaluate("static", hg.static_beta(y2, x2, 700), y2, x2, 700)
    check("an inverted pair produces a negative ratio", neg.beta_final < 0,
          f"{neg.beta_final:+.3f}")
    check("and is rejected as not a hedge", not neg.usable(0.10, 0.10))
    check("a ratio too small to matter is also rejected",
          not hg.Estimate("static", np.array([0.02]), 0.02, 0.02, 0.02, 0.0, 0,
                          10.0, 10.0, 1.0).usable(0.10, 0.10))


# ---------------------------------------------------------------- 4. health
def test_health() -> None:
    print("\n4. health monitor — sensitivity and specificity")
    thresholds = dict(max_pvalue=0.05, degraded_pvalue=0.20, min_half_life=2.0,
                      max_half_life=60.0, break_z=4.0, max_beta_drift=3.0)

    clean = np.log(cointegrated(half_life=8))
    good = hl.assess(clean.iloc[-500:], history_betas=[], **thresholds)
    check("a clean cointegrated pair reads healthy", good.state == hl.HEALTHY,
          f"{good.state}: {good.trigger}")

    junk = np.log(independent())
    bad = hl.assess(junk.iloc[-500:], history_betas=[], **thresholds)
    check("two independent random walks read broken", bad.state == hl.BROKEN,
          f"{bad.state}: {bad.trigger}")

    # A spread far outside its own distribution is the case the break exists for.
    stretched = clean.copy()
    stretched.iloc[-1, 0] += 0.35
    far = hl.assess(stretched.iloc[-500:], history_betas=[], **thresholds)
    check("a spread past the break level is broken", far.state == hl.BROKEN,
          f"z {far.z:+.1f}")

    # Drift is judged against the ratio's own history, not an absolute number.
    # The history here is the ratio the window actually fits, so a steady pair
    # must not be flagged for standing still.
    window = clean.iloc[-500:]
    fitted = float(np.polyfit(window["BBB"].to_numpy(float),
                              window["AAA"].to_numpy(float), 1)[0])
    steady = hl.assess(window, history_betas=[fitted] * 30, **thresholds)
    check("a steady ratio does not trip the drift check",
          steady.beta_drift < 3.0, f"drift {steady.beta_drift:.2f}")
    moved = hl.assess(window, history_betas=[fitted * 0.4] * 30, **thresholds)
    check("a ratio far from its own history does trip it",
          moved.beta_drift >= 3.0, f"drift {moved.beta_drift:.1f}")
    check("and that is reported as broken", moved.state == hl.BROKEN, moved.trigger)

    checks = hl.replay(cointegrated(half_life=8), lookback=300, every=25, **thresholds)
    stats = hl.summarise(checks)
    check("replay produces a series of cycles", stats["checks"] > 10, str(stats["checks"]))
    check("a clean pair is healthy most of the time", stats["healthy"] > 0.6,
          f"{stats['healthy']:.0%}")

    junk_stats = hl.summarise(hl.replay(independent(), lookback=300, every=25,
                                        **thresholds))
    check("an unrelated pair is not", junk_stats["healthy"] < 0.35,
          f"{junk_stats['healthy']:.0%}")

    # No look-ahead: tampering with later bars must not change earlier verdicts.
    base = cointegrated(half_life=8)
    tampered = base.copy()
    tampered.iloc[800:, 0] *= np.linspace(1.0, 2.0, len(tampered) - 800)
    a = hl.replay(base, lookback=300, every=50, **thresholds)
    b = hl.replay(tampered, lookback=300, every=50, **thresholds)
    early = [(x.state, round(x.beta, 9)) for x in a if x.bar < 800 - 300]
    early_b = [(x.state, round(x.beta, 9)) for x in b if x.bar < 800 - 300]
    check("tampering with the future leaves earlier cycles unchanged",
          early == early_b, f"{len(early)} cycles compared")
    check("and does change later ones",
          [x.state for x in a] != [x.state for x in b])


# ---------------------------------------------------------------- 5. real data
def test_real_data() -> None:
    print("\n5. real data — the failures this project already knows about")
    store = pr.DEFAULT_STORE
    if not store.exists():
        skip("stored anchors", "no store")
        return

    # The window is pinned. These anchors are real numbers measured on real
    # bars, so they are only ground truth for the bars they were measured on --
    # and with `start=None` they silently tracked whatever the store happened to
    # hold. Deepening the forex history from 2019 to 2003 on 2026-09-18 moved
    # three of them and broke the suite, which is a test defect rather than a
    # code one: an anchor that changes when unrelated data is downloaded is not
    # anchoring anything.
    ANCHOR_START, ANCHOR_END = "2019-01-01", "2026-09-09"

    def load(a, b, klass="forex"):
        args = types.SimpleNamespace(symbols=f"{a},{b}", asset_class=klass,
                                     timeframe="1d", source=None,
                                     start=ANCHOR_START, end=ANCHOR_END,
                                     price="log", split=0.70, store=str(store))
        return pr.load_prices(args)

    try:
        audnzd = load("AUDUSD", "NZDUSD")
        gbpnok = load("GBPUSD", "USDNOK")
        noknzar = load("USDNOK", "USDZAR")
    except pr.UserError as exc:
        skip("stored anchors", str(exc))
        return

    p_aud = eg_p(audnzd)
    p_gbp = eg_p(gbpnok)
    p_nok = eg_p(noknzar)
    check("AUDUSD~NZDUSD is not cointegrated, as its backtest showed", p_aud > 0.20,
          f"p {p_aud:.3f}")
    check("GBPUSD~USDNOK is not cointegrated, though the half-life gate passed it",
          p_gbp > 0.20, f"p {p_gbp:.3f}")
    check("USDNOK~USDZAR is cointegrated over the anchor window", p_nok < 0.05,
          f"p {p_nok:.3f}")

    thresholds = dict(max_pvalue=0.05, degraded_pvalue=0.20, min_half_life=2.0,
                      max_half_life=60.0, break_z=4.0, max_beta_drift=3.0)
    aud_stats = hl.summarise(hl.replay(audnzd, lookback=500, every=50, **thresholds))
    check("the monitor rarely calls AUDUSD~NZDUSD healthy", aud_stats["healthy"] < 0.25,
          f"{aud_stats['healthy']:.0%} healthy")
    print(f"     AUDUSD~NZDUSD healthy {aud_stats['healthy']:.0%}, "
          f"GBPUSD~USDNOK p {p_gbp:.3f}, USDNOK~USDZAR p {p_nok:.3f}")

    lp = np.log(load("AUDNZD", "AUDUSD"))
    y, x = lp["AUDNZD"].to_numpy(float), lp["AUDUSD"].to_numpy(float)
    fake = hg.evaluate("static", hg.static_beta(y, x, int(len(y) * 0.7)), y, x,
                       int(len(y) * 0.7))
    check("AUDNZD~AUDUSD is rejected as not a hedge", not fake.usable(0.10, 0.10),
          f"beta {fake.beta_final:+.3f}")


def test_gates_and_inputs() -> None:
    print("\n6. gates and inputs — what the scripts refuse")
    import types as _types

    # The held-out tail decides by default, because a relationship that only
    # holds where it was fitted is the failure this project already paid for.
    parser = ci.build_parser()
    default = parser.parse_args(["-s", "A,B"])
    check("the held-out tail decides by default", default.require_oos is True)
    relaxed = parser.parse_args(["-s", "A,B", "--no-require-oos"])
    check("and can be relaxed explicitly", relaxed.require_oos is False)

    for bad in ("banana", "-3", "2.5"):
        args = args_for(lags=bad, test="adf")
        try:
            ci.run_tests(cointegrated(n=300), args)
            check(f"--lags {bad!r} is refused", False, "no error raised")
        except (ci.UserError, ValueError):
            check(f"--lags {bad!r} is refused", True)
    for good in ("aic", "bic", "3"):
        args = args_for(lags=good, test="adf")
        try:
            ci.run_tests(cointegrated(n=400), args)
            check(f"--lags {good!r} is accepted", True)
        except Exception as exc:                                  # noqa: BLE001
            check(f"--lags {good!r} is accepted", False, f"{type(exc).__name__}: {exc}")

    # Every firing check names itself, so counting them needs no prose parsing.
    thresholds = dict(max_pvalue=0.05, degraded_pvalue=0.20, min_half_life=2.0,
                      max_half_life=60.0, break_z=4.0, max_beta_drift=3.0)
    checks = hl.replay(independent(), lookback=300, every=25, **thresholds)
    coded = [c for c in checks if c.state != hl.HEALTHY]
    check("every unhealthy cycle carries a trigger code",
          all(c.trigger_code for c in coded), f"{len(coded)} unhealthy cycles")
    check("codes come from a small fixed set",
          set(c.trigger_code for c in coded) <= {"break-level", "cointegration",
                                                 "not-reverting", "hedge-drift",
                                                 "half-life"},
          str(sorted(set(c.trigger_code for c in coded))))
    stats = hl.summarise(checks)
    check("the summary counts codes, not sentences",
          sum(stats["triggers"].values()) == len(coded),
          f"{stats['triggers']}")

    hp = hl.build_parser()
    for argv in (["-s", "A,B", "--lookback", "50"],
                 ["-s", "A,B", "--max-pvalue", "0.3", "--degraded-pvalue", "0.2"]):
        ns = hp.parse_args(argv)
        ok = ns.lookback >= 120 and ns.max_pvalue < ns.degraded_pvalue
        check(f"health rejects {' '.join(argv[2:])}", not ok)


def test_neutrality_and_screen() -> None:
    print("\n7. neutrality gate and the screener")
    import screen as sc

    # A hedge ratio alone is not a neutrality test: 0.10 leaves a position that
    # is 82% net long, which is a single-name bet wearing a spread's name.
    for beta, want in ((1.0, 0.0), (0.729, 0.157), (0.333, 0.5), (0.165, 0.717),
                       (0.10, 0.818)):
        e = hg.Estimate("static", np.array([beta]), beta, beta, beta, 0.0, 0,
                        10.0, 10.0, 1.0)
        check(f"beta {beta:g} gives {want:.0%} net exposure",
              close(e.net_exposure(), want, 0.01), f"{e.net_exposure():.3f}")

    balanced = hg.Estimate("static", np.array([0.8]), 0.8, 0.8, 0.8, 0.0, 0,
                           10.0, 10.0, 1.0)
    lopsided = hg.Estimate("static", np.array([0.165]), 0.165, 0.165, 0.165, 0.0, 0,
                           10.0, 10.0, 1.0)
    check("a balanced pair passes the neutrality gate",
          balanced.usable(0.10, 0.10, 0.35))
    check("a lopsided one is refused even though its ratio clears the old floor",
          lopsided.usable(0.10, 0.10) and not lopsided.usable(0.10, 0.10, 0.35),
          f"net {lopsided.net_exposure():.0%}")

    # The screener must count how many survivors chance alone would produce.
    parser = sc.build_parser()
    args = parser.parse_args(["-u", "fx-all"])
    check("the screener defaults to requiring the held-out tail", args.require_oos is True)
    check("and to a neutrality limit", args.max_net_exposure == 0.35)
    try:
        sc.resolve_universe(parser.parse_args(["-u", "no-such-universe"]))
        check("an unknown universe is refused", False, "no error raised")
    except sc.UserError:
        check("an unknown universe is refused", True)
    try:
        sc.resolve_universe(parser.parse_args(["-s", "AAA,BBB"]))
        check("explicit symbols without an asset class are refused", False)
    except sc.UserError:
        check("explicit symbols without an asset class are refused", True)

    def args_with(base, **over):
        """A copy of the parsed arguments with one gate changed."""
        import copy
        clone = copy.copy(base)
        for k, v in over.items():
            setattr(clone, k, v)
        return clone

    def screen_row(**over):
        """A row that passes every gate, unless a field is overridden.

        Built by keyword so that adding a gate to the screener cannot silently
        shift these fixtures onto the wrong columns — which is exactly what a
        positional constructor did when the reserved-window gate was added.
        """
        base = dict(a="A", b="B", bars=1000, pvalue=0.01, pvalue_oos=0.02,
                    beta=0.8, hedge_ok=True, half_life=10.0, half_life_oos=12.0,
                    net_exposure=0.11, pvalue_early=0.02, pvalue_late=0.03,
                    beta_early=0.75, beta_late=0.85)
        base.update(over)
        return sc.Row(**base)

    row = screen_row()
    check("a clean row survives", sc.survives(row, args))
    check("a failing tail stops it",
          not sc.survives(screen_row(pvalue_oos=0.40), args))
    check("an unusable hedge stops it",
          not sc.survives(screen_row(hedge_ok=False), args))
    check("a half-life outside the window stops it",
          not sc.survives(screen_row(half_life=900.0), args))
    check("stability is the ratio of the slower half-life to the faster",
          close(row.stability(), 1.2, 1e-9), f"{row.stability():.3f}")

    from marketdata.instruments import (EQUITY_SECTOR_OF, EQUITY_SECTORS,
                                        driver_groups, shared_drivers)
    check("every equity symbol maps to exactly one sector",
          len(EQUITY_SECTOR_OF) == sum(len(v) for v in EQUITY_SECTORS.values()),
          f"{len(EQUITY_SECTOR_OF)} mapped")
    check("two funds tracking different sectors share no driver",
          not shared_drivers("XLP", "XLB", "index"))
    check("two funds tracking the same sector do",
          shared_drivers("XLF", "KRE", "index") == {"banks"})
    check("two insurers share a driver",
          shared_drivers("ALL", "TRV", "equity") == {"insurers"})
    check("two large companies in unrelated businesses do not",
          not shared_drivers("AAPL", "AMZN", "equity"))
    check("currency pairs sharing a leg share a driver",
          shared_drivers("EURUSD", "GBPUSD", "forex") == {"USD"})
    check("currency pairs sharing no leg share nothing",
          not shared_drivers("EURUSD", "AUDNZD", "forex"))
    check("an unknown instrument links to nothing rather than to everything",
          not driver_groups("ZZZZ", "index"))
    check("a malformed currency pair links to nothing",
          not driver_groups("EUR", "forex"))
    check("crypto is one driver, not one per coin",
          shared_drivers("BTC-USDT", "ETH-USDT", "crypto") == {"crypto-beta"})
    check("the screener requires a shared driver by default",
          args.require_link is True)

    check("the screener reserves a window at each end by default",
          args.holdout > 0, f"{args.holdout}")
    check("and requires the relationship to exist there",
          args.require_holdout is True)
    check("a pair that rejects on neither reserved window is stopped",
          not sc.survives(screen_row(pvalue_early=0.40, pvalue_late=0.55), args))
    check("rejecting on the late reserved window is what counts",
          sc.survives(screen_row(pvalue_early=0.40, pvalue_late=0.01), args))
    # The rule this replaced accepted a pair on either window. `NUE~STLD`
    # cleared it at p_early 0.001 with p_late 0.648, and its relationship last
    # rejected in 1996-2000. You trade forward, so the late window decides.
    check("a relationship present only in the oldest window is stopped",
          not sc.survives(screen_row(pvalue_early=0.001, pvalue_late=0.648), args))
    check("the late window alone can carry a pair through",
          sc.survives(screen_row(pvalue_early=0.90, pvalue_late=0.004), args))
    check("--require-early also demands the older window",
          not sc.survives(screen_row(pvalue_early=0.90, pvalue_late=0.004),
                          args_with(args, require_early=True)))
    check("and accepts a pair present in both",
          sc.survives(screen_row(pvalue_early=0.01, pvalue_late=0.004),
                      args_with(args, require_early=True)))
    check("a pair with no late window at all is stopped",
          not sc.survives(screen_row(pvalue_late=float("nan")), args))
    check("a pair with no reserved windows at all is stopped",
          not sc.survives(screen_row(pvalue_early=float("nan"),
                                     pvalue_late=float("nan")), args))
    check("the hedge ratio swing is the widest ratio across windows",
          close(screen_row(beta=1.0, beta_early=0.5, beta_late=0.8).beta_swing(),
                2.0, 1e-12))
    check("a ratio that changes sign is refused outright",
          not math.isfinite(screen_row(beta=0.8, beta_early=-0.5,
                                       beta_late=0.9).beta_swing()))
    check("a ratio swinging wider than the limit stops the pair",
          not sc.survives(screen_row(beta=1.0, beta_early=0.1,
                                     beta_late=1.0), args))
    check("one window is not enough to measure a swing",
          not math.isfinite(screen_row(beta=0.8, beta_early=float("nan"),
                                       beta_late=float("nan")).beta_swing()))


def test_unified_hedge_fit() -> None:
    print("\n8. relationship.py -- the one hedge fit, checked against the raw "
          "formula it replaced")
    import relationship as rel

    rng = np.random.default_rng(11)
    x = rng.standard_normal(400) * 4 + 20
    y = 0.62 * x + rng.standard_normal(400) * 0.7 + 3.0

    beta_raw, alpha_raw = (float(v) for v in np.polyfit(x, y, 1))
    beta, alpha = rel.ols_beta(y, x)
    check("ols_beta matches raw np.polyfit exactly, not approximately",
          (beta, alpha) == (beta_raw, alpha_raw),
          f"{(beta, alpha)} against {(beta_raw, alpha_raw)}")

    beta_split_raw = float(np.polyfit(x[:250], y[:250], 1)[0])
    beta_split, _ = rel.ols_beta(y, x, split=250)
    check("a split fits only the slice before it, not the whole array",
          close(beta_split, beta_split_raw, 1e-12))
    beta_full, _ = rel.ols_beta(y, x)
    check("a split changes the answer -- fitting less data is not fitting all of it",
          abs(beta_split - beta_full) > 1e-6,
          f"split {beta_split:.6f} vs full {beta_full:.6f}")

    spread_raw = y - beta_raw * x - alpha_raw
    spread = rel.build_spread(y, x, beta, alpha)
    check("build_spread reproduces the manual residual",
          np.allclose(spread, spread_raw))

    # The n-leg form must agree with the pair form on one leg, and with a raw
    # lstsq on several -- two different code paths solving the same equations.
    w1, a1 = rel.ols_hedge(y, x)
    check("ols_hedge on one leg matches ols_beta to solver tolerance",
          close(float(w1[0]), beta_raw, 1e-8) and close(a1, alpha_raw, 1e-8),
          f"{float(w1[0]):.8f} against {beta_raw:.8f}")

    x3 = rng.standard_normal((400, 3))
    true_w = np.array([0.4, -0.9, 1.3])
    y3 = x3 @ true_w + 6.0 + rng.standard_normal(400) * 0.3
    design = np.column_stack([x3, np.ones(400)])
    coef_raw, *_ = np.linalg.lstsq(design, y3, rcond=None)
    w3, a3 = rel.ols_hedge(y3, x3)
    check("ols_hedge on three legs matches a raw lstsq on the same design",
          np.allclose(w3, coef_raw[:-1]) and close(a3, float(coef_raw[-1]), 1e-8))
    check("the fitted weights recover the generating weights, not just the algebra",
          np.allclose(w3, true_w, atol=0.05),
          f"{w3} against {true_w}")

    spread3_raw = y3 - x3 @ coef_raw[:-1] - coef_raw[-1]
    spread3 = rel.build_spread_n(y3, x3, coef_raw[:-1], float(coef_raw[-1]))
    check("build_spread_n reproduces the manual n-leg residual",
          np.allclose(spread3, spread3_raw))

    # A caller that swaps y and x must get a materially different fit, not a
    # silently transposed one that happens to look similar.
    beta_swapped, _ = rel.ols_beta(x, y)
    check("swapping the two sides changes the fitted ratio",
          abs(beta_swapped - beta) > 1e-3,
          f"swapped {beta_swapped:.4f} against {beta:.4f}")


def test_callers_agree_with_relationship() -> None:
    print("\n9. every refactored caller reproduces its pre-refactor number")
    import hedge as hg
    import relationship as rel

    rng = np.random.default_rng(23)
    x = rng.standard_normal(300) * 2 + 15
    y = 1.15 * x + rng.standard_normal(300) * 0.4 - 1.0
    split = 200

    beta_raw = float(np.polyfit(x[:split], y[:split], 1)[0])
    static = hg.static_beta(y, x, split)
    check("hedge.static_beta matches the raw np.polyfit it used to call",
          close(float(static[0]), beta_raw, 1e-9) and
          bool(np.all(static == static[0])),
          f"{static[0]:.8f} against {beta_raw:.8f}")

    window = 60
    roll_raw = np.full(len(y), np.nan)
    for i in range(window, len(y) + 1):
        roll_raw[i - 1] = float(np.polyfit(x[i - window:i], y[i - window:i], 1)[0])
    roll = hg.rolling_beta(y, x, window)
    check("hedge.rolling_beta matches a hand-rolled raw-polyfit loop",
          np.allclose(roll[window - 1:], roll_raw[window - 1:], atol=1e-9))

    import basket_screen as bs
    x2 = np.column_stack([x, rng.standard_normal(300) * 3 + 5])
    y2 = 0.8 * x2[:, 0] - 0.3 * x2[:, 1] + 2 + rng.standard_normal(300) * 0.2
    design = np.column_stack([x2, np.ones(300)])
    coef_raw, *_ = np.linalg.lstsq(design, y2, rcond=None)
    w, a = bs.fit_weights(y2, x2)
    check("basket_screen.fit_weights matches a raw lstsq on the same design",
          np.allclose(w, coef_raw[:-1]) and close(a, float(coef_raw[-1]), 1e-8))
    spread_raw = y2 - x2 @ coef_raw[:-1] - coef_raw[-1]
    check("basket_screen.spread_of matches the manual residual",
          np.allclose(bs.spread_of(y2, x2, w, a), spread_raw))


def test_fx_neutrality() -> None:
    print("\n10. forex neutrality is measured in currency space, not leg space")

    # AUDUSD is AUD/USD and USDNOK is USD/NOK. The dollar is on opposite sides,
    # so the rates move oppositely, the fitted beta is negative, and the leg
    # weights are (1, +|beta|) -- long both. Leg-space neutrality calls that
    # 100% directional. It is not: long AUDUSD plus long USDNOK is long AUD,
    # short NOK, with the dollar cancelling.
    for beta in (-0.2, -0.5813, -1.0, -1.1526, -3.0):
        check(f"opposite-side USD scores exactly 100% in leg space (beta {beta:+.4f})",
              close(hg.net_exposure(beta), 1.0, 1e-12),
              f"{hg.net_exposure(beta):.6f}")
    check("currency space does not, and separates the pairs leg space could not",
          len({round(hg.fx_net_exposure("AUDUSD", "USDNOK", b), 6)
               for b in (-0.2, -0.5813, -1.0, -1.1526, -3.0)}) == 5)

    # A beta of exactly -1 holds one unit of each, so the shared dollar cancels
    # exactly and the position is a pure AUD-against-NOK bet.
    check("beta of -1 cancels the shared currency exactly",
          close(hg.fx_net_exposure("AUDUSD", "USDNOK", -1.0), 0.0, 1e-12),
          f"{hg.fx_net_exposure('AUDUSD', 'USDNOK', -1.0):.8f}")

    # Worked by hand: weights (1, +0.5813); AUDUSD carries -1 USD, USDNOK
    # carries +0.5813 USD; net 0.4187 over a gross of 1.5813.
    got = hg.fx_net_exposure("AUDUSD", "USDNOK", -0.5813)
    check("opposite-side USD matches the hand-computed currency exposure",
          close(got, 0.4187 / 1.5813, 1e-6), f"{got:.6f} against {0.4187/1.5813:.6f}")

    # Same-side quotes were never broken and must not move.
    for a, b, beta in (("EURUSD", "GBPUSD", 0.70), ("EURUSD", "AUDUSD", 1.4),
                       ("EURGBP", "EURJPY", 0.80)):
        check(f"{a}~{b} is unchanged -- the shared currency is already on one side",
              close(hg.fx_net_exposure(a, b, beta), hg.net_exposure(beta), 1e-12),
              f"{hg.fx_net_exposure(a, b, beta):.6f} against {hg.net_exposure(beta):.6f}")

    # Anything that is not a pair of forex symbols falls back untouched, so the
    # equity and index screens are unaffected by this entirely.
    for a, b in (("XLP", "XLB"), ("NUE", "STLD"), ("BTC-USDT", "ETH-USDT")):
        check(f"{a}~{b} falls back to leg space",
              close(hg.fx_net_exposure(a, b, 0.594), hg.net_exposure(0.594), 1e-12))

    # Two pairs sharing no currency have nothing to cancel.
    check("EURGBP~USDJPY shares no currency and falls back",
          close(hg.fx_net_exposure("EURGBP", "USDJPY", 0.5),
                hg.net_exposure(0.5), 1e-12))
    check("a non-finite beta is refused in currency space too",
          not math.isfinite(hg.fx_net_exposure("AUDUSD", "USDNOK", float("nan"))))

    check("currency_legs splits a six-letter symbol",
          hg.currency_legs("AUDUSD") == ("AUD", "USD"))
    check("currency_legs refuses anything that is not one",
          hg.currency_legs("BTC-USDT") is None and hg.currency_legs("XLP") is None)

    # The direction of the correction must be a loosening, never a tightening:
    # currency space can only ever score at or below leg space for an
    # opposite-side pair, because leg space is already at its maximum of 1.
    for beta in (-0.1, -0.9, -2.5):
        check(f"currency space is no stricter than leg space (beta {beta:+.1f})",
              hg.fx_net_exposure("AUDUSD", "USDNOK", beta) <= hg.net_exposure(beta) + 1e-12)


def main() -> int:
    global VERBOSE
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--trials", type=int, default=300,
                        help="random-walk pairs for the calibration check")
    ns = parser.parse_args()
    VERBOSE = ns.verbose

    print("Verifying cointegration.py, hedge.py, health.py and relationship.py")
    test_ground_truth()
    test_calibration(ns.trials)
    test_hedge()
    test_health()
    test_real_data()
    test_gates_and_inputs()
    test_neutrality_and_screen()
    test_unified_hedge_fit()
    test_callers_agree_with_relationship()
    test_fx_neutrality()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("\nFAILED:")
        for name in FAILED:
            print(f"  - {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
