---
name: scorecard
description: >
  Grade a candidate on every gate instead of discarding it at the first
  failure, and say whether the failure is one a portfolio could fix. Covers the
  per-gate signed margin, the six tiers that separate fixable failures from
  final ones, the measurement of whether adding a candidate improves an
  existing book, and the trial registry that charges a second look before it is
  taken. Use whenever the user asks why a candidate was rejected, which gate it
  failed and by how much, whether a near-miss is worth another look, whether
  something weak alone might work in a portfolio, how close a pair came to
  passing, or for a breakdown rather than a verdict — including phrases like
  "why did it fail", "how close was it", "which gate", "near miss", "second
  chance", "would it help the book", "is it fixable", "score the candidates",
  "grade them", or before abandoning a market on a survivor count. Never report
  a pass/fail count as the whole result while this skill applies; `scorecard.py`
  records which gate bound each candidate and `contribution.py` measures whether
  a book would want it.
---

# Scorecard — which gate bound it, and can a book fix that

| File | Role |
|---|---|
| `scorecard.py` | `assess()` every gate, signed margins, `tier()` by written rule |
| `contribution.py` | does adding this candidate improve the book it would join |
| `triallog.register()` | charge a second look before taking it |
| `verify_scorecard.py` | 53 checks across seven groups |

## Working directory

```bash
cd development/statarb/code
```

Both modules are libraries rather than commands. `screen.py` calls them; `pipeline.py`
stage 06 reports the tier distribution.

## Why it exists

`screen.survives()` returned a bare boolean and stopped at the first failing gate. A pair
that missed one threshold by a hair was indistinguishable from one that failed every gate
badly, and from one that could not be tested at all. All three read as `survived = no`.

> The measurements were never the problem. `screen.evaluate()` already computed every field
> unconditionally. The information was discarded at **verdict** time, not at measurement
> time.

Re-grading the 2,278 crypto pairs of screen #25 — nothing re-run, the same numbers — found
**five candidates that failed only on magnitude** and had been thrown away with the 2,245
whose relationship was simply not there.

## The six tiers

A tier answers one question: **can portfolio management fix this failure?**

| Tier | Meaning | Fixable by a book? |
|---|---|---|
| `STANDALONE` | cleared every gate it could be asked | n/a |
| `PORTFOLIO_CANDIDATE` | failed only on magnitude | **yes** — exposures cancel across pairs |
| `WATCH_POWER` | right sign, error bars too wide | **maybe** — more data, not more management |
| `REJECT_STATISTICAL` | no relationship on the window that selected it | no |
| `REJECT_STRUCTURAL` | the relationship is not reliably present | no |
| `REJECT_ECONOMIC` | gross positive, costs exceed it | **no** — a book cannot dilute a per-trade cost |

A hedge leaving a pair 40% net long is **magnitude**: two such pairs with opposite exposure
cancel inside a book. A late reserved window saying the relationship is gone is
**structural**, and nothing brings a dead relationship back.

**`out_of_sample` is structural, not magnitude**, and that placement was forced rather than
chosen. `tier()` raises on a gate it has no rule for instead of defaulting, and on first
contact with real data it fired on exactly that gate. A relationship absent from its own
held-out tail is intermittent, and a book still holds it during the stretches it is not
there.

## There is no blended number, deliberately

`STEP4.md` refuses to aggregate gates into one score, on the evidence of a study where the
composite had no forward relationship. A vector of margins tells you *which* threshold bound
a result; a weighted sum of the same margins tells you nothing and looks authoritative doing
it.

`verify_scorecard.test_no_blended_number` asserts it: no banned function name in either
module, `tier()` returns a label rather than a number, and every gate names a unit —
normalising margins into a common scale is the first step towards adding them up.

## Reading a scorecard

```
AVA-USDT~COMP-USDT
  gate             value   limit   margin  unit
  cointegration   0.0002   0.050  +0.0498  p     PASS
  out_of_sample   0.0310   0.050  +0.0190  p     PASS
  late_window     0.0130   0.050  +0.0370  p     PASS
  beta_stability    1.42    3.00    +1.58  x     PASS
  hedge_usable      0.36    0.35    -0.01  net   FAIL
  reverting         18.3     inf     0.00  bars  PASS
  half_life         18.3   60.00   +16.30  bars  PASS

  TIER: PORTFOLIO_CANDIDATE — failed hedge_usable at 0.36 against 0.35 net
```

**The margin is signed and in the gate's own unit.** Positive is clearance. `-0.01` above
says this pair missed the exposure cap by one percentage point with a p-value of 0.0002 —
a fact the old boolean destroyed.

**`passed = None` is not `False`.** A gate that could not be asked — the tail too short, the
reserved window too short — reports `None`, and a card containing one does not `all_pass()`.
Absence of evidence must not read as consent.

## Measuring whether a book would want it

```python
import contribution as cb
c = cb.measure("AVA-USDT~COMP-USDT", candidate_returns, book_returns)
c.sharpe_change      # SR(B and c) - SR(B)
c.breadth_change     # effective_bets after - before
c.max_correlation    # closeness to the nearest book member
cb.improves_book(c)  # policy: must raise the Sharpe, not merely add breadth
```

**What you pass decides what the Sharpe means.** `risk.spread_returns` is a spread held
*continuously* — correct for breadth and correlation, **wrong for the Sharpe**, because the
strategy is flat most of the time. For a Sharpe that answers the question it appears to,
pass a differenced `equity_net` from a broker-backed `risk.load_book`.

**Adding breadth while lowering the Sharpe is not an improvement.** It is diversifying into
something worse, and `improves_book` refuses it.

## A second look is a second trial

Asking "does it improve a book" of a candidate already rejected is a second selection
channel, and it inflates the multiple-testing correction exactly as the first one does.

```python
triallog.register(paths.LOGS / "trial_registry.csv",
                  "crypto-contribution", 5, "five PORTFOLIO_CANDIDATE pairs")
```

Registered **before** the assessments run, so work abandoned half way through still counts.
Reconstructing the count afterwards counts only the tests somebody remembered.

## Verifying

```bash
python verify_scorecard.py          # 53 checks, seven groups
python verify_scorecard.py -v
```

Groups: no short-circuit, not-evaluable handling, margins, tiers, contribution, the
no-blending guard, and the trial registry.

The two that carry the weight are **the abuse checks**: neither a cost verdict nor a
contribution measurement may promote a structural failure, asserted directly. Mutation-tested
with three deliberate defects — a lenient tier that promotes structural failures, an
`all_pass` that counts `None` as a pass, and an `improves_book` that always says yes — all
three caught.

The refactor is behaviour-preserving: re-running the crypto screen after `survives()` began
delegating to `assess()` reproduces the funnel exactly — 400 / 51 / 11 / 9 / 6 / 6, same six
pairs, same order.

## Rules

- Never report a survivor count as the whole result. Report the tier distribution.
- Never treat `PORTFOLIO_CANDIDATE` as a recommendation. It means *the failure is of a kind a
  book could fix*, not that the candidate is good.
- Never let a contribution measurement promote a structural or economic failure.
- Never pass continuously-held spread returns and call the result a strategy Sharpe.
- Never take a second look without registering it as a trial.
- Never add a gate without classifying it structural, foundational or magnitude — `tier()`
  raises rather than guessing, and that is the guard working.

Related: **statarb** runs the screen that produces the rows; **portfolio** sizes what
survives; **validation** charges the trial count. Plan and results:
`development/statarb/plan/SCORECARD.md`.

Five candidates were reconsidered on 2026-09-18 and none earned promotion: they diversify
genuinely — correlations 0.09 to 0.44, roughly +0.9 bets each — but the book they would join
runs at a Sharpe of −0.427, and spreading across more uncorrelated things that do not earn
does not produce earning.
