# 2026-09-17 — forex: two real defects found, still no candidate

## Subject

Search forex for a relationship that produces profit in backtest, any timeframe,
using the whole toolchain.

## Status

**No survivor, but this was the most productive search so far.** Two genuine
defects were found and fixed, one in the data layer and one in the pipeline's
treatment of forex, and both had been silently corrupting results. The closest
candidate reached further than anything before it and then failed.

| Item | Result |
|---|---|
| Forex history deepened | 2019–2026 (2,002 bars) to 2003–2026 (~6,000) |
| Universe | `fx-wide`, 15 symbols, 60 linked pairs of 105 |
| New data defect found | close spike-and-revert — 16 bad bars |
| New validator check | `close-spike`, shipped in `marketdata` |
| Pipeline bug found | forex neutrality measured in the wrong space |
| Pairs reaching the trade replay | 1, the first in forex |
| Survivors | 0 |
| Checks | 629 across five suites, up from 608 |

## Defect one: Yahoo forex has bad close prints, and nothing was checking

The documented Yahoo forex defects are broken OHLC bars and zero volume. Both
are irrelevant here: this pipeline reads `aligned_panel(field="close")` and
never touches a high or a low. What was not documented, and what does matter,
is that **the close series itself contains bad prints**.

Sixteen of them across five symbols. Every one has the same signature — a
single-bar jump past 10% that fully reverses on the next bar:

| symbol | dates | move |
|---|---|---|
| EURUSD | 2008-12-08/09 | +15.96% then −14.33% |
| USDJPY | 2008-12-08/09 | +16.29% then −16.85% |
| EURGBP | 2022-10-09/10 | +11.01% then −11.05% |
| USDNOK | 2020-03-20/23 | −33.18% then +41.89% |
| USDNOK | 2021-01-01/04 | −10.90% then +11.11% |
| USDZAR | 2024-11, 2025-01 | four alternating spikes |

The round trip is the whole signal. A real shock moves a price and leaves it
moved — the Swiss National Bank dropped the euro floor on 2015-01-15 and EURCHF
never went back. A bad print moves it and returns it, because only one bar was
wrong.

This is worse than the OHLC defect for anything reading closes. One wrong close
is **two** large returns in opposite directions, and a mean-reversion strategy
reads the first as an opportunity and the second as the reversion it predicted.

`_spike_reversions` was added to `marketdata/validate.py` with a
`--spike-threshold` flag, defaulting to 0.10. Checked against ground truth: it
flags all 16 bad prints and correctly leaves alone all five genuine events —
the SNB on USDCHF and EURCHF, Brexit on GBPJPY, and the October 2008 crisis on
USDJPY and USDZAR.

## Defect two: forex neutrality was measured in the wrong space

`hedge.net_exposure` assumes both legs are quoted the same way round. That is
true of two equities and false of two currency pairs.

`AUDUSD` is AUD/USD and `USDNOK` is USD/NOK. The dollar sits on opposite sides,
so the two rates move oppositely and the fitted beta is negative. The leg
weights become `(1, +|beta|)` — long both — and the neutrality gate returns
**exactly 1.0**, reading the position as entirely directional.

It is not. Long AUDUSD plus long USDNOK is long AUD, short NOK: the dollar
cancels. **All 28 negative-beta pairs of 60 scored exactly 100%**, which is the
signature of a systematic representation error rather than a run of bad pairs.

The trade itself was never wrong — `leg_weights` with a negative beta already
produces the correct position. Only the measurement was wrong, so the fix is
surgical: `hedge.fx_net_exposure` sums exposure per currency and asks whether
the *shared* currency cancels, since the other two are the spread itself and are
supposed to be non-zero. Non-forex symbols and same-side quotes fall through to
the original function unchanged.

Cointegration is invariant to this: the p-value is bit-identical whether the leg
is inverted or not, because inverting is a sign flip on one regressor. Only the
hedge gate ever saw a difference.

| pair | beta | leg space | currency space |
|---|---|---|---|
| `AUDUSD~USDCAD` | −1.1526 | 100.0% | **7.1%** |
| `AUDUSD~USDNOK` | −0.5813 | 100.0% | **26.5%** |
| `EURUSD~GBPUSD` | +0.70 | 17.6% | 17.6%, unchanged |
| `XLP~XLB` | +0.594 | 25.5% | 25.5%, unchanged |

Thirteen checks added, five mutations tried, five caught.

## The suite broke, and it was the suite's fault

Deepening the forex history turned five checks red across two suites —
`AUDUSD/NZDUSD` correlation and hedge ratio, the identity check, `USDNOK~USDZAR`
cointegration and the `AUDNZD~AUDUSD` hedge rejection.

Reverting the neutrality change left all five still failing, which established
the cause: these are real numbers measured on real bars, loaded with
`start=None`, so they silently tracked whatever the store happened to contain.
An anchor that changes when unrelated data is downloaded is not anchoring
anything. The windows are now pinned to 2019-01-01 → 2026-09-09 in both suites,
and the original values pass again.

## `AUDUSD~USDNOK` — the furthest a forex pair has gone

It cleared every statistical gate, including the late reserved window that has
killed everything else in this project:

- p = 0.0001 screening window, p_oos = 0.015, **p_late = 0.039**
- weight swing 2.09 against a gate of 3.0, half-life 49 bars
- net exposure 11% once measured correctly
- backtest +3,126 bps net, 56 trades, 55% winners

Then it failed, on four separate grounds.

**Thirty-four per cent of its profit is a data error.** The single largest trade
in the record is `2020-03-19 → 2020-03-23`, two bars, **+881.9 bps**, entered on
the fabricated 33% drop in USDNOK and exited on the fabricated 41.89% rebound.
The top five trades of 73 are 84% of all profit, so the result has no breadth
even before that one is removed.

**The headline p-value is inflated a hundredfold by the same four bars.**
Removing them moves the screening p from 0.0001 to 0.0130. The late-window
p is untouched at 0.0387 → 0.0389, so that part is real.

**Deflated Sharpe 7.1%.** A probabilistic Sharpe of 98.3% falls to 7.1% once the
85 trials behind it are charged; the benchmark from noise alone is 0.298 and
this reached 0.176.

**Probability of backtest overfitting 67.5%**, median out-of-sample log-odds
−0.69 — the worse-than-random figure again.

Two more things the new risk block made visible: the Sharpe is 0.28 ± 0.22, so
its standard error is nearly as large as itself, and the strategy spends its
**longest drawdown 2,813 bars — eleven years — underwater**, still 495 bars
below its previous peak on the final bar.

## The first population excess this project has found

The bootstrap over 60 pairs and 15 instruments: 15 rejections against 4.0
expected, **bootstrap p = 0.038**. Dependence widens the standard deviation
2.0×, from 1.69 to 3.38. Crypto by contrast showed no excess at all (p = 0.423).

Four pairs clear a 10% false discovery rate, and all four survive removing the
bad prints — but every one containing USDNOK degrades by one to two orders of
magnitude:

| pair | p as stored | p cleaned |
|---|---|---|
| `USDCAD~USDNOK` | 0.00005 | 0.00236 |
| `AUDUSD~USDNOK` | 0.00006 | 0.01303 |
| `USDCHF~AUDUSD` | 0.00158 | 0.00158 |
| `USDMXN~USDNOK` | 0.00493 | 0.03657 |

After cleaning, only two still clear the family-wise Šidák threshold of 0.0077.
So the excess is partly real and partly bad data, and the honest statement is
that forex carries more structure than chance while no individual pair on the
shortlist has yet survived being traded.

## Why forex behaves differently from crypto

The economic-link gate does real work here. It skipped 45 of 105 pairs for
sharing no driver, because a currency pair is exposed to both of its legs and
two pairs sharing a leg move together for a reason that can be named. In crypto
every coin resolves to one driver, `crypto-beta`, so the same gate admitted
everything and the trial count had to carry the whole correction alone.

That is the difference between a population excess of p = 0.038 and no excess at
all, and it is an argument for searching markets where instruments have
nameable shared drivers rather than one common factor.

## Still open

1. **The store still contains the 16 bad prints.** They are detected but not
   repaired, and nothing was deleted. Any backtest touching EURUSD, USDJPY,
   EURGBP, USDNOK or USDZAR carries them until that is decided.
2. Feed the bootstrap floor into `screen.py`; it still prints `N x level`.
3. Dukascopy bulk fetch — and it now matters more, since it would give forex
   history that does not come from the feed with these defects.
4. The intermittent `verify_signal` failure, roughly one run in five.
