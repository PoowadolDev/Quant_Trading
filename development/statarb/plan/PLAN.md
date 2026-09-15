# Correlation / Cointegration Bot — Build Plan

Non-directional trading bot. Trades the *relationship* between N assets, not the direction
of any one of them. **Forex first, paper/demo only**, extending to crypto and equities once
the machinery works.

Objective is profit that survives years, so every step below is gated on evidence rather
than on the previous step being finished.

---

## Status board

| Step | What | State |
|---|---|---|
| — | Data layer (`development/marketdata`) | ✅ forex, crypto, commodity, index — 92 series |
| **0** | Structure study — is there anything to trade? | ✅ done |
| 1 | Cost model + backtest engine — split in [STEP1.md](STEP1.md) | ✅ built, 97 checks green |
| 2 | Relationship engine + health monitor — split in [STEP2.md](STEP2.md) | ✅ built, 89 checks green |
| 3 | Signal, risk, sizing — split in [STEP3.md](STEP3.md) | ✅ built, 188 checks green |
| 4 | Validation — split in [STEP4.md](STEP4.md) | ✅ built, 100 checks green |
| 5 | Paper execution | ⬜ |
| 6 | Live, small size | ⬜ |
| 7 | Port to crypto / equities | ✅ done early — crypto and indices already searched |

**Machinery: finished and verified. Candidates: none.** 547 checks pass across five
verification suites, and the newest of them has been mutation-tested — twenty deliberate
defects introduced one at a time, twenty caught. What is missing is not code, it is a
relationship worth trading.

## Where the search has been

| Universe | Pairs tested | Survived every gate |
|---|---|---|
| Forex, daily | 105 | 0 |
| Forex, 4h and 1m | 141 | 0 |
| Crypto, daily and hourly | 45 | 0 |
| Commodity against forex | 12 | 0 |
| Equity index against forex | 357 | 0 |
| Index against index | 84 | 0 — the four that passed are an index against its own tracker |
| Sector and industry funds | 105 | 0 — `XLP~XLB` failed its out-of-window re-test, 2026-09-14 |
| Equities, within sector | 205 | 1 — `ALL~TRV` |

Roughly 850 pair studies and 390 backtest configurations. `SPY~DIA` clears cointegration
and hedge quality and still loses 581 bps, because a 49-bar half-life pays 71 nights of
retail margin financing to capture a 529 bps move. `XLP~XLB` appeared to clear those gates
and the financing as well, and did not survive being tested on history it had not been
fitted on — see below.

## What changed, 2026-09-14

**`XLP~XLB` looked like the first real candidate and is not one.**
See [worklog/2026-09-14-xlp-xlb.md](../worklog/2026-09-14-xlp-xlb.md).

It was found on 2019-01 to 2026-09, which was the whole of the stored history. Both funds
launched in December 1998, so twenty years of daily bars existed that the pair had never
been fitted on. Downloading them settled it.

| Window | Bars | Hedge ratio | Engle-Granger p | Backtest net |
|---|---|---|---|---|
| 2019–2026, where it was found | 1,934 | +0.594 | 0.033 | +2,033 |
| 1998–2018, never fitted on | 5,037 | +0.865 | 0.418 | −391 |
| 1998–2026, everything | 6,972 | +0.928 | 0.101 | +1,737 |

Split into seven independent four-year eras, **none reject**. Slide a window of exactly the
winning length through the whole record and 4 of 80 reject, where chance alone on a true
null gives 4.0.

The earlier claim that the hedge ratio was stable at +0.541 to +0.594 was measured entirely
inside the window the pair was found in. Across the full record it runs **+0.079 to
+1.343** and spends 6% of the sample at or below zero.

Over 28 years of walk-forward trading the parameter surface — hedge fit window against
entry threshold — has three positive cells out of twelve, a mean of **−698 bps** and a
range of −3,678 to +3,747. The sign of the result is chosen by the parameters, not by the
pair.

There was never an economic reason for the pair. Consumer staples and materials producers
share no cash flow, no input, no customer and no arbitrage link. The screen has no way to
ask for one, which is why it found this.

### The reframing

Every earlier failure was a **financing** failure, not a signal failure. Crypto beat a coin
flip by 5,000 to 10,000 bps and lost all of it to borrow. `SPY~DIA` earned +205 gross and
paid −752 in carry. `XLP~XLB` lost the same way on the twenty years it had not been fitted
on: +528 gross against −754 of financing.

So the selection criterion changes. **Stop ranking candidates by half-life or correlation,
and rank them by how big the spread's move is against the financing needed to capture it.**
A forex major deviating 0.3% can never pay for forty nights of carry, whatever its
statistics look like. A sector spread moving several percent can.

That also explains why 750 studies came up empty: the search was in venues where the
numerator is small, not where the denominator is large.

### Done since, 2026-09-14

See [worklog/2026-09-14-screening.md](../worklog/2026-09-14-screening.md).

1. ✅ **`screen.py` built.** Universe in, every pair through every gate, ranked, logged to
   `logs/screens.csv` with the survivor count printed beside the number chance alone would
   produce. It replaces eight throwaway sweeps whose results were reported without any of
   them being reproducible.
2. ✅ **Equity universe added** — 76 listings across 14 sectors. Screening within sector
   rather than across cuts 2,850 tests to 205, and every test avoided is a false positive
   avoided.
3. ✅ **A hole in the hedge gate found and closed.** `AMGN~LLY` screened as the best result
   in the project — net +3358, out of sample +2196 — on a hedge ratio of +0.165. That
   leaves a position **72% net long**: a single-name bet wearing a spread's name. The old
   `--min-abs-beta 0.10` floor admits 82% net. Added `--max-net-exposure`, default 0.35 of
   gross; `AMGN~LLY` is now rejected.
4. ✅ **`--min-healthy-share` calibrated** against realised results, 0.40 → 0.10. The old
   value rejected every candidate, and a gate that rejects everything ranks nothing. Four
   points is not a calibration, and the new value is labelled provisional.

### Carried into Step 3

| Pair | Status |
|---|---|
| `XLP~XLB` | ❌ rejected 2026-09-14 on twenty years it was never fitted on |
| `ALL~TRV` | ❌ rejected 2026-09-14 on twenty-three years it was never fitted on |

**Step 3 is built and verified — see [STEP3.md](STEP3.md).** It was built without waiting for a
candidate, against simulated processes with known answers, which is what let its own
defects be found with a random number generator rather than with money. What is still true
is that there is no candidate — and Step 3 now rejects the last one on three independent
grounds: the expected move has the wrong sign above z = 2.5, the modelled entry floor loses
money when traded, and 75 trades do not establish a positive mean.
Nothing in roughly 850 studies has survived being tested on history it was not chosen on.
`ALL~TRV` was given the same treatment on 2026-09-14 and failed it — see
[worklog/2026-09-14-crosscheck.md](../worklog/2026-09-14-crosscheck.md). Cointegrated at
p = 0.014 on the window that selected it, p = 0.419 on the 5,789 bars before it, one of six
independent eras rejecting, hedge ratio running +0.147 to +1.331, and **gross negative** over
thirty years: −4,870 before any cost, net −7,004, drawdown −10,876. It is the first failure
in this project where the signal loses money before financing rather than because of it.

**Both candidates showed the same shape**: cointegrated only on the window that selected
them, a hedge ratio wandering by a factor of several across eras, and no era outside the
selection window rejecting the null. That shape is what a screen finds when it is allowed
to choose both the pair and the window.

### The screen was rebuilt, 2026-09-14

See [worklog/2026-09-14-screen-rebuild.md](../worklog/2026-09-14-screen-rebuild.md).

`screen.py` now **reserves a quarter of the record at each end and never looks at it while
ranking**, requires the relationship to exist in at least one reserved window, refuses a
hedge ratio that swings by more than 3× or changes sign, and — given `--broker` — puts
whatever survives through the three Step 3 questions before calling it a survivor.
`--holdout 0` restores the old behaviour and prints a warning naming what it cost last time.

Both rejected pairs are now refused on the first gate, without anyone having to remember to
download more history.

Re-screened: 389 pairs, six universes, three bar sizes. **Zero survivors.** One pair reached
the replay — `USDCHF~USDCAD` on one-minute bars, clearing every statistical gate including
the reserved windows — and was rejected there: the expected move over-predicts by 20×, no
threshold earns its own cost, and the uncertainty-adjusted mean is −1.4 bps. Under the old
screen it would have been reported as the best result in the project.

### Widened and linked, 2026-09-15

See [worklog/2026-09-15-widen-and-link.md](../worklog/2026-09-15-widen-and-link.md).

The equity universe went from 76 symbols across 14 sectors to **252 across 29**, and
`screen.py` now **requires a shared economic driver by default** — the same sector, the same
currency leg, the same commodity. Sector ETFs drop from 105 pairs to 4, forex from 66 to 36.

A `DukascopyFeed` is built and its decoding verified against a real tick file, but the bulk
download has not been run: the host allows about one file every 2.6 seconds, so a
symbol-month is half an hour of network.

**Yesterday's holdout gate had a direction it did not check.** The widened screen produced
`NUE~STLD` — Nucor against Steel Dynamics, a genuine economic link and the most stable hedge
ratio this project has measured, netting +9,810 bps over thirty years. It passed because the
rule was "at least one reserved window must reject" and its *early* window rejected at 0.001.
Its late window is 0.648, and the era table shows the relationship rejecting in 1996–2000 and
in no period since. A relationship that died in 2001 is not tradeable in 2026. The gate is
now **the late reserved window decides**, with `--require-early` for the stricter version.

After all of it, 1,235 pairs screened:

| universe | pairs | cointegrated | noise gives | still there now | noise gives |
|---|---|---|---|---|---|
| equities, within sector | 1,192 | 144 | 59 | 1 | 5.7 |
| forex | 36 | 8 | 2 | 0 | 0.2 |
| sector ETFs | 4 | 1 | 0.3 | 0 | 0.03 |
| index ETFs | 3 | 0 | 0.2 | 0 | 0.02 |

The equity row is the finding. 144 against 59 looks like an excess, and it is what testing
the same instruments in overlapping windows produces. **One** pair is still present in the
most recent window, where chance alone gives **5.7**. The forward-looking gate finds fewer
than noise.

Still open:

1. **Decide on Dukascopy.** Deep intraday is the only untested direction left, and fetching
   a useful window is hours of network.
2. **Ask whether the answer is no.** With a forward-looking gate and an economic-link
   requirement, nothing persists into the window it would have to be traded in. That is
   evidence about this class of strategy, not only about the breadth of the search.
The third thing that came out of the `XLP~XLB` work — that hourly bars cut its carry from
−1,058 to −75 bps by shortening the hold from 16 days to 2.5 — is now Step 3's, because
holding period is set by the exit rule. It is the only lever that has ever moved the
financing term.

Two smaller facts worth keeping:

- **The fill-lag guard passes** — delaying the fill makes results monotonically worse, so
  there is no look-ahead. But one day of delay removed 92% of the net, which means the edge
  sat almost entirely in the bar after the signal.
- **`--min-healthy-share 0.10` is too loose.** It passes a pair the monitor calls broken
  69% of the time. The threshold was fitted to four points and this is the first evidence
  against it.

---

## Step 0 — Structure study (research gate)

**Nothing else starts until this answers.** It is cheap, and it decides what the bot trades.

The trap: FX pairs are not N independent assets. With K currencies there are at most K−1
independent factors, and every pair is `log P(i,j) = s_i − s_j`. `EURGBP` *is*
`EURUSD/GBPUSD` to within the spread, enforced continuously by banks. Hunting mean-reverting
residuals across 12 pairs the way you would across equities finds residuals that are
**approximately zero by construction**.

Do:

1. Fit the currency-factor decomposition on the stored daily FX panel:
   `r_pair(i,j),t = f_i,t − f_j,t + ε_t`, least squares per period, gauge fixed by `Σf = 0`.
2. Report variance explained by the factors, and the size of residual `ε` **relative to the
   spread**. Inside the spread means pair-residual statarb in FX is dead — confirmed, not
   assumed.
3. Test the three candidate structures for cointegration (Engle–Granger, Johansen):
   - cointegrated currency strength with a macro link — AUDNZD, EURCHF, NOKSEK
   - FX against an external asset — CAD vs crude, AUD vs copper
   - carry with the currency beta hedged
4. For each surviving relationship compute the OU half-life `ln2/θ`. Discard anything whose
   half-life exceeds the intended holding horizon.

**Tooling:** `pair_report.py` runs one pair at a time and writes an HTML report plus a
row in `logs/trials.csv`:

```bash
cd development/statarb/code
python pair_report.py -s AUDUSD,NZDUSD
python pair_report.py -s EURUSD,GBPUSD --split 0.6 --entry-z 1.8 --cost-bps 3 --dry-run
```

Parameters are typed by hand on purpose: one run is one trial, and Step 4 needs an honest
count of them. Exit code 0 means the pair passed every gate, 3 means it was rejected.

**Result, 2026-09-12.** 162 pairs tested across forex, crypto and commodity-versus-FX.
The shortlist is one pair:

| Pair | Half-life IS / OOS | Beta range across windows | Survives |
|---|---|---|---|
| `USDNOK ~ USDZAR` | 4.9 / 7.2 bars | +0.42 to +0.91, no sign change | 4 of 5 re-tests |

Everything else failed a re-test on windows it was not fitted on. `GBPUSD~USDNOK` passed
the first gate and looked like the best result in the sweep, then failed six of seven
re-tests with the hedge ratio swinging from -0.65 to +0.22 — a sign change, meaning the
two legs did not even agree on direction. That is what a false positive looks like, and
the sweep predicted 1.4 of them from 105 pairs at the measured 1.3% null rate. Re-testing
the winner on a fresh window is therefore not optional; it is the step that separates the
one real candidate from the noise.

`USDNOK~USDZAR` is a relative-value trade between two commodity-exporting currencies, with
most of the USD exposure netting out. It clears the edge gate at every cost from 4 to 150
basis points, so the spread is not the fragile part. The carry is: ZAR is an
emerging-market currency with a large interest-rate differential, and a position held for
a 5 to 7 bar half-life pays swap every night. Whether this trade survives is a question
about financing cost, which is exactly what Step 1 measures.

**Earlier progress, 2026-09-12.** Commodity anchors added to the store (`GOLD`, `SILVER`,
`COPPER`, `WTI`, `BRENT`) and twelve commodity-versus-FX pairs tested — trials 2 to 13 in
`logs/trials.csv`. Every one is rejected at a 2-30 bar horizon: these relationships revert over
40 to 200 bars, which is a quarterly-to-annual trade, not a swing trade. Return
correlations are weak throughout (|corr| at most 0.29 against 0.89 for AUDUSD~NZDUSD).
The best behaved are `GOLD~USDCHF` (half-life 42 in-sample, 88 out-of-sample) and
`WTI~USDNOK` (66 and 90). `USDCAD`, the textbook oil currency, is the worst behaved of
the oil set. Still outstanding: the currency-factor decomposition and the cointegration
tests, both of which need `statsmodels`.

**Done when:** a shortlist of tradable relationships with half-lives exists, or the finding
that there are none — which redirects the bot to crypto/equities early and saves months.

Descriptive statistics only. No strategy selection yet, so no validation harness needed.

Data: already stored. 12 FX pairs, daily, 2019-01-01 onward — `marketdata list`.

---

## Step 1 — Cost model + backtest engine

Built together, because a backtest without costs is decoration.

**Cost model** — FX needs three terms, not one:

- spread, **time-of-day aware** (Asian session and rollover are wider)
- commission, if the account is raw-spread
- **swap / rollover, long and short quoted separately** — a spread held three days pays it
  three times, and on a thin mean-reversion edge that can exceed the edge

**Backtest engine** — hard architectural constraint: it replays bars through *the exact same
signal code that runs live*. Two code paths means the backtest measures nothing.

**Done when:** a known-losing strategy backtests as losing by roughly the cost it should.

Split into five runnable scripts in **[STEP1.md](STEP1.md)**: `costs.py`, `feasibility.py`,
`strategy.py`, `backtest.py`, `verify_backtest.py`. The first two can kill the candidate in an
afternoon, before any engine exists, so they come first.

---

## Step 2 — Relationship engine + health monitor

**Relationship engine** — the "correlation technical", in order:

1. currency-factor decomposition (FX) or factor residuals (other assets)
2. cointegration test → is the gap actually closing?
3. hedge ratio — OLS to start, Kalman filter for a time-varying ratio
4. spread construction
5. OU fit → `θ, μ, σ`, half-life `ln2/θ`, `σ_eq = σ/√(2θ)`
6. z-score

Correlation alone is **not tradable**. It says two things move together, not that the gap
closes. Cointegration is the tradable property.

**Health monitor** — the component most often missing, and the one that prevents the classic
statarb blow-up. Each cycle: re-test the cointegration p-value, re-estimate half-life, flag
degradation, and force an exit when the relationship has structurally broken. Without it the
bot averages into a spread that has stopped mean-reverting.

**Done when:** both run offline against the store and reproduce Step 0's shortlist.

Split into six runnable scripts in **[STEP2.md](STEP2.md)**: `factors.py`,
`cointegration.py`, `hedge.py`, `relationship.py`, `health.py`, `verify_relationship.py`.
Only `cointegration.py` needs anything new (`statsmodels`), and none of it waits on broker
numbers — so this is the work available while Step 1a is blocked.

---

## Step 3 — Signal, risk, sizing

Split into five runnable scripts in **[STEP3.md](STEP3.md)**, ordered 2026-09-14 after
measuring what each would have caught: `outcomes.py`, `thresholds.py`, `risk.py`,
`sizing.py`, `verify_signal.py`.

**None of it waits on a candidate.** Every component can be verified against a simulated
OU process with known parameters, which is how Step 2 was verified and why its defects were
found before they cost anything.

**The measurement that set the order.** The expected move this project has used since Step 0
— `(entry_z − exit_z) × σ_eq` — over-predicts the realised gross per trade by 10× to 68×
on the three pairs where it has the sign right, and has the sign wrong on the other three.
Two errors stack: the static OU fit overstates the traded spread's scale by up to 5.7× and
its half-life by up to 15×, and even after correcting for that, the formula assumes every
trade runs from entry to exit, which nothing has ever measured. Inverting the cost
arithmetic shows the break-even entry threshold is below z = 0.8 for all six pairs, each of
which spends about half its life beyond it — so **feasibility was never the binding
constraint**; completion is. That is why `outcomes.py` comes first and threshold
optimisation comes after it.

**Signal** — entry and exit thresholds as a *bound* from cost and measured holding time,
not as a fitted optimum. Sweeping thresholds on `XLP~XLB` over 28 years gave a net from
−3,678 to +3,747 bps across twelve cells; that surface is noise
(`research/paper/statarb/1811.09312` for the cost-in-objective form). Maximum holding
period is a first-class parameter, because moving `XLP~XLB` from daily to hourly bars cut
carry from −1,058 to −75 bps and is the only thing in this project that has ever moved the
financing term.

**Risk manager**

- per-relationship cap, gross and net exposure limits
- **correlation between spreads** — two "independent" pairs often share a currency leg;
  AUDUSD and NZDUSD spreads are nearly the same bet. Without this check the book is
  concentrated while appearing diversified
- drawdown kill switch

**Sizing** — growth-optimal leverage from the time-average growth rate `ḡ = μ − σ²/2`,
scaled down fractionally for parameter uncertainty. Sharpe is leverage-invariant and cannot
answer the sizing question (`research/paper/portfolio_sizing/0902.2965`).

**Done when:** the bot produces a position series offline, with every number traceable to a
config value.

---

## Step 4 — Validation

Run the whole thing through the harness. **Expect to fail here** — failing at this step is
cheap, and it is the entire reason the step exists.

- Deflated Sharpe Ratio with an **honest trial count** — every parameter tried, logged
- Probability of Backtest Overfitting (CSCV)
- purged K-fold with embargo — plain cross-validation leaks when labels overlap in time
- White's Reality Check / Hansen SPA across every variant tried
- minimum track record length — how long paper trading must run to mean anything

Report the gates individually. Do **not** aggregate them into one score
(`research/paper/validation/2608.23808` showed a composite has no forward relationship).

**Done when:** results survive the gates, or the strategy is killed and Step 0's shortlist
supplies the next candidate.

---

## Step 5 — Paper execution

Demo account only.

- broker adapter, **idempotent** order submission
- **leg risk** — a spread is two orders; one filling without the other leaves you directional.
  Needs explicit handling, not hope
- state store — positions, open orders, per-relationship parameters, last processed bar, so a
  restart neither loses positions nor re-enters a trade
- reconciliation against broker truth every cycle
- data sanity gate at runtime — staleness, gaps, and the free FX check that
  `EURGBP ≈ EURUSD/GBPUSD`; a feed dying quietly is the most common cause of a bot trading
  garbage
- monitoring — heartbeat, PnL, open positions, alerts, manual kill switch
- audit log — every decision with its inputs, so a loss can be explained rather than guessed at

**Done when:** the demo account has run unattended long enough to satisfy the minimum track
record length from Step 4.

---

## Step 6 — Live, small size

Only after Step 5's track record is long enough. Start below the size the maths justifies.

---

## Step 7 — Port to crypto / equities

**Already done, out of order, because the forex search kept coming up empty.** The
relationship engine, the cost model and the backtest are asset-agnostic; only the feed and
the cost profile change, and adding crypto, commodities and equity indices cost a day each
rather than a rewrite. What that bought was the knowledge that the emptiness is not
specific to forex.

Findings per venue:

- **Crypto.** Real signal — the strategy beats a coin flip on 5 of 5 pairs by 5,000 to
  10,000 bps — and the borrow cost on the short leg eats all of it. At zero borrow three
  pairs are profitable; at 3 bps a night they are marginal. Perpetual funding, where the
  short is often paid rather than charged, is the open question.
- **Commodities against forex.** Twelve pairs, all rejected. Reversion takes 40 to 200
  days, and correlations are weak: 0.29 at best against 0.89 for AUDUSD~NZDUSD.
- **Equity indices.** The best-behaved relationship found anywhere, and still not tradable
  at retail financing. See the Step 7 notes below.



The relationship engine, validation and execution code are asset-agnostic; only the feed and
the cost model change. Crypto adds perpetual funding carry
(`research/paper/relative_value/2212.06888`) as a second, uncorrelated return stream — the
realistic path to a portfolio worth compounding.

---

## FX details that bite

- **Rollover at 17:00 New York** — swap is charged and spreads widen sharply. Do not enter
  near it.
- **Weekend gap** — spread positions held over the weekend carry gap risk with no exit.
  Decide explicitly: flat on Friday, or size for it.
- **Session liquidity** — Asian spreads are wider; the cost model must be time-of-day aware.
- **Yahoo FX high/low is corrupt** — 1–3% of daily bars have an open or close outside the
  bar's own range. Close-only work is fine; any stop-loss or breakout logic needs a broker
  feed first. See `development/marketdata/MANUAL.md` §7.

---

## Not building yet, deliberately

| Thing | Why not |
|---|---|
| Machine learning | No data budget for it, and it multiplies the trial count |
| Portfolio optimiser / allocator | Needs two working strategies; there are zero |
| Live tick streaming | Bar-close decisions do not need ticks |
| Multi-asset expansion | Port after FX works — Step 7 |

---

## References

- Data: `development/marketdata/MANUAL.md`
- Spread construction, OU estimation, cost-aware thresholds: `research/paper/statarb/`
- Sizing and covariance: `research/paper/portfolio_sizing/`
- Validation gates: `research/paper/validation/`
- Crypto carry for Step 7: `research/paper/relative_value/`
