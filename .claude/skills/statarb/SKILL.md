---
name: statarb
description: >
  Run and interpret the Step 0 pair study for the non-directional trading bot:
  fit a hedge ratio between two instruments, build the spread, estimate the
  Ornstein-Uhlenbeck half-life in and out of sample, and decide whether the
  relationship is tradable after costs. Use whenever the user asks whether two
  assets are correlated or cointegrated, whether a pair is worth trading, to
  test a pair or basket, to compute a hedge ratio, spread, z-score or
  half-life, to run a mean-reversion or statistical-arbitrage study, or to
  produce a pair report — including phrases like "is EURUSD and GBPUSD
  tradable", "check this pair", "find correlated pairs", "test AUDUSD against
  NZDUSD", "what is the half-life", "run step 0", or before any statarb
  backtest or bot work. Never write ad-hoc cointegration or spread code while
  this skill applies; `pair_report.py` already handles the hedge ratio, the OU
  fit, the gate ordering, the trial log and the known failure modes of this
  data.
---

# Statistical Arbitrage — Step 0 Pair Study

`development/statarb/code/pair_report.py` answers one question about two instruments: **is the
gap between them actually closing, often enough and far enough to pay for the cost of
trading it?**

This is the research gate in `development/statarb/plan/PLAN.md`. Nothing downstream — backtest
engine, signal, risk, execution — starts until a pair passes it. Failing here is cheap;
failing in Step 4 after building a bot is not.

Scope is **descriptive statistics on close prices**. It is not a backtest, it produces no
PnL, and an accepted pair is a candidate for Step 1, nothing more.

## Step 0 — working directory

Paths default to locations relative to the package, so run from there:

```bash
cd development/statarb/code
python pair_report.py -s AUDUSD,NZDUSD
```

`code/paths.py` resolves the store, the studies folder and the logs, so the scripts also
work when run from anywhere by full path. Nothing needs installing.

The directory is split by what a file is for:

| Folder | Holds |
|---|---|
| `plan/` | `PLAN.md` and the per-step splits |
| `code/` | the scripts |
| `costs/` | broker cost profiles, one JSON per broker |
| `logs/` | `trials.csv`, `backtests.csv` — one row per run |
| `worklog/` | write-ups of what was done, for a human to read |
| `studies/pairs/`, `studies/backtests/` | what the scripts produced |

`worklog/` is written for the user; `studies/` is written by a script. Do not mix them.

## Workflow

### 1. Have the data first

The study reads the parquet store; it never downloads. Check coverage with the
`marketdata` skill before anything else:

```bash
cd ../marketdata && marketdata list
```

If a symbol is missing the study stops with the exact download command to run.

### 2. Preview with a dry run

```bash
python pair_report.py -s EURUSD,GBPUSD --dry-run
```

Fits everything, prints the verdict, writes no file and logs no trial. Use it while
exploring so the trial log records only deliberate tests.

### 3. Run the study

```bash
python pair_report.py -s AUDUSD,NZDUSD
python pair_report.py -s EURUSD,EURCHF --start 2022-01-01 --max-half-life 60 --cost-bps 3
python pair_report.py -s BTC-USDT,ETH-USDT -a crypto -t 1h --max-half-life 200
python pair_report.py -s GOLD,AUDUSD -a commodity,forex        # one class per leg
```

**Cross-asset pairs** are the interesting case — a commodity currency against the
commodity it is supposed to track. Give one asset class per leg, in the same order as
the symbols. Daily bars from different venues carry different stamps (Yahoo puts forex
at 23:00 UTC and futures at 04:00), so daily and weekly cross-asset pairs are matched on
the **UTC date**. The two closes are then not simultaneous, which biases measured
correlation downward and can manufacture apparent lead-lag. The report says so on every
cross-asset study.

Each run writes `studies/pairs/pair-A-B-trialNNN.html` and appends one row to
`logs/trials.csv`.

### 4. Read the verdict, not the charts

The banner at the top of the report is the answer. The charts explain it; they do not
override it. A pair that looks beautiful on the price chart and fails the half-life gate
is a failed pair.

### 5. Iterate honestly

Changing any parameter and re-running is a **new trial**, and it is logged. That is the
point: Step 4's Deflated Sharpe Ratio needs the true number of attempts. Never suppress
the log to make a search look smaller than it was.

## Options

Every flag, grouped the way the parameters actually behave.

### Selection

| Flag | Default | Meaning |
|---|---|---|
| `-s, --symbols` | required | exactly two canonical symbols, comma separated |
| `-a, --asset-class` | `forex` | `forex`, `crypto` or `commodity`; one value for both legs, or one per leg in the order given |
| `-t, --timeframe` | `1d` | `1m 5m 15m 1h 4h 1d 1w`, as stored |
| `--source` | per asset class | `yahoo` for forex and commodities, `binance` for crypto; one value or one per leg |
| `--start` | all history | `2019-01-01`, `20190101`, `2y`, `6mo`, `30d`, `now` |
| `--end` | all history | same formats; everything is UTC |

Symbols are canonical and source-agnostic: `EURUSD`, not `EURUSD=X`; `BTC-USDT`, not
`BTCUSDT`.

### Structure — choose once, not per run

These define what is being measured. Changing them mid-study makes trials incomparable.

| Flag | Default | Meaning |
|---|---|---|
| `--price` | `log` | `log` or `raw`. Log makes the hedge ratio a ratio of returns |
| `--hedge` | `ols` | hedge ratio estimator; static OLS of A on B |

### Searched — every value is a trial

| Flag | Default | Meaning |
|---|---|---|
| `--split` | `0.70` | in-sample fraction; the rest is held out |
| `--entry-z` | `2.0` | z-score at which a trade would open |
| `--exit-z` | `0.5` | z-score at which it would close; must be below entry |
| `--min-half-life` | `2` bars | below this the spread is noise at this timeframe |
| `--max-half-life` | `30` bars | above this capital is tied up longer than intended |
| `--min-edge` | `2.0` | required expected move as a multiple of round-trip cost |

### Given by reality — from the broker, not a knob

| Flag | Default | Meaning |
|---|---|---|
| `--cost-bps` | `2.0` | round-trip cost of **both legs**, in basis points |

Tuning `--cost-bps` downward until a pair passes is self-deception. Take it from the
account being traded, including the spread on each leg and any commission.

### Output

| Flag | Default | Meaning |
|---|---|---|
| `-o, --out` | `studies/pairs/pair-A-B-trialNNN.html` | report path |
| `--store` | `../../marketdata/store` | parquet store to read |
| `--trials` | `../logs/trials.csv` | trial log path |
| `--no-trial-log` | off | skip the log; the report then drops the trial number |
| `--bins` | `45` | histogram bins, 5 to 200 |
| `--dry-run` | off | fit and print, write nothing |
| `--json` | off | print the fit and verdict as JSON, even under `-q` |
| `--open` | off | open the report in a browser |
| `-q, --quiet` | off | suppress progress lines |
| `-v, --verbose` | off | full tracebacks instead of a one-line error |

## Reading the output

### Console

```
AUDUSD ~ NZDUSD  1d  2019-01-01 -> 2026-09-08  2,001 bars
  beta 0.8658   corr 0.891   half-life IS 49.7   OOS explosive
  REJECT - in-sample half-life 49.7 outside 2-30; out-of-sample spread diverges
  wrote studies/pairs/pair-AUDUSD-NZDUSD-trial001.html  (151.9 KB)
  trial #1 logged to logs/trials.csv
```

### Exit codes

`0` accepted, every gate passed · `3` rejected · `2` usage error (bad symbols, impossible
parameters, missing data, trial log schema mismatch) · `1` runtime error · `130`
interrupted.

Exit 3 is a result, not a failure. Scripting many pairs and collecting the zeros is a
valid way to work.

### The report

One self-contained HTML file, no external requests, light and dark aware:

1. **Verdict banner** — ACCEPT or REJECT with the reason. Read this alone and stop.
2. **Parameters used** — every value that produced this result, including source and
   asset class.
3. **Results table** — value, PASS/FAIL badge and a one-line note per gate.
4. **Price, one line per leg** — raw close, last price labelled at the right edge. Legs
   whose price levels differ by more than four times cannot share an axis, so the chart
   switches to index-100 and the legend keeps the real first and last prices.
5. **Legs, rebased log price** — do they track? Visual only.
6. **Spread** with the ±entry-z equilibrium band and the mean.
7. **Z-score** with entry and exit threshold lines.
8. **Spread distribution** histogram.

Charts 4 to 8 each carry a one-line caption saying what to look for. The in-sample and
out-of-sample halves are divided by a vertical marker on every time chart.

### `logs/trials.csv`

One row per run, 27 columns: `trial`, `run_utc`, `symbols`, `timeframe`, `start`, `end`,
`price`, `hedge`, `split`, `entry_z`, `exit_z`, `min_half_life`, `max_half_life`,
`cost_bps`, `min_edge`, `bars`, `beta`, `correlation`, `half_life`, `half_life_oos`,
`regime`, `regime_oos`, `sigma_eq_bps`, `edge_mult`, `verdict`, `reason`, `report`.

The `report` column names the file for that exact trial, which is why report filenames
carry the trial number. If the log was written by an older version of the script the run
stops with exit 2 rather than appending misaligned columns — rename the old file to keep
the history and a fresh log starts.

## Interpreting the numbers

### The three regimes

The OU fit is an AR(1) regression `s[t+1] = a·s[t] + b + noise`, and `a` decides
everything:

| Fitted `a` | Regime | Meaning |
|---|---|---|
| `0 < a < 1` | `reverting` | the OU case; half-life `ln2/θ` and σ_eq exist |
| `abs(a) >= 1` | `explosive` | the spread walks away instead of returning |
| `-1 < a <= 0` | `oscillating` | reverts faster than one bar: noise or bid-ask bounce |

`oscillating` is **not** a failure to revert — it is reversion too fast for this
timeframe. Never describe it as divergence.

### Gate order matters

Gates are applied in order and the order is load-bearing:

1. in-sample half-life inside the bounds
2. out-of-sample half-life inside the bounds
3. **only then** edge versus cost

A spread that is not stationary has no equilibrium standard deviation, so σ_eq is
meaningless and an edge computed from it is an artefact of the drift. On a real rejected
pair that spurious number came out as `136x` — enormous, convincing and worthless. The
report shows `not evaluated` instead. Never quote an edge multiple from a pair that
failed stationarity.

### The edge gate is weak on slow, volatile spreads

`edge vs cost` compares one round trip against the spread's own standard deviation, and
says nothing about how long the capital is tied up. A commodity-versus-FX spread with
σ_eq near 2000 bps and a half-life of 90 bars clears a 5 bps cost by a factor of several
hundred — a true statement that means almost nothing, because the binding constraints
are the holding period and the drawdown, neither of which this gate measures. Treat a
huge edge multiple on a slow spread as a description of volatility, not of opportunity.

### Correlation is not tradability

`correlation` is printed for context and is **not a gate**. AUDUSD and NZDUSD have 0.891
return correlation, track beautifully on the chart, and the spread is explosive out of
sample. Correlation says two things move together; cointegration says the gap closes.

### The out-of-sample half-life is the honest number

In-sample half-life is fitted on data the hedge ratio was also fitted on. The held-out
half is the only evidence that the relationship is structure rather than curve fitting.
A pair that reverts in-sample and diverges afterwards is a rejection, not a near miss.

## Verifying the tool itself

```bash
python verify_pair_report.py            # 60 checks
python verify_pair_report.py -v         # print every check
python verify_pair_report.py --trials 1000
```

Eight groups: ground truth against simulated OU processes with known parameters, regime
classification, gate ordering, null calibration, invariance, absence of look-ahead, real
data anchors, and report plumbing. Run it after changing anything in `pair_report.py`.

The null calibration is the one that matters. Feeding 300 pairs of independent random
walks through the default gates accepts about 1.3%. That is the false positive rate, and
it is the reason the next section exists.

## Traps in this data

State these when they affect what the user is trying to do. They are established facts
here, not hypotheticals.

### Multiple testing

30 instruments make 435 pairs. At a 1.3% false positive rate that is roughly **6 pairs
that pass the gates on noise alone**. Ranking every pair and trading the top hit is how
statarb books blow up. Re-test survivors on a different window, and carry the trial count
into Step 4.

### Forex pairs are not independent assets

With K currencies there are at most K−1 independent factors, because
`log P(i,j) = s_i − s_j`. EURGBP **is** EURUSD divided by GBPUSD: measured on the stored
daily data the identity holds to a median of 0.39 bps. Hunting mean-reverting residuals
across a complete set of FX pairs therefore finds residuals that are zero by
construction. The real candidates are cointegrated currency strength with a macro link
(AUDNZD, EURCHF, NOKSEK), FX against an external asset, and hedged carry.

### Yahoo forex bars

Roughly 1–3% of daily Yahoo FX bars have an open or close outside their own high/low
range. This study reads closes only, so it is unaffected, and the report says so. Any
stop-loss, breakout or swing-point work needs a broker feed first.

Yahoo forex volume is always zero, and intraday history is capped: 1-minute bars reach
back 7 days, hourly 730 days.

### Bad prints survive validation

`marketdata validate` checks each bar against itself, not against other instruments. Six
of 2001 stored EURGBP bars break the triangular identity by more than 20 bps, the worst
being 2022-10-09 at `EURGBP 0.97900` against an implied `0.87919` — a 10.8% bad print.
Holiday bars (1 January, 25–26 December) carry a stale quote on one leg. Check the price
chart for a spike before trusting a result on a short window.

### Forex timing

Rollover at 17:00 New York widens spreads and charges swap; weekend gaps cannot be
traded out of. Neither affects a Step 0 study on daily closes, but both matter the moment
Step 1 starts costing trades.

## Current limits

Say these plainly rather than implying more rigour than exists:

- **No cointegration test yet.** Engle-Granger and Johansen are in the Step 0 plan but
  `statsmodels` is not installed, so the gates are half-life bounds only. Half-life is
  evidence of mean reversion, not a hypothesis test — there is no p-value in this report.
- **Static OLS hedge only.** No Kalman filter, so a drifting hedge ratio reads as a
  failing spread.
- **Two legs only.** Baskets and the currency-factor decomposition are not implemented.
- **No cost model beyond a single number.** Time-of-day spread and swap arrive in Step 1.
- Two simultaneous runs can claim the same trial number.

## Rules

- Never present an ACCEPT as a working strategy. It is a candidate for Step 1.
- Never quote `edge vs cost` when the spread failed the stationarity gates; it shows
  `not evaluated` for a reason.
- Never call `oscillating` divergence, or `explosive` slow reversion.
- Never lower `--cost-bps` or widen `--max-half-life` to make a pair pass without saying
  that is what happened, and logging it as a trial.
- Never run with `--no-trial-log` to hide attempts. Use `--dry-run` while exploring.
- Never edit or delete the logs in `logs/`. If a schema is rejected, rename the file.
- Never describe correlation as evidence that a pair is tradable.
- Never write a new spread or cointegration script. Extend `pair_report.py` and add a
  check to `verify_pair_report.py` in the same change.
- Reports are for the user to read. Do not generate one as a side effect of an analysis
  task; use `--dry-run` or `--json` instead.

## Screening a whole universe

`pair_report.py` studies one pair. `screen.py` studies all of them, and it is the entry
point for any search:

```bash
python screen.py -u equities --within-sector --broker equity
python screen.py -u fx-all -t 1m --broker fxretail --max-half-life 200
python screen.py -s XLF,XLE,XLK,XLV -a index --broker etf
```

**It reserves a window at each end of the record and never looks at it while ranking.**
That is not a nicety. This project produced two candidates without it — `XLP~XLB` and
`ALL~TRV` — and both were cointegrated *only* on the window that had selected them, at
p = 0.033 and p = 0.014, and on no window before it. A tail split of the screening window
cannot catch that, because the window itself was part of the choice. `--holdout 0` restores
the old behaviour and prints a warning saying what happened last time.

The gates, in order, cheap first:

| Gate | Rejects |
|---|---|
| cointegration | the gap is not closing |
| held-out tail | it stops closing inside the screening window |
| **reserved windows** | it does not exist outside the window that selected it |
| **hedge-ratio swing** | the ratio moves by more than 3x across windows, or changes sign |
| hedge quality | the position is directional wearing a spread's name |
| reversion speed | the capital is tied up longer than intended |
| **replay** (`--broker`) | the trades do not do what the model predicted |

The last one runs only on whatever survived the rest, because it replays the strategy and
that costs real time. It asks the three questions the `sizing` skill owns: does the
expected move describe these trades, does any entry threshold earn its own cost back, does
the sample establish a positive mean. **All three have killed every candidate this project
has ever had.**

Every screen prints survivors beside the number chance alone would produce, for both the
first gate and the reserved windows. A screen that finds five where noise gives five has
found nothing, and the screen says so rather than leaving it to be noticed.

### What it currently finds

```
universe        pairs  coint  noise  outside  expected  survivors
equities          205     17   10.2        0       1.0          0
sector-etfs       105      6    5.2        0      0.51          0
fx-all             66     15    3.3        0      0.32          0
fx-all (1m)        45     16    1.0        3      0.10          0
index-etfs          6      0    0.3        0      0.03          0
crypto-majors       1      0    0.1        0       0.0          0
```

One pair has ever reached the replay: `USDCHF~USDCAD` on one-minute bars, which cleared
every statistical gate — p = 0.027, holding out of sample at 0.006 and on the reserved
early window at 0.000, ratio stable to 1.75x, 6% net exposed — and was then rejected
because its expected move over-predicts by 20x, no threshold earns its own cost, and the
uncertainty-adjusted mean is −1.4 bps.

That is the funnel working. The statistics let it through; the trades did not.

Once a pair passes this gate, the next steps have their own skills: **relationship** for
the cointegration test, the hedge-quality check and the health monitor, **tradingcosts**
for what the broker charges and whether the edge survives financing, then **backtest** for
what the strategy would have earned.

A half-life is an estimate, not a test. This skill has no p-value anywhere; **relationship**
does, and on stored data the two disagree on 7 of 13 pairs.

The screen's "noise alone would give about X" line is `N x level`, and on real equity data
the measured floor is a third higher — 78.8 against 58.6 on 1,171 pairs. The `validation`
skill measures it by bootstrap. Never report a hit count against the printed figure alone.

## The research log — every pair, every gate value, one file

`screen.py` appends one row per pair tested to `logs/pair_research.csv` on every run, and
the row carries **both the result and the parameters that produced it**. Suppress with
`--no-research-log`, redirect with `--research-log PATH`.

This exists because neither of the other two files can answer the question a later
optimisation asks. `--dump` writes per-pair results with no record of the gates in force;
`logs/screens.csv` writes the gates but only per-screen aggregates. Joining them after the
fact is guesswork once a default has changed.

45 columns in three blocks, left to right:

| block | columns |
|---|---|
| identity | `run`, `run_utc`, `universe`, `asset_class`, `timeframe`, `start`, `end`, `pair`, `a`, `b`, `sector`, `bars` |
| result | `pvalue`, `pvalue_oos`, `pvalue_early`, `pvalue_late`, `beta`, `beta_early`, `beta_late`, `beta_swing`, `hedge_ok`, `half_life`, `half_life_oos`, `net_exposure`, **`survived`** |
| parameter | `price`, `lags`, `split`, `level`, `holdout`, `min_tail`, `min_abs_beta`, `max_negative_share`, `max_net_exposure`, `min_half_life`, `max_half_life`, `max_beta_swing`, `min_screen_bars`, `require_oos`, `require_link`, `within_sector`, `require_early`, `broker`, `bars_per_night`, `max_overstatement` |

`survived` is recorded **per pair** rather than only counted, which is what turns the file
from a log into labelled data: a later run can ask which gate value would have changed a
given verdict without re-screening anything.

It appends rather than overwrites, and `run` joins back to `logs/screens.csv`.

**A warning that belongs with it.** This file makes parameter sweeping easy, and easy is
the danger. Every distinct parameter set in it is a trial, and the deflated-Sharpe benchmark
in Step 4 grows with the logarithm of that count. The file is for understanding which gate
bound a result, not for hunting the cell where something passes — that is the behaviour
`overfit.py` exists to detect.

## When to reach for the residual track instead

This skill studies **one pair at a time**, and that shape has now been measured to its
limit: 4,009 pair tests across 22 logged screens, zero survivors. The governing constraint
is breadth. Information ratio scales as `IC x sqrt(breadth)`, and a single pair trading a
few dozen times has a breadth of about one, which predicts the Sharpes actually observed.

The SPX screen of 2026-09-17 put a number on why. Across 380 within-sector pairs, 55 were
cointegrated in the early window and 41 in the late window, with **5 in both against 5.9
expected under independence**. Knowing a pair was cointegrated early says nothing about
whether it is cointegrated now.

Use the **factor-residual** skill when the universe is wide enough to support a factor
model — it produces a signal for every name at once rather than selecting one pair. Stay
here when the universe is narrow (forex at 15 names, crypto at 18) or when the question is
genuinely about two named instruments.

Full build plan and what comes after this gate: `development/statarb/plan/PLAN.md`, with
the per-step splits in `plan/STEP1.md`, `plan/STEP2.md` and `plan/STEP3.md`, and the
redesign in `plan/RESIDUAL.md`. Data loading, storage and quality: the `marketdata` skill.

The half-life and expected move this skill reports are **estimates, not outcomes**. Before
treating either as an edge, the `sizing` skill measures what the trades actually did: on
every pair tested so far the expected move over-predicts the realised result by 10x to 68x,
or has the wrong sign.
