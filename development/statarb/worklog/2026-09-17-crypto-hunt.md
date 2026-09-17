# 2026-09-17 — crypto: the full search, and what it found

## Subject

Use the whole toolchain to find between one and five crypto relationships that survive every
gate. Any timeframe, any number of legs, and keep going until something passes; if nothing
does, vary the parameters and try again.

## Status

**Done, and the answer is still no survivor.** One pair got further than anything this
project has produced in crypto and then failed the same gate that killed `NUE~STLD`.

| Item | Result |
|---|---|
| Universe widened | 2 coins to 18 |
| History deepened | daily, four-hour and hourly back to Binance's 2017 launch |
| Pair screens | 153 pairs at three timeframes |
| Parameter sweep | lags 1, 2, 4 against log and raw prices, two timeframes |
| Basket screens | 8 structural groups at three timeframes, new script |
| Screens logged | 19 pair screens, 26 basket rows |
| Survivors | 0 |

## What was built

`basket_screen.py`, the n-leg form of `screen.py`. Three things in it are worth recording
because each was a trap that had to be avoided rather than a feature that was wanted.

**The critical values must know how many legs were fitted.** The residual of an n-leg fit was
chosen to look stationary, so a plain ADF on it over-rejects, and the over-rejection grows
with every leg added. `statsmodels.coint` accepts a two-dimensional second argument and
applies the MacKinnon values for that many regressors. Measured here on independent random
walks, the five per cent critical value moves from -3.344 at one regressor to -4.433 at four,
and the rejection rate stays at or below five per cent throughout. That calibration was run
before the script was trusted, not after.

**Groups are named, not enumerated.** Eighteen coins admit 816 three-leg combinations and
3,060 four-leg ones. Screening them all would raise the deflation benchmark for whatever
survived while buying nothing. The eight groups each carry a structural claim statable in one
sentence without reference to a price: Bitcoin and its forks, Ethereum and its fork, the two
payment-settlement tokens, the competing smart-contract layer ones, and so on.

**The economic-link gate does no work in crypto.** Every coin resolves to one driver,
`crypto-beta`, because everything in this market moves with bitcoin. `--require-link` admits
all 153 pairs honestly. That gate was what would have caught `XLP~XLB`, and here it cannot
help, so the trial count has to carry the whole correction alone.

`load_basket` was needed because `pair_report.load_prices` refuses anything but two symbols.
It keeps that function's two protections: the panel is joined and any bar missing from any
leg is dropped, and a non-positive close is refused outright rather than becoming a NaN
somewhere downstream.

## The pair screens

| Timeframe | Pairs | Cointegrated | Noise alone gives | Survivors |
|---|---|---|---|---|
| 1d | 153 | 7 | about 8 | 0 |
| 4h | 153 | 6 | about 8 | 0 |
| 1h | 153 | 6 | about 8 | 0 |

Below chance at the first gate, three times.

## The parameter sweep

Twelve further screens: lags of 1, 2 and 4 against log and raw prices, at daily and
four-hour. Survivors in every one: zero.

The raw-price runs are worth recording because they look like a discovery and are not.
They return 22 to 26 cointegrated pairs against 7.7 expected, roughly three times chance —
and not one survives the hedge-ratio stability gate. That is the gate doing its job. The
relationship between two coins is multiplicative, a ratio; taking logs turns that ratio into
a difference, which is what a cointegration test is built to see. Raw-price cointegration
between instruments quoted at 77,000 and at 0.08 is an artefact of shared trend, and the
stability test catches it because a spurious hedge ratio will not hold still.

An earlier reading of the screen log, recorded here in error and corrected the same session:
the column showing zero stable ratios was read as the stability gate killing every candidate.
It was not. Ninety of 153 pairs have a swing at or below the 3.0 gate and the median is 2.13,
so crypto hedge ratios are reasonably stable. The zero means nothing reached that gate. The
binding constraint is earlier and is the late reserved window.

## The baskets

Eight groups at three timeframes. One cointegrated on the screening window,
`SOL~AVAX~DOT~ATOM` at p = 0.023, and it dies out of sample at 0.464 and in the late window
at 0.550.

Every basket of three or more legs shows an infinite weight swing, meaning at least one leg
changes sign between windows. The windows disagree about which way that leg hedges, which is
not one relationship measured three times. This is the instability of the Johansen
eigenvector appearing in ordinary least squares form, and it is the reason baskets are not
obviously the answer to a market with one driver.

## `DOT~FIL`, and why it still fails

The best candidate this project has produced in crypto.

What it passes:

- p = 0.0002 on the screening window at daily, 0.0001 at four-hour, 0.0000 at hourly
- p = 0.0003 in the **late reserved window**, which the screen never saw, and 0.0038 and
  0.0039 at the other two timeframes
- beta +0.807, +0.808, +0.808 across the three bar sizes, so not an artefact of sampling
- net exposure 11 per cent, a genuine spread rather than a directional bet wearing a hedge
- Benjamini-Hochberg at a 10 per cent false discovery rate, and the family-wise Sidak
  threshold of 0.0034 with p = 0.00021
- a positive backtest: 30 trades, 60 per cent winners, net +3,768.5 bps, out of sample
  +436.0 bps

What it fails:

- **deflated Sharpe 0.1 per cent.** The probabilistic Sharpe is 89.7 per cent, which is what
  the result looks like before the search is charged. Seventy-nine trials put the noise
  benchmark at 0.812 and this reached 0.234.
- **probability of backtest overfitting 67.5 per cent**, with a median out-of-sample
  log-odds of -0.69. That is the worse-than-random figure the method predicts for selection
  on noise, reproduced exactly.
- **no single year rejects at five per cent except 2022.** The year-by-year p-values are
  0.416, 0.0007, 0.144, 0.249, 0.134 and 0.111. The strong pooled p-values come from pooling.
- **the hedge ratio drifts monotonically**, 0.436 in 2021 to 1.291 in 2026, roughly three
  times in one direction. A ratio that wanders is noise around a relationship; a ratio that
  walks steadily one way is a relationship changing into a different one.
- `pair_report` rejects it on the full record, half-life 46.1 in sample and 168.1 out, both
  outside the 2-to-30 band.

Leakage was not tested at the natural horizon: purging removed 2.1 per cent of the training
rows, too little for the comparison to distinguish a clean strategy from a leaky one, and the
share did not move when the fold count was raised. The report's own configuration purged 48.5
per cent and found no leakage. Either way this does not rescue the pair, which is already
dead on two gates.

Report at `studies/validation/validation-DOT-USDT-FIL-USDT.html`.

## The population says the universe is noise

The bootstrap over 153 pairs and 18 instruments, 25 replicates, block 20 bars:

- observed rejections 7, expected 7.7, bootstrap mean 7.4 — these agree, which is the check
- bootstrap standard deviation 6.85 against 2.70 if the tests were independent; dependence
  widens it 2.5 times
- bootstrap p = 0.423, so **no population excess**

Two pairs nonetheless clear a 10 per cent false discovery rate. The tool's own verdict is the
right one: a single result not corroborated by the rest of its universe.

## `BNB~LINK` is the useful counter-example

It has the lowest p-value in the entire universe, 0.00015, and it is the worst candidate in
it. Out of sample 0.979, late window 0.700, half-life 55.1, and net exposure 67 per cent —
a directional bet on BNB wearing a hedge that does nothing, `hedge_ok` false.

The lowest p-value in a universe is not its best pair. Keep this one as the example.

## Why crypto resists this method

The finding underneath all of the above. Cointegration in levels requires two instruments to
hold a stable long-run price ratio. Over 2017 to 2026 crypto has repriced relatively and
permanently — coins do not return to an old ratio after a cycle, they establish a new one.
The `DOT~FIL` beta walking from 0.436 to 1.291 is that fact in miniature.

A market with one driver and permanently trending relative valuations is close to the worst
case for a levels-cointegration screen. That is a property of the market and the method, not
of the parameters, and no setting of `--lags`, `--price`, `--holdout` or `--level` changed it
across nineteen screens.

## What is left

1. **A different model class.** Residual reversion on *returns* after removing the market
   factor, rather than cointegration on levels. This does not require a stable price ratio,
   which is the assumption crypto violates, and it is the standard approach in this market.
   It is a real build, not a parameter change.
2. **More coins.** Cheap, and it raises the deflation benchmark for whatever it finds.
3. **Faster bars.** Fifteen and five minute data, where costs of roughly 28 bps a round trip
   against an estimated profile become the binding constraint rather than the statistics.

## Still open from before

1. Feed the bootstrap floor into `screen.py`. It prints `N x level`; every screen above
   reports that arithmetic figure while the measured floor is wider.
2. `relationship.py`, the Step 2 unifier.
3. Dukascopy bulk fetch.
4. The intermittent `verify_signal` failure, roughly one run in five, undiagnosed.
