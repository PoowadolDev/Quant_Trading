# Step 4 — Validation, split into runnable pieces

Step 4 in `PLAN.md` is the step that says no. Every step before it searches; this one asks
whether anything found was real, and it is expected to reject rather than confirm.

> **Order set 2026-09-15, before writing any of it.** Step 3's order came from measuring
> what each component would have caught. That method cannot be used here, because Step 4 has
> caught nothing yet — there is no candidate to run it on. So the order comes from a
> different question: *which of these can be answered today, on evidence that already
> exists?* One of them can, and it goes first.

| Order | Script | Why here | State |
|---|---|---|---|
| 1 | `multiple_testing.py` | the only Step 4 question answerable **now**, on the screen's own output | ✅ built |
| 2 | `deflated_sharpe.py` | a Sharpe ratio adjusted for how many things were tried to find it | ⬜ |
| 3 | `overfit.py` | probability of backtest overfitting, by combinatorially symmetric cross-validation | ⬜ |
| 4 | `purged_cv.py` | k-fold that does not leak when labels overlap in time | ⬜ |
| 5 | `verify_validation.py` | none of the above is trustworthy unverified | ✅ 49 checks green |
| 6 | `track_record.py` | how long paper trading must run before it means anything | ⬜ deferred |

**Step 4 does not need a candidate to be built or verified**, for the same reason Step 3
did not: every component can be checked against a series whose answer is known in advance —
a simulated process with a chosen Sharpe, a deliberately overfit strategy, a deliberately
planted leak. Step 3 was built that way and it found five defects, two of them in the test
fixtures rather than the code.

**It does need a candidate to produce a verdict.** There is none, and script 1 is the
exception that does not need one.

---

## Why this order, and not the order in `PLAN.md`

`PLAN.md` lists Deflated Sharpe first because that is the order the literature is usually
taught in. That is the wrong order here.

The most important number in this project today is on the screen's own output:

```
equities, within sector   1,192 pairs   144 cointegrated   noise alone would give about 59
```

144 against 59 looks like a large excess, and the project has been reading it as one. **It
is almost certainly not.** The comparison assumes 1,192 independent tests. They are not
independent: they are built from 252 instruments, so `NUE~STLD`, `NUE~CLF` and `STLD~CLF`
share legs and share errors, and the same instruments are tested in overlapping windows.
The true number of independent tests is smaller than 1,192 — possibly much smaller — and
the expected count under the null is correspondingly different.

Answering that changes what to do next. If the excess vanishes under a correct treatment,
these venues contain nothing at daily resolution and the remaining question is whether
intraday differs. If a genuine excess survives, it says where to point the search.

So `multiple_testing.py` is first because it is the only piece whose output changes a
decision this week.

---

## 1. `multiple_testing.py` — how many tests were really run

**The question.** Given N pair tests over M instruments, how many independent tests is that,
and how many rejections would chance alone produce?

```bash
python multiple_testing.py --screen logs/screens.csv --run 3
python multiple_testing.py --universe equities --within-sector --method bootstrap
```

Three estimates, reported separately:

- **Naive.** `N × level`, which is what `screen.py` prints today. Kept so the difference is
  visible rather than asserted.
- **Effective tests from the correlation structure.** The participation ratio of the
  correlation matrix of the tested spreads — the same statistic `risk.py` already uses to
  count independent bets in a book, applied to count independent tests in a screen. One
  definition, two uses.
- **Bootstrap under the null.** Shuffle or block-bootstrap the instruments to break any real
  relationship while keeping each instrument's own serial correlation, re-run the whole
  screen, and count rejections. Repeat. This is the honest answer and the expensive one;
  the other two are there to be checked against it.

Also reports **Benjamini–Hochberg** on the screen's p-values: at a false discovery rate of
10%, which pairs survive? That is a different and more useful question than "which have
p < 0.05", because it controls the share of the *reported* set that is wrong.

**Verified against**: a universe of pure random walks, where the true number of discoveries
is zero and the bootstrap must recover the nominal rate; and a universe with a known number
of planted cointegrated pairs, where BH must find most of them and few others.

**Done when**: the screen's "noise alone would give about X" line is replaced by a number
that accounts for dependence, and the difference between the two is reported.

## What script 1 found, 2026-09-15

See [worklog/2026-09-15-multiple-testing.md](../worklog/2026-09-15-multiple-testing.md).

**The screen's noise floor was a third too low.** On 1,171 equity pairs the bootstrap puts
the null rejection count at **78.8**, not the 58.6 that `N x level` gives. The cause is not
the test — Engle-Granger at the screen's fixed lag rejects at 5.33% on clean random walks —
it is the data: real equity returns carry serial correlation and volatility clustering that
a random walk does not, and on series that look real but are unrelated by construction the
test rejects about 6.7% of the time.

Against the correct floor: 144 observed, 78.8 expected, **bootstrap p = 0.038**. A real
excess, and far smaller than 144-against-59 implied.

**Sixteen pairs survive Benjamini-Hochberg at a 10% false discovery rate** — regional banks,
the US waste duopoly, three health insurers, two payment processors. Fourteen are gone by
the late reserved window. The two that remain, `RSG~WM` and `KEY~ZION`, both fail every
Step 3 question with a **negative** realised mean.

**The script also caught an error in its own first draft**, which had reported
`effective tests x level` as an expected count. Expectation is linear: the expected count is
`N x level` whatever the dependence. Dependence inflates the *variance* — measured at 2.3x
the independent binomial. The effective count now feeds a Sidak family-wise threshold, which
is where it belongs.

---

## 2. `deflated_sharpe.py` — a Sharpe that knows how many tries it took

A Sharpe ratio selected as the best of many trials is biased upward, and the bias grows with
the number of trials and with the variance between them. The Deflated Sharpe Ratio corrects
for it and returns the probability that the true Sharpe exceeds zero
(`research/paper/validation/` — Bailey and López de Prado).

```bash
python deflated_sharpe.py --backtest logs/backtests.csv --pair "NUE ~ STLD"
python deflated_sharpe.py --returns <file> --trials 151 --skew -0.4 --kurtosis 5.2
```

**The trial count is the whole point, and this project has been logging it since day one for
exactly this.** 151 runs across the live logs and archives, plus every parameter cell inside
a sweep. An honest count includes cells that were run and discarded — `thresholds.py` alone
evaluates five entry thresholds per call.

Non-normality matters here: the correction uses skew and kurtosis of the return series, and
pair-trade returns are neither symmetric nor thin-tailed. Computing them from the trades
rather than assuming normality is the difference between a real correction and a decoration.

**Verified against**: a series with a known Sharpe and a known trial count, where the
deflation is derivable; and the degenerate case of one trial, where DSR must reduce to the
probabilistic Sharpe ratio.

## 3. `overfit.py` — probability of backtest overfitting

CSCV: split the return series into S even blocks, take every way of choosing half of them as
a training set, pick the best configuration in-sample, and record its rank out of sample.
PBO is the share of splits where the in-sample best lands in the bottom half out of sample.

```bash
python overfit.py --grid logs/thresholds.csv --pair "XLP ~ XLB" --blocks 12
```

This is the direct measurement of the thing Step 3 kept running into. The
`XLP~XLB` parameter surface ran from −3,678 to +3,747 bps across twelve cells; PBO turns
that observation into a number.

**Verified against**: a strategy that is pure noise, where PBO must sit near 0.5 or above;
and one with a genuine stationary edge, where it must sit near zero.

## 4. `purged_cv.py` — cross-validation that does not leak

Plain k-fold leaks whenever a label depends on a window of future bars, because the training
fold then contains information about the test fold. A trade held sixteen bars has a label
spanning sixteen bars. Purging removes training observations whose windows overlap the test
fold, and an embargo drops a further margin after it.

```bash
python purged_cv.py --pair NUE,STLD -a equity --broker equity --folds 6 --embargo 20
```

**Verified against**: a deliberately planted leak — a label copied from a future bar — which
plain k-fold must score highly and purged k-fold must not.

## 5. `verify_validation.py` — the suite

Same standard as the four existing suites. Targets around 70 checks, bringing the project
past 500.

The checks that matter:

- **null calibration** — on random walks, the corrected rejection rate must match the
  nominal level, measured with a tolerance that scales to the trial count. This is the check
  `verify_relationship.py` already does for cointegration, and the one that caught a claim of
  mine that turned out to be sampling noise.
- **known Sharpe** — DSR on a series built with a chosen Sharpe and trial count.
- **noise scores badly** — PBO near or above 0.5 on a strategy that is pure noise.
- **a planted leak is caught** — purged k-fold must score it far below plain k-fold.
- **no aggregation** — the suite asserts that no function returns a single combined score.
  `research/paper/validation/2608.23808` found a composite has no forward relationship, and
  the temptation to build one is strong enough to be worth a failing test.
- **dependency direction** — Steps 1 to 3 must not import Step 4.

## 6. `track_record.py` — deferred, with the reason

Minimum track record length says how long a paper account must run before its Sharpe is
distinguishable from zero. It is a Step 5 input and there is nothing to paper trade. It
comes back when something survives scripts 1 to 4.

---

## What Step 4 will not do

| Tempting | Why not |
|---|---|
| Aggregate the gates into one score | A composite had no forward relationship in the study this plan cites. Report them separately and let them disagree |
| Run the gates on a strategy and publish a verdict | There is no candidate. A verdict about nothing is worse than no verdict |
| Tune a gate until something passes | That is the failure mode the entire project is built against, and this is the step that exists to catch it |
| Treat a pass as permission to trade | Step 4 can only fail a strategy. Surviving it means the evidence is not yet against you |

## Order of work

1. `multiple_testing.py`, because its output changes what is done next
2. `verify_validation.py` alongside each script, not after all of them
3. `deflated_sharpe.py`
4. `overfit.py`
5. `purged_cv.py`

Then re-state the screen's headline number with dependence accounted for, and decide on the
strength of that number whether deep intraday is worth the network time.
