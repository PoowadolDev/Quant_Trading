# 2026-09-14 — Screening, and a hole in my own gate

## Subject

Build the screener the research needed, widen the search to equities, calibrate the health
threshold, and stop at the edge of Step 3.

## Status

**Done. Step 3 not started, as agreed.**

| Item | Status |
|---|---|
| `screen.py` — universe in, every pair, every gate, ranked, logged | ✅ built |
| Equity asset class, 76 listings across 14 sectors | ✅ added |
| Equity, sector-ETF, forex, index, crypto and commodity screens | ✅ run and logged |
| Net-exposure gate — the hole found in `hedge.py` | ✅ fixed |
| `--min-healthy-share` calibration | ✅ lowered 0.40 → 0.10, provisional |
| Verification | ✅ 223 checks green across three suites |
| Step 3 | ⏸ paused |

## What was found

`screen.py` replaces eight throwaway sweep scripts written across this session, none of
them reproducible afterwards, whose results were reported anyway. Screens are now logged
runs in `logs/screens.csv`, each printing survivors next to the number chance alone would
produce.

| Universe | Pairs | Cointegrated | Noise would give | Survivors |
|---|---|---|---|---|
| equities, within sector | 205 | 20 | 10 | 1 |
| sector ETFs | 105 | 14 | 5 | 1 |
| forex | 66 | 12 | 3 | 1 |
| index ETFs | 6 | 1 | 0.3 | 1 |
| crypto | 1 | 0 | 0.1 | 0 |
| commodities | 6 | 0 | 0.3 | 0 |

## The hole

`AMGN~LLY` screened as the best result in the project — net +3358, out of sample +2196,
Sharpe 0.59, beating its control by a wide margin. Its hedge ratio was +0.165, which
cleared the `--min-abs-beta 0.10` floor.

A ratio of 0.165 leaves a position that is **72% net long**. The floor of 0.10 admits 82%.
The gate was measuring the wrong thing: the sign of the ratio catches a leg on the wrong
side, but nothing was checking whether the second leg was large enough to hedge anything.

Added `--max-net-exposure`, defaulting to 0.35 of gross. `AMGN~LLY` is now rejected, and
the remaining survivors sit at 7% to 30% net.

## Health calibration

Measured against what the four candidates actually earned:

| Pair | Healthy share | Net | Out of sample |
|---|---|---|---|
| `XLP~XLB` | 18% | +1572 | +751 |
| `ALL~TRV` | 17% | +215 | +1593 |
| `SPY~DIA` | 3% | −500 | −106 |
| `EURUSD~GBPUSD` | 2% | −288 | +207 |

The old floor of 0.40 rejected all four, which makes it useless as a discriminator: a gate
that rejects everything ranks nothing. Lowered to 0.10, which separates the two that made
money from the two that did not.

**Four points calibrate nothing.** The correlation is +0.82 and means little at that sample
size. The new value is provisional and labelled as such in `--help`.

## Where this leaves Step 3

Two candidates worth carrying forward, both marginal:

- `XLP~XLB` — sector ETFs, net +1572, out of sample +751, 30% net exposure
- `ALL~TRV` — insurers, net +215, out of sample +1593, 16% net exposure

Both are healthy less than a fifth of the time, and neither has been re-tested across
windows the way the plan requires. That re-test is the first thing Step 3 should not skip.
