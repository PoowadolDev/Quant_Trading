---
name: validation
description: >
  Decide whether a backtest result is real or an artefact of the search that
  found it. Corrects a screen's rejection count for dependence between tests,
  deflates a Sharpe ratio by how many configurations were tried, measures the
  probability that a chosen parameter was chosen by noise, and cross-validates
  without letting overlapping trade outcomes leak across fold boundaries. Use
  whenever the user asks whether a result is real or overfit, how many of their
  findings are false positives, what a Sharpe is worth given how much they
  searched, whether a parameter choice will hold up, whether a backtest is
  cherry-picked, how to correct for multiple testing or data snooping, or
  whether cross-validation is leaking — including phrases like "is this real",
  "is this overfit", "am I fooling myself", "p-hacking", "multiple testing",
  "false discovery rate", "Benjamini-Hochberg", "deflated Sharpe", "PBO",
  "probability of backtest overfitting", "purged k-fold", "embargo", "data
  snooping", "too good to be true", or before trusting any screen output or
  backtest number. Never report a screen's hit count against `N x level`, quote
  a Sharpe without its trial count, or pick the best cell of a parameter sweep
  while this skill applies; these scripts already handle the dependence, the
  selection bias and the leakage.
---

# Validation — is this result real, or is it the search?

Five scripts in `development/statarb/code`:

| Script | Answers | Exit 0 means |
|---|---|---|
| `multiple_testing.py` | how many tests were really run, and how many hits chance gives | the excess survives correction |
| `deflated_sharpe.py` | is this Sharpe worth the search behind it? | it survives deflation |
| `overfit.py` | was the winning parameter chosen, or lucky? | the choice holds up |
| `purged_cv.py` | does the score survive purging and an embargo? | no leakage |
| `validation_report.py` | all four, on one page | every gate passed |
| `verify_validation.py` | none of the above is trustworthy unverified | 123 checks pass |

This is Step 4 of `plan/PLAN.md`, **the step that says no.** Every step before it searches.
This one asks whether anything found was real, and it is expected to reject rather than
confirm. Nothing in this project has passed it.

## Where the output goes

Each script logs one row per run — `logs/multiple_testing.csv`,
`logs/deflated_sharpe.csv`, `logs/overfit.csv`, `logs/purged_cv.csv` — and
`validation_report.py` writes a self-contained HTML page per pair into
`studies/validation/`:

```bash
python validation_report.py -s NUE,STLD -a equity --broker equity
python validation_report.py -s RSG,WM -a equity --broker equity \n    --dump ../logs/dump-equities.csv --open
```

The page carries all four gates as separate sections, the deflation arithmetic with the
trials it charged for, and five charts — including the deflated Sharpe plotted against the
number of trials charged, which shows the shape that matters: the benchmark grows with the
logarithm of N, so the first few dozen trials cost far more than the next few hundred.

Supplying `--dump` adds the population section, and says whether this pair was among the
Benjamini-Hochberg survivors. Being named there is not the same as being tradeable.

## The two rules that matter most

**Never aggregate the gates into one score.** They answer different questions and are
allowed to disagree — a pair can hold up on parameter choice and still fail deflation, which
is exactly what happens below. `research/paper/validation/2608.23808` found a composite score
has no forward relationship. `verify_validation.py` asserts no function returns one.

**A pass is not permission.** These gates can only *fail* a strategy. Surviving them means
the evidence is not yet against you.

## Worked example — two real pairs, two different failures

Both came out of this project's own screening. Running them is the fastest way to see what
each gate is for.

### `NUE~STLD` — Nucor against Steel Dynamics

Two steel makers: same scrap input, same customers, same regulator. The most stable hedge
ratio this project has measured, and the only pair where an entry threshold pays for itself.

```bash
python deflated_sharpe.py -s NUE,STLD -a equity --broker equity
python overfit.py -s NUE,STLD -a equity --broker equity --holding-grid 10,20,40
python purged_cv.py -s NUE,STLD -a equity --horizon 400 --folds 8
```

```
103 trades   Sharpe +0.0848   skew +0.14   kurtosis 4.47
trials counted            77   spread across trials 0.1080
benchmark Sharpe      0.2632   the best of 77 trials under the null

probabilistic Sharpe   80.5%   probability the true Sharpe beats zero
deflated Sharpe         3.5%   probability it beats the benchmark above

probability of backtest overfitting  35.7%   HOLDS UP
purging removed 11.7% of the training rows   NO LEAKAGE
```

**This is what deflation is for.** On its own the Sharpe reads as a reasonable result —
there is an 80.5% chance the true value beats zero. Charged for the seventy-seven
configurations this project tried in order to find it, that falls to 3.5%. The best of
seventy-seven trials reaches 0.263 on noise alone; this reached 0.085.

Note the other two gates pass. The parameter choice is not an artefact of the sweep, and
nothing is leaking. **It fails on selection alone**, and only deflation could have said so.

### `RSG~WM` — Republic Services against Waste Management

The two firms that are the US waste industry. It survived Benjamini-Hochberg at a 10% false
discovery rate out of 1,171 pairs and is still cointegrated in the most recent window.

```
76 trades   Sharpe -0.0231   skew -0.40   kurtosis 6.42
probabilistic Sharpe   42.0%   deflated Sharpe 4.2%

probability of backtest overfitting  76.6%   OVERFIT
median out-of-sample log-odds        -0.79
```

**A different failure.** The Sharpe is negative before any correction, so there is nothing
for the search to have inflated — and the overfitting probability is 77%: across the CSCV
splits, the configuration that wins in sample lands in the bottom half out of sample better
than three times in four. Whatever that sweep selected, it selected noise.

Two pairs, two gates, two different verdicts. That is why they are not combined.

## 1. How many tests were really run

```bash
python screen.py -u equities --within-sector --dump ../logs/dump-equities.csv
python multiple_testing.py --dump ../logs/dump-equities.csv -a equity --bootstrap 25
```

`screen.py` prints `144 cointegrated, noise would give about 59`. That assumes 1,192
independent tests. They are built from 252 instruments, so `NUE~STLD`, `NUE~CLF` and
`STLD~CLF` share legs and share their errors.

Three figures, reported side by side:

- **expected count** — `N × level`. **Dependence does not change this.** Expectation is
  linear: every test still rejects with probability `level` under the null however
  correlated. An early version of this script reported `effective tests × level` as an
  expected count, and the bootstrap caught it.
- **effective tests** — the participation ratio of the spread correlation matrix, feeding a
  Šidák family-wise threshold. That is where a reduced test count belongs.
- **bootstrap** — resample each instrument under the null, keeping its own serial
  correlation and destroying every cross-instrument relation, then re-run the screen. Slow,
  and the only one of the three that measures rather than assumes.

On this project's equity screen the bootstrap put the null count at **78.8**, not 58.6. The
cause is not the test — Engle-Granger at the screen's fixed lag rejects at 5.33% on clean
random walks. It is the data: real equity returns carry serial correlation and volatility
clustering, and on series that look real but are unrelated the test rejects about 6.7% of
the time. **The screen's noise floor was a third too low.**

Two verdicts, separately:

- **population** — is there more here than chance? Decided by the bootstrap p-value, never
  by comparing a count to a mean. Six hits against 4.8 expected reads like an excess and
  happens 39% of the time.
- **individuals** — Benjamini-Hochberg at a false discovery rate. "Which have p < 0.05"
  controls one false positive anywhere; this controls the *share of the reported list* that
  is wrong, which is the question a screen asks.

## 2. Deflating a Sharpe

```bash
python deflated_sharpe.py -s NUE,STLD -a equity --broker equity --count-trials
```

A Sharpe selected as the best of many attempts is biased upward. The benchmark is the
expected maximum of N draws — `(1−γ)Φ⁻¹(1−1/N) + γΦ⁻¹(1−1/(Ne))`, scaled by how much the
trials varied — and the deflated Sharpe is the probability of beating it.

**The trial count is the whole point**, and this project has logged every run since day one
for exactly this. `--count-trials` shows what each log contributed.

Three things the count gets right, each of which was once wrong:

- **Per-pair dumps are not trials.** `screen.py --dump` writes one row per tested pair into
  the log directory. Counting them put the figure at 1,464 when the real one was 77.
- **Screening tests are not strategy configurations.** 1,192 pairs is 1,192 chances to
  reject a null, which `multiple_testing.py` corrects for — not 1,192 Sharpe ratios anyone
  could have picked. `screens.csv` and `cointegration.csv` are excluded.
- **Deflation does not count its own runs.** It measures a configuration; it does not try
  another one. Counting itself made the benchmark climb on every run — 78, then 82, then 83
  — so the same question gave a different answer each time, always harsher.

Skew and kurtosis enter the standard error. Pair-trade returns are neither symmetric nor
thin-tailed — `RSG~WM` has kurtosis 6.42 — and assuming normality is the difference between
a correction and a decoration.

## 3. Was the parameter chosen, or lucky?

```bash
python overfit.py -s NUE,STLD -a equity --broker equity --holding-grid 10,20,40
```

Combinatorially symmetric cross-validation. Cut the returns into S blocks; for every way of
choosing half as training, find the in-sample best and record where it ranks out of sample.
PBO is the share of splits where it lands in the bottom half.

A real edge keeps its ranking. A sweep over noise does not — and notably gives a
**worse-than-random** rank, because the in-sample winner is whichever cell overfitted
hardest. Median log-odds on noise run around −0.7, not zero.

The output also shows which cell won and how often. One cell winning every split is
stability, not evidence: a consistently lucky cell looks exactly the same.

## 4. Cross-validation that does not leak

```bash
python purged_cv.py -s NUE,STLD -a equity --horizon 400 --folds 8
```

A trade held sixteen bars has an outcome spanning sixteen bars, so a training row's window
can reach into the test fold. Purging drops those rows; an embargo drops a margin after.

**Purging is usually a no-op, and the script says so.** At a 20-bar horizon with six folds
over seven thousand bars it removes 0.6% of training rows, and a score on 5,990 rows is
indistinguishable from one on 6,023. Below 5% removed the verdict is `NOT TESTED`, not
`NO LEAKAGE`. Raise `--folds` or `--horizon` until it bites.

An earlier version offered `--plant-leak`, claiming to plant a leak purging would catch. It
could not: the leak was inside each row, and purging removes cross-fold overlap. The flag is
gone and the demonstration lives in the suite, on synthetic data where the overlap is built
deliberately.

## Verifying

```bash
python verify_validation.py          # 123 checks
python verify_validation.py --trials 2000
```

Nine groups. The load-bearing ones: Benjamini-Hochberg against a set worked by hand and at
both boundaries; the null calibration that caught the expected-count error; block resampling
shown to keep serial correlation *and* destroy the cross-series relation; the deflation
benchmark pinned to derived values (2.530603 at 100 trials, 3.255122 at 1,000); CSCV calling
a noise sweep overfit and a planted edge not; and sixteen command-line refusals, each
asserting the message names the flag.

**Mutation-tested at 19 defects, 19 caught.** Two rounds were needed. The first missed a
removed guard because the check asserted an exit code and two different failures share it;
the second missed a dropped term in the deflation benchmark because every monotonicity check
still passed while the value came out 8% low. Both were failures of the tests rather than
the code — the same shape as two found in the Step 3 audit. **A check that passes for a
reason other than the one it claims is the recurring defect in this project.**

## Rules

- Never aggregate the gates into a single score.
- Never report a screen's hit count against `N × level` without the bootstrap. The measured
  floor on real equity data was a third higher.
- Never quote a Sharpe without the trial count that produced it.
- Never take the best cell of a parameter sweep. Run `overfit.py` on the sweep instead.
- Never claim "no leakage" when purging removed under 5% of the training rows. That is
  `NOT TESTED`.
- Never treat Benjamini-Hochberg survivors as candidates. Of sixteen survivors in 1,171
  equity pairs, fourteen were gone by the most recent window and the two that remained both
  lose money.
- Never tune a gate until something passes. That is the failure mode this entire step exists
  to catch.
- **Surviving Step 4 is not permission to trade.** It means the evidence is not yet against
  you.

## What it has concluded

Every candidate this project has produced, through all four gates:

| pair | Sharpe | PSR | DSR | PBO | verdict |
|---|---|---|---|---|---|
| `NUE~STLD` | +0.085 | 80.5% | **3.5%** | 35.7% | fails deflation alone |
| `RSG~WM` | −0.023 | 42.0% | **4.2%** | **76.6%** | fails deflation and overfitting |
| `KEY~ZION` | −0.019 | 42.7% | **26.1%** | **66.7%** | fails both |
| `XLP~XLB` | +0.054 | 68.6% | **0.0%** | 34.9% | fails deflation alone |

Nothing has passed. The two that fail on deflation alone are the instructive ones: their
parameter choices hold up and nothing leaks, so only the trial count could have refused
them.

Related: `statarb` finds candidates, `relationship` tests them, `tradingcosts` prices them,
`backtest` measures them, `sizing` decides whether and how much to trade them, `marketdata`
supplies the bars. Plan and evidence: `development/statarb/plan/STEP4.md`,
`worklog/2026-09-15-multiple-testing.md`, `worklog/2026-09-16-step4-gates.md` and
`worklog/2026-09-16-step4-audit.md`.
