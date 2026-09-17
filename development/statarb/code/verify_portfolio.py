"""Stage 12.1 — prove portfolio.py sizes from the process rather than from hope.

The sizing layer is where a defect costs money rather than time, and RESIDUAL.md §2.3 names
the specific danger in advance: removing the entry threshold removes the thing that used to
cap a position, so an overstated reversion speed now oversizes with nothing to stop it. The
checks that matter most are therefore the ones about magnitude, not about sign.

Verified against a simulated OU process with known `theta`, `mu` and `sigma`, which is how
Step 2 and Step 3 were verified and why their defects were found with a random number
generator instead of with money.

    python verify_portfolio.py
    python verify_portfolio.py -v
"""
from __future__ import annotations

import argparse
import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pair_report as pr                                          # noqa: E402
import portfolio as pf                                            # noqa: E402
import risk
import residual as rs                                             # noqa: E402
import sizing                                                     # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []
VERBOSE = False


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(name)
    if not ok or VERBOSE:
        print(("  ok   " if ok else "  FAIL ") + name + (f"   {detail}" if detail else ""))


def close(got: float, want: float, tol: float) -> bool:
    return math.isfinite(got) and abs(got - want) <= tol


# ---------------------------------------------------------------- fixtures
def args_for(**over):
    ns = pf.build_parser().parse_args(["--no-log"])
    ns.pca_window, ns.signal_window, ns.step = 252, 60, 21
    ns.factors, ns.confidence, ns.gross = 5, 1.0, 1.0
    ns.unit_root_level, ns.neutralise = 0.05, True
    for key, value in over.items():
        setattr(ns, key, value)
    return ns


def universe(level_ar: float, *, bars=1500, names=40, factors=3, seed=0,
             factor_vol=0.01, idio_vol=0.01) -> np.ndarray:
    """Returns whose residual level is an AR(1) with the given coefficient."""
    rng = np.random.default_rng(seed)
    common = rng.normal(0, factor_vol, (bars, factors)) @ rng.normal(0, 1, (factors, names))
    level = np.zeros((bars, names))
    for t in range(1, bars):
        level[t] = level_ar * level[t - 1] + rng.normal(0, idio_vol, names)
    return common + np.vstack([level[0], np.diff(level, axis=0)])


def position(**over):
    base = dict(name="AAA", regime=pr.REVERTING, theta=0.2, mu=0.0, sigma=0.01,
                x=-0.05, drift=0.01, drift_lower=0.008, weight=80.0, loading_norm=1.0)
    base.update(over)
    return pf.Position(**base)


# ---------------------------------------------------------------- 1. the identity
def test_sizing_identity() -> None:
    print("\n1. the weight is the growth-optimal size of the OU drift, exactly")

    returns = universe(0.0, seed=1)
    args = args_for()
    positions, _loadings = pf.fit_positions(returns, [f"N{i:02d}" for i in range(40)], 800, args)

    held = [p for p in positions if p.weight != 0.0]
    check("a strongly reverting panel produces held positions", len(held) > 5,
          f"{len(held)} of {len(positions)}")

    # The identity the whole script rests on: weight == haircut drift / sigma^2. Checked
    # against sizing.py's own function rather than against a second copy of the formula,
    # because two copies of one formula is the defect relationship.py exists to prevent.
    worst = max(abs(p.weight - sizing.growth_optimal_leverage(p.drift_lower, p.sigma))
                for p in held)
    check("every weight equals growth_optimal_leverage of the haircut drift",
          worst < 1e-9, f"largest disagreement {worst:.3e}")

    # And that function is mu/sigma^2, worked by hand: 0.008 / 0.01^2 = 80.
    check("growth_optimal_leverage is the hand-computed mu/sigma^2",
          close(sizing.growth_optimal_leverage(0.008, 0.01), 80.0, 1e-9),
          f"{sizing.growth_optimal_leverage(0.008, 0.01):.6f}")

    # Sign: a residual below its mean has a positive drift and must be held long.
    below = [p for p in held if p.x < p.mu]
    above = [p for p in held if p.x > p.mu]
    check("a residual below its own mean is held long",
          all(p.weight > 0 for p in below), f"{len(below)} such names")
    check("a residual above its own mean is held short",
          all(p.weight < 0 for p in above), f"{len(above)} such names")


# ---------------------------------------------------------------- 2. magnitude
def test_magnitude() -> None:
    print("\n2. size falls when the evidence weakens, which is the guard that replaced "
          "the threshold")

    # Doubling sigma must at least halve the size. The weight goes as mu/sigma^2, so
    # doubling sigma quarters it before the haircut and by more after, since the haircut
    # itself grows with sigma.
    base = sizing.growth_optimal_leverage(0.008, 0.01)
    doubled = sizing.growth_optimal_leverage(0.008, 0.02)
    check("doubling the deviation at least halves the size",
          doubled <= base / 2 + 1e-12, f"{base:.2f} to {doubled:.2f}")
    check("doubling the deviation quarters it exactly, since size goes as 1/sigma^2",
          close(doubled, base / 4, 1e-9), f"{doubled:.6f} against {base / 4:.6f}")

    # A larger haircut can only shrink a position, never grow one.
    returns = universe(0.0, seed=2)
    names = [f"N{i:02d}" for i in range(40)]
    grosses = []
    for confidence in (0.0, 1.0, 2.0, 4.0):
        ps = pf.fit_positions(returns, names, 800, args_for(confidence=confidence))[0]
        grosses.append(sum(abs(p.weight) for p in ps))
    check("raising the uncertainty haircut never raises gross exposure",
          all(a >= b - 1e-12 for a, b in zip(grosses, grosses[1:])),
          " >= ".join(f"{g:.1f}" for g in grosses))
    check("a haircut of zero is not the same as a haircut of four",
          grosses[0] > grosses[-1], f"{grosses[0]:.1f} against {grosses[-1]:.1f}")

    # A haircut larger than the estimate must close the position, not reverse it. This is
    # the sign-flip trap: |drift| - k*se goes negative, and copysign on a negative
    # magnitude would hold the position the wrong way round.
    huge = pf.fit_positions(returns, names, 800, args_for(confidence=50.0))[0]
    check("a haircut that exceeds the drift closes the position rather than reversing it",
          all(p.weight == 0.0 for p in huge),
          f"{sum(1 for p in huge if p.weight != 0)} non-zero")

    # lower_bound_mean is the haircut, hand-computed: 0.01 - 1.0 * 0.01/sqrt(100) = 0.009
    check("the haircut is the hand-computed mean minus k standard errors",
          close(sizing.lower_bound_mean(0.01, 0.01, 100, 1.0), 0.009, 1e-12),
          f"{sizing.lower_bound_mean(0.01, 0.01, 100, 1.0):.8f}")

    # No weight may ever be non-finite, whatever the inputs do.
    for sigma in (0.0, -1.0, float("nan"), float("inf")):
        value = sizing.growth_optimal_leverage(0.01, sigma)
        check(f"a deviation of {sigma} gives no finite size rather than a wrong one",
              not math.isfinite(value), str(value))


# ---------------------------------------------------------------- 3. regimes
def test_regimes() -> None:
    print("\n3. a residual that is not reverting is not sized")

    returns = universe(1.0, seed=3)            # random-walk level, nothing to revert to
    names = [f"N{i:02d}" for i in range(40)]
    walk = pf.fit_positions(returns, names, 800, args_for())[0]
    non_reverting = [p for p in walk if p.regime != pr.REVERTING]
    check("names outside the reverting regime carry no weight",
          all(p.weight == 0.0 for p in non_reverting),
          f"{len(non_reverting)} non-reverting names")

    # theta is zero in the explosive and oscillating regimes by pair_report's design, so a
    # half-life must not be constructible from them here either.
    for regime in (pr.EXPLOSIVE, pr.OSCILLATING):
        p = position(regime=regime, theta=0.0)
        check(f"a {regime} position reports no half-life",
              not math.isfinite(p.half_life), str(p.half_life))

    p = position(theta=math.log(2) / 10)
    check("a reverting position reports the hand-computed half-life",
          close(p.half_life, 10.0, 1e-9), f"{p.half_life:.6f}")


# ---------------------------------------------------------------- 4. loadings
def test_heavy_loadings() -> None:
    print("\n4. the documented failure regime is gated, not trusted")

    ps = [position(name=f"N{i}", loading_norm=n, weight=1.0)
          for i, n in enumerate([1.0, 1.0, 1.0, 1.0, 10.0])]
    kept = pf.drop_heavy_loadings(ps, 3.0)
    check("the name whose loading is far above the median is dropped",
          kept[4].weight == 0.0, f"{kept[4].regime}")
    check("the ordinary names are untouched",
          all(p.weight == 1.0 for p in kept[:4]))
    check("the dropped name says why in its regime label",
          "loading" in kept[4].regime, kept[4].regime)

    # The threshold is a multiple of the median, so it must scale with the cross-section
    # rather than being an absolute number that means something different per --factors.
    scaled = pf.drop_heavy_loadings(
        [position(name=f"N{i}", loading_norm=n, weight=1.0)
         for i, n in enumerate([10.0, 10.0, 10.0, 10.0, 100.0])], 3.0)
    check("the same shape at ten times the scale gives the same verdict",
          scaled[4].weight == 0.0 and all(p.weight == 1.0 for p in scaled[:4]))

    # A cross-section with no outlier must lose nobody.
    flat = pf.drop_heavy_loadings(
        [position(name=f"N{i}", loading_norm=1.0, weight=1.0) for i in range(5)], 3.0)
    check("a cross-section with no outlier keeps every name",
          all(p.weight == 1.0 for p in flat))


# ---------------------------------------------------------------- 5. scaling
def test_scaling() -> None:
    print("\n5. scaling sets how much of the book to hold, not its shape")

    ps = [position(name="A", weight=2.0), position(name="B", weight=-1.0),
          position(name="C", weight=1.0)]
    before = [p.weight for p in ps]
    scaled = pf.scale_to_gross(ps, 1.0)
    gross = sum(abs(p.weight) for p in scaled)
    check("gross exposure after scaling is exactly the budget",
          close(gross, 1.0, 1e-12), f"{gross:.10f}")

    # Ratios must survive. Worked by hand: gross was 4, so every weight is divided by 4 and
    # A:B:C stays 2:-1:1.
    check("relative sizes are unchanged by scaling",
          close(scaled[0].weight, 0.5, 1e-12)
          and close(scaled[1].weight, -0.25, 1e-12)
          and close(scaled[2].weight, 0.25, 1e-12),
          " ".join(f"{p.weight:+.4f}" for p in scaled))
    check("the ratio between the first two is preserved exactly",
          close(scaled[0].weight / scaled[1].weight, before[0] / before[1], 1e-12))

    # An empty book must not divide by zero.
    empty = pf.scale_to_gross([position(weight=0.0)], 1.0)
    check("a book of zeros is left alone rather than dividing by zero",
          empty[0].weight == 0.0)

    # A larger budget scales up proportionally.
    doubled = pf.scale_to_gross([position(name="A", weight=2.0),
                                 position(name="B", weight=-2.0)], 2.0)
    check("doubling the budget doubles gross",
          close(sum(abs(p.weight) for p in doubled), 2.0, 1e-12))


# ---------------------------------------------------------------- 6. book gates
def test_book_gates() -> None:
    print("\n6. the book-level caps refuse rather than warn")

    returns = universe(0.0, bars=2000, names=30, seed=4)
    names = [f"N{i:02d}" for i in range(30)]

    # The net cap is widened for this fixture, and the reason is arithmetic rather than
    # convenience. With independent drifts the net is a sum of N mean-zero weights, so it
    # grows as sqrt(N)|w| while gross grows as N|w|, which makes net/gross scale as
    # 1/sqrt(N). At the production panel's 160 names that predicts 7.9% and the measured
    # standard deviation is 7.8%; at this fixture's 30 names it predicts 18%. Applying the
    # 160-name cap to a 30-name book would be testing the fixture's size, not the gate.
    # The law itself is checked below rather than assumed here.
    book = pf.assemble(returns, names, len(returns),
                       args_for(min_effective_bets=2.0, max_net=0.45))
    check("a well-behaved panel assembles into an accepted book", book.ok,
          "; ".join(book.breaches))
    check("net over gross is reported and finite", math.isfinite(book.net_share),
          f"{book.net_share:+.4f}")
    check("gross is the budget", close(book.gross, 1.0, 1e-9), f"{book.gross:.6f}")

    # Each cap must be capable of firing. Set impossible and confirm a breach appears.
    for flag, value, word in (("min_effective_bets", 1e6, "independent bets"),
                              ("max_net", 0.0, "net exposure"),
                              ("max_correlation", 0.0, "correlate")):
        overrides = {"min_effective_bets": 2.0, "max_net": 0.45}
        overrides[flag] = value
        strict = pf.assemble(returns, names, len(returns), args_for(**overrides))
        check(f"the {flag} cap can refuse a book",
              not strict.ok and any(word in b for b in strict.breaches),
              "; ".join(strict.breaches)[:70])

    # The 1/sqrt(N) law the cap is calibrated on. A residual book is not neutral because
    # anybody imposed neutrality; it is neutral because independent drifts cancel, and the
    # cancellation improves with the square root of the cross-section. If this failed, the
    # cap would be a number nobody could justify at any panel size.
    # The direction of the 1/sqrt(N) law, and deliberately not its magnitude.
    #
    # Two earlier versions of this check were wrong in instructive ways. The first compared
    # single draws and measured a shrink of 6.78x against an expected 2.83x, because
    # |net/gross| is a folded mean-zero quantity and the ratio of two draws of it is mostly
    # noise. The second averaged five seeds per panel size and printed
    # 26.6% -> 5.4% -> 23.7% -> 9.1% -- no decay at all, yet the endpoints happened to give
    # 2.92x and the magnitude bound passed. That is a check passing for the wrong reason.
    #
    # The cause is that the law runs on the number of names *held*, not the number in the
    # panel, and the uncertainty haircut decides how many are held independently of panel
    # size. Isolating that needs far more draws than this check is worth, so the magnitude
    # claim is dropped and only the direction is asserted, over enough seeds to be stable.
    # The production cap's calibration rests on the measurement of the real 160-name panel
    # recorded in portfolio.py's --max-net help, not on this fixture.
    def mean_net(count: int, draws: int = 12) -> float:
        values = []
        for seed in range(draws):
            panel = universe(0.0, bars=1200, names=count, seed=90 + seed)
            book_n = pf.assemble(panel, [f"N{i:03d}" for i in range(count)], len(panel),
                                 args_for(min_effective_bets=2.0, max_net=1.0,
                                          max_correlation=1.0))
            values.append(abs(book_n.net_share))
        return float(np.mean(values))

    narrow, wide = mean_net(20), mean_net(160)
    check("net over gross is smaller on a wide cross-section than on a narrow one",
          wide < narrow, f"{narrow:.1%} at 20 names against {wide:.1%} at 160")

    # An empty book is refused rather than reported as a flawless book of nothing, which
    # would otherwise pass every cap trivially.
    empty = pf.assemble(returns, names, len(returns),
                        args_for(confidence=50.0, min_effective_bets=2.0, max_net=0.45))
    check("a book holding nothing is refused, not passed as flawless",
          not empty.ok and any("empty" in b for b in empty.breaches),
          "; ".join(empty.breaches)[:70])


# ---------------------------------------------------------------- 7. guards
def test_guards() -> None:
    print("\n7. bad settings are refused rather than quietly producing a size")

    for flags, why in (
        (["--factors", "0"], "zero factors"),
        (["--factors", "300"], "more factors than fit-window bars"),
        (["--signal-window", "10"], "a signal window too short to fit three parameters"),
        (["--signal-window", "400"], "a signal window longer than the fit window"),
        (["--confidence", "-1"], "a negative haircut"),
        (["--gross", "0"], "a gross budget of zero"),
        (["--max-net", "2"], "a net cap above one"),
    ):
        try:
            pf.main(["--no-log", "--quiet", "--dry-run", *flags])
            check(f"{why} is refused", False)
        except pf.UserError:
            check(f"{why} is refused", True)
        except Exception as exc:                                   # noqa: BLE001
            check(f"{why} is refused", False, f"raised {type(exc).__name__}")

    # A negative haircut would inflate the very drift it exists to discount, which is the
    # direction that flatters a result, so it is refused rather than clamped.
    check("the haircut cannot be negative, because that would inflate the drift",
          sizing.lower_bound_mean(0.01, 0.01, 100, 1.0)
          < sizing.lower_bound_mean(0.01, 0.01, 100, 0.0))


# ---------------------------------------------------------------- 8. pair mode
def relationship(name: str, level: np.ndarray, beta: float = 0.8):
    """A risk.Relationship whose spread RETURNS cumulate back to the given level."""
    returns = np.diff(level, prepend=level[0])
    index = pd.date_range("2015-01-01", periods=len(returns), freq="D", tz="UTC")
    a, b = name.split("~")
    return risk.Relationship(a=a, b=b, asset_class="equity", beta=beta,
                             spread_returns=pd.Series(returns, index=index))


def ou_level(phi: float, n: int = 400, seed: int = 0, vol: float = 0.01,
             start: float = 0.0) -> np.ndarray:
    """An AR(1) level with a known coefficient, offset so it starts away from its mean."""
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    x[0] = start
    for t in range(1, n):
        x[t] = phi * x[t - 1] + rng.normal(0, vol)
    return x


def test_pair_mode() -> None:
    print("\n8. a book of pairs is sized by the same rule as a cross-section")

    args = args_for(signal_window=200)
    # Seeds chosen so the level ends displaced from its own mean. A series sitting AT its
    # mean has no drift and is correctly closed by the haircut, which makes it useless as a
    # fixture for "is a reverting spread held" -- the first attempt at this check used one
    # and failed for that reason rather than for a defect.
    book = [relationship("AAA~BBB", ou_level(0.90, seed=3)),
            relationship("CCC~DDD", ou_level(0.90, seed=5))]
    positions = pf.fit_pairs(book, args)

    check("every pair in the book is fitted", len(positions) == 2, str(len(positions)))
    check("positions are labelled as pairs", all(p.kind == "pair" for p in positions))
    check("the hedge ratio is carried through for the report",
          all(math.isfinite(p.beta) for p in positions))

    held = [p for p in positions if p.weight != 0.0]
    check("a reverting spread is held", len(held) >= 1, f"{len(held)} of 2")
    worst = max((abs(p.weight - sizing.growth_optimal_leverage(p.drift_lower, p.sigma))
                 for p in held), default=0.0)
    check("every pair weight equals growth_optimal_leverage of its haircut drift",
          worst < 1e-9, f"largest disagreement {worst:.3e}")

    # Random walks, plural and deliberately. The OU fit calls every one of them reverting
    # -- that is the small-sample AR bias, not a bug -- so the gate that has to stop them is
    # the unit-root test. One draw would pass by luck.
    walks = [pf.fit_pairs([relationship("EEE~FFF", np.cumsum(
        np.random.default_rng(s).normal(0, 0.01, 400)))], args)[0] for s in range(6)]
    check("no random-walk spread carries weight",
          all(p.weight == 0.0 for p in walks),
          f"{sum(1 for p in walks if p.weight != 0)} of 6 sized")
    check("random walks are labelled unidentified, not reverting",
          any(p.regime == pf.UNIDENTIFIED for p in walks),
          str(sorted({p.regime for p in walks})))
    check("the OU fit alone would have called them reverting",
          all(pr._fit_ou(np.cumsum(np.random.default_rng(s).normal(0, 0.01, 400))[-200:])[3]
              == pr.REVERTING for s in range(6)),
          "which is why the unit-root gate is not optional")

    # The decisive check that the shared sizer is genuinely shared: hand the identical
    # level to both code paths and require identical weights. If these diverge, pair mode
    # and residual mode have started sizing by different formulas.
    level = ou_level(0.88, n=args.signal_window, seed=5, start=0.06)
    direct = pf.size_from_ou(level, args.signal_window, args.confidence)
    via_pair = pf.fit_pairs([relationship("III~JJJ", level)], args)[0]
    check("pair mode and the shared sizer agree to floating point",
          close(via_pair.weight, direct["weight"], 1e-12),
          f"{via_pair.weight:.10f} against {direct['weight']:.10f}")

    # risk.parse_book owns the book grammar; confirm the refusals this mode depends on.
    for text, why in (("AAA~BBB:equity", "a book of one"),
                      ("AAA~BBB,CCC~DDD", "a missing asset class"),
                      ("AAA~AAA:equity,CCC~DDD:equity", "a pair of one instrument"),
                      ("AAA~BBB:equity,AAA~BBB:equity", "a repeated relationship")):
        try:
            risk.parse_book(text, "1d")
            check(f"{why} is refused", False)
        except pf.UserError:
            check(f"{why} is refused", True)

    try:
        pf.fit_pairs([relationship("MMM~NNN", ou_level(0.9, n=30, seed=6))], args)
        check("a spread shorter than the OU window is refused", False)
    except pf.UserError:
        check("a spread shorter than the OU window is refused", True)


# ---------------------------------------------------------------- 9. projection
def test_projection() -> None:
    print("\n9. factor neutrality is algebra, and it does not bypass the gates")

    rng = np.random.default_rng(7)
    loadings = rng.normal(0, 1, (5, 40))
    ps = [position(name=f"N{i:02d}", weight=float(w))
          for i, w in enumerate(rng.normal(0, 1, 40))]

    out, cost = pf.neutralise(ps, loadings)
    w = np.array([p.weight for p in out])
    check("factor exposure after projection is zero to floating point",
          float(np.linalg.norm(loadings @ w)) < 1e-9,
          f"{np.linalg.norm(loadings @ w):.3e}")
    check("the projection reports the exposure it removed",
          cost["exposure_before"] > 1e-6 and cost["exposure_after"] < 1e-9,
          f"{cost['exposure_before']:.3e} -> {cost['exposure_after']:.3e}")
    check("the projection reports what it cost the book's shape",
          math.isfinite(cost["correlation"]), f"{cost['correlation']:+.4f}")

    again, _ = pf.neutralise([position(name=p.name, weight=p.weight) for p in out],
                             loadings)
    check("projecting twice equals projecting once",
          np.allclose(w, [p.weight for p in again], atol=1e-12))

    orthogonal = np.linalg.svd(loadings, full_matrices=True)[2][loadings.shape[0]:][0]
    kept, _ = pf.neutralise([position(name=f"N{i:02d}", weight=float(v))
                             for i, v in enumerate(orthogonal)], loadings)
    check("a book already orthogonal to the factors is unchanged",
          np.allclose([p.weight for p in kept], orthogonal, atol=1e-9))

    try:
        pf.neutralise([position(name=f"N{i:02d}", weight=float(v))
                       for i, v in enumerate(loadings[0])], loadings)
        check("a book lying entirely in the factor span is refused", False)
    except pf.UserError:
        check("a book lying entirely in the factor span is refused", True)

    # THE GATE CHECK. An unrestricted projection puts weight back on every name, including
    # the ones the haircut closed and the one the heavy-loading gate dropped. Measured on
    # the real panel, 70 gated names came back as a book of 160 -- which removes the gate
    # that exists because heavy loadings are the construction's documented failure regime.
    gated = [position(name=f"N{i:02d}", weight=(0.0 if i < 30 else float(rng.normal())))
             for i in range(40)]
    after, detail = pf.neutralise(gated, loadings)
    check("names the gates closed stay closed through the projection",
          all(p.weight == 0.0 for p in after[:30]),
          f"{sum(1 for p in after[:30] if p.weight != 0)} reopened")
    check("the held names are exactly factor-neutral among themselves",
          float(np.linalg.norm(
              loadings[:, 30:] @ np.array([p.weight for p in after[30:]]))) < 1e-9)
    check("the projection reports how many names it ran over",
          detail["names"] == 10, str(detail["names"]))

    try:
        pf.neutralise([position(name=f"N{i}", weight=1.0) for i in range(3)],
                      rng.normal(0, 1, (5, 3)))
        check("more factors than held names is refused", False)
    except pf.UserError:
        check("more factors than held names is refused", True)

    # The dollar-net payoff, which is a *consequence* of the projection rather than what it
    # targets, and only on a universe with a market factor.
    #
    # Projection zeroes exposure to the estimated factors — that is exact and is checked
    # above. Whether it also shrinks dollar net depends on the leading factor being close to
    # "all names", which is true of real equities and not of a fixture whose loadings are
    # drawn with random signs. Measured on such a fixture the projection made dollar net
    # slightly worse (13.25% against 11.70%), and asserting otherwise would be asserting
    # something the construction does not promise. The fixture below carries an explicit
    # positive market factor, which is the case the production cap is calibrated on.
    rng2 = np.random.default_rng(11)
    bars, count = 1400, 60
    market = rng2.normal(0, 0.012, (bars, 1)) @ np.abs(rng2.normal(1.0, 0.2, (1, count)))
    idiosyncratic = universe(0.0, bars=bars, names=count, factors=2, seed=12)
    returns = market + idiosyncratic
    names = [f"N{i:02d}" for i in range(count)]
    means = {}
    for flag in (True, False):
        nets = [abs(pf.assemble(returns, names, int(end),
                                args_for(neutralise=flag, max_net=1.0,
                                         max_correlation=1.0, min_effective_bets=2.0),
                                measure_breadth=False).net_share)
                for end in np.linspace(700, bars, 10, dtype=int)]
        means[flag] = float(np.mean(nets))
    check("on a universe with a market factor, neutralising shrinks dollar net exposure",
          means[True] < means[False],
          f"{means[True]:.2%} neutralised against {means[False]:.2%} not")


def main() -> int:
    global VERBOSE
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true")
    ns = parser.parse_args()
    VERBOSE = ns.verbose

    print("Verifying portfolio.py")
    test_sizing_identity()
    test_magnitude()
    test_regimes()
    test_heavy_loadings()
    test_scaling()
    test_book_gates()
    test_guards()
    test_pair_mode()
    test_projection()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("\nFAILED:")
        for name in FAILED:
            print(f"  - {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
