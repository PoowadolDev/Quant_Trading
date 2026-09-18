# Scorecards, tiers, and portfolio contribution

**Status: built and measured, 2026-09-18. Three items outstanding, listed in §8.**

A candidate that fails one gate was previously indistinguishable from one that failed every
gate, and from one that could not be tested at all. All three read as `survived = no` and were
discarded together. This document is the plan that changed that, and the results of applying it.

---

## 1. Where this came from

Feedback, translated from the original Thai:

> "I'd like the process adjusted. It feels like if something doesn't pass a stage it Fails and
> gets thrown away entirely, without trying the other steps. I'd like it changed so everything
> runs through all stages, and add a Scoring system — because it isn't true that every profit
> is unusable. There are still other ways to manage it, or blend it into other profiles, and
> with good portfolio management it might work."

Three asks: run every stage regardless of failure, score rather than pass/fail, and recognise
that a candidate weak alone may work inside a book.

**Checked against the code, the first was half-true and the third was entirely unaddressed.**

- `screen.evaluate()` already computed every measurement unconditionally. Nothing was lost at
  measurement time. But `survives(r, args) -> bool` short-circuited at the first failing gate,
  so *which* gate failed and *by how much* was discarded at verdict time.
- `logs/pair_research.csv` recorded `survived = yes/no` with no reason column.
- **Nothing anywhere measured whether adding a candidate improves an existing book.**
  `risk.effective_bets` made the difference one subtraction away, and that subtraction was not
  in the codebase.

---

## 2. The tension this had to resolve

The request collides with the project's own standing rules. `STEP4.md` refuses to aggregate
gates into one score, on the evidence of a study where the composite had no forward
relationship, and `verify_validation.test_no_aggregation` asserts it.

Inspecting that assertion showed it is weaker than advertised — it checks *function names*
against a banned list in four files only, does not inspect return values, and `hedge.py`
already contains a nested function literally named `score` that passes because it is not
scanned. It could have been sidestepped trivially.

**It was strengthened instead.** `verify_scorecard.test_no_blended_number` extends the scan to
the new modules and additionally asserts that `tier()` returns a label rather than a number,
and that every gate names a unit — because normalising margins into a common scale is the
first step towards adding them together.

**The resolution: a scorecard, not a score.** Every gate keeps its own line carrying a signed
margin in its own unit. A tier is assigned by explicit branches, never by arithmetic across
gates.

---

## 3. The idea that makes it defensible

Not every failure is the same kind of failure. The honest version of "not every profit is
unusable" is to separate failures portfolio management *can* fix from those it cannot.

| Tier | Meaning | Can a book fix it? |
|---|---|---|
| `STANDALONE` | clears every gate it could be asked | n/a |
| `PORTFOLIO_CANDIDATE` | fails only on magnitude | **yes** — exposures cancel across pairs, holding period is set by the exit rule |
| `WATCH_POWER` | right sign, error bars too wide | **maybe** — more data, not more management |
| `REJECT_STATISTICAL` | no relationship on the window that selected it | no |
| `REJECT_STRUCTURAL` | the relationship is not reliably present | no |
| `REJECT_ECONOMIC` | gross positive, costs exceed it | **no** — a book does not dilute a per-trade cost |

A pair whose hedge leaves it 40% net long is a *magnitude* failure: two such pairs with
opposite exposure cancel inside a book. A pair whose late reserved window says the
relationship is gone is *structural*, and nothing brings a dead relationship back.

### One classification was forced rather than chosen

`tier()` raises `AssertionError` on a gate it has no rule for, rather than defaulting. On first
contact with real data it fired immediately:

```
AssertionError: ACM-USDT~IOST-USDT failed ['out_of_sample'], which no tier rule covers.
```

`out_of_sample` is now **structural**, not magnitude. A relationship absent from its own
held-out tail is intermittent, and intermittency is not a size problem — a book holding it
alongside others still holds it during the stretches it is not there. Which gate failed is
still reported separately, so "dead now", "intermittent" and "never reverted" stay
distinguishable despite sharing a verdict.

---

## 4. What was built

| File | Role | State |
|---|---|---|
| `code/scorecard.py` | `Gate`, `Scorecard`, `assess()`, `tier()`, `describe()` | ✅ |
| `code/contribution.py` | `measure()` — the missing book-contribution measurement | ✅ |
| `code/triallog.py` | `register()` — prospective trial counting | ✅ |
| `code/verify_scorecard.py` | 53 checks, seven groups | ✅ |
| `code/screen.py` | `survives()` delegates to `assess()`; `grade()` added | ✅ |

**`passed = None` is a distinct state from `False`.** The precedent is `pair_report.judge()`,
which refuses to score the edge gate on a non-stationary spread because doing so *"produces a
large, convincing and entirely spurious number"*. Running every stage must not mean computing
numbers that cannot mean anything, so a gate that cannot be asked says so — and a card
containing one does not `all_pass()`. Absence of evidence must not read as consent.

**Behaviour was preserved.** Re-running the crypto screen after the refactor reproduces the
funnel exactly — 400 cointegrated, 51 out of sample, 11 still there now, 9 stable, 6 hedged,
6 reverting — with the same six pairs in the same order.

Reused rather than rebuilt: `feasibility.headroom()` and `break_even_swap()` were already
distance-from-threshold primitives; `risk.effective_bets` and `risk.correlation_matrix` supply
breadth; `backtest.sharpe_ratio` supplies the Sharpe.

---

## 5. What the re-grading found

The same 2,278 crypto pairs from screen #25, re-graded with nothing re-run:

| tier | count |
|---|---|
| `STANDALONE` | 6 |
| **`PORTFOLIO_CANDIDATE`** | **5** |
| `REJECT_STATISTICAL` | 22 |
| `REJECT_STRUCTURAL` | 2,245 |

The five were being discarded by the binary verdict and are not statistically marginal:

| pair | p | p_late | failed on |
|---|---|---|---|
| `AVA-USDT~COMP-USDT` | 0.0002 | 0.013 | net 36% against a 35% cap |
| `AVA-USDT~HIVE-USDT` | 0.0014 | 0.002 | beta stability |
| `AVA-USDT~CRV-USDT` | 0.0016 | 0.047 | net 54% |
| `BAND-USDT~EGLD-USDT` | 0.0020 | 0.003 | beta stability |
| `CTSI-USDT~FET-USDT` | 0.0424 | 0.018 | net 43%, half-life 62.7 |

All five are **alive in the late reserved window**. `AVA~COMP` misses the exposure cap by one
percentage point with a p-value of 0.0002.

---

## 6. And what happened when they were tested

Five trials registered *before* the assessments ran, via `triallog.register`.

```
candidate            SR before  SR after     dSR         bets   max corr  helps?
AVA~COMP                -0.427    -0.445  -0.018  4.86->5.78      0.09   no
AVA~HIVE                -0.427    -0.420  +0.007  4.86->5.73      0.15   no
AVA~CRV                 -0.427    -0.411  +0.016  4.86->5.70      0.17   no
BAND~EGLD               -0.427    -0.412  +0.015  4.86->5.35      0.44   no
CTSI~FET                -0.427    -0.508  -0.080  4.86->5.64      0.23   no
```

**The hypothesis was reasonable, testable, and tested negative — but not for the obvious
reason.** The diversification works exactly as hoped: correlations of 0.09 to 0.44, and each
candidate adds roughly 0.9 of an independent bet. The problem is what they diversify *into*.
The book of six `STANDALONE` survivors runs at a Sharpe of **−0.427**. Spreading across more
uncorrelated things that do not earn does not produce earning.

### The caveat that belongs beside those numbers

That Sharpe is of the spreads held **continuously**, not traded. `risk.spread_returns` is a
buy-and-hold series and the strategy is flat most of the time.

- Breadth and correlation are **correct** on that input — they ask how the spreads co-move,
  which does not depend on anyone being in them.
- The Sharpe is **not the strategy's Sharpe**.

This is documented in `contribution.measure`'s docstring with the fix named: pass a
differenced `equity_net` from a broker-backed `risk.load_book`. Reporting a
continuously-held Sharpe as a strategy Sharpe would be the same class of error as the
expected-move formula that over-predicted realised gross by 10x to 68x — correct about what
it computes, wrong about what it implies.

---

## 7. The cost of a second chance

Asking "does it improve a book" of a candidate already rejected on its own **is a second
selection channel**, and it inflates the multiple-testing correction exactly as the first one
does. Left uncharged it would understate every later deflated Sharpe, which is the error §19
of the standing brief names: *"Do not reconstruct trial count only after finding a winner."*

`triallog.register(path, campaign, trials, description)` records the count before the
assessments run, so work abandoned half way through still counts. Cumulative registered trials
are now tracked in `logs/trial_registry.csv`, separate from the reconstructed 6,440 in
`logs/screens.csv`.

---

## 8. Outstanding

1. **`--confirm-top N`** — replay the top N by scorecard through `confirm_with_trades`
   regardless of pass/fail. Currently the cost replay runs only on pairs that already passed,
   which is the last remaining place where a near-miss is genuinely not tried. The argument
   for it is already in the code: *"a run that aborts on pair three tells you nothing about
   the other hundred."*
2. **`pipeline.py` `NOT_EVALUABLE`** — a sixth stage state, distinct from `NOT_RUN` and
   `FAIL`, for stages whose inputs make the number meaningless.
3. **`equity_net` input to `contribution.measure`** — so the Sharpe answers the question it
   appears to answer. Requires cost profiles for seven more crypto symbols, each carrying the
   same estimated-spread caveat recorded in `worklog/2026-09-17-crypto-wide-screen.md`.

Also unreconciled: `REPROCESSING.md` §8 proposes a rejection taxonomy
(`REJECTED_STATISTICAL`, `REJECTED_ECONOMIC`, `REJECTED_OOS`, `REJECTED_COST`,
`REJECTED_STABILITY`). These tiers are the same taxonomy arrived at independently and should
be merged into one vocabulary rather than left as two.

---

## 9. What this does not claim

Grading is not rescuing. `PORTFOLIO_CANDIDATE` is the tier most exposed to abuse — it exists
to reconsider candidates whose only failing is magnitude, and `verify_scorecard.test_tiers`
asserts explicitly that neither a cost verdict nor a contribution measurement can promote a
structural failure.

Five candidates were reconsidered here and none earned promotion. That is the system working:
the second look was cheap, honestly charged, and it said no.
