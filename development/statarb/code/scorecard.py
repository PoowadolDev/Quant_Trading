"""Every gate, evaluated, with the distance to its threshold and why it matters.

`screen.survives()` returned a bare boolean and short-circuited at the first failing gate.
The measurements were all there — `screen.evaluate()` computes every field unconditionally —
but the verdict discarded which gate failed and by how much, so a pair that missed one
threshold by a hair was indistinguishable from one that failed every gate badly.

This module keeps all of it. Every gate is evaluated even when an earlier one has already
failed, each records a signed margin in its own unit, and a tier is assigned by a written
rule rather than by adding anything up.

**There is no blended number here, and that is deliberate.** `STEP4.md` refuses to aggregate
gates into one score on the evidence of a study where the composite had no forward
relationship, and `verify_validation.test_no_aggregation` asserts it. A vector of margins
tells you *which* threshold bound a result; a weighted sum of the same margins tells you
nothing and looks authoritative doing it.

**The tiers separate failures management can fix from failures it cannot**, which is the
whole point of grading rather than rejecting:

    STANDALONE           clears every gate it could be asked
    PORTFOLIO_CANDIDATE  fails only on magnitude -- a book may fix it
    WATCH_POWER          right sign, error bars too wide -- more data may fix it
    REJECT_STATISTICAL   no relationship to begin with
    REJECT_STRUCTURAL    the relationship stopped existing -- nothing fixes it
    REJECT_ECONOMIC      gross positive, costs exceed it -- a book cannot dilute a
                         per-trade cost

A pair whose hedge leaves it 40% net long is a magnitude failure, not a structural one: two
such pairs with opposite exposure cancel inside a book. A pair whose late reserved window
says the relationship is gone is structural, and no amount of portfolio management brings a
dead relationship back.

**A gate that cannot be evaluated reports `None`, never `False`.** The precedent is
`pair_report.judge()`, which refuses to score the edge gate on a non-stationary spread
because doing so "produces a large, convincing and entirely spurious number". Running every
stage does not mean computing numbers that cannot mean anything.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

__all__ = ["Gate", "Scorecard", "assess", "tier", "STANDALONE",
           "PORTFOLIO_CANDIDATE", "WATCH_POWER", "REJECT_STATISTICAL",
           "REJECT_STRUCTURAL", "REJECT_ECONOMIC", "TIERS"]

STANDALONE = "STANDALONE"
PORTFOLIO_CANDIDATE = "PORTFOLIO_CANDIDATE"
WATCH_POWER = "WATCH_POWER"
REJECT_STATISTICAL = "REJECT_STATISTICAL"
REJECT_STRUCTURAL = "REJECT_STRUCTURAL"
REJECT_ECONOMIC = "REJECT_ECONOMIC"

TIERS = (STANDALONE, PORTFOLIO_CANDIDATE, WATCH_POWER,
         REJECT_STATISTICAL, REJECT_STRUCTURAL, REJECT_ECONOMIC)

#: Gates whose failure says the relationship is not reliably *present*. No position sizing,
#: no combination and no cost improvement recovers one of these, because none of them is
#: about how large anything is.
#:
#: `out_of_sample` is here rather than in MAGNITUDE, and the placement was forced by the
#: assertion at the end of `tier()` rather than chosen in advance. A relationship absent
#: from its own held-out tail is intermittent, and intermittency is not a size problem: a
#: book holding it alongside others still holds it during the stretches it is not there.
#: The tier answers "can management fix this", and for all three of these the answer is no.
#: Which one failed is still reported — `describe()` names it — so "dead now", "intermittent"
#: and "never reverted" stay distinguishable even though they share a verdict.
STRUCTURAL = ("late_window", "out_of_sample", "reverting")

#: Gates whose failure is about how big something is rather than whether it exists. These
#: are the ones a book can plausibly fix: net exposures cancel across pairs, and a holding
#: period is a property of the exit rule and the bar size rather than of the relationship.
MAGNITUDE = ("hedge_usable", "half_life", "beta_stability")

#: The gate that has to hold before any of the others mean anything.
FOUNDATION = "cointegration"


@dataclass(frozen=True)
class Gate:
    """One threshold, what was measured against it, and how much room was left.

    `margin` is signed and expressed in the gate's own unit, positive meaning clearance.
    It is deliberately not normalised into a common scale: dividing a p-value margin by a
    half-life margin to make them comparable is the first step towards adding them up, and
    the units are what make each line readable on its own.
    """

    name: str
    value: float
    limit: float
    passed: bool | None
    margin: float
    unit: str
    note: str = ""

    @property
    def evaluable(self) -> bool:
        return self.passed is not None


@dataclass(frozen=True)
class Scorecard:
    """Every gate a candidate was asked, in the order they are read."""

    pair: str
    gates: list = field(default_factory=list)

    def get(self, name: str) -> Gate | None:
        return next((g for g in self.gates if g.name == name), None)

    def failed(self) -> list:
        return [g.name for g in self.gates if g.passed is False]

    def unevaluable(self) -> list:
        return [g.name for g in self.gates if g.passed is None]

    def all_pass(self) -> bool:
        """True when every gate that could be asked was cleared.

        A gate that could not be evaluated is not a pass. It is the absence of evidence,
        and `WATCH_POWER` exists to say so rather than letting silence read as consent.
        """
        return all(g.passed is True for g in self.gates)


def _margin(value: float, limit: float, *, higher_is_better: bool) -> float:
    """Signed distance to a one-sided threshold, positive when the gate is cleared."""
    if not (math.isfinite(value) and math.isfinite(limit)):
        return float("nan")
    return (value - limit) if higher_is_better else (limit - value)


def _band_margin(value: float, low: float, high: float) -> float:
    """Distance to the nearer edge of a two-sided band, positive when inside it.

    Inside the band this is the room before the nearer edge is reached; outside it, the
    amount by which the nearer edge was overshot. One number covers both because the sign
    already says which side of the band the value is on.
    """
    if not math.isfinite(value):
        return float("nan")
    if value < low:
        return value - low
    if value > high:
        return high - value
    return min(value - low, high - value)


def assess(row, args) -> Scorecard:
    """Every gate `screen.survives` applied, evaluated without short-circuiting.

    Takes a `screen.Row`, which already carries every measurement; nothing here recomputes
    anything or touches the store. The gates and their thresholds are exactly those
    `survives` used, so a card whose gates all pass is a pair `survives` would have
    accepted — a property the verification suite pins rather than assumes.
    """
    level = args.level
    gates: list = []

    # 1. Cointegration on the screening window. Everything downstream is conditional on
    #    this, which is why it has its own tier when it fails.
    gates.append(Gate(
        name=FOUNDATION, value=row.pvalue, limit=level,
        passed=bool(math.isfinite(row.pvalue) and row.pvalue < level),
        margin=_margin(row.pvalue, level, higher_is_better=False), unit="p",
        note="Engle-Granger on the window the screen ranked"))

    # 2. The held-out tail of the screening window.
    if getattr(args, "require_oos", True):
        finite = math.isfinite(row.pvalue_oos)
        gates.append(Gate(
            name="out_of_sample", value=row.pvalue_oos, limit=level,
            passed=(row.pvalue_oos < level) if finite else None,
            margin=_margin(row.pvalue_oos, level, higher_is_better=False), unit="p",
            note="" if finite else "the tail was shorter than --min-tail, so it was "
                                   "never tested"))

    # 3. The late reserved window. This is the gate that decides whether the relationship
    #    is present in the window it would have to be traded in, and it is structural:
    #    `NUE~STLD` netted +9,810 bps over thirty years with a late-window p of 0.648.
    if getattr(args, "require_holdout", True):
        finite = math.isfinite(row.pvalue_late)
        gates.append(Gate(
            name="late_window", value=row.pvalue_late, limit=level,
            passed=bool(row.holds_out_of_window(
                level, require_early=getattr(args, "require_early", False)))
            if finite else None,
            margin=_margin(row.pvalue_late, level, higher_is_better=False), unit="p",
            note="" if finite else "the reserved window was too short to test"))

    # 4. Hedge-ratio stability across windows. An infinite swing is a sign change, which
    #    means the two legs do not agree on direction and it is not one relationship.
    swing = row.beta_swing()
    limit_swing = getattr(args, "max_beta_swing", float("inf"))
    sign_change = math.isinf(swing)
    gates.append(Gate(
        name="beta_stability", value=swing, limit=limit_swing,
        passed=None if not math.isfinite(swing) and not sign_change
        else bool(swing <= limit_swing),
        margin=_margin(swing, limit_swing, higher_is_better=False), unit="x",
        note="the hedge ratio changes sign across windows" if sign_change else ""))

    # 5. Is the fitted ratio a hedge at all, or a directional bet wearing a spread's name?
    #    `AMGN~LLY` screened as the best result in the project on a ratio that left it 72%
    #    net long.
    max_net = getattr(args, "max_net_exposure", 1.0)
    gates.append(Gate(
        name="hedge_usable", value=row.net_exposure, limit=max_net,
        passed=bool(row.hedge_ok),
        margin=_margin(row.net_exposure, max_net, higher_is_better=False), unit="net",
        note="net over gross exposure carried by the fitted ratio"))

    # 6. Does it revert at all, and 7. does it revert inside the intended horizon. Split
    #    because they fail for different reasons and belong in different tiers: no OU fit
    #    is structural, a half-life of 200 bars is a holding-period problem.
    finite_hl = math.isfinite(row.half_life)
    gates.append(Gate(
        name="reverting", value=row.half_life, limit=float("inf"),
        passed=finite_hl, margin=0.0 if finite_hl else float("nan"), unit="bars",
        note="" if finite_hl else "no OU fit: the spread is explosive or reverts faster "
                                  "than the bar"))
    lo = getattr(args, "min_half_life", 0.0)
    hi = getattr(args, "max_half_life", float("inf"))
    gates.append(Gate(
        name="half_life", value=row.half_life, limit=hi,
        passed=bool(lo <= row.half_life <= hi) if finite_hl else None,
        margin=_band_margin(row.half_life, lo, hi), unit="bars",
        note=f"wanted between {lo:g} and {hi:g} bars"))

    return Scorecard(pair=row.pair, gates=gates)


def tier(card: Scorecard, *, economics: str | None = None,
         contribution=None) -> str:
    """Grade a candidate by which gates failed, never by how many.

    Explicit branches in priority order, because the order encodes a claim: a structural
    failure outranks an economic one, which outranks a magnitude one, because that is the
    order in which the failures are irreversible.

    `economics` is the verdict from the cost replay when one was run — `screen`'s
    confirmation step — and is the only way `REJECT_ECONOMIC` can be reached. Without a
    cost profile the economics are unknown, not passed, so the tier falls back to what the
    statistics alone support.

    `contribution` is a `contribution.Contribution` when the candidate was measured against
    a book. It can only ever promote a magnitude failure to `PORTFOLIO_CANDIDATE`; it can
    never rescue a structural or economic one, which is the abuse this argument is most
    exposed to and the reason the check for it is explicit rather than implied.
    """
    failed = set(card.failed())

    # 1. The relationship stopped existing, or never was one. Nothing downstream can fix
    #    a dead relationship, so this outranks every other verdict.
    if failed & set(STRUCTURAL):
        return REJECT_STRUCTURAL

    # 2. No relationship on the window that selected it. Everything else was conditional
    #    on this, so the other gates' verdicts are not evidence of anything.
    if FOUNDATION in failed:
        return REJECT_STATISTICAL

    # 3. The trade earns gross and loses net. A book does not dilute a per-trade cost:
    #    holding the same spread alongside others pays the same spread and the same
    #    financing, so this is not a magnitude failure and is not promotable.
    if economics == REJECT_ECONOMIC:
        return REJECT_ECONOMIC

    # 4. A gate could not be asked. The out-of-sample tail or the reserved window was too
    #    short. The sign of the effect may be right and the evidence is simply absent, so
    #    this is a "come back with more data", not a rejection.
    if card.unevaluable():
        return WATCH_POWER

    # 5. Everything that could be asked was cleared.
    if card.all_pass():
        return STANDALONE

    # 6. What is left fails only on magnitude: exposure too large, reversion too slow, the
    #    ratio moving more than allowed. These are the failures a book can plausibly fix,
    #    because exposures cancel across pairs and holding period is set by the exit rule.
    if failed and failed <= set(MAGNITUDE):
        return PORTFOLIO_CANDIDATE

    # 7. A gate failed that is in no category above. Reaching here means a gate was added
    #    without deciding what its failure means, which is a bug in this function rather
    #    than a property of the candidate.
    raise AssertionError(
        f"{card.pair} failed {sorted(failed)}, which no tier rule covers. A gate was "
        f"added without classifying it as structural, foundational or magnitude."
    )


def describe(card: Scorecard, tier_name: str) -> str:
    """One line a human can read, naming what bound the result."""
    if tier_name == STANDALONE:
        tightest = min((g for g in card.gates if g.passed and math.isfinite(g.margin)),
                       key=lambda g: g.margin, default=None)
        if tightest is None:
            return "every gate cleared"
        return (f"every gate cleared; tightest was {tightest.name} with "
                f"{tightest.margin:+.4g} {tightest.unit} to spare")
    failed = card.failed()
    if failed:
        worst = min((g for g in card.gates if g.passed is False
                     and math.isfinite(g.margin)),
                    key=lambda g: g.margin, default=None)
        if worst is not None:
            return (f"failed {', '.join(failed)}; worst was {worst.name} at "
                    f"{worst.value:.4g} against {worst.limit:.4g} {worst.unit}")
        return f"failed {', '.join(failed)}"
    return f"not evaluable: {', '.join(card.unevaluable())}"
