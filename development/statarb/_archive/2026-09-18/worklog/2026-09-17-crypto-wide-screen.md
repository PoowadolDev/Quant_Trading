# 2026-09-17 — Widened crypto screen: six survivors, and why they are not candidates

## Subject

Search crypto for surviving pairs using the names in `data/stats_list.csv`, and build a
per-pair research log carrying the parameters that produced each verdict, so a later
optimisation has a surface to read rather than a screen to re-run.

## Status

**Six pairs survive `screen.py`. None survives `portfolio.py`. The screen's decisive gate
found exactly what chance gives.**

| Item | Status |
|---|---|
| Crypto universe widened | ✅ 19 → 243 series at 1d, 220 downloaded from Binance |
| Screened | ✅ 68 names with 2,000+ bars, 2,278 pairs, screen #25 |
| Survivors of the screen | ✅ 6 |
| Survivors of the allocator | ❌ 0 of 6 |
| `logs/pair_research.csv` built | ✅ 2,431 rows, 45 columns, 20 of them parameters |
| Suites after the `screen.py` change | ✅ 123 + 72 green |

## What was run

The store held 18 USDT names at 1d against 493 in `stats_list.csv`. 220 more were fetched
alphabetically — not hand-picked, so the history filter does the selecting rather than
recognition of a ticker — giving 243 series. 68 of them carry 2,000+ bars, which is the
universe screened.

```
custom  68 instruments  1d  2278 pairs

  cointegrated           400   noise alone would give about 114
  and out of sample       51
  and still there now     11   noise would give about 11.1
  and a stable ratio       9
  and a usable hedge       6
  and reverting in time    6   <- survivors
```

## The finding

**The population excess is real and the persistence is not.**

`multiple_testing.py` puts 400 rejections against 113.9 expected with a standard deviation
of 10.4 — a 27-sigma excess, and 209 pairs survive Benjamini-Hochberg at a 10% false
discovery rate. There is genuinely more cointegration in crypto than chance produces.

All of it is historical. The line that matters is **`still there now: 11, noise would give
11.1`**. The gate asking whether the relationship exists in the window it would have to be
traded in found exactly the chance rate. The six survivors are a subset of eleven pairs that
are, as a group, indistinguishable from noise.

This is the same shape as the SPX equity screen of the same day, where early-window and
late-window cointegration were independent (5 observed against 5.9 expected). Two different
asset classes, the same answer: cointegration is abundant and does not persist.

## The six, and what the allocator says

| pair | p | p_late | half-life | net | screen |
|---|---|---|---|---|---|
| `BAND-USDT~FIL-USDT` | 0.0068 | 0.000 | 16 | 27% | survived |
| `ANKR-USDT~FIL-USDT` | 0.0111 | 0.000 | 15 | 10% | survived |
| `BAND-USDT~IOTA-USDT` | 0.0125 | 0.012 | 26 | 7% | survived |
| `ARPA-USDT~GRT-USDT` | 0.0237 | 0.001 | 17 | 27% | survived |
| `ACM-USDT~ASR-USDT` | 0.0346 | 0.041 | 26 | 3% | survived |
| `FIL-USDT~IOST-USDT` | 0.0396 | 0.000 | 27 | 5% | survived |

Run as a book through `portfolio.py --book`, at two window lengths:

| signal window | explosive | unidentified | held |
|---|---|---|---|
| 120 bars | 1 | 5 | **0** |
| 250 bars | 3 | 3 | **0** |

`unidentified` means the OU fit reported a half-life but the spread's level cannot reject a
unit root on the recent window, so the fitted `theta` is indistinguishable from what
small-sample bias produces on a random walk. `ARPA-USDT~GRT-USDT` is separately refused at
40% net exposure against the 35% cap.

The two verdicts are not in conflict. The screen tests Engle-Granger on a ~361-bar late
window with the hedge ratio refitted inside the test; the allocator applies a plain
unit-root test to the rolling-refit spread the strategy would actually have held, over the
trailing 120 to 250 bars. A relationship can clear the first and fail the second, and when
it does, the thing that fails is the one closer to what would be traded.

`FIL-USDT` appears in three of the six and `BAND-USDT` in two, yet the six contain 4.9
independent bets by the participation ratio — less clustered than the shared legs suggest.

## Stage 15-17 — the backtest, which was skipped on the first pass

**It was skipped because eight of the nine symbols had no cost profile, and that was not
reported at the time.** The omission, not the blockage, was the error: a stage that cannot
run has to say so. `costs.py add` now carries estimated profiles for all eight, on the same
convention as the existing crypto entries — 1 bp spread, 10 bps commission per side, -3 bps
per night to borrow the short leg — every one flagged `estimated`.

| pair | trades | gross | cost | carry | net | out of sample | Sharpe |
|---|---|---|---|---|---|---|---|
| `FIL-USDT~IOST-USDT` | 24 | +14,704 | -552 | -388 | **+13,765** | +13,257 | 0.74 |
| `BAND-USDT~FIL-USDT` | 24 | +10,955 | -546 | -459 | **+9,951** | +3,299 | 0.62 |
| `ACM-USDT~ASR-USDT` | 33 | +4,349 | -693 | -472 | +3,185 | +500 | 0.21 |
| `BAND-USDT~IOTA-USDT` | 38 | +3,126 | -798 | -791 | +1,537 | +2,852 | 0.06 |
| `ANKR-USDT~FIL-USDT` | 28 | +2,566 | -637 | -504 | +1,425 | +1,740 | 0.07 |
| `ARPA-USDT~GRT-USDT` | 21 | -1,820 | -441 | -393 | -2,654 | +3,045 | -0.15 |

Five of six are net positive and the top two clear the mean/standard-error bar:
`FIL~IOST` at +2.17, `BAND~FIL` at +2.41. On their own these are the best backtests this
project has produced.

**And the spread is the input they are least robust to.** 1 bp is BTC's spread, and these
are small-cap alts — `ANKR-USDT` trades near $0.0045, where one tick is a large fraction of
a basis point. The figures above therefore understate cost in the direction that flatters.

## Stage 20 — deflation, which is what settles it

Charged the 2,278 pairs of screen #25:

| pair | Sharpe | probabilistic | benchmark (best of 2,278 on noise) | **deflated** |
|---|---|---|---|---|
| `FIL-USDT~IOST-USDT` | 0.443 | 100.0% | 0.687 | **1.7%** |
| `BAND-USDT~FIL-USDT` | 0.492 | 97.4% | 0.456 | **55.7%** |

`FIL~IOST` reads as certain on its own and collapses to 1.7% once the search is charged: the
best of 2,278 trials reaches 0.687 on noise alone and this reached 0.443. Neither survives.

**Four independent gates, one answer.** The late-window gate found chance (11 against 11.1);
the allocator holds none of the six; the deflated Sharpe rejects both leaders; and the one
pair the backtest liked least also has the widest true spread uncertainty. Nothing here
contradicts anything else.

## `logs/pair_research.csv`

One row per pair tested, appended across runs, carrying **both the result and every gate
value that produced it**. 2,431 rows and 45 columns after two screens.

Neither existing file could answer "which threshold would have changed this pair's
verdict". `screen.py --dump` writes per-pair results with no record of the gates in force;
`logs/screens.csv` writes the gates but only per-screen aggregates. Joining them after the
fact is guesswork once a default has moved.

| block | columns |
|---|---|
| identity | 12 — `run`, `run_utc`, `universe`, `asset_class`, `timeframe`, `start`, `end`, `pair`, `a`, `b`, `sector`, `bars` |
| result | 13 — the four p-values, three betas, `beta_swing`, `hedge_ok`, two half-lives, `net_exposure`, **`survived`** |
| parameter | 20 — `price`, `lags`, `split`, `level`, `holdout`, `min_tail`, `min_abs_beta`, `max_negative_share`, `max_net_exposure`, `min_half_life`, `max_half_life`, `max_beta_swing`, `min_screen_bars`, `require_oos`, `require_link`, `within_sector`, `require_early`, `broker`, `bars_per_night`, `max_overstatement` |

`survived` is recorded per pair rather than only counted, which is what makes the file
labelled data instead of an archive. `run` joins back to `logs/screens.csv`.

**The warning that belongs with it.** This file makes parameter sweeping easy, and easy is
the danger. Every distinct parameter set is a trial and the deflation benchmark grows with
the logarithm of the count. It is for understanding which gate bound a result, not for
hunting the cell where something passes.

## Trials charged

2,278 pairs in screen #25 and 153 in #24. The project total rises from 4,009 to **6,440** —
a 61% increase in one session. Every future candidate, from either track, is now harder to
establish. That was the price of widening the universe and it is recorded rather than
absorbed quietly.

## What this opens

Crypto now has 243 series where `RESIDUAL.md` §3 recorded 18 and ruled the market out of the
residual method for being too narrow. At 68 names with 2,000+ bars the factor model becomes
estimable, and — unlike the pair screen — it requires **no pair selection at all**, so it
adds no combinatorial trial count. That is the cheaper next question, and it is the one with
measured evidence behind it: Stage 0 and Stage 1 both passed on equities.

## Next

Run `residual.py` on the crypto panel. The kill criterion is unchanged: if the residual does
not reject a unit root more than a shuffled null, crypto is finished as a residual market
too, and the answer costs one run.
