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
| — | Data layer (`development/marketdata`) | ✅ done |
| **0** | Structure study — is there anything to trade? | ✅ done |
| 1 | Cost model + backtest engine — split in [STEP1.md](STEP1.md) | ✅ engine done, candidate fails |
| 2 | Relationship engine + health monitor — split in [STEP2.md](STEP2.md) | 🟡 next |
| 3 | Signal, risk, sizing | ⬜ |
| 4 | Validation | ⬜ |
| 5 | Paper execution | ⬜ |
| 6 | Live, small size | ⬜ |
| 7 | Port to crypto / equities | ⬜ |

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

**Signal** — entry and exit thresholds from cost-aware optimisation, not a fixed ±2σ.
Maximise expected profit per unit time subject to a variance cap, with cost `c` inside the
objective (`research/paper/statarb/1811.09312`). Half-life acts as a gate before any trade.

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
