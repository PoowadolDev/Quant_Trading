---
name: tradingcosts
description: >
  Record what a broker actually charges and decide whether a mean-reversion
  trade survives it. Covers the spread, commission and overnight swap of each
  leg, and the feasibility gate that compares a spread's expected move against
  the full cost of capturing it, financing included. Use whenever the user asks
  what a trade costs, what the spread or commission or swap is, whether an edge
  survives costs, how long a position can be held before financing eats it,
  what the break-even swap rate is, or to set up or compare broker cost
  profiles — including phrases like "how much does this cost to trade", "add my
  broker's spreads", "is this still profitable after costs", "what about swap",
  "carry cost", "rollover", "does it pay", or before any backtest or live
  sizing decision. Never invent a cost figure or hard-code basis points in a
  script while this skill applies; `costs.py` holds the numbers and
  `feasibility.py` applies them.
---

# Trading costs and the feasibility gate

Two scripts in `development/statarb/code`:

| Script | Answers |
|---|---|
| `costs.py` | what does the broker charge? |
| `feasibility.py` | does the expected move survive it? |

`feasibility.py` is the cheapest kill switch in the project. It takes minutes and can end a
candidate before a line of engine code is written.

## Working directory

```bash
cd development/statarb/code
```

`paths.py` resolves the store, the profiles and the logs, so the scripts also work when run
from anywhere by full path. Profiles live in `../costs/<broker>.json`, one file per broker.

## Why three cost terms, not one

Forex charges in three places, and for a mean-reversion trade the third usually decides the
outcome:

1. **Spread** — per leg, wider in the Asian session and around rollover. Crossing it once
   costs **half** the quoted spread, because the quote is the round trip between bid and ask.
2. **Commission** — per side, on raw-spread accounts.
3. **Swap** — quoted separately for long and short, charged **every night**, tripled on
   Wednesday to cover the weekend.

A spread held for a five to seven bar half-life pays swap five to seven times. On a
high-yield currency that term can exceed the whole expected move, which is exactly why the
pair study's cost figure is not the final word.

## Recording a broker

```bash
python costs.py add --broker ig --symbol USDZAR \
    --spread-pips 25 --commission-bps 0 \
    --swap-long -8.5 --swap-short 3.2 --swap-unit points-per-lot \
    --session-widening 1.8 --rollover-widening 3.0 --from-broker-sheet

python costs.py list                       # which brokers are on file
python costs.py show --broker ig           # one table per symbol
python costs.py remove --broker ig --symbol USDZAR
```

### `add`

| Flag | Default | Meaning |
|---|---|---|
| `--broker` | required | profile name; becomes `costs/<broker>.json` |
| `--symbol` | required | canonical symbol, as in the store |
| `-a, --asset-class` | `forex` | `forex`, `crypto` or `commodity` |
| `--spread-pips` | required | quoted bid-ask spread in pips; **basis points** for non-forex |
| `--commission-bps` | `0` | per side, on notional |
| `--swap-long` | `0` | financing on a long position; **negative is a debit** |
| `--swap-short` | `0` | financing on a short position |
| `--swap-unit` | `points-per-lot` | or `percent-per-annum`, or `bps-per-night` |
| `--session-widening` | `1.0` | spread multiple in thin hours |
| `--rollover-widening` | `1.0` | spread multiple around 17:00 New York |
| `--price` | from the store | quote level used for the conversions |
| `--from-broker-sheet` | off | these numbers were read off the contract specification |

**`--from-broker-sheet` is the flag that matters.** Without it the entry is recorded as an
estimate, and every downstream report prints `ESTIMATED` or `COST PROFILE IS ESTIMATED`.
That default is deliberate: a guessed cost that looks authoritative is worse than no cost
at all. Only pass the flag for numbers actually read from the broker.

### `show`

```bash
python costs.py show --broker ig -s USDNOK,USDZAR --directions long,short --holding-bars 7
```

| Flag | Default | Meaning |
|---|---|---|
| `-s, --symbols` | all on file | legs to cost, comma separated |
| `--directions` | `long,short` | one value, or one per symbol in the same order |
| `--holding-bars` | `1` | how long the position is held |
| `--bars-per-night` | `1.0` | `1.0` for daily bars, `1/24` for hourly |
| `--json` | off | machine-readable totals |

```
symbol        spread  commission  carry long  carry short  source
USDNOK         1.62b       0.00b      -0.67b       +0.12b  estimated
USDZAR         3.73b       0.00b      -2.17b       +0.75b  estimated

held 7 bars = 7.0 nights, long USDNOK and short USDZAR
  transaction      10.69 bps   both legs, in and out
  carry            -0.54 bps   financing over the hold
  total            10.15 bps
  NOTE: at least one leg is an estimate, not a broker sheet
```

Signs follow the broker's own convention: **negative carry is a debit, positive is a
credit**, and a credit reduces the total bill.

## The feasibility gate

```bash
python feasibility.py -s USDNOK,USDZAR --broker ig
python feasibility.py -s USDNOK,USDZAR --broker ig --holding-bars 10 --sweep-holding 1,20
```

It refits the pair itself, so the expected move always matches the relationship being
costed. The arithmetic:

```
expected move    = (entry_z - exit_z) * sigma_eq
transaction cost = spread + commission, both legs, in and out
carry cost       = nightly swap * nights held
edge             = expected move / (transaction + carry)
```

The pair study compares the move against **transaction cost only**. This script adds the
financing, which is the term that can reverse the answer.

| Flag | Default | Meaning |
|---|---|---|
| `-s, --symbols` | required | the two legs |
| `-a`, `-t`, `--source`, `--start`, `--end` | | selection, as in the pair study |
| `--price`, `--hedge`, `--split` | `log`, `ols`, `0.70` | must match the pair study, or the move is not the one measured |
| `--entry-z`, `--exit-z` | `2.0`, `0.5` | the move being captured |
| `--holding-bars` | the fitted half-life | nights held |
| `--min-edge` | `2.0` | at or above this is ALIVE |
| `--marginal-edge` | `1.0` | between the two is MARGINAL, below is DEAD |
| `--sweep-holding LO,HI` | off | print the edge across a range of holding periods |
| `--broker`, `--costs-dir` | required | which profile to apply |
| `--bars-per-night` | `1.0` | bar length in nights |
| `--json`, `-q`, `-v` | | output control |

### Reading it

```
long spread   long USDNOK, short USDZAR
  transaction    10.69 bps
  carry          -0.38 bps over 4.9 nights
  total          10.31 bps
  edge           47.76x   ALIVE
  break-even    +47.90 bps per night of financing is the most this move can carry
  headroom      +47.98 bps per night before the edge falls to 2x, after what this
                          direction already pays
```

**Both directions are always reported, because they are not priced the same.** Short ZAR
pays financing; long ZAR collects it. The same spread can be alive one way and dead the
other.

- **break-even** is a property of the move and the transaction cost, so it is identical in
  both directions.
- **headroom** subtracts what that direction already pays, so it differs. Read this one.

Exit code `0` means ALIVE in at least one direction, `3` means dead both ways.

## Rules

- Never invent a cost number. If it is not on a broker sheet, record it without
  `--from-broker-sheet` and let every report say ESTIMATED.
- Never hard-code basis points in analysis code. Read the profile.
- Never lower a cost, or shorten the holding period, to make something pass. If a
  parameter is changed, say so and log it as a trial.
- Never quote an edge from a spread that failed its stationarity gates — see the `statarb`
  skill on gate ordering.
- A large edge multiple on a slow spread means the spread is **volatile**, not that the
  trade is good. The gate ignores holding period and drawdown.
- DEAD in both directions ends the candidate. Go back to the shortlist rather than
  building an engine for a trade that cannot pay.

## What this does not cover

Slippage, partial fills, market impact, and the widening multiples (`--session-widening`,
`--rollover-widening`) are recorded but not yet applied by the backtest — it charges the
base spread. Say so when a result depends on them.

Related: `statarb` finds candidates, `relationship` proves whether they are really
cointegrated, `backtest` measures what one would have earned, `sizing` decides whether any
entry threshold pays for its financing and how large a position is justified. Plan and
status: `development/statarb/plan/STEP1.md`.

**A daily bar is not a night.** `costs.nights_per_bar(asset_class, timeframe)` is the one
definition: 1.45 for equities and their funds, 1.40 for forex, 1.00 only for crypto.
Charging 1.0 on a daily equity bar understates financing by 45%.
