# 2026-09-15 — A wider universe, an economic-link gate, and a hole in yesterday's gate

## Subject

Three items from the plan: a deeper intraday source, an economic-link requirement outside
equities, and a wider equity universe. Two finished; the third is built but not fetched.
Running the result found a defect in the holdout gate added the day before.

## Status

| Item | Status |
|---|---|
| Dukascopy feed — decoding verified, bulk fetch not run | ⚠️ built, download not approved |
| Economic-link gate, all asset classes | ✅ built, on by default |
| Equity universe 76 → 252 symbols, 14 → 29 sectors | ✅ built and downloaded |
| Duplicate-sector bug in `EQUITY_SECTOR_OF` | ✅ found and fixed |
| Six delisted names removed | ✅ done |
| **Directional defect in the holdout gate** | ✅ found and fixed |
| Verification | ✅ 446 checks across four suites |

## 1. Dukascopy — built, not fetched

Yahoo serves seven days of one-minute forex and no volume at all. The only universe ever to
reach the replay did so on 2,817 bars of a single week, which says something about the
mechanism and nothing about the pair.

`DukascopyFeed` is written and registered: one LZMA-compressed file per instrument per
hour, twenty bytes a record — `>IIIff`, being milliseconds into the hour, ask and bid in
points, and ask and bid volume. Bars are built from the **mid**, so the OHLC is a real
range rather than one side of the book, and volume is the tick count, which is genuine
activity rather than the zeros Yahoo returns.

Decoding is verified against a real file: EURUSD, 2 January 2024, 10:00 — 5,626 ticks,
first mid 1.10150, spread 0.1 pip. Those are the right numbers.

**The bulk download was not run.** The host rate-limits hard: eight concurrent workers earn
503s within a minute, and sequential fetching with a pooled session runs at about 2.65
seconds a file. One symbol-month is roughly 32 minutes of network. That is the call that
was stopped, and it is left as a decision rather than a default.

Two things were needed to make it work at all and are in the code: a single pooled
`requests.Session` per download — without connection reuse this host drops about a third of
requests on connect — and retrying 429 and 5xx *inside* the retried call, because
`raise_for_status` outside it turns a transient refusal into a failed download.

## 2. An economic-link gate

Nothing in the pipeline recorded what an instrument is a claim on, so nothing could say
that consumer staples and materials have no common cash flow, input, customer or regulator.
`XLP~XLB` was this project's best result for a day on exactly that pairing.

`driver_groups(symbol, asset_class)` now answers it:

| Asset class | Drivers |
|---|---|
| equity | its sector |
| index fund | what it tracks — `XLF` is banks and insurers, `QQQ` is broad plus semis and software |
| forex | both currency legs, so `EURUSD` and `GBPUSD` share USD |
| commodity | oil, gas, precious, industrial metal, grain |
| crypto | one driver. Everything in that market moves with bitcoin, and pretending otherwise is how a screen finds dozens of relationships inside a single beta |

An unknown instrument returns an empty set, which is treated as "no link" rather than
"links to everything" — silence is not evidence of a relationship.

`screen.py --require-link` is **on by default**. On sector ETFs it cuts 105 pairs to 4; on
forex, 66 to 36; on index funds, 6 to 3. Every test avoided is a false positive avoided,
and the screen prints how many it skipped and names the first few.

## 3. A wider equity universe

76 symbols across 14 sectors became **252 across 29**, adding utilities, REITs,
homebuilders, miners, chemicals, defence, machinery, media, hotels, restaurants, apparel,
exchanges, asset managers, health providers, truckers and waste, and deepening the sectors
that already existed.

Within-sector pairing keeps the cost proportional: **1,192 within-sector pairs against
31,626 across-sector.**

Two defects turned up while doing it.

**A symbol could sit in two sectors.** `MSFT` was in both `software` and a `majors_tech`
grouping, and `EQUITY_SECTOR_OF` was a dict comprehension that silently kept whichever came
last — so a symbol's sector depended on the order the sectors happened to be written in. It
now raises on a duplicate. `majors_tech` is gone for a second reason: "large technology
company" is a size, not a shared driver, and `AAPL` against `AMZN` is precisely the kind of
pairing this work exists to prevent.

**Six names had no data.** ANSS, HES, K, MRO, SKX and X were all acquired between 2024 and
2025, so the feed serves nothing and any pair holding one would have been silently
truncated to the shorter leg. Removed: a universe is a list of things that can be traded
now.

## 4. The defect this found

The widened screen produced one pair that cleared the reserved windows: **`NUE~STLD`**,
Nucor against Steel Dynamics. Two steel makers — same scrap input, same customers, same
regulator. A real economic link, unlike anything this project had found before.

```
p 0.0055   p_oos 0.023   p_early 0.001   p_late 0.648   beta +0.695   swing 1.65   net 18%
```

The hedge ratio is the most stable this project has measured. Backtested over thirty years
at the measured entry floor it nets **+9,810 bps**, the largest figure yet produced.

It is still not a candidate, and the reason matters:

```
era          beta    eg_p   cointegrated
1996-2000  +0.483   0.003        YES
2001-2005  +0.792   0.598         no
2006-2010  +0.483   0.606         no
2011-2015  +0.500   0.649         no
2016-2020  +0.589   0.428         no
2021-2026  +0.602   0.284         no
```

**The relationship existed in the 1990s and has not existed since 2001.** The +9,810 comes
with an out-of-sample result of −504, and the sizing layer returns zero: mean +35.3 bps per
trade across 103 trades, one standard error below is −5.7.

And yesterday's holdout gate **passed it**, because the rule was "at least one reserved
window must also reject" and `p_early` was 0.001. A relationship that died in 2001 is not
tradeable in 2026, whatever the oldest quarter of the record says.

The rule is now **the late reserved window decides** — the most recent data, which the
screen never saw, because that is the only window answering the question a trader is
actually asking. `--require-early` demands the older one as well, which is stronger
evidence, and the early p-value is reported either way.

That is the second time in two days that a gate written to catch a specific failure turned
out to have a direction it did not check. Both were found by running the thing, not by
reading it.

## The search, after all of it

| universe | pairs after link gate | cointegrated | noise gives | still there now | noise gives | survivors |
|---|---|---|---|---|---|---|
| equities, within sector | 1,192 | 144 | 59 | 1 | 5.7 | 0 |
| forex | 36 | 8 | 2 | 0 | 0.2 | 0 |
| sector ETFs | 4 | 1 | 0.3 | 0 | 0.03 | 0 |
| index ETFs | 3 | 0 | 0.2 | 0 | 0.02 | 0 |

Read the equity row carefully. 144 cointegrated against 59 by chance looks like a real
excess — but **one** pair is still there in the most recent window, where chance alone would
give **5.7**. The screening-window excess is what you get from testing the same instruments
in overlapping windows; the forward-looking gate finds fewer than noise.

That is the clearest statement of the project's position so far. It is not that the search
has been too narrow. It is that relationships of this kind, in these venues, do not persist
into the window you would have to trade them in.

## Verification

446 checks, up from 430. New: driver groups for every asset class including the
unknown-instrument and malformed-symbol cases, the one-sector-per-symbol rule, and the
directional holdout — including a fixture built from `NUE~STLD`'s actual numbers, so the
rule that let it through cannot come back.

## Next

1. **Decide on Dukascopy.** The feed works. Fetching a useful window is hours of network,
   and worth it only if deep intraday is the direction to take. It is currently the only
   untested direction left.
2. **Ask whether the answer is no.** Roughly 1,300 pairs have now been screened with a
   forward-looking gate and an economic-link requirement, and nothing persists. That is
   evidence about the strategy class, not only about the search.
