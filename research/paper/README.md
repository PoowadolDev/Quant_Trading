# Non-Directional Trading — Paper Library by Topic

Papers sourced from arXiv (via the `literature_search_arxiv` skill), organised by the seven
topics that make up the mathematics of non-directional (market-neutral) trading. **Every
paper was read before being saved**, and each topic folder has a `_triage.md` recording what
was kept, what was rejected, and why — the test applied was "can this be implemented and
trusted on live capital", not "is this interesting".

Rejections are documented rather than silently dropped, because several of them are more
instructive than the keeps: they show the specific ways a backtest manufactures an edge that
is not there.

| # | Topic | Folder | Kept | Rejected |
|---|-------|--------|------|----------|
| 1 | Neutrality construction | [`neutrality/`](neutrality/) | 1 | 1 |
| 2 | Statistical arbitrage / pairs / OU | [`statarb/`](statarb/) | 3 | 1 |
| 3 | Volatility arbitrage | [`volatility_arb/`](volatility_arb/) | 4 | 1 |
| 4 | Market making / order flow | [`market_making/`](market_making/) | 4 | 1 |
| 5 | Relative value / dispersion / carry | [`relative_value/`](relative_value/) | 3 | 1 |
| 6 | Portfolio construction + sizing | [`portfolio_sizing/`](portfolio_sizing/) | 3 | 1 |
| 7 | Validation mathematics | [`validation/`](validation/) | 3 | 1 |

Pre-existing papers on backtest overfitting sit at this folder's root (`1905.05023`,
`2209.05559`, `2210.11532`, `2604.18821`, `2605.17937`, `2606.31251`, plus the `wyckoff/`
and `volume/` subfolders) with digests under `research/wiki/`. They were left in place and
are cross-referenced from `validation/_triage.md` rather than duplicated.

## What each topic contributes

**1. Neutrality construction** — how a raw signal becomes a portfolio with zero market
exposure. The one keep (Capital Fund Management) shows portfolio construction moving Sharpe
from 0.34 to 1.19 on the *same* momentum signal, and supplies a beta-neutral projection that
needs no matrix inversion.

**2. Statistical arbitrage** — spread construction (cointegration or factor/eigenportfolio
residuals), OU parameter estimation, half-life gating, and cost-aware entry/exit thresholds
instead of a fixed ±2σ rule.

**3. Volatility arbitrage** — arbitrage-free surface fitting, discretisation-invariant
premium estimators, hedging with costs and tail risk in the objective, and model-independent
bounds for the jump risk that log-contract replication ignores.

**4. Market making** — closed-form quotes with inventory constraints, an inventory-risk dial
that trades mean PnL for Sharpe, folding a price forecast into placement, and a real-data RL
study whose transferable lesson is about reward design, not the algorithm.

**5. Relative value** — the crypto perpetual basis with a cost-aware no-arbitrage band
(Sharpe 1.8 on BTC at retail fee tiers), the dispersion-trade PnL identity and its volga
term, and repairing implied correlation matrices so cross-sectional signals are meaningful.

**6. Portfolio construction + sizing** — turnover penalisation *is* covariance shrinkage;
sample covariance understates optimised risk by `1/(1−q)` with `q = N/T`; and leverage must
come from time-average growth because Sharpe is leverage-invariant.

**7. Validation** — derive rule parameters instead of searching for them; condition on the
search with empirical Bayes rather than blunt FDR hurdles; use discrete-p-value FDR for
thousands of rules; report validation gates individually instead of as a composite grade.

## Recurring failure modes found in the rejected papers

Collected here because they are the checks to run against any new backtest, including your
own:

- **Mid-price fills.** Entry and exit at the mid, no half-spread and no commissions, in
  instruments (single-name options, small caps) where the spread is a large fraction of the
  edge. — `volatility_arb`
- **Notional-denominated returns.** Dividing PnL by a large fixed notional and averaging
  trade returns produces a low reported volatility and a near-zero drawdown that describe
  the accounting, not the book. A short-put strategy reporting 0.0% max drawdown across 2008
  is the tell. — `volatility_arb`
- **Overlapping-window t-statistics.** Forward realised-volatility or multi-day return
  windows share data; effective sample size can be overstated more than tenfold. — `volatility_arb`
- **An abstract that contradicts the tables.** One paper claims its OU model beats a naive
  rolling z-score baseline; the tables show it losing, 0.47 Sharpe against 0.78. — `statarb`
- **No empirical section at all.** A portfolio-construction method whose own stability
  theorem defers the likeliest production failure mode to being "handled empirically". — `neutrality`
- **Simulator-internal evidence.** Strategy validated only inside a simulator the author
  designed, against a weak baseline, with no historical out-of-sample test. — `market_making`
- **Solving the inverse problem.** Deriving the funding rate consistent with an assumed
  price, when in reality the funding mechanism is fixed and the price deviates — plus a
  zero-cost assumption that removes the band deciding whether a deviation is actionable. — `relative_value`
- **Composite scores that do not forecast.** Five sound validation gates compressed into one
  grade, which then shows no significant forward relationship on unseen real data
  (ρ = 0.013, p = 0.40) and barely improves on one of its own components. — `validation`

## Suggested reading order for implementation

1. `validation/` first — it decides what the rest of the work is allowed to conclude.
2. `portfolio_sizing/` — the covariance estimator and cost treatment that every construction
   method below depends on.
3. `neutrality/` — the step that makes a strategy non-directional at all.
4. Then whichever strategy family is in scope: `statarb/`, `volatility_arb/`,
   `market_making/`, or `relative_value/`.

## Open gaps

- **Adverse selection / flow toxicity** — no usable estimator found on arXiv (Kyle's `λ`,
  Glosten-Milgrom informed-trader updating, VPIN). Needed before quoting live. See
  `market_making/_triage.md`.
- **Fixed-income relative value** — the yield-curve PCA level/slope/curvature decomposition
  and PC1/PC2-neutral butterfly weighting. Searches returned ML term-structure forecasting
  and credit basis measures instead. Low priority unless rates enter scope. See
  `relative_value/_triage.md`.
