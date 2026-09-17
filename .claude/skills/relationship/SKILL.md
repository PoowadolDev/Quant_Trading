---
name: relationship
description: >
  Test whether two instruments are genuinely cointegrated, whether the fitted
  hedge ratio is a hedge at all, and whether the relationship is still alive
  today. Covers the Engle-Granger, ADF and Johansen tests, static against
  rolling against Kalman hedge ratios, and a three-state health monitor that
  replays history to show when a relationship died. Use whenever the user asks
  whether a pair is cointegrated, for a p-value or significance on a spread,
  whether a relationship still holds or has broken down, how stable a hedge
  ratio is, whether a spread is really market-neutral, to compare hedge
  estimators, or to prove a pair study result — including phrases like "is this
  cointegrated", "what is the p-value", "run ADF", "Engle-Granger", "Johansen",
  "is the relationship still working", "has it broken", "check the hedge
  ratio", "Kalman", "is this actually hedged", or before trusting any backtest
  of a pair. Never write an ad-hoc cointegration test, hedge-ratio filter or
  regime check while this skill applies; these scripts already handle the
  critical values, the look-ahead traps and the calibration.
---

# Relationship — cointegration, hedge quality, health

Four scripts in `development/statarb/code`:

| Script | Answers | Exit 0 means |
|---|---|---|
| `cointegration.py` | is the gap statistically closing? | cointegrated in and out of sample |
| `hedge.py` | is the hedge a hedge, and which estimator? | usable hedge |
| `health.py` | is the relationship alive now? | healthy |
| `relationship_report.py` | all three, on one page | every gate passed |

This is Step 2 of `plan/PLAN.md`. It depends on nothing from Step 1 — verified by running
its suite with `backtest`, `costs`, `strategy` and `feasibility` blocked at the import
hook. Step 1 may consult it (`backtest.py --health-gate`), never the reverse.

## Why it exists

Everything before Step 2 judged a spread by its Ornstein-Uhlenbeck half-life. **A half-life
is an estimate, not a test** — no null hypothesis, no p-value, so a fitted number can be
compared against a bound somebody chose but never actually *rejected*.

Measured on stored data the two disagree on **7 of 13 pairs**. `GBPUSD~USDNOK` passed the
half-life gate, was reported as the best forex candidate, then failed six of seven
robustness re-tests — and Engle-Granger rejects it at p = 0.391 on the first run. In the
other direction `SOL~LINK` and `DOGE~AVAX` are cointegrated at p = 0.000 and the half-life
bound throws both away.

## Working directory

```bash
cd development/statarb/code
python relationship_report.py -s USDNOK,USDZAR
```

Reports land in `studies/relationships/`, logs in `logs/cointegration.csv` and
`logs/hedge.csv`. `paths.py` resolves everything, so the scripts run from anywhere.

## The three gates

### 1. Cointegration

```bash
python cointegration.py -s USDNOK,USDZAR --both-directions
python cointegration.py -s SOL-USDT,LINK-USDT -a crypto --lags bic
python cointegration.py -s EURUSD,GBPUSD --test engle-granger --no-require-oos
```

Three tests, answering different questions:

- **ADF** on the spread — is this series stationary, treating the hedge ratio as given?
- **Engle-Granger** — are they cointegrated, *paying for the fact that the ratio was
  estimated*? Its critical values are stricter than ADF's for exactly that reason, and
  using the ADF table on a fitted residual is a standard way to manufacture significance.
- **Johansen** — how many cointegrating relationships exist. Generalises past two legs.

| Flag | Default | Meaning |
|---|---|---|
| `--test` | `all` | `adf`, `engle-granger`, `johansen` or all |
| `--lags` | `aic` | `aic`, `bic`, `t-stat` or a fixed integer |
| `--adf-trend`, `--eg-trend` | `c` | `n` none, `c` constant, `ct` constant and trend |
| `--det-order`, `--johansen-lags` | `0`, `1` | Johansen deterministic term and lags |
| `--split` | `0.70` | the tail is tested separately as well |
| `--level` | `0.05` | significance level |
| `--require-oos` | on | the held-out tail must also reject before the run counts |
| `--both-directions` | off | also regress B on A; disagreement weakens the evidence |
| `--log`, `--no-log`, `--json`, `-q`, `-v` | | output |

**`--require-oos` is on by default**, and it changes answers. `USDNOK~USDZAR` is
cointegrated at p = 0.007 on the full sample and p = 0.410 on the held-out tail. With the
default it exits 3. `--no-require-oos` reports the tail without letting it decide — the
tail is shorter and the test has less power there, so that is a legitimate choice, but it
should be a decision rather than an accident.

**The test is correctly sized.** On 2000 independent random-walk pairs every lag rule
rejects between 4.5% and 4.9% at the nominal 5% level. Earlier runs of 200 to 800 pairs
gave 4.0%, 7.1% and 8.5% — all noise around the same value. A rejection rate needs
thousands of trials before it can be called over-sized; do not repeat a size claim from a
few hundred.

### 2. Hedge quality

```bash
python hedge.py -s USDNOK,USDZAR
python hedge.py -s EURCHF,EURJPY --method all --window 120
```

A spread is `A - beta*B`, so the position is long one unit of A and short `beta` of B.
**When `beta` is negative that second leg flips: both legs sit on the same side of the
market.** That is a leveraged directional bet wearing a spread's clothes — the opposite of
what a market-neutral book is for — and no estimator repairs it. A Kalman filter would
track the sign change, not fix it.

Measured on stored forex data the separation is clean:

```
pair              full beta   share of time at or below zero
EURUSD~GBPUSD        +0.895                              0%
AUDUSD~NZDUSD        +0.675                              0%
GBPJPY~EURJPY        +1.055                              0%
USDNOK~USDZAR        +0.824                              3%
USDMXN~USDZAR        -0.201                             33%
AUDNZD~AUDUSD        -0.047                             39%
EURCHF~EURJPY        -0.431                             44%
```

| Flag | Default | Meaning |
|---|---|---|
| `--method` | `all` | `static`, `rolling`, `kalman` |
| `--window` | `250` | rolling window in bars |
| `--kalman-delta` | `1e-4` | how far the ratio may move per bar; smaller is stiffer |
| `--kalman-obs-var` | measured | observation variance, from in-sample data only |
| `--min-abs-beta` | `0.10` | below this the second leg barely participates |
| `--max-negative-share` | `0.10` | share of the sample the ratio may spend at or below zero |
| `--split`, `--log`, `--no-log`, `--json` | | as elsewhere |

**The estimator is chosen out of sample**, ranked by how close the half-life in sample is
to the half-life out of sample. A filter fitting better in sample is what filters do by
construction, so in-sample fit cannot be the criterion.

The Kalman filter is written out in the script rather than taken from statsmodels, whose
state-space extension is blocked by an Application Control policy on this machine. It is
seeded from in-sample data only — measuring its observation variance over the whole series
let a bar in 2026 change the ratio reported for 2020, which the suite now checks for.

### 3. Health

```bash
python health.py -s USDNOK,USDZAR --replay
python health.py -s AUDUSD,NZDUSD --replay --lookback 500 --recheck-every 20
```

Three states, and the middle one matters:

- **healthy** — trade normally
- **degraded** — no new entries; positions already open may run
- **broken** — force the exit now, at a loss, without waiting for reversion

| Flag | Default | Meaning |
|---|---|---|
| `--lookback` | `500` | bars the monitor may look back on, minimum 120 |
| `--recheck-every` | `10` | bars between cycles |
| `--max-pvalue` | `0.05` | above this, degraded |
| `--degraded-pvalue` | `0.20` | above this, broken |
| `--min-half-life`, `--max-half-life` | `2`, `60` | usable reversion speed |
| `--break-z` | `4.0` | spread distance at which the relationship is presumed broken |
| `--max-beta-drift` | `3.0` | ratio movement in standard deviations of its own past |
| `--replay` | off | walk the whole history instead of judging the last bar |
| `--show` | `25` | rows printed when replaying |

**Set the thresholds with `--replay`, not by taste.** Choose them so the monitor flags the
failures already known: `AUDUSD~NZDUSD` reads broken in every window it has, and
`GBPUSD~USDNOK` turns broken in 2022 — years before a full-sample fit noticed.

Drift is judged against the ratio's own past variation, with the scale floored at a tenth
of the ratio. Without that floor a perfectly steady ratio has zero dispersion and the first
movement reads as infinitely abnormal.

## The report

```bash
python relationship_report.py -s USDNOK,USDZAR --open
```

One self-contained HTML file in `studies/relationships/`: a verdict banner, six tiles, the
test tables for full sample and held-out tail, the estimator comparison, the health
summary, and five charts — rebased legs, spread with its equilibrium band, the three hedge
ratio paths, the cointegration p-value through time against its thresholds, and a
health-state timeline with one coloured block per monitoring cycle.

It takes every flag the three scripts take, plus `--min-healthy-share` (default `0.40`).
**That last one is a judgement, not a measurement** — no stored forex pair reaches it, so
read a failure there as information about the universe rather than about the pair.

## Reading the output

```
USDNOK ~ USDZAR   1d   2,004 bars
  cointegration FAIL   hedge PASS   health PASS
```

Measured across the current store:

```
                     cointegration   hedge   health
USDNOK~USDZAR             FAIL        PASS    PASS
EURUSD~GBPUSD             PASS        PASS    FAIL
AUDUSD~NZDUSD             FAIL        PASS    FAIL
BTC-USDT~ETH-USDT         FAIL        PASS    FAIL
```

No pair passes all three, and the gates disagree with the earlier stages in both
directions. `EURUSD~GBPUSD` fails the Step 0 half-life bound but is cointegrated and
backtests profitably. `BTC-USDT~ETH-USDT` passes the pair study, the cost gate and the
backtest, and Step 2 still says no.

Exit codes throughout: `0` passed, `3` rejected, `2` usage error, `1` runtime error.

## Driving the backtest

```bash
python backtest.py -s USDNOK,USDZAR --broker fxretail --health-gate
```

The monitor can then force the engine flat while broken and refuse new entries while
degraded. It only ever *reduces* exposure. Verdicts are computed walk-forward, so a bar is
never scored with information it could not have had.

On stored data the gate improved 6 of 12 pairs with a median change of −11 bps — **not
evidence that it helps**. It also cut trade counts by half to nine tenths, so most of those
comparisons rest on a handful of trades. Its diagnostic value is proven; its value as a
trading filter is not.

## Verifying

```bash
python verify_relationship.py                 # 48 checks
python verify_relationship.py --trials 2000   # tighter calibration
```

Six groups: ground truth on simulated pairs, test calibration, hedge estimators and the
quality gate, monitor sensitivity and specificity, real-data anchors, and input validation.
The calibration check scales its own tolerance to the trial count — three standard errors
either side of 5% — so it cannot repeat the over-sizing mistake described above.

## Rules

- Never report a half-life as evidence of cointegration. It is an estimate; run the test.
- Never quote a p-value from the ADF table on a spread whose hedge ratio was fitted. Use
  Engle-Granger.
- Never call a pair market-neutral without checking the sign of the ratio.
- Never choose a hedge estimator on in-sample fit.
- Never call the test over-sized from a few hundred trials.
- Never set health thresholds without `--replay` against a known failure.
- Never trade a relationship the monitor calls broken in order to "wait for reversion".
  That is the failure the monitor exists to prevent.
- A pair passing all three gates is a candidate for a backtest, not a strategy. Step 4 is
  the only step that can say yes.

Related: `statarb` finds candidates, `tradingcosts` prices them, `backtest` measures them,
`sizing` decides whether and how much to trade them, `validation` decides whether any of it
survives the search that found it, `marketdata` supplies the bars.

A p-value from this skill is one test among many whenever it came out of a screen. Sixteen
pairs survived a 10% false discovery rate out of 1,171; fourteen were gone by the most
recent window. Plan and evidence: `development/statarb/plan/STEP2.md`.
