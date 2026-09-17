---
name: backtest
description: >
  Replay stored bars through the live signal code, charge real broker costs,
  and report what a pair-trading strategy would have earned. Covers the
  decision function shared with live trading, the replay engine, entry and exit
  thresholds, stops and holding limits, and the verification suite that proves
  the engine is not overstating returns. Use whenever the user asks to backtest
  or simulate a strategy, what a pair would have made, how a signal performs,
  to tune entry or exit thresholds, to check an equity curve, drawdown, win
  rate or Sharpe, or to test whether a result is real — including phrases like
  "backtest this", "run a simulation", "what would it have returned", "test
  these thresholds", "is this profitable", "show the equity curve", or before
  any paper or live trading decision. Never write an ad-hoc backtest loop while
  this skill applies; `backtest.py` already handles fill timing, cost and carry
  accounting, trade booking and the look-ahead traps.
---

# Backtest — replay, charge, and check

Three files in `development/statarb/code`:

| File | Role |
|---|---|
| `strategy.py` | the decision function. A pure function, and the same one that runs live |
| `backtest.py` | the replay engine. Walks bars, fills, charges, reports |
| `verify_backtest.py` | 122 checks that the engine is not lying |

## The constraint everything else follows from

> The backtest must replay bars through **the exact code that runs live**. Two code paths
> means the backtest measures nothing.

That is why the decision lives in its own module with this signature:

```python
def target_position(history: pd.DataFrame, state: SignalState,
                    params: SignalParams) -> Target
```

`history` ends at the bar being decided on and contains nothing later, so look-ahead is
impossible **by construction rather than by discipline**. `state` is what the strategy
remembers; `params` is everything typed on the command line. No file reading, no printing,
no order placing.

## Working directory

```bash
cd development/statarb/code
python backtest.py -s USDNOK,USDZAR --broker demo
```

Needs two things that already exist: price history in the store (`marketdata` skill) and a
cost profile (`tradingcosts` skill). It never downloads and never invents a cost.

## Workflow

### 1. Have a candidate and a cost profile

A backtest of a pair that failed its Step 0 gates measures nothing useful. Check the
`statarb` skill first, then `costs.py list` for a broker profile.

### 2. Preview

```bash
python backtest.py -s USDNOK,USDZAR --broker demo --dry-run
```

Runs everything, prints the result, writes no report and logs no run.

### 3. Run the control alongside the strategy

```bash
python backtest.py -s USDNOK,USDZAR --broker demo --signal random --seed 3 --dry-run
```

`--signal random` replaces the decision with a coin flip at the same trade frequency. A
coin flip has no edge, so it should lose roughly what it spends. **If the strategy is not
clearly better than the control, there is no strategy** — this is the comparison that
matters most, and it is one flag away.

### 4. Read the four lines, not the equity curve

```
gross   -49.6    what the positions earned
cost   -109.6    spread and commission
carry  -108.1    financing
net    -267.3    what is left
```

A negative **gross** means the signal earned nothing to pay costs with, and no better
broker rescues it. A positive gross eaten by cost is a different problem with different
fixes.

### 4a. Then read the risk and profit block

Printed under those lines by default. `--brief` suppresses it; everything in it is also in
`--json`.

```
  profit                              risk
    net                 31.26%         max drawdown         -12.53%
    per year             1.49%         volatility/year        5.26%
    gross               35.52%         Calmar                  0.12
    profit factor         2.10         Sortino                 0.35
    payoff ratio          1.69         longest underwater   2,813 bars
    trades/year            2.7         worst losing run         5 trades

    per trade: expectancy +55.8 bps, average win +192.6, average loss -113.8
    tail:      worst -327.6 bps, worst 5% start -216.9, average beyond it -264.9

    Sharpe 0.28 +/- 0.22 (standard error; on this many observations)
    mean/standard error +1.32 - the mean is indistinguishable from zero
    still 495 bars below the previous peak on the last bar of the record
    all figures are per unit of spread notional, not account equity; sizing.py converts
```

**Percent and basis points are both shown** so neither has to be taken on faith. 100 bps is
1%. The engine computes in basis points because that is the unit costs are quoted in;
percent is there because it is the unit a result is read in.

The three lines at the bottom are the ones that stop the block above being read too kindly.

**`Sharpe 0.28 +/- 0.22`** — the standard error of the Sharpe itself. When it is close to
the ratio, as here, the Sharpe is not distinguishable from zero and printing it alone
invites treating it as though it were. Expect a large error on any pair with few trades.

**`mean/standard error +1.32`** — the per-trade mean measured against its own uncertainty.
Below 2 it says, in as many words, that the mean is indistinguishable from zero. This is
the same quantity the **sizing** skill haircuts on, shown before the profit rather than
after it.

**`all figures are per unit of spread notional`** — these are not account returns. A net of
31% means 31% of the notional put into the spread, at leverage of one, and converting it
into what an account would have made is `sizing.py`'s job, not this one's.

Two more worth knowing by name. **Calmar** is annual return over the worst drawdown: 0.12
means twelve and a half percent was risked to earn one and a half. **Longest underwater**
is the longest unbroken stretch below a previous peak, in bars — 2,813 daily bars is
eleven years, and a strategy nobody could sit through is not a strategy. When the record
ends below its peak the block says so on its own line, because a maximum drawdown that has
never been recovered has not been shown to recover at all.

A high profit factor with a tiny `trades/year` is a warning, not a result: check whether a
handful of trades carry everything. On `AUDUSD~USDNOK` the top five trades of 73 were 84%
of all profit, and the single largest was a bad data print.

### 5. Iterate honestly

Every run appends a row to `logs/backtests.csv`. Threshold tuning is a parameter search and
the trial count feeds the Deflated Sharpe Ratio in Step 4. Use `--dry-run` while exploring.

## Options

### Selection

| Flag | Default | Meaning |
|---|---|---|
| `-s, --symbols` | required | the two legs |
| `-a, --asset-class` | `forex` | one value, or one per leg |
| `-t, --timeframe` | `1d` | as stored |
| `--source`, `--start`, `--end` | | as in the pair study |

### Structure — choose once

| Flag | Default | Meaning |
|---|---|---|
| `--price` | `log` | `log` or `raw` |
| `--hedge` | `ols` | hedge ratio estimator |
| `--hedge-source` | `rolling` | `static` fits once; `rolling` refits on a trailing window |
| `--signal` | `strategy` | `random` is the calibration control, never a strategy |

### Searched — every value is a trial

| Flag | Default | Meaning |
|---|---|---|
| `--split` | `0.70` | in-sample fraction; the report divides the charts at it |
| `--entry-z` | `2.0` | open when the spread is this far from its mean |
| `--exit-z` | `0.5` | close when it comes back inside |
| `--stop-z` | `4.0` | give up: the relationship is presumed broken |
| `--max-holding-bars` | `20` | refuse to wait forever to be proved right |
| `--min-bars-between-trades` | `0` | cooling-off period after an exit |
| `--fit-window` | `250` | bars a rolling fit uses |
| `--rehedge-every` | `5` | bars between refits; never while a position is open |
| `--warmup` | `260` | bars reserved for the first fit, never traded |

`--stop-z` and `--max-holding-bars` are **risk controls, not optimisations**. Removing them
to improve a backtest removes the two things that limit the loss when a spread stops
reverting.

### Given by reality

| Flag | Default | Meaning |
|---|---|---|
| `--broker` | required | cost profile to charge |
| `--costs-dir` | `../costs` | where profiles live |
| `--bars-per-night` | `1.0` | `1.0` for daily bars, `1/24` for hourly |
| `--lag` | `1` | bars between the decision and the fill; 1 is the next close |
| `--leave-open` | off | do not close a position still open at the last bar |

### Output

| Flag | Default | Meaning |
|---|---|---|
| `-o, --out` | `studies/backtests/backtest-A-B-SIGNAL.html` | report path |
| `--store` | `../../marketdata/store` | price store |
| `--trials` | `../logs/backtests.csv` | run log |
| `--no-trial-log` | off | skip the log |
| `--bins`, `--max-trade-rows` | `30`, `60` | report detail |
| `--brief` | off | print only the headline lines, without the risk and profit block |
| `--bars-per-year` | `252` | annualisation for the Sharpe figure |
| `--seed` | `0` | for `--signal random` |
| `--dry-run`, `--json`, `--open`, `-q`, `-v` | | as elsewhere |

Exit codes: `0` net profitable, `3` net loss, `2` usage error, `1` runtime error.
**Exit 3 is a result**, not a failure.

## How the engine accounts

Facts worth knowing before trusting a number:

- **Decide on a close, fill at the next bar.** Deciding and filling on the same close is the
  most common way a backtest invents profit. `--lag` raises the delay; the result must get
  worse, and the verification suite checks that it does.
- **Returns accrue on the position held coming into the bar**, so a fill never earns the
  move it was filled on.
- **A change of position is always an exit and then an entry**, even a straight flip from
  long to short. Booking a flip as one continuous trade reports a direction and a holding
  period that never happened.
- **A position still open at the last bar is closed at the final price** and charged, so
  every basis point belongs to some trade. `--leave-open` disables that and leaves a gap.
- **Carry is charged per night held**, using the direction-specific swap, signed the way the
  broker quotes it.
- **The per-trade table reconciles with the equity curve to the basis point.** If it ever
  does not, that is a bug, not a rounding artefact.
- **Close-only fills.** Yahoo forex high and low are unusable — 1 to 3% of daily bars have an
  open or close outside their own range — so `--stop-z` is evaluated on closes, not intrabar.
  A real stop-loss simulation needs a broker feed first.

## The report

One self-contained HTML file: a verdict banner, six headline tiles, a results table, then
charts — a waterfall of gross into cost, carry and net; gross against net equity with the
in-sample divider; drawdown; the z-score with the position overlaid; and the distribution
of holding periods. Then every trade, with the reason it closed.

A pile of holding periods at the maximum means the **time stop is doing the exiting**, not
the spread.

## Verifying the engine

```bash
python verify_backtest.py            # 122 checks, about two minutes
python verify_backtest.py -v         # print every check
```

Fifteen groups: accounting identity, zero-cost, null calibration, look-ahead, carry
scaling, the flat strategy, the signal contract, exit reasons, real data, trade booking,
the cost profile, nights per bar, feasibility, the health gate, and the risk and profit
metrics.

The risk-metric group pins values worked out by hand rather than copied from a previous
run, and it exists in that form because three of its checks passed a mutation test on the
first attempt for the wrong reason: the Sharpe standard error was pinned on a constant
series where the term being tested is zero, the losing-streak check had no scratch trade in
its sample so `<` and `<=` agreed, and the expected-shortfall check asserted only an
inequality that still held when the mutation made two quantities equal. All three now pin
values on data where the term actually bites.

Run it after touching `strategy.py` or `backtest.py`. The suite has already caught, among
others, a financing debit added to equity as a credit, a flip booked as one trade, and a
position left unattributed at the end of the sample — each of which produced plausible,
confident, wrong numbers.

The group that matters most is the **null calibration**: a random signal must lose about
what it spends. An engine that shows a coin flip making money is broken, whatever else it
reports.

## Rules

- Never write a separate backtest loop, and never let the live bot use a different decision
  function. One code path.
- Never report a net figure without the gross, cost and carry beside it.
- Never quote a Sharpe from this engine without its standard error. On a few dozen trades
  the error is routinely as large as the ratio.
- Never present a percent from this engine as an account return. It is per unit of spread
  notional; `sizing.py` converts, and its haircut is usually severe.
- Never report a profit without checking how few trades produced it. The block prints
  `trades/year`, `profit factor` and the tail for this reason.
- Never present a backtest as evidence without the `--signal random` control from the same
  data and costs.
- Never remove `--stop-z` or `--max-holding-bars` to improve a result.
- Never trust a result from a cost profile marked ESTIMATED without saying so.
- Never tune thresholds without logging every attempt; the count is an input to Step 4.
- A profitable backtest is not a working strategy. It is a candidate for validation —
  `PLAN.md` Step 4 is the only step that can say yes.

Related: `statarb` finds candidates, `relationship` tests whether they are genuinely
cointegrated and still alive, `tradingcosts` supplies the charges, `marketdata` supplies
the bars. Plan and status: `development/statarb/plan/STEP1.md`.

`--health-gate` hands control of exposure to the **relationship** skill's monitor: flat
while broken, no new entries while degraded.

A net figure from this engine is not an edge, and it is not evidence either until the
`validation` skill has charged it for the search that produced it — the same result can
read as an 80.5% probability of beating zero and a 3.5% probability of beating what the
search alone would find.

## Thresholds are not the only way to size

Every entry and exit threshold this engine accepts is a **trial**, and the deflated-Sharpe
benchmark in Step 4 grows with the logarithm of the trial count. Sweeping five entry values
multiplies the count by five before any of them has earned anything.

The **portfolio** skill sizes without thresholds at all: the position is continuous in the
fitted Ornstein-Uhlenbeck drift, `w = theta(mu - X)/sigma^2`, so there is no value to
sweep. That path is currently cross-sectional only and is not yet wired into this engine —
stage 16 of the **pipeline** skill is exactly that gap.

A net figure from this engine is not an edge. The **sizing** skill takes the same trades
and asks whether they did what was predicted, whether any entry threshold earned its own
cost back, and whether the sample establishes a positive mean at all. On every pair tested
so far the answer to the last question has been no — including the ones that made money.
