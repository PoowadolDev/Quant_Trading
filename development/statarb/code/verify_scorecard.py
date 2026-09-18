"""Prove the scorecard grades honestly and the contribution measure is not a rescue hatch.

Two dangers specific to this layer, and the checks are built around them.

**Grading can become laundering.** The point of tiers is to say which rejections a book
might fix. The failure mode is a tier that quietly promotes a candidate whose relationship
is dead, which would turn a grading system into a way of keeping everything. The tier rules
are therefore checked for exhaustiveness *and* for what they refuse.

**A second chance is a second trial.** `contribution.measure` gives an already-rejected
candidate another opportunity to look good. If it were free, the multiple-testing correction
would be understated by exactly the number of free looks.

    python verify_scorecard.py
    python verify_scorecard.py -v
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

import contribution as cb                                          # noqa: E402
import scorecard as sc                                             # noqa: E402
import screen as scr                                               # noqa: E402
import triallog                                                    # noqa: E402

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
    base = types.SimpleNamespace(
        level=0.05, require_oos=True, require_holdout=True, require_early=False,
        max_beta_swing=3.0, max_net_exposure=0.35, min_abs_beta=0.10,
        max_negative_share=0.30, min_half_life=2.0, max_half_life=60.0)
    for key, value in over.items():
        setattr(base, key, value)
    return base


def row(**over):
    """A pair that clears every gate, unless an override breaks one."""
    base = dict(a="AAA", b="BBB", bars=1200, pvalue=0.01, pvalue_oos=0.02,
                beta=0.9, hedge_ok=True, half_life=20.0, half_life_oos=22.0,
                net_exposure=0.05, sector="", pvalue_early=0.03, pvalue_late=0.01,
                beta_early=0.85, beta_late=0.95)
    base.update(over)
    return scr.Row(**base)


def series(values, start="2020-01-01"):
    index = pd.date_range(start, periods=len(values), freq="D", tz="UTC")
    return pd.Series(np.asarray(values, float), index=index)


# ---------------------------------------------------------------- 1. no short-circuit
def test_every_gate_runs() -> None:
    print("\n1. every gate is evaluated, whatever an earlier one said")

    args = args_for()
    good = sc.assess(row(), args)
    awful = sc.assess(row(pvalue=0.9, pvalue_oos=0.9, pvalue_late=0.9,
                          hedge_ok=False, net_exposure=0.8, half_life=500.0), args)

    check("a passing and a failing candidate produce the same number of gates",
          len(good.gates) == len(awful.gates) and len(good.gates) == 7,
          f"{len(good.gates)} against {len(awful.gates)}")
    check("the gate names are identical regardless of the verdict",
          [g.name for g in good.gates] == [g.name for g in awful.gates])
    check("a candidate failing the first gate still reports the last",
          awful.get("half_life") is not None
          and awful.get("half_life").passed is False)
    check("the failing candidate names every gate it failed, not just the first",
          len(awful.failed()) >= 4, f"{sorted(awful.failed())}")

    # The behaviour the refactor had to preserve.
    check("all_pass agrees with the old boolean on a clearing candidate",
          good.all_pass() is True and scr.survives(row(), args) is True)
    check("all_pass agrees with the old boolean on a failing candidate",
          awful.all_pass() is False)


# ---------------------------------------------------------------- 2. not evaluable
def test_not_evaluable() -> None:
    print("\n2. a gate that cannot be asked says so, and is never a pass")

    args = args_for()
    short = sc.assess(row(pvalue_oos=float("nan"), pvalue_late=float("nan")), args)

    check("an untested tail reports None, not False",
          short.get("out_of_sample").passed is None,
          str(short.get("out_of_sample").passed))
    check("an untested reserved window reports None, not False",
          short.get("late_window").passed is None)
    check("None is not counted as a failure",
          "out_of_sample" not in short.failed()
          and "out_of_sample" in short.unevaluable())
    check("a card with an unevaluable gate does not all_pass",
          short.all_pass() is False,
          "absence of evidence must not read as evidence")
    check("the unevaluable gate explains itself",
          bool(short.get("out_of_sample").note))

    # No OU fit at all: the half-life band cannot be judged either.
    nofit = sc.assess(row(half_life=float("nan")), args)
    check("no OU fit makes the reverting gate fail and the band unevaluable",
          nofit.get("reverting").passed is False
          and nofit.get("half_life").passed is None)


# ---------------------------------------------------------------- 3. margins
def test_margins() -> None:
    print("\n3. margins are signed, in their own unit, and zero on the threshold")

    args = args_for(level=0.05, max_half_life=60.0, min_half_life=2.0)

    # Worked by hand: p of 0.01 against a limit of 0.05 leaves 0.04 of room.
    card = sc.assess(row(pvalue=0.01), args)
    check("a cleared p-value margin is the limit minus the value",
          close(card.get("cointegration").margin, 0.04, 1e-12),
          f"{card.get('cointegration').margin:.6f}")

    # And a failure is negative by the amount of the overshoot.
    over = sc.assess(row(pvalue=0.08), args)
    check("a failed p-value margin is negative by the overshoot",
          close(over.get("cointegration").margin, -0.03, 1e-12),
          f"{over.get('cointegration').margin:.6f}")

    check("a value exactly on the threshold has a margin of zero",
          close(sc.assess(row(pvalue=0.05), args).get("cointegration").margin,
                0.0, 1e-12))
    # ...and is a failure, because the gate is a strict inequality.
    check("a value exactly on the threshold does not pass",
          sc.assess(row(pvalue=0.05), args).get("cointegration").passed is False)

    # The half-life band is two-sided: the margin is the distance to the NEARER edge.
    # Worked by hand: 20 bars inside [2, 60] is 18 from the low edge and 40 from the
    # high one, so the margin is 18.
    band = sc.assess(row(half_life=20.0), args)
    check("a two-sided band reports the distance to the nearer edge",
          close(band.get("half_life").margin, 18.0, 1e-12),
          f"{band.get('half_life').margin:.4f}")
    check("below the band the margin is negative",
          sc.assess(row(half_life=1.0), args).get("half_life").margin < 0)
    check("above the band the margin is negative",
          sc.assess(row(half_life=100.0), args).get("half_life").margin < 0)

    # Units are kept rather than normalised, because normalising is the first step to
    # adding them together.
    units = {g.unit for g in sc.assess(row(), args).gates}
    check("gates keep their own units rather than a common scale",
          len(units) >= 3, str(sorted(units)))


# ---------------------------------------------------------------- 4. tiers
def test_tiers() -> None:
    print("\n4. tiers separate what a book can fix from what it cannot")

    args = args_for()

    check("a candidate clearing everything is STANDALONE",
          sc.tier(sc.assess(row(), args)) == sc.STANDALONE)

    # Structural: the relationship is not present in the window it would be traded in.
    # This is the NUE~STLD failure and nothing recovers it.
    dead = sc.assess(row(pvalue_late=0.648), args)
    check("a dead late window is REJECT_STRUCTURAL",
          sc.tier(dead) == sc.REJECT_STRUCTURAL, sc.tier(dead))

    # Structural: no OU fit.
    check("no reversion at all is REJECT_STRUCTURAL",
          sc.tier(sc.assess(row(half_life=float("nan")), args))
          == sc.REJECT_STRUCTURAL)

    # Foundational.
    check("no cointegration is REJECT_STATISTICAL",
          sc.tier(sc.assess(row(pvalue=0.9), args)) == sc.REJECT_STATISTICAL)

    # Magnitude: a directional hedge. Two such pairs with opposite exposure cancel, so a
    # book is exactly the fix.
    directional = sc.assess(row(hedge_ok=False, net_exposure=0.72), args)
    check("a directional hedge is PORTFOLIO_CANDIDATE",
          sc.tier(directional) == sc.PORTFOLIO_CANDIDATE, sc.tier(directional))

    # Magnitude: reverts, but too slowly for the intended horizon.
    slow = sc.assess(row(half_life=90.0), args)
    check("reversion too slow for the horizon is PORTFOLIO_CANDIDATE",
          sc.tier(slow) == sc.PORTFOLIO_CANDIDATE, sc.tier(slow))

    # Power.
    check("an untested reserved window is WATCH_POWER",
          sc.tier(sc.assess(row(pvalue_late=float("nan")), args)) == sc.WATCH_POWER)

    # Economics can only ever come from a cost replay, and it outranks magnitude.
    check("a cost verdict of REJECT_ECONOMIC is honoured",
          sc.tier(sc.assess(row(), args), economics=sc.REJECT_ECONOMIC)
          == sc.REJECT_ECONOMIC)

    # THE ABUSE CHECK. Economics and contribution must never rescue a structural failure.
    check("a cost verdict cannot rescue a dead relationship",
          sc.tier(dead, economics=None) == sc.REJECT_STRUCTURAL
          and sc.tier(dead, economics=sc.STANDALONE) == sc.REJECT_STRUCTURAL)
    check("structural outranks economic",
          sc.tier(dead, economics=sc.REJECT_ECONOMIC) == sc.REJECT_STRUCTURAL)

    # Exhaustive: every constructed case lands in a declared tier, none raises.
    cases = [row(), row(pvalue=0.9), row(pvalue_late=0.9), row(hedge_ok=False),
             row(half_life=200.0), row(half_life=float("nan")),
             row(pvalue_oos=float("nan")), row(beta_early=-0.5),
             row(pvalue=0.9, pvalue_late=0.9, hedge_ok=False)]
    tiers = [sc.tier(sc.assess(c, args)) for c in cases]
    check("every constructed case lands in a declared tier",
          all(t in sc.TIERS for t in tiers), str(sorted(set(tiers))))

    # A sign change in the hedge ratio is not one relationship.
    flip = sc.assess(row(beta_early=-0.8, beta_late=0.9), args)
    check("a hedge ratio that changes sign fails the stability gate",
          flip.get("beta_stability").passed is False,
          f"swing {flip.get('beta_stability').value}")


# ---------------------------------------------------------------- 5. contribution
def test_contribution() -> None:
    print("\n5. contribution measures a book, and a duplicate adds nothing")

    rng = np.random.default_rng(3)
    n = 400
    book = {f"P{i}": series(rng.normal(0.0004, 0.01, n)) for i in range(4)}

    # A duplicate of a book member adds no breadth: it is the same bet twice.
    duplicate = cb.measure("DUP", book["P0"].copy(), book)
    check("a duplicate of a book member is perfectly correlated to it",
          close(duplicate.max_correlation, 1.0, 1e-9),
          f"{duplicate.max_correlation:.6f}")
    check("a duplicate names which member it duplicates",
          duplicate.closest == "P0", duplicate.closest)
    check("a duplicate adds essentially no breadth",
          duplicate.breadth_change < 0.5, f"{duplicate.breadth_change:+.4f}")

    # An independent candidate adds close to a whole bet.
    independent = cb.measure("NEW", series(rng.normal(0.0004, 0.01, n)), book)
    check("an independent candidate adds close to a whole bet",
          independent.breadth_change > 0.6, f"{independent.breadth_change:+.4f}")
    check("an independent candidate is weakly correlated to the book",
          independent.max_correlation < 0.3, f"{independent.max_correlation:.4f}")

    # The arithmetic itself: before and after differ only by the candidate.
    check("the book measured before excludes the candidate",
          duplicate.book_size == 4, str(duplicate.book_size))
    check("sharpe_change is after minus before",
          close(independent.sharpe_change,
                independent.sharpe_after - independent.sharpe_before, 1e-12))

    # A candidate that is pure loss must not be promoted however uncorrelated it is.
    awful = cb.measure("BAD", series(rng.normal(-0.004, 0.01, n)), book)
    check("an uncorrelated loser does not improve the book",
          not cb.improves_book(awful),
          f"sharpe {awful.sharpe_change:+.3f}, breadth {awful.breadth_change:+.2f}")
    check("adding breadth while lowering the Sharpe is not an improvement",
          awful.breadth_change > 0.5 and not awful.helps,
          "breadth rose and it still does not qualify")

    # Rounding must not count as a gain.
    check("a Sharpe change below the noise floor is not an improvement",
          cb.MIN_SHARPE_GAIN > 0.0,
          f"floor is {cb.MIN_SHARPE_GAIN}")

    # Guards.
    for bad, why in (({}, "an empty book"),
                     ({"P0": series(rng.normal(0, 0.01, 10))}, "too few shared bars")):
        try:
            cb.measure("X", series(rng.normal(0, 0.01, 10)), bad)
            check(f"{why} is refused", False)
        except ValueError:
            check(f"{why} is refused", True)


# ---------------------------------------------------------------- 6. no blending
def test_no_blended_number() -> None:
    print("\n6. nothing here collapses the gates into one number")

    import ast

    banned = {"score", "composite", "overall", "combined", "aggregate",
              "total_score", "quality_score", "rank_score", "blend"}
    for module in ("scorecard", "contribution"):
        tree = ast.parse((HERE / f"{module}.py").read_text(encoding="utf-8"))
        names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        check(f"{module}.py has no function pretending to be a combined number",
              not (names & banned), f"found {sorted(names & banned)}")

    # A tier is a label chosen by branches, never a number compared to a cut-off. If this
    # ever returns something numeric the guard above stops being enough.
    args = args_for()
    check("tier returns a label, not a number",
          isinstance(sc.tier(sc.assess(row(), args)), str))
    check("every tier value is one of the declared constants",
          sc.tier(sc.assess(row(), args)) in sc.TIERS)

    # Margins stay in their own units, which is what stops them being summable.
    gates = sc.assess(row(), args).gates
    check("no gate exposes a normalised or dimensionless margin",
          all(g.unit for g in gates), "every gate names its unit")


# ---------------------------------------------------------------- 7. trial registry
def test_trial_registry(tmp: Path) -> None:
    print("\n7. a second chance is registered before it is taken")

    path = tmp / "registry.csv"
    first = triallog.register(path, "crypto-contribution", 6, "six near-misses")
    check("registering returns the cumulative trial count", first == 6, str(first))

    second = triallog.register(path, "equity-contribution", 10, "ten near-misses")
    check("a second campaign accumulates", second == 16, str(second))

    check("registering a negative count is refused",
          _raises(lambda: triallog.register(path, "bad", -1, "nonsense"), ValueError))

    # The point of registering rather than appending afterwards.
    check("the registry records intent, so abandoned work still counts",
          path.read_text(encoding="utf-8").count("\n") >= 3,
          "two campaigns plus a header")


def _raises(fn, exc) -> bool:
    try:
        fn()
    except exc:
        return True
    except Exception:                                              # noqa: BLE001
        return False
    return False


def main() -> int:
    global VERBOSE
    import tempfile

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true")
    ns = parser.parse_args()
    VERBOSE = ns.verbose

    print("Verifying scorecard.py and contribution.py")
    test_every_gate_runs()
    test_not_evaluable()
    test_margins()
    test_tiers()
    test_contribution()
    test_no_blended_number()
    with tempfile.TemporaryDirectory() as tmp:
        test_trial_registry(Path(tmp))

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("\nFAILED:")
        for name in FAILED:
            print(f"  - {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
