"""Step 1c — the decision function, shared by the backtest and by live trading.

Named `strategy` rather than `signal` on purpose: a module called `signal.py`
next to a script shadows the standard library module of that name, and the
first thing to break is `subprocess`, several imports away and with an error
that names neither file.

One pure function: bars in, target position out. No file reading, no order
placing, no printing. It exists as its own module because of the single hard
constraint in the plan — the backtest must replay bars through the exact code
that runs live. Two code paths means the backtest measures nothing.

    target = target_position(history, state, params)

`history` ends at the bar being decided on, so look-ahead is impossible by
construction rather than by discipline. Everything the strategy remembers lives
in `state`, and everything the operator chose lives in `params`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

FLAT, LONG, SHORT = 0, 1, -1

#: Why the position changed, recorded on every decision so a trade can be
#: explained afterwards rather than guessed at.
ENTRY_LONG = "entry: z below the negative entry threshold"
ENTRY_SHORT = "entry: z above the entry threshold"
EXIT_TARGET = "exit: z returned inside the exit threshold"
EXIT_STOP = "exit: z passed the stop, the relationship is presumed broken"
EXIT_TIME = "exit: held longer than the maximum"
HOLD = "hold"
WAIT = "flat"
NO_FIT = "flat: not enough history to fit the relationship"


@dataclass(frozen=True)
class SignalParams:
    """Everything the operator chooses. Nothing here is learned at run time."""

    entry_z: float = 2.0
    exit_z: float = 0.5
    stop_z: float = 4.0
    max_holding_bars: int = 20
    min_bars_between_trades: int = 0
    hedge_source: str = "rolling"             # static or rolling
    fit_window: int = 250                     # bars used by a rolling fit
    rehedge_every: int = 5                    # bars between rolling refits
    use_log: bool = True

    def __post_init__(self) -> None:
        if self.exit_z >= self.entry_z:
            raise ValueError("exit_z must be below entry_z")
        if self.stop_z <= self.entry_z:
            raise ValueError("stop_z must be above entry_z")
        if self.hedge_source not in ("static", "rolling"):
            raise ValueError(f"unknown hedge_source {self.hedge_source!r}")


@dataclass(frozen=True)
class Fit:
    """The relationship as measured at one moment, never updated in place."""

    beta: float
    alpha: float
    mu: float
    sigma_eq: float
    fitted_at: int                            # index of the bar it was fitted on

    def z(self, log_a: float, log_b: float) -> float:
        spread = log_a - self.beta * log_b - self.alpha
        return (spread - self.mu) / self.sigma_eq


@dataclass(frozen=True)
class SignalState:
    """What the strategy remembers between bars."""

    position: int = FLAT
    bars_held: int = 0
    bars_since_exit: int = 10 ** 6
    entry_z: float = 0.0
    fit: Fit | None = None


@dataclass(frozen=True)
class Target:
    """The decision for this bar."""

    position: int
    reason: str
    z: float = float("nan")
    fit: Fit | None = None
    state: SignalState = field(default_factory=SignalState)


def fit_relationship(prices: pd.DataFrame, *, use_log: bool, at: int) -> Fit | None:
    """Hedge ratio and spread statistics from the frame given, and nothing after it.

    Returns None when the sample is too short or the spread is not an OU
    process, which the caller must treat as "stay flat" rather than as zero.
    """
    if len(prices) < 60:
        return None
    px = np.log(prices) if use_log else prices
    a, b = prices.columns
    x = px[b].to_numpy(float)
    y = px[a].to_numpy(float)
    if not (np.isfinite(x).all() and np.isfinite(y).all()):
        return None
    beta, alpha = (float(v) for v in np.polyfit(x, y, 1))
    spread = y - beta * x - alpha
    s0, s1 = spread[:-1], spread[1:]
    ar, const = (float(v) for v in np.polyfit(s0, s1, 1))
    if not (0.0 < ar < 1.0):
        return None                            # explosive or sub-bar: no OU fit
    mu = const / (1 - ar)
    resid_sd = float(np.std(s1 - (ar * s0 + const), ddof=2))
    sigma_eq = resid_sd / math.sqrt(1 - ar ** 2)
    if not (math.isfinite(sigma_eq) and sigma_eq > 0):
        return None
    return Fit(beta=beta, alpha=alpha, mu=mu, sigma_eq=sigma_eq, fitted_at=at)


def _needs_refit(state: SignalState, params: SignalParams, bar: int) -> bool:
    if state.fit is None:
        return True
    if params.hedge_source == "static":
        return False
    # A position is never re-hedged underneath itself: changing the ratio while
    # the trade is open silently changes what is being held.
    if state.position != FLAT:
        return False
    return bar - state.fit.fitted_at >= params.rehedge_every


def target_position(history: pd.DataFrame, state: SignalState,
                    params: SignalParams) -> Target:
    """Position for both legs at the last bar of `history`.

    The contract: `history` contains bars up to and including the one being
    decided, and nothing later. The returned target is acted on at the next
    bar, which is the caller's responsibility to honour.
    """
    bar = len(history) - 1

    fit = state.fit
    if _needs_refit(state, params, bar):
        window = (history if params.hedge_source == "static"
                  else history.iloc[max(0, len(history) - params.fit_window):])
        refitted = fit_relationship(window, use_log=params.use_log, at=bar)
        fit = refitted if refitted is not None else fit

    if fit is None:
        return Target(FLAT, NO_FIT, float("nan"), None,
                      replace(state, position=FLAT, bars_held=0,
                              bars_since_exit=state.bars_since_exit + 1, fit=None))

    # Only the last bar is needed to score the spread. Transforming the whole
    # history here would make the replay quadratic in the number of bars.
    last = history.iloc[-1]
    last_a, last_b = float(last.iloc[0]), float(last.iloc[1])
    if params.use_log:
        if last_a <= 0 or last_b <= 0:
            return Target(FLAT, NO_FIT, float("nan"), fit,
                          replace(state, position=FLAT, bars_held=0, fit=fit))
        last_a, last_b = math.log(last_a), math.log(last_b)
    z = fit.z(last_a, last_b)

    if state.position != FLAT:
        held = state.bars_held + 1
        if abs(z) >= params.stop_z:
            reason, position = EXIT_STOP, FLAT
        elif held >= params.max_holding_bars:
            reason, position = EXIT_TIME, FLAT
        elif abs(z) <= params.exit_z:
            reason, position = EXIT_TARGET, FLAT
        else:
            return Target(state.position, HOLD, z, fit,
                          replace(state, bars_held=held, fit=fit))
        return Target(position, reason, z, fit,
                      SignalState(position=FLAT, bars_held=0, bars_since_exit=0,
                                  entry_z=0.0, fit=fit))

    waited = state.bars_since_exit + 1
    if waited < params.min_bars_between_trades:
        return Target(FLAT, WAIT, z, fit, replace(state, bars_since_exit=waited, fit=fit))

    # A spread beyond the stop is not an opportunity, it is the case the stop
    # exists for, so no position is opened there.
    if params.entry_z <= abs(z) < params.stop_z:
        position = SHORT if z > 0 else LONG
        reason = ENTRY_SHORT if z > 0 else ENTRY_LONG
        return Target(position, reason, z, fit,
                      SignalState(position=position, bars_held=0, bars_since_exit=waited,
                                  entry_z=z, fit=fit))

    return Target(FLAT, WAIT, z, fit, replace(state, bars_since_exit=waited, fit=fit))


def leg_weights(position: int, beta: float) -> tuple[float, float]:
    """Units of each leg for a unit of spread exposure.

    Long the spread is long A and short beta of B. A negative beta already
    flips the second leg, which is what makes the arithmetic uniform.
    """
    return float(position), float(-position * beta)
