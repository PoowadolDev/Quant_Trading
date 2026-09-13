# Step 2 — Relationship engine and health monitor, split into runnable pieces

Step 2 in `PLAN.md` is the "correlation technical" itself: the machinery that turns two
price series into a tradable spread, plus the monitor that notices when the relationship
stops working. This file splits it into six scripts, each run by hand with parameters on
the command line, in the same style as `pair_report.py`.

**Most of this is not blocked.** Step 1a and 1b are waiting on broker swap and spread
numbers. Sub-steps 2a to 2d need nothing but the data already in the store, so they are the
useful thing to build while that wait continues.

| Sub-step | Script | Needs | State |
|---|---|---|---|
| 2a | `factors.py` — currency-factor decomposition | — | ⬜ |
| 2b | `cointegration.py` — the hypothesis test Step 0 never had | `statsmodels` | ⬜ |
| 2c | `hedge.py` — static, rolling and Kalman hedge ratios compared | — | ⬜ |
| 2d | `relationship.py` — the engine, one import for everything above | 2a–2c | ⬜ |
| 2e | `health.py` — detect a relationship that has died | 2d | ⬜ |
| 2f | `verify_relationship.py` — prove the engine is not lying | 2d, 2e | ⬜ |

The candidate is still `USDNOK ~ USDZAR`, hedge ratio about +0.77, half-life 5 to 7 bars on
daily data, trial 23 in `logs/trials.csv`.

---

## 2a — Currency-factor decomposition

**What it is.** The check that `PLAN.md` Step 0 called for and the pair study never did.
Forex pairs are not independent assets: with K currencies there are at most K−1 independent
factors, because `log P(i,j) = s_i − s_j`. Fit that structure explicitly and two things fall
out — how much of each pair is explained by plain currency strength, and how big the leftover
is compared with the spread you would pay to trade it.

```
r_pair(i,j),t  =  f_i,t  −  f_j,t  +  e_t          least squares per period, gauge fixed by sum(f) = 0
```

**Why it matters for the candidate.** `USDNOK~USDZAR` shares the USD leg, so the trade is
really NOK against ZAR with the dollar mostly netting out. This script says how much of the
spread is genuine NOK-versus-ZAR and how much is residual dollar exposure that will show up
as unexplained risk later.

**Command shape**

```bash
cd development/statarb/code
python factors.py -u fx-all --start 2019-01-01 --window 250 --gauge sum-zero
python factors.py -u fx-all --residuals-for USDNOK,USDZAR --compare-to-spread 8
```

`--compare-to-spread` takes the round-trip cost in basis points and reports what share of
residuals are smaller than it. Residuals inside the spread are not an opportunity, whatever
their statistics look like.

**Parameters**

- *structure* — `--gauge` (sum-zero is standard), `--price log|raw`, `--window` (rolling or
  full-sample fit)
- *searched* — `--start`, `--end`, the instrument set
- *given by reality* — `--compare-to-spread`

**Output.** Variance explained per pair, the factor time series per currency, the residual
distribution, and the share of residuals inside the spread. HTML report and a trial row.

**Done when** the eigenvalue spectrum and the residual-versus-spread comparison are recorded
for the stored FX panel, confirming or refuting rank deficiency with numbers rather than
assertion. The earlier ad-hoc measurement gave eigenvalues `[4.44 1.73 1.31 1.07 0.70 0.39
0.25 0.11 0.01 0.00]` with the top six holding 96.3% of variance; this script makes that
reproducible.

---

## 2b — Cointegration test

**What it is.** The missing hypothesis test. Everything so far has used the OU half-life as
evidence of mean reversion, which is an estimate, not a test: there is no p-value anywhere in
the current pair report, so there is no statement of the form "a relationship this strong
would arise by chance with probability p".

Three tests, because they answer different questions:

- **ADF on the spread** — is this particular spread stationary?
- **Engle–Granger** — are the two series cointegrated, using a residual from a fitted
  regression? The critical values differ from plain ADF precisely because the hedge ratio
  was estimated, and using the wrong table is a classic way to manufacture significance.
- **Johansen** — how many cointegrating relationships exist among the legs, which is the
  test that generalises beyond two legs.

**Command shape**

```bash
python cointegration.py -s USDNOK,USDZAR --test all --adf-trend c --lags aic
python cointegration.py -s USDNOK,USDZAR --test engle-granger --split 0.70 --both-directions
python cointegration.py -u fx-all --test johansen --det-order 0
```

`--both-directions` matters: Engle–Granger regressing A on B and B on A can disagree, and a
pair that is only cointegrated one way is weaker evidence than one that passes both.

**Parameters**

- *structure* — `--test`, `--adf-trend` (none, constant, constant plus trend), `--lags`
  (aic, bic or a fixed number), `--det-order` for Johansen
- *searched* — `--split`, `--start`, `--end`
- *given by reality* — nothing; this sub-step has no cost input

**Output.** Statistic, critical values at 1/5/10%, p-value, and a plain sentence saying what
it means. The report must state the trial count alongside, because testing many pairs and
reporting the best p-value is exactly the multiple-comparisons error that killed
`GBPUSD~USDNOK`.

**Done when** `USDNOK~USDZAR` has ADF and Engle–Granger results in and out of sample, and
the pair report grows a real p-value row in place of the current placeholder.

**Blocked on** `pip install statsmodels`. One command, and it also unblocks nothing else —
this is the only sub-step that needs it.

---

## 2c — Hedge ratio estimators

**What it is.** A comparison, not a choice made in advance. The static OLS ratio is the
current baseline, and the reason `GBPUSD~USDNOK` was exposed as a false positive is that its
static ratio moved from −0.65 to +0.22 across windows. A hedge ratio that needs to move is
telling you something; the question is whether letting it move helps or just fits noise.

Three estimators:

- **Static OLS** — one number for the whole sample. The baseline to beat.
- **Rolling OLS** — refit over a trailing window. One parameter, `--window`, and it is a
  searched parameter, so every value tried is a trial.
- **Kalman filter** — the ratio as a hidden state with its own process noise. Adapts
  continuously, at the cost of two parameters that are easy to over-tune.

**Command shape**

```bash
python hedge.py -s USDNOK,USDZAR --method static,rolling,kalman \
    --window 120 --kalman-delta 1e-4 --kalman-obs-var auto --compare
```

**Output.** The three ratio paths on one chart, and for each method the resulting spread's
half-life in and out of sample, plus the stability ratio used throughout this project. The
verdict is which estimator produces the most stable spread out of sample — not which fits
best in sample, which the Kalman filter will always win.

**Done when** the candidate has a recommended estimator with the evidence for it, and the
recommendation is carried into `relationship.py` as a default.

---

## 2d — Relationship engine

**What it is.** One module that performs the whole chain in order, so that the backtest, the
health monitor and eventually the live bot all compute the spread the same way. This is the
component `strategy.py` from Step 1c imports.

The chain, in the order `PLAN.md` specifies:

1. factor decomposition or factor residuals (2a)
2. cointegration test — is the gap actually closing? (2b)
3. hedge ratio (2c)
4. spread construction
5. OU fit: `theta`, `mu`, `sigma`, half-life `ln2/theta`, `sigma_eq = sigma / sqrt(2*theta)`
6. z-score

```python
def fit_relationship(prices: pd.DataFrame, params: RelationshipParams) -> Relationship:
    """Everything about the pair as of the last bar in `prices`, and nothing after it."""
```

The signature is the design, exactly as in `strategy.py`: `prices` ends at the current bar, so
look-ahead is impossible by construction. `pair_report.py` should be refactored to call this
rather than keeping a second copy of the arithmetic — two implementations of a spread is two
chances to be subtly different, and the difference will surface as a backtest that cannot be
reproduced live.

**Done when** `relationship.py` reproduces the Step 0 shortlist exactly — same betas, same
half-lives, same verdicts — and `pair_report.py` uses it.

---

## 2e — Health monitor

**What it is.** The component most often missing, and the one that prevents the classic
statistical-arbitrage blow-up: a bot that keeps averaging into a spread which has stopped
mean-reverting. `AUDUSD~NZDUSD` from the first study is the picture to keep in mind — return
correlation 0.891, legs tracking beautifully, and an out-of-sample spread that simply walked
away.

Each cycle the monitor re-runs the relationship on recent data and asks:

- has the cointegration p-value drifted above the threshold?
- has the half-life left its bounds, or turned explosive?
- has the hedge ratio moved more than its own historical variation?
- has the spread exceeded the level at which the relationship should be presumed broken?

and produces one of three states: **healthy**, **degraded** — no new entries, existing
positions run — or **broken** — force the exit now, at a loss, without waiting for reversion.

**Command shape**

```bash
python health.py -s USDNOK,USDZAR --lookback 250 --recheck-every 5 \
    --max-pvalue 0.05 --max-half-life 30 --max-beta-drift 2.0 --break-z 4.0 --replay
```

`--replay` walks the whole history and reports what the monitor would have said at each
point. That is the only honest way to choose these thresholds: set them so the monitor would
have flagged the known failures — `AUDUSD~NZDUSD`, `GBPUSD~USDNOK` — before the loss, not
after.

**Parameters**

- *structure* — which checks are active
- *searched* — every threshold above, and `--lookback`; each setting is a trial
- *given by reality* — nothing directly, but a forced exit pays the full cost from Step 1a,
  so a jumpy monitor is expensive

**Output.** A state timeline aligned with the spread chart, the trigger that fired at each
transition, and a count of how often each check was the binding one. A monitor where one
check fires every time is really a one-check monitor.

**Done when** replaying the known-dead relationships raises **broken** before the spread
diverges, and replaying the candidate does not raise it spuriously during normal trading.

---

## 2f — Verification

**What it is.** The same treatment `verify_pair_report.py` gives the pair study, extended to
the engine. It should reuse that file's helpers rather than starting again.

The checks that matter:

- **Ground truth** — simulate a cointegrated pair with a known hedge ratio and half-life;
  the engine recovers both. Simulate an independent pair; the cointegration test rejects.
- **Test calibration** — run the cointegration test on many independent random walks and
  confirm it rejects the null about 5% of the time at the 5% level. A test that fires more
  often than its own size is worse than no test, and this is the single most important check
  in 2b.
- **Kalman reduces to OLS** when the process noise goes to zero. If it does not, the filter
  is wrong.
- **Factor gauge invariance** — adding a constant to every currency factor changes no pair
  residual, because only differences are observable.
- **No look-ahead** — tampering with data after bar `t` must not change anything the engine
  reports at bar `t`.
- **Health monitor sensitivity and specificity** — it flags the known-dead pairs, and does
  not flag a clean simulated OU pair.
- **Engine agrees with the pair study** to the last decimal on the Step 0 shortlist.

**Done when** the suite runs green and the cointegration test's false-positive rate is
measured, not assumed.

---

## What is deliberately not here

| Thing | Why not |
|---|---|
| Entry and exit thresholds | Step 3. The engine reports a z-score; deciding what to do with it is the signal's job |
| Position sizing | Step 3 |
| Machine-learned hedge ratios | Multiplies the trial count for a problem that has two estimators and a baseline |
| Multi-leg baskets | The engine should be written so it generalises, but the candidate has two legs |
| Live data feed | Step 5 |

## Order of work

1. `pip install statsmodels` — the one blocking dependency, and it only gates 2b
2. Build 2c first if you want a quick result: it is self-contained and it directly addresses
   the failure mode that killed `GBPUSD~USDNOK`
3. 2a and 2b in either order
4. 2d to unify them, then refactor `pair_report.py` onto it
5. 2e, then 2f before trusting any of it
