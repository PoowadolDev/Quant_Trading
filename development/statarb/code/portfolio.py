"""Stage 12 — position sizes derived from the OU process, not searched on a grid.

`STEP3.md` deferred this script with the reason "needs two candidates to mean anything, and
there are none". That reason expired when the residual track replaced one pair with a
cross-section: there are 160 concurrent signals, and combining them is the whole point.

**What replaces what.** Every earlier position in this project was sized by a swept
threshold — enter at `z = 2.0`, exit at `0.5` — with the pair of numbers chosen by trying
several. Here the size is a consequence of the fitted process instead:

    dX = θ(μ − X)dt + σ dB        the residual, fitted per name
    drift_i = θ_i(μ_i − X_i,t)     expected return from where it currently sits
    w_i     = drift_i / σ_i²       growth-optimal, which is `sizing.growth_optimal_leverage`

The last line is not a new formula. The growth-optimal leverage of a bet with mean `μ` and
deviation `σ` is `μ/σ²`, and the OU drift is simply what supplies the mean. Kelly sizing and
OU sizing are the same arithmetic reached from two directions, so this script calls
`sizing.py` rather than writing a second copy that can drift out of agreement.

**Why this matters beyond elegance.** Every swept threshold is a trial, and the
deflated-Sharpe benchmark in Step 4 grows with the logarithm of the trial count. Removing
the sweep removes a whole dimension of selection bias rather than merely tidying it.

**What it costs.** RESIDUAL.md §2.3 records the trade honestly: one free parameter is
exchanged for three estimated ones, `θ`, `μ` and `σ`, and an overstated reversion speed now
produces systematic oversizing with no threshold left to cap it. Two guards follow from
that and neither is optional:

* the **uncertainty haircut** from `sizing.lower_bound_mean`, because every parameter in
  this project has moved by a factor of several across windows, and
* the **heavy-loading check**, because the paper this construction comes from documents its
  own failure regime — Figure 5(c),(i), where the largest factor loadings produce the
  largest positions and, once transaction costs are charged, heavy losses. A name whose
  loading norm is far above the cross-section is the analogue of a pair with a large hedge
  ratio, and this project has already been burned once by not having a gate for that.

**Sizing a name that is not reverting is refused, not shrunk.** `pair_report._fit_ou`
returns `θ = 0` for the explosive and oscillating regimes precisely so no caller can build a
half-life out of them, and a zero `θ` gives a zero drift and a zero weight here.

**And a fitted half-life is not on its own evidence of reversion.** The OU fit labels a
series reverting whenever its AR(1) coefficient lands in (0, 1), which on a few hundred
points a random walk does as a matter of course — the estimate is biased downward by about
`1 - c/n`. Six pure random walks tested here came back `reverting` every time, with
half-lives of 26 to 51 bars, and two were sized. **Pair mode** therefore puts every spread
through a unit-root test before it can carry weight, because a `--book` is whatever the
caller names and a handful of pairs has a breadth of a handful: each one has to be real.

**The residual cross-section is deliberately not held to that test**, and the asymmetry is
the argument of RESIDUAL.md §1.4 rather than an oversight. A portfolio of 160 residuals
"does not need any individual name to be significant — it needs the average to be
positive", and the aggregate evidence comes from Stage 0's lift over a shuffled null and
Stage 1's information coefficient. Applying the per-name gate there admits about 8% of the
cross-section, which is exactly the measured rejection rate, and destroys the breadth this
whole redesign exists to buy: measured, it left 10 names against 15 factors and no book.

    python portfolio.py                                    # the residual cross-section
    python portfolio.py --book NUE~STLD:equity,HBAN~KEY:equity
    python portfolio.py --dates 12 --json

Exit codes: 0 the book passes every cap and holds something; 3 it is refused or empty;
2 usage error.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import paths

paths.ensure_code_importable()
paths.ensure_marketdata_importable()

import ic                                                          # noqa: E402
import pair_report as pr                                           # noqa: E402
import residual as rs                                              # noqa: E402
import risk                                                        # noqa: E402
import sizing                                                      # noqa: E402

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from statsmodels.tsa.stattools import adfuller                  # noqa: E402

UserError = pr.UserError
DEFAULT_LOG = paths.LOGS / "portfolio.csv"

#: A series the OU fit called reverting but whose level cannot reject a unit root. The fit
#: reports a theta and a half-life; the test says they are indistinguishable from what a
#: random walk produces through small-sample bias alone. Given its own label rather than
#: folded into the explosive regime, because the two say different things: explosive means
#: the series walks away, this means nobody can yet tell whether it does.
UNIDENTIFIED = "unidentified"


@dataclass
class Position:
    """One reverting series, its fitted process, and the size that follows.

    `kind` is `residual` for a factor residual and `pair` for a hedged spread. The two are
    sized by identical arithmetic — both are series that revert to their own mean — and the
    field exists so the report can say which it is holding rather than to branch on.
    """

    name: str
    regime: str
    theta: float
    mu: float
    sigma: float
    x: float
    drift: float
    drift_lower: float
    weight: float
    loading_norm: float = float("nan")
    kind: str = "residual"
    beta: float = float("nan")

    @property
    def half_life(self) -> float:
        return math.log(2) / self.theta if self.theta > 0 else float("nan")


def size_from_ou(series: np.ndarray, n_obs: int, confidence: float,
                 unit_root_level: float = 0.05) -> dict:
    """Fit the OU process to one reverting level and derive its size.

    This is the single implementation of the sizing rule, called by both book types. It is
    a function rather than two copies for the reason `relationship.py` exists: three of this
    project's defects trace to the same formula being written twice and the copies quietly
    disagreeing.

        drift = theta(mu - X)          expected return from where the series sits now
        w     = drift / sigma^2        growth-optimal, via sizing.growth_optimal_leverage

    The drift is discounted by its own standard error before it sizes anything. A haircut
    that exceeds the estimate closes the position; it must never reverse it, so the
    magnitude is discounted and the sign put back afterwards rather than the other way
    round.
    """
    theta, mu, sigma, regime = pr._fit_ou(series)
    x = float(series[-1])
    drift = theta * (mu - x)

    # **A fitted half-life is not evidence of reversion, and this is where that bites.**
    #
    # `pair_report._fit_ou` labels a series reverting whenever the AR(1) coefficient lands
    # in (0, 1). On a few hundred points that estimate is biased downward — the
    # Dickey-Fuller small-sample bias — so a genuine random walk is labelled reverting as a
    # matter of course. The bias is about `1 - c/n`, which on 200 points puts a random
    # walk's apparent half-life near 27 bars; measured here, six pure random walks came back
    # `reverting` every time, with half-lives of 26 to 51, and two of them were sized (-2.98
    # and +5.72) purely because they had wandered away from their own running mean.
    #
    # A half-life bound cannot separate that from real slow reversion, because the artefact
    # and the signal live in the same range. The test that can is the unit-root test.
    #
    # **It is applied to pairs and deliberately not to residuals**, and the asymmetry is the
    # whole argument of RESIDUAL.md section 1.4 rather than an inconsistency. A book of a
    # handful of pairs has a breadth of a handful: each one must be individually real,
    # because there is nothing else to average with. A cross-section of 160 residuals is the
    # opposite case — the strategy "does not need any individual name to be significant, it
    # needs the average to be positive", and the aggregate evidence is supplied upstream by
    # Stage 0's lift over a shuffled null and Stage 1's information coefficient.
    #
    # Demanding per-name significance here would admit about 8% of the cross-section, which
    # is precisely the measured rejection rate, and would destroy the breadth the redesign
    # exists to buy. Measured: the gate applied to residuals left 10 names against 15
    # factors, an empty null space, and no book at all.
    if regime == pr.REVERTING and 0.0 < unit_root_level < 1.0:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pvalue = float(adfuller(series, maxlag=1, autolag=None,
                                    regression="c")[1])
        if not pvalue < unit_root_level:
            regime = UNIDENTIFIED

    lower = sizing.lower_bound_mean(abs(drift), sigma, n_obs, confidence)
    bounded = math.copysign(max(lower, 0.0), drift) if math.isfinite(lower) else 0.0

    weight = 0.0
    if regime == pr.REVERTING and sigma > 0 and bounded != 0.0:
        weight = sizing.growth_optimal_leverage(bounded, sigma)
        if not math.isfinite(weight):
            weight = 0.0
    return {"regime": regime, "theta": theta, "mu": mu, "sigma": sigma, "x": x,
            "drift": drift, "drift_lower": bounded, "weight": weight}


@dataclass
class Book:
    """The whole cross-section at one formation date."""

    positions: list = field(default_factory=list)
    effective_bets: float = float("nan")
    worst_pair: str = ""
    worst_correlation: float = float("nan")
    breaches: list = field(default_factory=list)
    kind: str = "residual"
    projection: dict = field(default_factory=dict)

    @property
    def held(self) -> list:
        return [p for p in self.positions if p.weight != 0.0]

    @property
    def gross(self) -> float:
        return float(sum(abs(p.weight) for p in self.positions))

    @property
    def net(self) -> float:
        return float(sum(p.weight for p in self.positions))

    @property
    def net_share(self) -> float:
        """Net over gross.

        For a residual book this is near zero by construction once neutralised. For a pair
        book it is the directional tilt of the spread bets, which with only a handful of
        relationships is routinely large and is not the same thing as market exposure.
        """
        return self.net / self.gross if self.gross > 0 else float("nan")

    @property
    def ok(self) -> bool:
        return not self.breaches and bool(self.held)


# ------------------------------------------------------------------ the sizing

def fit_positions(returns: np.ndarray, names: list, end: int, args) -> list:
    """Fit the OU process per name at one formation date and size each one.

    The loadings come from the bars before `end` and the residual is accumulated over the
    trailing `--signal-window`, which is the same construction `ic.py` measures skill on.
    Using a different one here would mean sizing a signal nobody has measured.
    """
    window = returns[end - args.pca_window:end]
    usable, weights = rs.eigenportfolios(window, args.factors)
    design = np.column_stack([window[:, usable] @ weights, np.ones(len(window))])
    loadings, *_ = np.linalg.lstsq(design, window, rcond=None)

    tail = slice(len(window) - args.signal_window, len(window))
    accumulated = np.cumsum(window[tail] - design[tail] @ loadings, axis=0)

    # The factor part of each name's loading vector, excluding the intercept. This is the
    # quantity the paper's documented failure regime is indexed by.
    norms = np.linalg.norm(loadings[:-1, :], axis=0)

    out = []
    for i, name in enumerate(names):
        series = accumulated[:, i]
        if not np.isfinite(series).all():
            continue
        # 1.0 disables the per-name unit-root gate. See size_from_ou: the aggregate
        # evidence for the residual cross-section is Stage 0 and Stage 1, not 160
        # individually significant names.
        fitted = size_from_ou(series, args.signal_window, args.confidence, 1.0)
        out.append(Position(name=name, loading_norm=float(norms[i]),
                            kind="residual", **fitted))
    if not out:
        raise UserError("no name produced a usable residual at this formation date")
    return out, loadings[:-1, :]


def fit_pairs(book: list, args) -> list:
    """Fit the OU process to each hedged spread in a book of pairs and size it.

    `book` is a list of `risk.Relationship`, built by `risk.load_book`, whose
    `spread_returns` are the bar-to-bar change in the gross-normalised spread the strategy
    would have been holding — refit on a rolling window at the strategy's own cadence, so
    the series is the thing actually traded rather than a static regression nobody holds.

    The OU process lives in the **level**, not the return, so the level is recovered by
    cumulative sum. The constant of integration is irrelevant: the fit estimates `mu`
    itself, so shifting the whole series shifts `mu` with it and the drift `theta(mu - X)`
    is unchanged.
    """
    out = []
    for relationship in book:
        returns = relationship.spread_returns.dropna()
        if len(returns) < args.signal_window:
            raise UserError(
                f"{relationship.name} has {len(returns)} usable spread bars, fewer than "
                f"the {args.signal_window} the OU fit needs. Lower --signal-window or "
                f"--fit-window, or choose a pair with more history."
            )
        level = np.cumsum(returns.to_numpy(float)[-args.signal_window:])
        fitted = size_from_ou(level, args.signal_window, args.confidence,
                              args.unit_root_level)
        out.append(Position(name=relationship.name, kind="pair",
                            beta=float(relationship.beta), **fitted))
    return out


def neutralise(positions: list, loadings: np.ndarray) -> tuple:
    """Project the weight vector onto the null space of the factor loadings.

    `RESIDUAL.md` section 2.2 adopts this and states why: neutrality becomes an **algebraic
    identity** rather than a fitted quantity, so it cannot silently drift. Before this, the
    book was neutral only because independent drifts happened to cancel — mean net +1.8% but
    a standard deviation of 7.8%, and +47% on a date where the haircut left few names
    standing.

        w_neutral = w - L' (L L')^-1 L w

    with `L` the factors-by-names loading matrix. The book's factor exposure `L w` is then
    zero to floating point. Because the leading component is close to "all names", removing
    exposure to it is close to dollar neutrality, which is what the breach was about.

    Solved by least squares rather than by forming an explicit inverse: `L L'` is
    near-singular whenever two components are nearly collinear, and inverting it there
    produces enormous weights from arithmetic rather than from signal.

    Returns the positions and how much the projection cost, because a projection that
    reshapes the book is removing intended signal rather than unintended exposure, and that
    has to be visible rather than assumed away.
    """
    before = np.array([p.weight for p in positions], dtype=float)
    if not np.isfinite(before).all() or np.allclose(before, 0.0):
        return positions, {"correlation": float("nan"), "gross_before": 0.0,
                           "gross_after": 0.0, "exposure_before": float("nan"),
                           "exposure_after": float("nan"), "names": 0}

    # **Projection runs only over the names the gates already allow.**
    #
    # Projecting the full vector puts weight back on every name, including the ones the
    # uncertainty haircut closed and the one the heavy-loading gate dropped. Measured: the
    # gates allowed 70 names and an unrestricted projection returned a book of 160. That is
    # not a rounding detail -- the heavy-loading gate exists because the construction's own
    # author documents heavy loadings as the regime where this method loses badly, and a
    # projection that silently reinstates a dropped name has removed the gate.
    #
    # Restricting the projection to the held subspace keeps both gates and still reaches
    # exact neutrality, because the null space of a 15-by-70 loading matrix has 55
    # dimensions and there is ample room inside it.
    mask = before != 0.0
    if mask.sum() == 0:
        return positions, {"correlation": float("nan"), "gross_before": 0.0,
                           "gross_after": 0.0, "exposure_before": float("nan"),
                           "exposure_after": float("nan"), "names": 0}

    factors = np.atleast_2d(loadings)[:, mask]
    held_before = before[mask]
    if factors.shape[0] >= mask.sum():
        raise UserError(
            f"{mask.sum()} names are held against {factors.shape[0]} factors, so the null "
            f"space is empty and no non-zero book can be factor-neutral. Reduce --factors, "
            f"lower --confidence so fewer names are closed, or widen the universe."
        )

    exposure_before = float(np.linalg.norm(factors @ held_before))
    coefficients, *_ = np.linalg.lstsq(factors @ factors.T, factors @ held_before,
                                       rcond=None)
    held_after = held_before - factors.T @ coefficients

    # Projection annihilating the whole vector means every held weight lay inside the factor
    # span, so the "residual" book was a factor bet wearing a residual's name. Refused
    # rather than returned as an empty book, which would otherwise read as a clean pass.
    if np.linalg.norm(held_after) <= 1e-12 * max(np.linalg.norm(held_before), 1e-300):
        raise UserError(
            "factor-neutralising annihilated every weight: the book lay entirely inside "
            "the span of the factor loadings, so it was a factor bet rather than a "
            "residual one. Reduce --factors or widen the universe."
        )

    after = np.zeros_like(before)
    after[mask] = held_after
    for position, weight in zip(positions, after):
        position.weight = float(weight)

    denominator = np.linalg.norm(held_before) * np.linalg.norm(held_after)
    return positions, {
        "correlation": (float(held_before @ held_after / denominator)
                        if denominator > 0 else float("nan")),
        "gross_before": float(np.abs(held_before).sum()),
        "gross_after": float(np.abs(held_after).sum()),
        "exposure_before": exposure_before,
        "exposure_after": float(np.linalg.norm(factors @ held_after)),
        "names": int(mask.sum()),
    }


def drop_heavy_loadings(positions: list, multiple: float) -> list:
    """Refuse names whose factor loading is far above the cross-section.

    The construction's own author documents the failure: the heaviest loadings produce the
    largest positions and, with transaction costs charged, heavy losses. The threshold is a
    multiple of the median rather than an absolute number, because the scale of a loading
    depends on how many factors were removed and an absolute bound would silently mean
    something different at every `--factors`.
    """
    norms = np.array([p.loading_norm for p in positions])
    finite = norms[np.isfinite(norms)]
    if finite.size == 0:
        return positions
    limit = float(np.median(finite)) * multiple
    for position in positions:
        if math.isfinite(position.loading_norm) and position.loading_norm > limit:
            position.weight = 0.0
            position.regime = f"{position.regime} (loading {position.loading_norm:.2f} "\
                              f"over {limit:.2f})"
    return positions


def scale_to_gross(positions: list, gross: float) -> list:
    """Rescale so the book's gross exposure is the stated budget.

    Scaling is uniform, so it changes the size of the book and not the relative sizes
    inside it — the shape is what the OU fit decided and this only chooses how much of it
    to hold.
    """
    total = sum(abs(p.weight) for p in positions)
    if total <= 0:
        return positions
    factor = gross / total
    for position in positions:
        position.weight *= factor
    return positions


def assemble(returns: np.ndarray, names: list, end: int, args,
             measure_breadth: bool = True) -> Book:
    """The residual cross-section: fit, gate, neutralise, scale, then check the caps.

    `measure_breadth` exists for `size_across_dates`, which asks only how net exposure
    varies from date to date. Breadth needs a long tiled sample and is refused on a short
    one, so an early formation date cannot supply it -- and the distribution of net exposure
    does not need it.
    """
    positions, loadings = fit_positions(returns, names, end, args)
    positions = drop_heavy_loadings(positions, args.max_loading_multiple)

    projection = {}
    if getattr(args, "neutralise", True):
        # Before scaling, so the gross budget is set on what is actually held rather than
        # on a vector the projection is about to shorten.
        positions, projection = neutralise(positions, loadings)
    positions = scale_to_gross(positions, args.gross)

    book = Book(positions=positions, kind="residual", projection=projection)

    # Breadth on the residual cross-section, from the same tiled sample `ic.py` uses, so
    # the two scripts cannot report different breadths for the same panel.
    if measure_breadth:
        measured = ic.breadth(ic.breadth_returns(returns[:end], args), names)
        book.effective_bets = measured["effective_bets"]
        book.worst_pair = measured["worst_pair"]
        book.worst_correlation = measured["worst_correlation"]

    if not book.held:
        book.breaches.append("no name is in the reverting regime with a drift that "
                             "survives its own uncertainty; the book is empty")
    if math.isfinite(book.net_share) and abs(book.net_share) > args.max_net:
        book.breaches.append(
            f"net exposure is {book.net_share:+.0%} of gross, above the "
            f"{args.max_net:.0%} cap. A residual book sits near zero by construction, so "
            f"this says the signal is one-sided rather than market-neutral")
    if (measure_breadth and math.isfinite(book.effective_bets)
            and book.effective_bets < args.min_effective_bets):
        book.breaches.append(
            f"the residuals contain {book.effective_bets:.1f} independent bets, below the "
            f"{args.min_effective_bets:g} required. Breadth is the entire reason this "
            f"redesign exists")
    if measure_breadth and abs(book.worst_correlation) > args.max_correlation:
        book.breaches.append(
            f"{book.worst_pair} residuals correlate at {book.worst_correlation:+.2f}, above "
            f"the {args.max_correlation:.2f} cap; the factor model has not separated them")
    return book


def assemble_pairs(relationships: list, args) -> Book:
    """A book of hedged pairs: fit, size, scale, then check the same caps.

    No factor projection here. Each pair carries its own hedge ratio, so its neutrality is
    already a property of the relationship rather than of the book, and `risk.check_caps`
    gates it per relationship through `hedge.net_exposure(beta)`. Projecting across pairs
    would impose a constraint nobody derived.
    """
    positions = scale_to_gross(fit_pairs(relationships, args), args.gross)
    book = Book(positions=positions, kind="pair")

    correlation = risk.correlation_matrix(relationships)
    book.effective_bets = risk.effective_bets(correlation)
    worst = risk.worst_correlation(correlation)
    book.worst_pair, book.worst_correlation = f"{worst[0]} / {worst[1]}", float(worst[2])

    verdict = risk.check_caps(relationships, correlation,
                              max_net=args.max_leg_net,
                              max_book_net=args.max_leg_net,
                              max_correlation=args.max_correlation,
                              min_effective_bets=args.min_pair_bets)
    book.breaches.extend(verdict.breaches)

    if not book.held:
        book.breaches.append("no pair is in the reverting regime with a drift that "
                             "survives its own uncertainty; the book is empty")
    return book


# ------------------------------------------------------------------ reporting

def size_across_dates(returns: np.ndarray, names: list, args) -> dict:
    """Size at several evenly spaced formation dates and collect the spread.

    Sizing only at the final bar is what let one unusual date decide a verdict: on
    2026-09-14 the haircut left 70 names standing instead of the usual 155, and the few
    survivors happened to be one-sided. A single date is a book; several are a property.
    """
    first = args.pca_window + args.signal_window
    if len(returns) <= first:
        raise UserError("the panel is too short to size at more than one date")
    ends = np.linspace(first, len(returns), args.dates, dtype=int)
    nets, held, grosses = [], [], []
    for end in ends:
        book = assemble(returns, names, int(end), args, measure_breadth=False)
        nets.append(book.net_share)
        held.append(len(book.held))
        grosses.append(book.gross)
    return {"ends": [int(e) for e in ends], "nets": nets, "held": held,
            "gross": grosses}


def show(book: Book, args, log) -> None:
    held = book.held
    noun = "residuals" if book.kind == "residual" else "pairs"
    width = 10 if book.kind == "residual" else 20
    log("")
    log(f"  {len(book.positions)} {noun} fitted, {len(held)} held, "
        f"{len(book.positions) - len(held)} at zero")
    log(f"  gross {book.gross:.3f}   net {book.net:+.4f} "
        f"({book.net_share:+.1%} of gross)   "
        f"{book.effective_bets:.1f} independent bets")
    if book.kind == "pair":
        # Two different quantities share the word "net" and confusing them would be easy.
        # This one says whether the spread bets point the same way; it is not leg-level
        # market exposure, which is a property of each hedge ratio and is capped per
        # relationship by --max-leg-net inside risk.check_caps.
        log(f"  that net is the tilt of the spread bets, not market exposure: leg-level "
            f"exposure")
        log(f"  is capped per relationship at {args.max_leg_net:.0%} of gross. A book of "
            f"two bets on the")
        log(f"  same side reads as 100% tilted and may still be market-neutral.")
    log("")
    level = "X" if book.kind == "residual" else "S"
    extra = f"{'beta':>8s}" if book.kind == "pair" else ""
    log(f"  {'name':{width}s} {'regime':12s} {'half-life':>10s} {level:>9s} "
        f"{'drift':>10s} {'haircut':>10s} {'weight':>9s}{extra}")
    ordered = sorted(held, key=lambda p: -abs(p.weight))[:args.show]
    for p in ordered:
        tail = f"{p.beta:8.3f}" if book.kind == "pair" else ""
        log(f"  {p.name:{width}s} {p.regime[:12]:12s} {p.half_life:10.1f} {p.x:9.4f} "
            f"{p.drift:+10.5f} {p.drift_lower:+10.5f} {p.weight:+9.4f}{tail}")
    if len(held) > args.show:
        log(f"  … {len(held) - args.show} more")

    zeroed = [p for p in book.positions if p.weight == 0.0]
    if zeroed:
        reasons: dict = {}
        for p in zeroed:
            key = p.regime.split(" (")[0] if "(" in p.regime else p.regime
            key = "loading too heavy" if "loading" in p.regime else key
            reasons[key] = reasons.get(key, 0) + 1
        log("")
        log("  not held: " + ", ".join(f"{count} {reason}"
                                       for reason, count in sorted(reasons.items())))


def append_log(path: Path, args, book: Book, panel: pd.DataFrame | None) -> int:
    row = {"run": 0,
           "run_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "kind": book.kind,
           "asset_class": args.asset_class, "timeframe": args.timeframe,
           "names": panel.shape[1] if panel is not None else len(book.positions),
           "bars": panel.shape[0] if panel is not None else 0,
           "neutralised": "yes" if book.projection else "no",
           "factors": args.factors, "pca_window": args.pca_window,
           "signal_window": args.signal_window, "confidence": args.confidence,
           "gross": args.gross, "fitted": len(book.positions), "held": len(book.held),
           "net_share": round(book.net_share, 5) if math.isfinite(book.net_share) else "",
           "effective_bets": round(book.effective_bets, 2),
           "worst_pair": book.worst_pair,
           "worst_correlation": round(book.worst_correlation, 4),
           "breaches": len(book.breaches),
           "accepted": "yes" if book.ok else "no"}
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
    p = argparse.ArgumentParser(prog="portfolio", description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sel = p.add_argument_group("selection")
    sel.add_argument("--book", default=None,
                     help="a book of named pairs, as A~B:asset_class[:broker] separated by "
                          "commas. Given this, the script sizes those spreads instead of "
                          "the residual cross-section")
    sel.add_argument("-a", "--asset-class", default="equity")
    sel.add_argument("-t", "--timeframe", default="1d")
    sel.add_argument("--source", default=None)
    sel.add_argument("--min-bars", type=int, default=5000)
    sel.add_argument("--start", default=None)
    sel.add_argument("--end", default=None)

    struct = p.add_argument_group("structure - choose once, not per run")
    struct.add_argument("--pca-window", type=int, default=252)
    struct.add_argument("--signal-window", type=int, default=60)
    struct.add_argument("--step", type=int, default=21,
                        help="used only for the breadth sample, which tiles the panel")
    struct.add_argument("--factors", type=int, default=15)
    struct.add_argument("--neutralise", action=argparse.BooleanOptionalAction, default=True,
                        help="project the residual book onto the null space of the factor "
                             "loadings, so its factor exposure is zero by algebra rather "
                             "than by cancellation. --no-neutralise restores the older "
                             "behaviour and is there to measure what the projection costs, "
                             "not to be run routinely")
    struct.add_argument("--fit-window", type=int, default=250,
                        help="pair mode: bars the hedge ratio is refit on")
    struct.add_argument("--rehedge-every", type=int, default=5,
                        help="pair mode: bars between hedge refits")
    struct.add_argument("--price", default="log", choices=("log", "raw"))

    given = p.add_argument_group("given by reality")
    given.add_argument("--gross", type=float, default=1.0,
                       help="gross exposure budget the book is scaled to, in units of "
                            "equity. Scaling is uniform, so it sets how much of the book "
                            "to hold and not its shape")

    gates = p.add_argument_group("gates - every value is a trial")
    gates.add_argument("--unit-root-level", type=float, default=0.05,
                       help="PAIR MODE ONLY. A spread whose level does not reject a unit "
                            "root at this level is not sized. Without it the OU fit calls a "
                            "random walk reverting -- six pure random walks were labelled "
                            "reverting every time here, two of them sized -- because the "
                            "AR(1) estimate is biased downwards on a few hundred points. "
                            "Deliberately NOT applied to the residual cross-section: "
                            "RESIDUAL.md 1.4 is that a portfolio needs the average to be "
                            "positive rather than each name to be significant, and applying "
                            "it there admitted 8%% of names and produced no book at all. "
                            "Set 1.0 to disable it in pair mode too")
    gates.add_argument("--confidence", type=float, default=1.0,
                       help="standard errors of haircut applied to the OU drift before it "
                            "sizes anything")
    gates.add_argument("--max-loading-multiple", type=float, default=3.0,
                       help="a name whose factor loading norm exceeds this multiple of the "
                            "median is not held; the construction's documented failure "
                            "regime is the heaviest loadings")
    gates.add_argument("--max-net", type=float, default=0.10,
                       help="net over gross exposure the book may carry. A residual book is "
                            "not neutral because anybody imposed neutrality; it is neutral "
                            "because independent drifts cancel, and net/gross therefore "
                            "scales as 1/sqrt(N). At 160 names that predicts 7.9%%, and "
                            "measured across eleven formation dates it is a mean of +1.8%% "
                            "with a standard deviation of 7.8%%. So this cap sits at about "
                            "1.3 standard deviations and is breached on roughly one date in "
                            "five by ordinary variation. Widen it for a narrower panel; the "
                            "default assumes a cross-section of this size")
    gates.add_argument("--max-correlation", type=float, default=0.70,
                       help="largest absolute correlation permitted between two residuals")
    gates.add_argument("--min-effective-bets", type=float, default=20.0,
                       help="independent bets the cross-section must contain")
    gates.add_argument("--min-pair-bets", type=float, default=1.5,
                       help="pair mode: independent bets the book must contain. Lower than "
                            "the residual cap because a book of pairs is small by nature; "
                            "this is risk.py's own default")
    gates.add_argument("--max-leg-net", type=float, default=0.35,
                       help="pair mode: net over gross exposure one relationship may carry, "
                            "from its hedge ratio. This is the gate that rejected AMGN~LLY "
                            "at 72% net long -- a single-name bet wearing a spread's name")

    out = p.add_argument_group("output")
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--log", default=str(DEFAULT_LOG))
    out.add_argument("--no-log", action="store_true")
    out.add_argument("--show", type=int, default=20, help="rows of the book to print")
    out.add_argument("--dates", type=int, default=1,
                     help="size at this many evenly spaced formation dates and report the "
                          "distribution. The default of 1 sizes the last bar, which is the "
                          "live book; more than 1 is how to tell whether that bar was "
                          "typical. Residual mode only")
    out.add_argument("--dry-run", action="store_true",
                     help="fit and size but write nothing")
    out.add_argument("--json", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))
    if args.factors < 1:
        raise UserError("--factors must be at least 1")
    if args.factors >= args.pca_window:
        raise UserError("--factors must be fewer than --pca-window bars, or the loading "
                        "regression has no degrees of freedom")
    if args.signal_window > args.pca_window:
        raise UserError("--signal-window cannot exceed --pca-window")
    if args.signal_window < 20:
        raise UserError("--signal-window below 20 bars leaves the OU fit with almost "
                        "nothing to estimate three parameters from")
    if args.confidence < 0:
        raise UserError("--confidence cannot be negative; it is a haircut, and a negative "
                        "one would inflate the drift it is meant to discount")
    if args.gross <= 0:
        raise UserError("--gross must be positive")
    if not 0.0 <= args.max_net <= 1.0:
        raise UserError("--max-net is a share of gross and must be between 0 and 1")

    if args.dates < 1:
        raise UserError("--dates must be at least 1")

    panel, returns, names = None, None, None
    if args.book:
        relationships = risk.load_book(risk.parse_book(args.book, args.timeframe), args)
        log(f"pair portfolio   {len(relationships)} relationships   "
            f"{args.timeframe}   hedge refit every {args.rehedge_every} bars on "
            f"{args.fit_window}")
        log(f"  weights are OU-derived: w = theta(mu - S)/sigma^2, haircut "
            f"{args.confidence:g} standard errors, no entry threshold")
        book = assemble_pairs(relationships, args)
    else:
        panel = rs.load_panel(Path(args.store), args.asset_class, args.timeframe,
                              args.min_bars, args.source)
        returns = np.diff(np.log(panel.to_numpy(float)), axis=0)
        names = list(panel.columns)

        log(f"{args.asset_class} residual portfolio   {panel.shape[1]} names   "
            f"{panel.shape[0]:,} common bars   "
            f"{panel.index[0]:%Y-%m-%d} to {panel.index[-1]:%Y-%m-%d}")
        log(f"  {args.factors} factors on {args.pca_window} bars, residual over the "
            f"trailing {args.signal_window}, sized at the last bar")
        log(f"  weights are OU-derived: w = theta(mu - X)/sigma^2, haircut "
            f"{args.confidence:g} standard errors, no entry threshold"
            + (", factor-neutralised" if args.neutralise else ", NOT neutralised"))

        book = assemble(returns, names, len(returns), args)

    show(book, args, log)

    if book.projection:
        p = book.projection
        log("")
        log(f"  factor-neutralising: exposure ||Lw|| {p['exposure_before']:.3e} -> "
            f"{p['exposure_after']:.3e}")
        log(f"  cost of the projection: weights correlate {p['correlation']:+.4f} with "
            f"their pre-projection values,")
        log(f"  gross {p['gross_before']:.3f} -> {p['gross_after']:.3f} before rescaling. "
            f"A low correlation would mean")
        log(f"  the projection is removing signal rather than unintended exposure.")

    if args.dates > 1 and not args.book:
        spread = size_across_dates(returns, names, args)
        log("")
        log(f"  across {len(spread['nets'])} formation dates: net "
            f"{np.mean(spread['nets']):+.2%} +/- {np.std(spread['nets'], ddof=1):.2%}, "
            f"|net| mean {np.mean(np.abs(spread['nets'])):.2%}")
        log(f"  held {np.mean(spread['held']):.0f} names on average, "
            f"{np.min(spread['held'])} to {np.max(spread['held'])}")
        log(f"  dates breaching the {args.max_net:.0%} net cap: "
            f"{np.mean(np.abs(spread['nets']) > args.max_net):.0%}")

    log("")
    if book.ok:
        log(f"  ACCEPTED — {len(book.held)} positions, gross {book.gross:.2f}, net "
            f"{book.net_share:+.1%} of gross,")
        log(f"  {book.effective_bets:.1f} independent bets. Every size is a consequence of "
            f"a fitted")
        log(f"  process rather than a threshold somebody chose.")
        log(f"  This is not a backtest. It is the book as it stands on the last bar, and "
            f"what")
        log(f"  it would have earned is Stage 2's question, with the real spread charged.")
        if book.kind == "pair":
            log(f"  These pairs have not cleared Stage 2. Sizing them exercises the "
                f"allocator;")
            log(f"  it is not a recommendation to hold them.")
    else:
        log(f"  REFUSED — {len(book.breaches)} breach(es):")
        for breach in book.breaches:
            log(f"    - {breach}")

    if args.json:
        print(json.dumps({
            "kind": book.kind,
            "names": panel.shape[1] if panel is not None else len(book.positions),
            "fitted": len(book.positions),
            "held": len(book.held), "gross": book.gross, "net": book.net,
            "net_share": book.net_share, "effective_bets": book.effective_bets,
            "worst_pair": book.worst_pair, "worst_correlation": book.worst_correlation,
            "projection": book.projection,
            "breaches": book.breaches, "accepted": book.ok,
            "positions": [{"name": p.name, "kind": p.kind, "regime": p.regime,
                           "theta": p.theta, "half_life": p.half_life, "x": p.x,
                           "drift": p.drift, "weight": p.weight, "beta": p.beta,
                           "loading_norm": p.loading_norm}
                          for p in sorted(book.held, key=lambda q: -abs(q.weight))],
        }, indent=2, default=str))

    if not args.no_log and not args.dry_run:
        run = append_log(Path(args.log), args, book, panel)
        log(f"\n  run #{run} logged to {Path(args.log).resolve()}")
    return 0 if book.ok else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:                                       # noqa: BLE001
        if "-v" in sys.argv or "--verbose" in sys.argv:
            raise
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
