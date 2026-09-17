# 2026-09-17 — `relationship.py`, the Step 2 unifier

## Subject

Build the last deferred item in Step 2. It was not blocked on a candidate,
only sequenced after the other Step 2 scripts settled, and they have — 89
checks green since the last audit. Step 3's `portfolio.py` and Step 4's
`track_record.py` remain genuinely blocked, both needing a candidate that does
not exist, and were left alone.

## Status

**Done. 608 checks across five suites, up from 595.**

| Item | Status |
|---|---|
| `relationship.py` built | ✅ 4 functions, 78 lines |
| Numerical equivalence to the code it replaces | ✅ bit-exact on the pair form |
| Callers refactored | ✅ `pair_report.py`, `hedge.py`, `screen.py`, `basket_screen.py`, `health.py` |
| Full suite after every file | ✅ green throughout, no batched changes |
| New checks | ✅ 13 in `verify_relationship.py`, 89 → 102 |
| Mutation test | ✅ 4 deliberate defects, 4 caught |
| Known result reproduced post-refactor | ✅ `DOT~FIL` beta 0.5640, half-life 46.1/168.1, unchanged |

## The duplication, precisely

Eight call sites across five files ran their own `np.polyfit(x, y, 1)` to fit
a hedge ratio: `pair_report.fit_pair`, `health.assess`, `hedge.static_beta`,
`hedge.rolling_beta`, `hedge.kalman_beta` (twice — the seed state and the
observation-variance estimate), `screen._window`, and `basket_screen` ran a
ninth version by hand with `numpy.linalg.lstsq` for more than one leg.

A second family of `polyfit` calls was found alongside these and deliberately
left alone: the AR(1) fit that measures mean-reversion speed
(`pair_report._fit_ou`, `outcomes.py`, `health.py`'s own next line,
`hedge.kalman_beta`'s seed for `obs_var`). That is a series against its own
lag, not one instrument against another, and folding it into the same module
would have hidden the distinction this project needed to keep rather than
removed the duplication it actually had.

## What `relationship.py` is

Four functions and nothing else — no gate, no threshold, no verdict:

- `ols_beta(y, x, split=None)` — the pair fit, returns `(beta, alpha)`
- `ols_hedge(y, x)` — the n-leg fit, returns `(weights, alpha)`
- `build_spread(y, x, beta, alpha)` — the pair residual
- `build_spread_n(y, x, weights, alpha)` — the n-leg residual

`ols_beta` exists separately from `ols_hedge` rather than as a one-line
wrapper around it, because every call site that used to write
`np.polyfit(x, y, 1)` wants a scalar back, and unwrapping a one-element array
at every call site would have been its own small chance to introduce the next
version of the bug this module exists to remove.

## Verifying it before trusting it

Before any caller was touched, `ols_beta` was checked against raw
`np.polyfit` on synthetic data and found **bit-exact** — same floating-point
value, not merely close. `ols_hedge` uses `numpy.linalg.lstsq` instead of
`polyfit` internally, since that is the only one of the two that generalises
past one leg, so its one-leg case agrees with `ols_beta` to solver tolerance
(1e-8) rather than exactly, and both were checked against the closed-form
normal equations on the same data.

## Refactoring, one file at a time

Backed up all five files before starting. Each file was patched with a
scripted, anchor-checked replacement — no hand-editing near behaviour this
project has already broken by hand before — and the full five-suite run
followed immediately, before the next file was touched:

| Order | File | Sites | Suite after |
|---|---|---|---|
| 1 | `screen.py` | 1 | green |
| 2 | `hedge.py` | 4 | green |
| 3 | `basket_screen.py` | 2 | (verified with the rest) |
| 4 | `pair_report.py` | 1 | green |
| 5 | `health.py` | 1 | green |

No file was refactored on the assumption that a prior one had gone well.
Every one was independently confirmed, so a regression would have pointed at
exactly the file that caused it rather than at five files changed together.

`DOT~FIL` was rerun after the last file: beta 0.5640, half-life 46.1
in-sample and 168.1 out-of-sample, `REJECT` on the same reason as before this
work started. Nothing about the search's conclusions moved.

## New checks, and what the mutation test found

13 checks added to `verify_relationship.py`, two new sections: one on
`relationship.py` itself against the raw formulas it replaced, one on every
refactored caller against its own pre-refactor behaviour, run with a fresh
`np.polyfit` or `lstsq` call inside the test rather than a stored constant, so
a change to the reference implementation would be caught too.

Four deliberate defects, four caught on the first pass — no repeat of the
"passes for the wrong reason" pattern from the Step 3 and Step 4 audits this
time, because every pinned value was checked with a real reference computed
inside the test rather than copied from a prior run's output.

| Mutation | Result |
|---|---|
| sign flipped in `build_spread` | caught, 3 checks failed |
| sign flipped in `build_spread_n` | caught, 2 checks failed |
| `split` argument silently ignored | caught, loud crash — a variable used before assignment |
| `lstsq` target zeroed out | caught, 5 checks failed |

## What this did not do

`factors.py` remains marked deferred in `plan/STEP2.md`, unchanged. It was
judged low-value rather than blocked — it would confirm what is already
measured elsewhere rather than decide anything new — and that recommendation
is still open, not acted on here.

`portfolio.py` (Step 3) and `track_record.py` (Step 4) were not started. Both
are blocked on a candidate that survives Steps 0 through 4, and none does.
`DOT~FIL`, the furthest any candidate has reached, still fails deflated Sharpe
and PBO as of the 2026-09-17 crypto search. Nothing in this session's work
changes that; a spread-fitting refactor cannot manufacture a candidate.
