"""The one hedge-fit and one spread-build, so there is a single implementation
of each rather than several that can quietly disagree.

Before this module existed, eight call sites across `pair_report.py`,
`health.py`, `hedge.py`, `screen.py` and `basket_screen.py` each ran their own
`np.polyfit(x, y, 1)` to fit a hedge ratio, and `basket_screen.py` ran a ninth
version by hand for more than one leg. Three separate "two copies of a formula
disagreed" defects in this project trace back to that duplication -- not
because the math is hard, but because six people writing the same six-line fit
six times will eventually write it six different ways, and nothing forces them
to notice.

This module deliberately does not decide anything: it has no gate, no p-value
threshold, and no verdict. It answers exactly one question -- given a spread's
two sides, what is the hedge ratio and what is the residual -- and every script
that needs that answer asks it here instead of asking `numpy` again.

What is **not** unified, on purpose: the OU/AR(1) fit that measures how fast a
spread mean-reverts (`pair_report._fit_ou`, `outcomes.py`, `health.py`,
`hedge.kalman_beta`'s seed) is a different regression on different data -- a
series against its own lag, not one instrument against another -- and folding
it into this module would hide that distinction rather than remove it.
"""
from __future__ import annotations

import numpy as np

__all__ = ["ols_beta", "ols_hedge", "build_spread", "build_spread_n"]


def ols_beta(y: np.ndarray, x: np.ndarray, *, split: int | None = None) -> tuple[float, float]:
    """Fit `y = beta * x + alpha` by ordinary least squares, one leg on one leg.

    Fitted on `x[:split], y[:split]` when `split` is given, and on the whole
    array otherwise. The split is a parameter here rather than a slice the
    caller takes beforehand, so that "fit only on what has been seen so far" is
    stated in one place instead of trusted to whoever calls this.

    This is the pair form of `ols_hedge`, kept separate because every call site
    that used to write `np.polyfit(x, y, 1)` wants a scalar beta back, not a
    one-element array, and a wrapper that unwraps it every time would be its own
    small source of the bug this module exists to remove.
    """
    xs = x[:split] if split is not None else x
    ys = y[:split] if split is not None else y
    beta, alpha = (float(v) for v in np.polyfit(xs, ys, 1))
    return beta, alpha


def ols_hedge(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, float]:
    """Fit `y = x @ weights + alpha` by ordinary least squares, one leg on many.

    `x` is bars by legs. For a single leg this returns the same weight
    `ols_beta` does, to floating-point tolerance -- both solve the same normal
    equations, one through `numpy.polyfit` and one through `numpy.linalg.lstsq`
    -- so a basket of one is not a special case a caller has to branch on.
    """
    x2d = np.atleast_2d(x)
    if x2d.shape[0] == len(y) and x.ndim == 1:
        x2d = x.reshape(-1, 1)
    elif x2d.shape[0] != len(y):
        x2d = x2d.T
    design = np.column_stack([x2d, np.ones(len(y))])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    return coef[:-1], float(coef[-1])


def build_spread(y: np.ndarray, x: np.ndarray, beta: float, alpha: float) -> np.ndarray:
    """The residual of a pair hedge: `y - beta * x - alpha`."""
    return y - beta * x - alpha


def build_spread_n(y: np.ndarray, x: np.ndarray, weights: np.ndarray, alpha: float) -> np.ndarray:
    """The residual of a basket hedge: `y - x @ weights - alpha`."""
    x2d = np.atleast_2d(x)
    if x2d.shape[0] == len(y) and x.ndim == 1:
        x2d = x.reshape(-1, 1)
    elif x2d.shape[0] != len(y):
        x2d = x2d.T
    return y - x2d @ weights - alpha
