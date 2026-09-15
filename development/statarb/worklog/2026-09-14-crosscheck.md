# 2026-09-14 — Cross-checking Step 3 against the reports already on disk

## Subject

Run the new Step 3 scripts against every backtest this project has already logged, and see
whether they describe the same trades. Two reproducibility defects and one dead candidate
came out of it.

## Status

**Done.**

| Item | Status |
|---|---|
| `outcomes.py` rebuilds the engine's gross on every logged run | ✅ exact on all 12 |
| Net reproduced against the historical log | ✅ 6 of 12 exactly; the other 6 explained |
| Missing `start` / `end` in `backtests.csv` | ✅ found and fixed |
| Missing `bars_per_night` / `warmup` in the logs | ✅ found and fixed |
| `--bars-per-night` defaulting to 1.0 for every asset class | ✅ fixed — now per class and timeframe |
| `ALL~TRV` re-tested on 23 years it was never fitted on | ✅ done — rejected |
| Step 3 had no HTML report | ✅ `signal_report.py` built |
| Verification | ✅ 400 checks across four suites, 0 failures |

## The cross-check

`logs/backtests.csv` is the independent record: every backtest ever run, with its
parameters and its result. Re-running each row through the new tooling asks whether
`outcomes.py` really describes the trades the engine makes.

**The gross rebuilt from the outcome categories matched the engine's own gross on all
twelve comparable rows, to the basis point.** That is the claim the script exists to
support, and it holds.

Net was a different story, and a more useful one.

## Two reproducibility defects

### The window was not on the row

Runs 9 and 11 of `backtests.csv` both read `XLP ~ XLB, 1d, entry 2.0, exit 0.5, stop 4.0,
hold 20, fit window 250`. One ran on 1,934 bars and returned 18 trades; the other on 6,972
and returned 75. Nothing on either row said so, because the log recorded `split` but not
`--start` or `--end`.

`trials.csv` and `cointegration.csv` had always recorded the window. `backtests.csv` never
had, and neither did the four new Step 3 logs. All five now do.

### The financing rate was not on the row either, and its default was wrong

Run 5 — `SPY ~ DIA`, the report open in the editor — logged 25 trades, gross +100.6,
transaction −50.0, carry −513.0, net −462.4. Re-running it reproduced the trades and the
gross exactly and gave carry −353.8.

Identical positions cannot produce different financing unless the rate changed. The ratio
was 513.0 / 353.8 = **1.4500** exactly, and supplying `--bars-per-night 1.45` reproduced
the row to the last digit.

**A daily bar is not a night.** Equities and their funds trade five days a week and are
financed seven, plus market holidays: about 1.45. Forex is the same five-for-seven,
collected as a triple charge on Wednesday. Crypto trades every day, so there a bar really
is a night. The flag defaulted to 1.0 everywhere, which undercharges a daily equity bar by
45% — and financing is the term that has decided every candidate in this project.

Worse, the log contains runs made at three different rates:

| Runs | Rate used | Reproduce at the correct per-class rate? |
|---|---|---|
| 1–5, 8 | correct per class | ✅ exactly |
| 6, 7 | 1.45 on forex, which should be 1.40 | ✗ off by 4–6 bps |
| 9–11, 13 | 1.0 on equities, which should be 1.45 | ✗ off by hundreds |

Fixed in three places: `costs.nights_per_bar()` now holds the rate per asset class and
timeframe as one definition; `--bars-per-night` defaults to it rather than to 1.0; and the
value used is written on every logged row. With no flags at all, `SPY~DIA` now reproduces
run 5 exactly.

The sub-daily rates fall out of the same function, which is what made hourly `XLP~XLB` pay
75 basis points of carry against 1,058 on daily bars.

## Do the Step 3 verdicts agree with the old ones?

Every pair below already had a study, a relationship report and a backtest. Step 3 judges
on different evidence entirely: whether trades complete, whether a threshold pays for its
own financing, whether the sample establishes a positive mean.

| Pair | trades | reached exit | predicted | realised | over by | mean less 1 s.e. | size | net |
|---|---|---|---|---|---|---|---|---|---|
| `USDNOK~USDZAR` | 23 | 39% | 359 | −2.2 | wrong sign | −87.6 | 0.00 | −285.0 |
| `EURUSD~GBPUSD` | 25 | 20% | 164 | +8.1 | 20.2× | −22.0 | 0.00 | +15.0 |
| `AUDUSD~NZDUSD` | 12 | 0% | 187 | −29.0 | wrong sign | −65.1 | 0.00 | −462.9 |
| `BTC-USDT~ETH-USDT` | 23 | 13% | 1,025 | +80.1 | 12.8× | −59.3 | 0.00 | +787.1 |
| `SPY~DIA` | 25 | 8% | 273 | +4.0 | 68.0× | −37.1 | 0.00 | −462.4 |
| `ALL~TRV` | 24 | 42% | 812 | −71.2 | wrong sign | −184.6 | 0.00 | −2,239.9 |
| `XLP~XLB` | 75 | 27% | 404 | +40.3 | 10.0× | −18.9 | 0.00 | +1,261.1 |

Every net in that table matches the historical log exactly. The measured entry floor is
left out of it and reported in the `signal_report.py` table further down instead: the
ad-hoc script that produced this table priced financing at a placeholder hedge ratio of
0.5 rather than each pair's own, so its floors were not the pairs' floors.

**Sizing returns zero on all seven**, including the three that made money. A mean of +80.1
bps per trade across 23 trades with a per-trade deviation in the hundreds does not
establish that the mean is positive, and `BTC~ETH`'s +787 total is not evidence it will
happen again. That conclusion is reached from trade returns alone, without reference to any
of the cointegration or hedge-stability work that reached the same place.

**Completion rate separates the table.** The pairs with a positive realised mean complete
13% to 39% of their trades. `AUDUSD~NZDUSD` completes **none** — not one of its twelve
trades reached the exit — and loses 463.

## `ALL~TRV` is dead

It was the only remaining screen output and had never been tested outside the window it was
found in. Both insurers have history back to 1996, so the test was available.

| Window | Bars | Hedge ratio | Engle-Granger p |
|---|---|---|---|
| 2019–2026, where it was screened | 1,935 | +0.903 | **0.014** |
| 1996–2018, never fitted on | 5,789 | +0.630 | 0.419 |
| 1996–2026, everything | 7,725 | +0.829 | 0.241 |

Six independent five-year eras, one rejects — the one containing the screening window.
Hedge ratio across eras: +0.987, +0.147, +1.259, +1.331, +1.024, +0.954.

```
1996-2018, never fitted on   59 trades   gross -2,805   carry -1,377   net -4,359
1996-2026, everything        85 trades   gross -4,870   carry -1,879   net -7,004
```

Maximum drawdown over the full record is −10,876 bps. **Gross is negative**: unlike every
other failure in this project, this one loses before any cost is charged. The signal is
wrong on this pair, not merely too small to pay for itself.

One caveat on the data: one bar of 7,725 in `ALL` has an open or close outside its own
high-low range, which `marketdata validate` flags. Every test above reads closes only, so
the defect does not touch the result.

## Step 3 had no report, and now does

Every other step in this project writes a self-contained HTML page: `pair_report.py` for
Step 0, `relationship_report.py` for Step 2, `backtest.py` for its own runs. Step 3 wrote
terminal text and CSV rows and nothing that could be looked at. That was an inconsistency,
not a decision.

`signal_report.py` puts all three questions on one page — does the prediction describe these
trades, does any threshold pay for itself, is any size justified — with the outcome
breakdown, the measured grid, the sizing arithmetic, and five charts. Output goes to
`studies/signals/`.

Writing it turned up one more defect. Financing is signed the way brokers quote swap, so a
debit is negative, and the cheaper of the two directions is therefore the **larger** signed
value. The report took the minimum, which picks the most expensive leg and quietly made
every threshold look unaffordable: it reported "no threshold pays" for `XLP~XLB` where
`thresholds.py` reported a floor at z = 1.50. Fixed, and three checks added so the sign
cannot drift again.

| Pair | prediction | threshold | size |
|---|---|---|---|
| `XLP~XLB` | fails, 10.0× | z 1.50 | 0.00 |
| `SPY~DIA` | fails, 68.0× | none pays | 0.00 |
| `EURUSD~GBPUSD` | fails, 20.2× | none pays | 0.00 |
| `AUDUSD~NZDUSD` | fails, wrong sign | none pays | 0.00 |
| `USDNOK~USDZAR` | fails, wrong sign | z 1.50 | 0.00 |
| `BTC-USDT~ETH-USDT` | fails, 12.8× | none pays | 0.00 |
| `ALL~TRV` | fails, wrong sign | none pays | 0.00 |

Seven pairs, seven rejections, on three independent tests each.

## Where this leaves the project

**No candidate remains.** `XLP~XLB` was rejected on 2026-09-14 on twenty years it was never
fitted on; `ALL~TRV` is now rejected on twenty-three. Both showed the same shape: cointegrated
only on the window that selected them, a hedge ratio wandering by a factor of several across
eras, and no era outside the selection window rejecting the null.

That shape is now familiar enough to be worth naming. It is what a screen finds when it is
allowed to choose both the pair and the window.

Next:

1. **Re-screen requiring an economic link**, not a p-value alone — same industry, same input
   cost, or one instrument holding the other. Both rejected pairs had a plausible-sounding
   story and no mechanism.
2. **Screen on a window, test on another, always.** The screener should hold back years by
   construction rather than leaving it to be remembered afterwards.
3. **Re-test the measured entry floor out of window.** It was read off the same
   twenty-eight years it was then evaluated on.
