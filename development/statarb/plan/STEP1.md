# Step 1 — Cost model and backtest engine, split into runnable pieces

> **Status: all five built and verified.** Summary with diagrams:
> [../worklog/step1-summary.html](../worklog/step1-summary.html).
>
> The engine works. The candidate does not: `USDNOK~USDZAR` backtests at
> **-267 bps**, and its gross result is already negative before any cost,
> so there is no edge for a better cost profile to rescue. Costs are still
> a placeholder profile — 1a needs real broker numbers to be final.
>
> The module is `strategy.py`. It must not be called `signal.py`: a file of that
> name beside a script shadows the standard library module of the same name, and
> the first thing to break is `subprocess`, several imports away.
>
> **Audited twice.** The first pass found five defects; a later pass, after the health
> gate was wired in, found none. Details below.
>
> **Audited 2026-09-13.** Five more defects found and fixed, all in trade
> accounting rather than in the totals: a long-to-short flip was booked as one
> continuous trade, a position still open at the last bar was left unattributed,
> a fill delay queued the same order on every bar, guessed costs were recorded as
> broker sheets by default, and a spread crossing outside forex was charged at
> full width instead of half. The verification suite went from 39 checks to 77,
> and the per-trade table now reconciles with the equity curve to the basis point.

Step 1 in `PLAN.md` is one line: "cost model plus backtest engine, built together, because
a backtest without costs is decoration." That is correct but too big to sit down and write.
This file splits it into five scripts, each run by hand with parameters typed on the command
line, in the same style as `pair_report.py`.

The order is deliberate. **1a and 1b can kill the candidate in an afternoon**, before a line
of engine code exists. Do not skip ahead to the fun part.

| Sub-step | Script | Kills the idea? | State |
|---|---|---|---|
| 1a | `costs.py` — record what the broker actually charges | — | ✅ four profiles on file, all estimated |
| 1b | `feasibility.py` — does the edge survive the carry? | **yes** | ✅ |
| 1c | `strategy.py` — the decision function, shared with live | — | ✅ |
| 1d | `backtest.py` — replay bars, apply costs, report | — | ✅ plus `--health-gate` |
| 1e | `verify_backtest.py` — prove the engine is not lying | — | ✅ 87 checks green |

Cost profiles recorded so far, every one marked estimated because none came off a broker
contract sheet:

| Profile | Covers | Shape of the bill |
|---|---|---|
| `fxretail` | 15 forex pairs | spread in pips, financing as a 1%/yr markup both ways |
| `binance` | 10 crypto pairs | 10 bps taker per fill, 3 bps a night to borrow the short leg |
| `etf` | SPY, DIA, QQQ, IWM | 1 bps spread, margin at 6%/yr long, 0.5%/yr borrow short |
| `demo` | USDNOK, USDZAR | the first placeholder, kept for comparison |

**The candidate this file was written for is dead.** `USDNOK ~ USDZAR` backtests at −285
bps with gross already negative, and Step 2 later rejected it: cointegrated at p = 0.007
on the full sample and p = 0.410 on the held-out tail. Every other candidate tried since
has failed too — see the search table in `PLAN.md`.

What survived is the machinery. `backtest.py` now also takes `--health-gate`, which hands
control of exposure to the Step 2 monitor: flat while broken, no new entries while
degraded, and it can only ever reduce exposure. Measured across twelve pairs the gate
improved six of them with a median change of −11 bps, which is not evidence that it helps;
its value so far is diagnostic rather than as a filter.

---

## 1a — Cost model

**What it is.** A place to type in what the broker charges, once, so that every later step
reads the same numbers instead of a guess buried in a script.

Forex needs three terms, and the third is the one that decides this trade:

1. **Spread**, per leg, wider in the Asian session and at rollover
2. **Commission**, per side, if the account is raw-spread
3. **Swap**, quoted separately for long and short, charged every night, tripled on
   Wednesday for the weekend

A spread position held for a 5 to 7 bar half-life pays swap five to seven times. ZAR has a
large interest-rate differential, so this term can be larger than the entire expected move.

**Command shape**

```bash
cd development/statarb/code
python costs.py add --broker ig --symbol USDZAR \
    --spread-pips 25 --commission-bps 0 \
    --swap-long -8.5 --swap-short 3.2 --swap-unit points-per-lot \
    --session-widening 1.8 --rollover-widening 3.0
python costs.py show --broker ig
python costs.py show --broker ig --symbol USDZAR --holding-bars 7
```

**Output.** A table of cost in basis points: entry, exit, and carry per night, with the
total for a stated holding period. Saved to `costs/<broker>.json` so the number is recorded
rather than retyped, and so two brokers can be compared later.

**Parameters, in the project's usual three groups**

- *given by reality* — every number above comes off the broker's contract sheet, not from
  judgement. If a value is a guess, mark it: `--estimated`.
- *structure* — `--swap-unit` (points per lot, percent per annum, or basis points),
  `--weekend-rule` (triple Wednesday is the usual convention)
- *searched* — `--holding-bars`, because the answer depends on how long the trade is held

**Done when** `USDNOK` and `USDZAR` both have a real cost profile from a named broker, and
`costs.py show` prints a round-trip figure in basis points.

**Blocked on you.** These numbers come from a broker account. Until then the scripts can run
on a clearly-labelled placeholder profile, and every downstream report must say the profile
is a placeholder.

---

## 1b — Feasibility gate

**What it is.** The shortest possible answer to "is this trade alive?". It takes the Step 0
fit and the 1a cost profile and compares the expected move against the *total* cost of
capturing it, financing included.

The arithmetic that matters:

```
expected move      = (entry_z - exit_z) * sigma_eq        already 492 bps for this pair
transaction cost   = spread + commission, both legs, in and out
carry cost         = nightly swap * expected holding nights
edge               = expected move / (transaction + carry)
```

Step 0 only ever compared the move against the transaction cost, and found 12x at 40 basis
points. Adding carry can reverse that completely, and the whole point of this sub-step is to
find out before building anything.

**Command shape**

```bash
python feasibility.py -s USDNOK,USDZAR --broker ig --trial 23 \
    --entry-z 2.0 --exit-z 0.5 --holding-bars 7 --direction both
```

`--direction` matters: short ZAR and long ZAR pay different swap, so the same spread can be
profitable in one direction and dead in the other. Report both.

**Output.** One screen, and a row in `logs/trials.csv`. A verdict of ALIVE, MARGINAL or DEAD with
the numbers that produced it, plus the break-even nightly swap — the swap rate at which the
edge reaches 1.0 — which tells you how much room there is.

**Done when** `USDNOK~USDZAR` has a verdict in each direction. If it is DEAD both ways, stop
and return to Step 0's shortlist rather than building an engine for a trade that cannot pay.

---

## 1c — Strategy module (`strategy.py`)

**What it is.** A pure function: bars in, target position out. No file reading, no order
placing, no printing. It exists as its own module because of the one hard constraint in the
plan — the backtest must replay bars through *the exact code that runs live*. Two code paths
means the backtest measures nothing.

```python
def target_position(history: pd.DataFrame, state: SignalState,
                    params: SignalParams) -> Target:
    """Positions for both legs at this bar, given only bars up to and including it."""
```

The signature is the design. `history` ends at the current bar, so look-ahead is impossible
by construction rather than by discipline. `state` carries what the strategy remembers —
current position, bars held, the hedge ratio in force. `params` is everything typed on the
command line.

**Parameters**

- *structure* — `--hedge-source` (static from the Step 0 fit, or rolling), `--price log|raw`
- *searched* — `--entry-z`, `--exit-z`, `--stop-z`, `--max-holding-bars`,
  `--rehedge-every`, `--min-bars-between-trades`
- *given by reality* — the cost profile, so a cost-aware entry threshold can be computed
  instead of assumed

`--stop-z` and `--max-holding-bars` are new and both are risk controls, not optimisations:
the first exits when the spread has gone so far that the relationship is probably broken,
the second refuses to hold a mean-reversion trade forever waiting to be proved right.

**Done when** the module runs offline over the stored panel and produces a position series
in which every value is explainable from the bar that produced it.

---

## 1d — Backtest engine

**What it is.** The loop that walks bars forward, calls `target_position`, turns the change
in target into fills, charges the 1a costs, and accumulates the result.

Design points that are not negotiable:

- **Decisions on bar close, fills at the next bar** — deciding and filling on the same close
  is the most common way a backtest invents profit that does not exist.
- **Both legs are one trade.** Filling one leg and not the other leaves a directional
  position. The engine must model the possibility and the report must count it.
- **Carry charged per night held**, using the direction-specific swap.
- **Yahoo forex high and low are unusable** — 1 to 3 percent of daily bars have an open or
  close outside their own range. Close-only fills for now; any stop-loss simulation needs a
  broker feed first, and `--stop-z` must therefore be evaluated on closes, not intrabar.

**Command shape**

```bash
python backtest.py -s USDNOK,USDZAR --broker ig \
    --start 2019-01-01 --split 0.70 \
    --entry-z 2.0 --exit-z 0.5 --stop-z 4.0 --max-holding-bars 20 \
    --capital 10000 --risk-per-trade 0.01 \
    --fill-at next-close --dry-run
```

**Output.** An HTML report in the same shape as the pair study: verdict banner, parameters
used, a results table, then charts. Trades table, equity curve with the in-sample and
out-of-sample divider, drawdown, and the distribution of holding periods. Plus a row in
`logs/trials.csv`, because a backtest run is a trial like any other.

The headline numbers should be gross PnL, cost paid, carry paid and net PnL as four separate
lines. If cost and carry are not shown next to the profit they came out of, the report is
decoration again.

**Done when** a backtest of the candidate produces a trade list and an equity curve, with
every number traceable to a parameter.

---

## 1e — Engine verification

**What it is.** The same treatment `verify_pair_report.py` gives the pair study. An engine
that silently overstates returns is worse than no engine, and the only defence is a set of
tests whose answers are known before running them.

The checks that matter:

- **A known-losing strategy loses by about the cost it should.** Trade a pure random signal
  and the net result must land near minus the cost of the trades it made. This is the single
  most informative test in the whole file.
- **Zero cost and perfect foresight** produce a known upper bound; anything above it is a
  bug.
- **Shifting the signal one bar later must reduce the result.** If it does not, the engine is
  reading the future somewhere.
- **Accounting identity** — the sum of individual trade results plus carry equals the change
  in equity, to the cent.
- **Carry scales with nights held.** Doubling the holding period doubles the financing.
- **A flat strategy pays nothing** and ends exactly where it started.

**Done when** the suite runs green, and the known-losing strategy's loss matches its cost
within a few percent. The plan's own success criterion for Step 1 is exactly this.

---

## What is deliberately not here

| Thing | Why not |
|---|---|
| Parameter optimisation | Step 4 counts trials; optimising before the cost model is honest is how a backtest gets fitted to nothing |
| Kalman hedge ratio | Step 2. The static ratio from Step 0 is the baseline to beat |
| Position sizing from growth rate | Step 3, and it needs a working backtest first |
| Live broker connection | Step 5 |
| A second candidate pair | One is enough to build the machinery; the shortlist is in `PLAN.md` |

## Order of work

1. Get broker numbers, fill in `costs.py` — blocked on a broker account
2. Run `feasibility.py`; if DEAD both directions, stop and pick another candidate
3. Write `strategy.py` against the Step 0 fit
4. Write `backtest.py` around it
5. Write `verify_backtest.py` and do not trust a single backtest number until it passes
