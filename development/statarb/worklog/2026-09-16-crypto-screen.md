# 2026-09-16 — crypto pair screen

## Subject

Search the crypto universe for a pair that survives the backtest gates. The instruction was
to keep screening crypto until at least one candidate survives, with one-to-one or
many-to-many constructions both allowed.

## Status

**Incomplete — stopped for the day partway through the hourly leg.** Daily and four-hour are
finished and both found nothing. Hourly data is 12 of 18 symbols downloaded; the screen has
not been run at that timeframe.

| Item | Status |
|---|---|
| Widen the crypto universe | Done — 18 coins, was 2 |
| Deepen daily history to 2017 | Done — BTC and ETH now 3,318 bars, were 2,081 |
| Cost entries for the new coins | Done — 8 added, all estimated |
| Daily screen | Done — no survivor |
| Four-hour download and screen | Done — no survivor |
| Hourly download | Partial — 12 of 18 symbols |
| Hourly screen | Not started |
| Many-to-many baskets | Not started |

## What was built

`crypto-majors` held two symbols, which is one pair. A universe of one pair cannot be
screened in any meaningful sense, so `CRYPTO_LIQUID` was added to
`development/marketdata/marketdata/instruments.py` alongside a `crypto-all` universe: 18
coins that have traded on Binance under an unchanged ticker since at least 2019.

Three deliberate omissions, recorded in the source because each is a trap rather than an
oversight. MATIC rebranded to POL in 2024, so a series under one ticker is two different
instruments spliced together — the same defect class as mixing `BTC-USDT` with `BTC-USD`.
LUNA and FTT both collapsed; a dead instrument cannot be traded forward no matter what its
backtest says, and including it would let survivorship work backwards.

The stored history was 2021 onward. Binance has daily bars from its 2017 launch, so the
daily series were extended: BTC and ETH from 2,081 bars to 3,318. All 18 daily series pass
`marketdata validate` cleanly, unlike the Yahoo forex series, so high and low prices are
usable here and not only closes.

The `binance.json` cost profile covered the original ten symbols. Eight were added — DOT,
ATOM, TRX, ETC, BCH, XLM, UNI and FIL — at 10 basis points commission per side and 3 basis
points per night to borrow the short leg, matching the existing entries. Every one is marked
estimated, so any report that uses them says so.

## What the screens found

Nothing. Both screens are worse than chance at the first gate.

| Timeframe | Pairs | Cointegrated | Noise alone gives | Survivors |
|---|---|---|---|---|
| 1d | 153 | 7 | about 8 | 0 |
| 4h | 153 | 6 | about 8 | 0 |

Finding fewer relationships than random data would produce is not a near miss. It means the
first gate carries no signal at all on this universe, and everything ranked below it is
noise being sorted.

One pair reached the out-of-sample gate at both timeframes, `XRP-USDT~ADA-USDT`, and failed
the same way twice: p of 0.025 on the screening window and 0.406 on the late reserved
window at daily, 0.035 and 0.413 at four-hour. The early window is worse still at 0.889 and
0.943. The relationship exists in the middle of the record and is absent at both ends.

That the same pair surfaces at two timeframes is not corroboration. Four-hour and daily bars
of the same two instruments over the same years are close to the same data sampled twice, so
a mid-sample artefact appears in both by construction. Two views of one artefact is one
observation.

## Why crypto is structurally hard for this screen

Every crypto instrument resolves to a single driver, `crypto-beta`, because everything in
the market moves with bitcoin. The `--require-link` gate exists to stop the screen pairing
instruments with nothing in common, and it was the gate that would have caught `XLP~XLB`.
Here it admits all 153 pairs, because they genuinely do share their one driver.

So the economic-link gate does no filtering in this asset class. The trial count carries the
whole burden of the correction instead, which is a weaker position to be in.

## The incident

The hourly download was moved to the background after ten minutes and exited with code 4.
That code is outside the documented set of 0, 1, 2 and 130, so it is not a reported
validation or usage failure; the likely cause is the harness terminating a long-running
background task, with Binance rate limiting as the alternative. This has not been diagnosed.

Twelve of the eighteen symbols completed and are intact. Writes merge per instrument, so a
symbol is either fully written or absent; there is no partial series to clean up.

Present at 1h, 2017 to 2026, roughly 53,000 to 79,500 bars each: BTC, ETH, BNB, XRP, ADA,
DOGE, LTC, LINK, SOL, AVAX, DOT, ATOM.

Missing at 1h: TRX, ETC, BCH, XLM, UNI, FIL.

## Resuming

1. Finish the hourly download for the six missing symbols. `--resume` is not the right flag
   here because the gap is at the start of the record, not the end; repeat the same command
   and the merge will fill it.
2. Screen at 1h with `--bars-per-night 0.041667`. The daily figure for crypto is 1.00 and
   there are 24 hourly bars in a crypto day.
3. If nothing survives, move to many-to-many. A basket construction is the part of the
   instruction not yet attempted, and it is the more defensible one in this market: one coin
   against a basket of its peers nets out the shared bitcoin beta, which is exactly the
   driver that makes every one-to-one crypto pair look related.

## Open from before, unchanged

1. Feed the bootstrap floor into `screen.py`. It still prints `N x level`; the measured floor
   on real equity data is a third higher. Both screens above report the arithmetic figure.
2. `relationship.py`, the Step 2 unifier.
3. Dukascopy bulk fetch, still not run.

## Also noted

Running the five verification suites back to back, `verify_signal.py` reported one failure,
`a negative leverage cap is refused`. Standalone it passes 189 of 189, four consecutive
times. Intermittent at roughly one run in five and not yet diagnosed; the suspicion is the
subprocess refusal check colliding with a log append while the other suites write, but that
is a guess. The machinery should not be called green until this is understood.
