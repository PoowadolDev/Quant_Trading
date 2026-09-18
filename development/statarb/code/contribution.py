"""Does adding this candidate improve the book it would join?

Everything else in this project judges a candidate alone. That is the right question for a
strategy held alone and the wrong one for a strategy held alongside others, and the
difference is not rhetorical: a candidate with a poor standalone Sharpe but little
correlation to what is already held can raise the book's Sharpe, because the book's risk
falls faster than its return does.

Nothing measured this before. `risk.effective_bets` and `risk.correlation_matrix` already
compute the whole-book quantities; the missing step was one subtraction.

    incremental Sharpe   SR(B and c) - SR(B)
    breadth change       effective_bets(B and c) - effective_bets(B)
    closeness            max |corr(c, b)| over b in B

**Equal weighting is an assumption, stated rather than hidden.** `risk.book_equity` weights
a book equally with the comment that "sizing is `sizing.py`'s job and guessing at it here
would make the drawdown a statement about weights nobody chose". The same reasoning applies:
this measures whether a candidate helps a book held the simplest way, not whether some
optimal weighting could be found to make it help. An optimiser asked "can this possibly
help" will nearly always answer yes, which is why it is not asked here.

**Every assessment is a trial.** Asking "does it improve a book" of a candidate already
rejected on its own is a second selection channel, and a second channel inflates the
multiple-testing correction exactly as the first one does. `triallog.register` records the
count before the assessments run, so the denominator is not reconstructed afterwards.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

import paths

paths.ensure_code_importable()

import backtest as bt                                              # noqa: E402
import risk                                                        # noqa: E402

__all__ = ["Contribution", "measure", "improves_book"]

#: A candidate has to move the book's Sharpe by more than rounding to count as helping.
#: Deliberately not zero: a difference in the fourth decimal of a Sharpe estimated on a few
#: hundred bars is noise, and treating it as a promotion would let any candidate in.
MIN_SHARPE_GAIN = 0.05


@dataclass(frozen=True)
class Contribution:
    """What one candidate does to a book it is added to, under equal weights."""

    name: str
    book_size: int
    bars: int
    sharpe_before: float
    sharpe_after: float
    bets_before: float
    bets_after: float
    max_correlation: float
    closest: str

    @property
    def sharpe_change(self) -> float:
        return self.sharpe_after - self.sharpe_before

    @property
    def breadth_change(self) -> float:
        return self.bets_after - self.bets_before

    @property
    def helps(self) -> bool:
        """Does it raise the book's Sharpe by more than rounding?"""
        return (math.isfinite(self.sharpe_change)
                and self.sharpe_change >= MIN_SHARPE_GAIN)


def _equal_weight_returns(frame: pd.DataFrame) -> np.ndarray:
    """The return series of holding every column in equal size."""
    return frame.mean(axis=1).to_numpy(float)


def measure(name: str, candidate: pd.Series, book: dict, *,
            bars_per_year: float = 252.0) -> Contribution:
    """Compare the book with and without the candidate.

    `candidate` and the values of `book` are **return series indexed by time**. They are
    aligned on the bars they share rather than filled: a filled return is a return that did
    not happen, and it biases every correlation towards zero, which is the direction that
    makes a book look safer than it is.

    **What you pass decides what the Sharpe means, and the two available inputs do not mean
    the same thing.**

    * `risk.spread_returns` gives the bar-to-bar change of a spread held *continuously*.
      Correct for breadth and correlation, because those are questions about how the
      spreads co-move whether or not anyone is in them. **Wrong for the Sharpe**, which
      then describes always holding the spread rather than trading it — and the strategy is
      flat most of the time.
    * A traded equity curve, differenced — `risk.load_book` supplies one as `equity_net`
      when an entry names a broker. Correct for the Sharpe, and it is what a decision about
      adding a candidate to a live book should use.

    This function cannot tell which it was given, so the caller has to know. Reporting a
    continuously-held Sharpe as though it were a strategy Sharpe would be the same class of
    error as the expected-move formula that over-predicted realised gross by 10x to 68x:
    a number that is correct about what it computes and wrong about what it implies.
    """
    if not book:
        raise ValueError("a contribution is measured against a book; this one is empty")

    frame = pd.DataFrame({**book, name: candidate}).dropna()
    if len(frame) < 30:
        raise ValueError(
            f"{name} shares only {len(frame)} bars with the book, too few to compare a "
            f"Sharpe before and after. Check the date ranges overlap.")

    without = frame.drop(columns=[name])
    before = bt.sharpe_ratio(_equal_weight_returns(without), bars_per_year)
    after = bt.sharpe_ratio(_equal_weight_returns(frame), bars_per_year)

    # Breadth from the same participation ratio the rest of the project uses, so a
    # "breadth" here means what it means everywhere else.
    bets_before = risk.effective_bets(without.corr()) if without.shape[1] > 1 else 1.0
    bets_after = risk.effective_bets(frame.corr())

    correlations = {column: abs(float(frame[column].corr(frame[name])))
                    for column in without.columns}
    closest = max(correlations, key=correlations.get)

    return Contribution(
        name=name, book_size=without.shape[1], bars=len(frame),
        sharpe_before=float(before), sharpe_after=float(after),
        bets_before=float(bets_before), bets_after=float(bets_after),
        max_correlation=float(correlations[closest]), closest=closest)


def improves_book(contribution: Contribution | None) -> bool:
    """Whether a candidate earns its place in the book on the evidence measured.

    A separate function rather than an attribute because the answer is a policy and the
    attribute is a measurement, and the two should be replaceable independently. Right now
    the policy is the simplest defensible one: it has to raise the Sharpe. Adding breadth
    while lowering the Sharpe is not an improvement, it is diversifying into something
    worse.
    """
    return contribution is not None and contribution.helps
