# 2026-09-14 — Rebuilding the screen so it cannot repeat itself

## Subject

Both candidates this project produced were artifacts of the screen choosing the window
along with the pair. Fix the screen so that cannot happen, put the Step 3 gates in front of
it, and search again.

## Status

**Done. 430 checks green. 389 pairs screened across six universes and three bar sizes; one
pair reached the replay and was rejected there.**

| Item | Status |
|---|---|
| Reserve a window at each end, never seen while ranking | ✅ built |
| Gate on the reserved windows and on hedge-ratio swing | ✅ built |
| Replay confirmation — the three Step 3 questions, on survivors only | ✅ built |
| Acceptance test against the two known-bad pairs | ✅ both rejected |
| Screens re-run across every universe and 1d, 4h, 1m | ✅ logged |
| Missing sector-ETF cost entries | ✅ ten added |
| Screener documented in the `statarb` skill | ✅ written |
| Verification | ✅ 430 checks, 0 failures |

## What was wrong

`screen.py` fitted and tested on whatever record it was given. Its "out of sample" was a
30% tail of that same record. When the record *is* the selection — and it was, because the
store held 2019 onward and nothing earlier — the tail is inside the choice and proves
nothing.

Both rejections of the previous day came from noticing this by hand, downloading two
decades more history, and re-testing. That should not depend on anyone remembering.

## What changed

### A reserved window at each end

`--holdout 0.25` (default) reserves the oldest quarter and the newest quarter. The screen
fits and ranks on the middle half and never looks at the reserved parts until it reports
them. `--require-holdout` (default on) demands that at least one reserved window also
rejects the null.

The noise arithmetic is stated for both: with two reserved windows, the joint probability
under a true null is `level × (1 − (1−level)²)` — about 0.0049 at the 5% level, against
0.05 for the screening window alone.

`--holdout 0` restores the old behaviour and prints:

```
WARNING: --holdout 0 screens and tests on the same record. Two candidates were
produced this way and both were wrong.
```

### A hedge-ratio swing gate

`--max-beta-swing 3.0` compares the ratio fitted on each window and refuses a pair whose
widest ratio exceeds the limit. A sign change is refused outright — that is not one
relationship measured twice.

The two rejected pairs swung by 17× (`XLP~XLB`, +0.079 to +1.343) and 9× (`ALL~TRV`,
+0.147 to +1.331).

### The Step 3 questions, on survivors only

`--broker` turns on a replay of everything that survived the statistical gates:

- does the expected move describe the trades, within `--max-overstatement`?
- does any entry threshold earn `--min-edge` times its own cost?
- does the sample establish a positive mean?

Cheap gates on every pair, the expensive one on the handful that got past them. It
delegates to `outcomes.py`, `thresholds.py` and `sizing.py` rather than reimplementing
them, and the verification suite now checks that by refusing to find their formulas copied
into `screen.py`.

A pair whose legs have no entry in the cost profile is reported as unconfirmed and the
screen carries on. It used to abort the whole run, which meant a missing `XLF` told you
nothing about the other hundred pairs.

## Acceptance test

The question that matters is whether the rebuilt screen catches what the old one missed.

```
XLP~XLB   old behaviour, screening on 2019+          cointegrated, p 0.033
          new behaviour, windows reserved            not cointegrated

ALL~TRV   old behaviour, screening on 2019+          cointegrated, p 0.015, oos 0.001
          new behaviour, windows reserved            not cointegrated
```

Both are refused now, on the first gate, without anyone having to remember to download more
history.

## What the search found

389 pairs across six universes at daily bars:

| universe | pairs | cointegrated | noise gives | outside the window | noise gives | survivors |
|---|---|---|---|---|---|---|
| equities, within sector | 205 | 17 | 10.2 | 0 | 1.0 | 0 |
| sector ETFs | 105 | 6 | 5.2 | 0 | 0.51 | 0 |
| forex | 66 | 15 | 3.3 | 0 | 0.32 | 0 |
| index ETFs | 6 | 0 | 0.3 | 0 | 0.03 | 0 |
| commodity against forex | 6 | 1 | 0.3 | 0 | 0.03 | 0 |
| crypto | 1 | 0 | 0.1 | 0 | 0.0 | 0 |

Forex shows the largest excess over chance — 15 against 3.3 — but currency pairs share
legs, so those are not 66 independent tests; twelve pairs resolve to eight directions. Two
hold out of sample. **None exists outside the window that selected it.**

### Bar size

| universe | bars | cointegrated | noise gives | outside | survivors |
|---|---|---|---|---|---|
| forex, 4h | 66 | 7 | 3.3 | 0 | 0 |
| forex, 1m | 45 | 16 | 1.0 | **3** | **1** |
| crypto, 1h | 1 | 0 | 0.1 | 0 | 0 |

**One pair reached the replay.** `USDCHF~USDCAD` on one-minute bars cleared every
statistical gate: p = 0.027 on the screening window, 0.006 on the held-out tail, 0.000 on
the reserved early window, hedge ratio stable to 1.75×, 6% net exposed, half-life 50 bars.

The replay rejected it:

```
pair                    over by   floor    mu-1se   size  verdict
USDCHF~USDCAD             20.0x    none      -1.4   0.00  rejected
```

The expected move over-predicts by 20×, no entry threshold earns its own cost back, and the
uncertainty-adjusted mean is −1.4 basis points.

**That is the funnel doing exactly what it was rebuilt to do.** The statistics let a pair
through; the trades did not. Under the old screen it would have been reported as the best
result in the project.

Two caveats on that run: Yahoo serves seven days of one-minute bars, so the screening
window is 2,817 bars of a single week, and 21 of 66 pairs had no one-minute data at all.
A week is not evidence of anything; the interesting part is the mechanism, not the pair.

## Verification

430 checks across four suites, up from 418.

New in `verify_relationship.py`: the reserved-window gate, the hedge-ratio swing including
the sign-change case, and a fixture rebuilt to use keyword arguments — the positional
constructor silently shifted every screen fixture onto the wrong column when the new fields
were added, which is the same class of defect the CSV schema guard exists to catch.

New in `verify_signal.py`: the layering rule now says where `screen.py` sits. It is an
orchestrator rather than a Step 1 or Step 2 primitive, so it is allowed to call Step 3 —
and the check confirms it *calls* rather than copies, by refusing to find the sizing and
threshold formulas duplicated in its source.

## Where this leaves the project

Machinery for Steps 0 to 3 complete and verified. The screen can no longer produce the
failure that produced both previous candidates. Still no candidate.

Next, in order:

1. **Deeper intraday data.** The only universe to reach the replay was one-minute forex, on
   seven days. Dukascopy or HistData would give years of it. This is now the highest-value
   data work, and `marketdata` would need a new source.
2. **An economic-link requirement for non-equity universes.** `--within-sector` handles
   equities. Sector ETFs across different sectors have no shared driver at all, and should
   probably not be screened as pairs; forex has the triangular identities, which are
   arithmetic rather than statistics.
3. **Widen the equity universe.** 76 listings across 14 sectors is thin, and within-sector
   screening keeps the multiple-testing cost proportional.
