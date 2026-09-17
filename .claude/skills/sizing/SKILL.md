---
name: sizing
description: >
  Decide whether a pair trade is worth placing and how large it should be:
  measure what actually happened to past trades against what the model
  predicted, find the entry threshold below which a trade cannot pay for its own
  financing, check how many independent bets a book of spreads really contains,
  and compute growth-optimal leverage discounted for the uncertainty in its own
  estimate. Use whenever the user asks how much to trade, what position size or
  leverage to use, where to set entry or exit thresholds, how long a trade can
  be held, whether an edge is real or just the model flattering itself, whether
  trades actually reach their targets, how diversified a book is, when to stop
  trading after losses, or to produce a signal or sizing report — including
  phrases like "how big should this position be", "what leverage", "Kelly",
  "where should I enter", "what entry threshold", "how long can I hold this",
  "do the trades actually work out", "win rate versus expectancy", "is this book
  diversified", "correlation between my spreads", "drawdown limit", "kill
  switch", "position sizing", or before any paper or live trading decision.
  Never compute a position size, pick a z-score threshold, or judge
  diversification by counting positions while this skill applies; these scripts
  already handle the completion problem, the financing inversion and the
  uncertainty haircut.
---

# Sizing — outcomes, thresholds, risk, position size

Five scripts in `development/statarb/code`:

| Script | Answers | Exit 0 means |
|---|---|---|
| `outcomes.py` | did the trades do what was predicted? | the prediction is within tolerance |
| `thresholds.py` | where can this be entered at all, and how long held? | a feasible region exists |
| `risk.py` | how many bets is this book really, and when do we stop? | every cap holds |
| `sizing.py` | how much should be held? | a positive size is justified |
| `signal_report.py` | all three, on one page | every question answered yes |

This is Step 3 of `plan/PLAN.md`. It builds on Step 1 (`backtest`, `tradingcosts`) and
Step 2 (`relationship`); the dependency runs one way only, and `verify_signal.py` parses
the syntax tree of every Step 1 and Step 2 script to prove none of them imports Step 3.

## Why it exists

Every edge number in this project came from one formula:

```
expected move = (entry_z - exit_z) * sigma_eq
```

**It had never been compared with what a trade actually earned.** When it finally was, on
every pair that has ever been a candidate:

| Pair | predicted per trade | realised per trade | over by |
|---|---|---|---|
| `XLP~XLB` | 404 | +40.3 | 10× |
| `SPY~DIA` | 273 | +4.0 | 68× |
| `EURUSD~GBPUSD` | 164 | +8.1 | 20× |
| `BTC-USDT~ETH-USDT` | 1,025 | +80.1 | 13× |
| `ALL~TRV` | 758 | −57.3 | wrong sign |
| `AUDUSD~NZDUSD` | 187 | −29.0 | wrong sign |
| `USDNOK~USDZAR` | 359 | −2.2 | wrong sign |

Two errors stack.

**Scale.** The reports fit one OU process to the whole in-sample half; the strategy refits
on a trailing window every few bars. The traded spread is smaller by 1.4× to 5.7×, and its
half-life shorter by up to 15× — `XLP~XLB` is fitted at 260.6 bars and traded at 17.1.

**Completion.** The formula describes a trade that opens at `entry_z` and runs to
`exit_z`. Most do not. `XLP~XLB` reaches its exit on 27% of trades; `AUDUSD~NZDUSD` on
**none** of twelve. The formula silently assumes 100%.

## Working directory

```bash
cd development/statarb/code
python signal_report.py -s XLP,XLB -a index --broker etf
```

Reports land in `studies/signals/`, logs in `logs/outcomes.csv`, `logs/thresholds.csv`,
`logs/risk.csv` and `logs/sizing.csv`. `paths.py` resolves everything, so the scripts run
from anywhere.

Needs price history in the store (`marketdata` skill) and a cost profile (`tradingcosts`
skill). It never downloads and never invents a cost.

## 1. What happened to the trades

```bash
python outcomes.py -s XLP,XLB -a index --broker etf
python outcomes.py -s XLP,XLB -a index --broker etf --entry-z 1.5,2.0,2.5,3.0
```

The replay is `backtest.run_backtest`, unchanged and uncopied — a second replay would be a
second set of bugs. This classifies the trades it produces:

```
 entry  trades  target   stop   time  other   done   avg win  avg loss    w/l
  1.50     134      41     15     78      0    31%    +209.5    -179.4   1.17
  2.00      75      20     15     40      0    27%    +242.2    -216.7   1.12
  2.50      30       5     14     11      0    17%    +165.9    -185.9   0.89
  3.00      11       2      9      0      0    18%    +153.6    -190.7   0.81
```

**Read the completion column first.** The formula says a wider entry earns more, because
the distance back to the exit is longer. The trades say the opposite: what rises with the
threshold is the chance there is no reversion left to catch. At z = 3.0, nine of eleven
trades ended at the stop.

**A large deviation is evidence the relationship has broken, not evidence of opportunity.**
That single sentence is what this script exists to establish.

Exit 3 means the prediction is more than `--max-overstatement` (default 3×) above the
realised mean, or has the wrong sign.

## 2. Where it can be entered, and for how long

```bash
python thresholds.py -s XLP,XLB -a index --broker etf
python thresholds.py -s XLP,XLB -a index -t 1h --broker etf
```

**This is not an optimiser and must never be used as one.** Sweeping entry thresholds on
`XLP~XLB` over twenty-eight years gave a net from −3,678 to +3,747 basis points across
twelve cells, three positive. That surface has no maximum worth finding.

It produces two floors and a holding limit:

- **The modelled floor** inverts the cost arithmetic: the z at which the move is
  `--min-edge` times the transaction and financing. It is optimistic, because it charges
  financing for the fitted half-life and credits a move the trade only collects if it
  completes.
- **The measured floor** replays the strategy at each threshold on a grid and takes **the
  lowest** whose own trades earned `--min-edge` times their own cost. Lowest, not best:
  picking the most profitable cell is what Step 4 exists to catch, and a boundary moves
  less than a maximum.

The difference is not academic. On `XLP~XLB`:

```
modelled floor, z 0.61   339 trades   gross +4,124   carry -3,609   net  -501
measured floor, z 1.50   116 trades   gross +5,803   carry -2,041   net +3,414
```

- **The holding limit** inverts the financing: how many nights the deviation the spread
  actually offers can pay for. A spread whose half-life exceeds it cannot be traded at that
  bar size, whatever its statistics say — and the answer is then a finer bar, not a
  different threshold.

## 3. How many bets the book really holds

```bash
python risk.py --book XLP~XLB:index,ALL~TRV:equity
python risk.py --book XLP~XLB:index:etf,ALL~TRV:equity:equity   # with a kill switch
```

Three checks, cheapest first:

- **Shared legs** — two relationships naming the same instrument. No statistics needed.
- **Effective bets** — the participation ratio of the spread correlation matrix,
  `(ΣL)² / ΣL²`. Equals N when the spreads are independent and falls towards 1 as they
  become the same bet. Reported alongside **bet share** (bets over positions), which unlike
  an absolute floor does not tighten as the book grows.
- **Exposure caps** — per relationship and for the book, using `hedge.net_exposure` so the
  screen gate and the risk layer cannot drift apart.

Forex makes the point concrete: twelve currency pairs resolve to eight independent
directions, so a book of `EURUSD~GBPUSD` and `AUDUSD~NZDUSD` is more concentrated than its
position count suggests.

Naming a broker on every entry (`PAIR:asset_class:broker`) builds an equity curve and runs
the **drawdown kill switch**, which reports the *first* bar past the limit, not the worst —
everything after that date is a trade the rule says was never placed. Without brokers the
switch says it was not evaluated rather than passing silently.

## 4. How much

```bash
python sizing.py -s XLP,XLB -a index --broker etf --net
```

Sharpe is leverage-invariant: doubling every position doubles return and volatility and
leaves the ratio unmoved. It cannot answer this question at all.

Growth can. Holding leverage `f` on per-trade log returns with mean `mu` and variance
`sigma²` grows the account at `g(f) = f·mu − f²·sigma²/2`, maximised at `f = mu / sigma²`.

**The estimate is the problem, not the formula.** Every parameter in this project has moved
by a factor of several across windows. So `mu` is replaced by a lower confidence bound:

```
mu_adjusted = mu - k * sigma / sqrt(n)
```

`k` is `--confidence`, stated by the operator; `sigma/√n` is the standard error of the
mean. Nothing here is a fudge factor.

On `XLP~XLB` net returns: mean +23.2 bps per trade, deviation 309.5, 75 trades, standard
error 35.7. One standard error below is **−12.6**. Seventy-five trades do not establish
that the mean is positive, so the size is zero — reached from trade returns alone, without
reference to any of the cointegration work that reached the same place.

## 5. All three on one page

```bash
python signal_report.py -s XLP,XLB -a index --broker etf --open
```

One self-contained HTML file per pair in `studies/signals/`: the outcome breakdown, the
measured grid, the sizing arithmetic, and five charts. Exit 0 only when all three questions
answer yes.

## Financing is per asset class, and it is not 1.0

`costs.nights_per_bar(asset_class, timeframe)` is the one definition. A **daily bar is not
a night**: equities and their funds trade five days and are financed seven plus holidays
(1.45), forex the same collected as a triple charge on Wednesday (1.40), crypto every day
(1.00). `--bars-per-night` defaults to it.

Charging 1.0 on a daily equity bar understates financing by 45%, and financing is the term
that has decided every candidate in this project. It also made two rows of
`logs/backtests.csv` irreproducible until the value was written onto every logged row.

## Verifying

```bash
python verify_signal.py          # 189 checks
python verify_signal.py -v
```

The checks that carry weight:

- **The OU round trip.** A simulated process with a chosen theta, mu and sigma, where
  completion rate and payoff follow from theory. The prediction holds within 3× there.
  That is what makes the same script's verdict on real data worth reading: it fails on
  `XLP~XLB` because `XLP~XLB` is not an OU process, not because the script cannot measure
  one.
- **The financing inversion**, against thresholds worked out on paper, with the two
  functions shown to invert each other.
- **Rank detection** — three spreads built from two factors must report fewer than three
  bets; two identical spreads, one.
- **Sizing monotonicity** — doubling the estimated deviation at least halves the size, and
  no input produces a size that is negative, infinite, or not a number.
- **Dependency direction**, by parsing the syntax tree rather than grepping, because Step 1
  and Step 2 mention Step 3 in prose all over.

**The suite has been mutation-tested.** Twenty deliberate defects were introduced one at a
time — an uncertainty haircut applied upwards, a dropped edge requirement, leverage
dividing by the deviation instead of the variance, a kill switch reporting the last breach
instead of the first — and every one was caught. Two were only caught after a fixture was
rebuilt, because the originals could not tell the right answer from the wrong one. A suite
that has never been shown to fail is not evidence.

## Rules

- Never quote `(entry_z − exit_z) × sigma` as an expected payoff. Measure it with
  `outcomes.py` first; it has been wrong by 10× to 68× on every pair tested.
- Never take a threshold from a swept grid's best cell. The floor is the lowest cell that
  pays.
- Never use the modelled floor to trade. It loses money; use the measured one.
- Never size on gross returns. Use `--net`.
- Never size on the point estimate. `--confidence 0` is full Kelly on a mean this project
  has never had enough trades to establish.
- Never count positions as bets. Two spreads sharing a leg are one bet.
- Never charge 1.0 nights per bar outside crypto.
- Never report a result from a run whose window and financing rate are not on its logged
  row — that is how two rows of `backtests.csv` became irreproducible.
- Every run is a trial and every trial is logged. Step 4 needs an honest count.
- **Passing all three questions makes a pair worth validating, not worth trading.** Step 4
  is the only step that can say yes, and it is where a result like this is expected to die.

## Called from the screener

`screen.py --broker <profile>` runs these three questions on whatever survives its
statistical gates, and only on those — the cheap gates run on every pair, the replay on the
handful that got past them:

```bash
python screen.py -u equities --within-sector --broker equity
```

It delegates rather than reimplementing, and `verify_signal.py` enforces that by refusing
to find the sizing and threshold formulas copied into `screen.py`. A pair whose legs have no
entry in the cost profile is reported as unconfirmed and the screen carries on.

## What this has actually concluded

Nine pairs, nine rejections, on three independent tests each:

```
pair                prediction        threshold    size
XLP~XLB             fails 10.0x       z 1.50       0.00
SPY~DIA             fails 68.0x       none pays    0.00
EURUSD~GBPUSD       fails 20.2x       none pays    0.00
AUDUSD~NZDUSD       fails wrong sign  none pays    0.00
USDNOK~USDZAR       fails wrong sign  z 1.50       0.00
BTC-USDT~ETH-USDT   fails 12.8x       none pays    0.00
ALL~TRV             fails wrong sign  none pays    0.00
NUE~STLD            fails 12.0x       z 1.00       0.00
USDCHF~USDCAD (1m)  fails 20.0x       none pays    0.00
```

Sizing returns zero on every one, **including the three that made money**. That is the
layer working, not failing.

`NUE~STLD` — two steel makers, a genuinely shared input — is the closest this project has
come. It is the only pair where a threshold pays for itself, it nets +9,810 bps over thirty
years at that threshold, and its mean is +35.3 bps per trade. One standard error below that
mean is **-5.7**, so 103 trades do not establish it is positive, and the size is zero. The
cointegration behind it last held in 1996-2000.

Read that as the shape of the whole problem: a real relationship, a stable hedge ratio, a
large backtest number, and not enough evidence to put money on it.

## Sizing one relationship against sizing a book

This skill sizes **one** relationship from its own realised trades. Sizing a whole
cross-section at once is the **portfolio** skill, and the two meet at one function:
`growth_optimal_leverage(mu, sigma)` is `mu/sigma^2` either way. What differs is where
`mu` comes from — realised trade outcomes here, the fitted Ornstein-Uhlenbeck drift
`theta(mu - X)` there.

`portfolio.py` is no longer deferred. `STEP3.md` held it back because it "needs two
candidates to mean anything, and there are none"; the residual track replaced one pair with
160 concurrent signals and that reason expired.

Related: `statarb` finds candidates, `relationship` tests them, `tradingcosts` prices them,
`backtest` measures them, `portfolio` combines them into a book, `ic` measures how much
skill the signal being sized actually carries, `validation` decides whether any of it is
real, `marketdata` supplies the bars.

A size this skill justifies has not been validated. `validation` deflates the Sharpe behind
it for the search that found it: `NUE~STLD` goes from a probabilistic Sharpe of 80.5% to a
deflated 3.5% once charged for seventy-seven trials. Plan and evidence:
`development/statarb/plan/STEP3.md`, `worklog/2026-09-14-step3.md`,
`worklog/2026-09-14-crosscheck.md`, `worklog/2026-09-14-step3-audit.md` and
`worklog/2026-09-15-widen-and-link.md`.
