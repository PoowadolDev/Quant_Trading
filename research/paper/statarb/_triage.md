# Topic 2 — Statistical Arbitrage / Pairs / Cointegration / Ornstein-Uhlenbeck

Scope: constructing a mean-reverting spread (cointegration, residuals against factors),
modelling it as an OU process, estimating its parameters, and choosing entry/exit levels.
PnL comes from the spread reverting, not from the direction of either leg.

Source: arXiv API (literature_search_arxiv skill). Every paper was read before deciding;
the bar is "implementable, and the evidence survives costs and out-of-sample testing".

## Kept

### 1811.09312 — Estimation of the OU Process Using Ultra-High-Frequency Data, with an Intraday Pairs Trading Application (Holý & Tomanová, 2018, rev. 2025)
`1811.09312_ou_estimation_uhf_intraday_pairs.pdf` · https://arxiv.org/abs/1811.09312

The strongest of the four for intraday work. Two results matter:

- **Noise-robust maximum-likelihood estimator of the OU parameters** for irregularly
  spaced tick data. The paper proves that an OU process contaminated by independent
  Gaussian white noise and sampled at discrete equidistant times is exactly an
  ARMA(1,1) process, which is what makes the noise-robust likelihood tractable. Naive
  estimators are shown (simulation, Table 1) to be materially biased by microstructure
  noise — the same bias that inflates realized variance.
- **Entry/exit levels from optimisation rather than a fixed ±2σ rule**: maximise
  expected profit per unit time subject to a cap on variance of profit per unit time,
  with the transaction cost `c` inside the objective, giving optimal entry `a*` and
  exit `b*` per pair per day. Pairs are traded only when the optimal expected profit
  clears a threshold `ζ`, and positions are force-closed before the bell to remove
  overnight risk.

Empirical study: all 21 pairs from 7 Big Oil names, mid-2015 to late-2018, walk-forward
with a 6-month training window. The noise-robust estimator (TICK-MLE-NR) beats the
noise-sensitive one, and per-pair trade counts, hit rates, profits and Sharpes are
reported individually.

Honest caveats the paper itself flags: profit is quite sensitive to the thresholds
`η` (variance cap) and `ζ` (minimum mean profit) — with no cap on expected mean, almost
every pair trades every day and the strategy loses heavily. Trading is also very
unevenly distributed across years (2017 was nearly flat because spread volatility was
low). Both are parameters to walk-forward, not to fit once.

### 1908.02164 — Statistical Arbitrage for Multiple Co-Integrated Stocks (Li & Papanicolaou, 2019, rev. 2022)
`1908.02164_statarb_multiple_cointegrated_stocks.pdf` · https://arxiv.org/abs/1908.02164

Generalises pairs trading to *many* names at once, following Avellaneda & Lee (2010):
spreads are the residuals from regressing each stock's total return on factor returns,
where the factors are **eigenportfolios** (PCA of the return covariance) rather than
sector ETFs — which is what makes long backtests possible before ETFs were liquid.
Optimal weights solve an HJB PDE, derived twice: unconstrained, and with an explicit
market-neutrality constraint. Includes sufficient conditions on the parameters for
long-term stability of the HJB solution (matrix Riccati equation) and for stable
portfolio growth rates.

Backtest: S&P 500 constituents, 2000-2021, sliding-window estimation, 375 names with
full history, and an explicit regression-based **survivorship-bias adjustment** rather
than silently trading today's index membership.

Three conclusions worth carrying into practice: the eigenportfolio-factor model does
generate plenty of cointegrated names over long horizons; the optimal portfolios are
**sensitive to parameter estimation** (consistent with Yeo & Papanicolaou 2017, who
show Sharpe varying with the estimation window); and profitability concentrates in
high-volatility regimes. The last point argues for a regime filter on top of the
strategy rather than constant risk.

### 2309.00875 — A Hidden Markov Model for Statistical Arbitrage in International Crude Oil Futures Markets (Fanelli, Fontana & Rotondi, 2023)
`2309.00875_hmm_statarb_crude_oil_futures.pdf` · https://arxiv.org/abs/2309.00875

Extends classical pairs trading to three cointegrated futures (Brent, WTI, Shanghai)
and models the cointegration spread as a **mean-reverting regime-switching process
modulated by a hidden Markov chain**, with online filter-based parameter estimators —
so parameters update as each observation arrives instead of being refit in batch.

This is the best template in the set for *how to evaluate* a non-directional strategy:

- Transaction costs are not assumed; the per-contract cost `cᵢ` is estimated as the
  average effective daily half bid-ask spread over the sample (highest, as expected,
  for the Shanghai contract).
- Sharpe significance via the Ledoit-Wolf (2008) test with a fixed-size circular block
  bootstrap (2,000 replications, 20 blocks), not a bare Sharpe number.
- **White's Reality Check** across the strategy variants, because several bandwidth
  levels `α` were tried — the data-snooping correction most backtests skip.
- Passive benchmarks that incur no transaction costs (buy-and-hold S&P, ETF) are
  included, so the strategy has to beat something free.

Result: the best variant reaches annualised Sharpe ≈ 1.1-1.3 net of the estimated
costs, significant at 5% and confirmed as the Reality Check winner. Strategies using
only the three traditional benchmarks (Brent, WTI, Dubai) are *not* profitable — the
edge comes specifically from including the Shanghai contract.

## Rejected

### 2412.12458 — An Application of the Ornstein-Uhlenbeck Process to Pairs Trading (Suchato et al., 2024)
https://arxiv.org/abs/2412.12458

Rejected on its own evidence. The paper is clear and its formulas are correct — spread
`S = Pᵢ - Pⱼ`, OU discretised to the AR(1) regression `S_{t+1} = aS_t + b + ε`, then
`λ = -ln(a)/δ`, `μ = b/(1-a)`, `σ = sd(ε)·√(-2ln(a)/(δ(1-a²)))` — and the pair-selection
pipeline (mean-squared-distance ranking, Engle-Granger cointegration test, manual
industry review) is sensible.

But the OU version **loses to the naive rolling 30-day z-score baseline it is meant to
beat**: Sharpe 0.47 versus 0.78, with lower return (4.9% vs 7.2%) at slightly higher
volatility. The abstract claims the opposite of what the tables show. On top of that:
no transaction costs, no slippage, a single one-year test window, arbitrarily fixed
25th/75th-percentile thresholds, and it is stated coursework "for educational purposes
only".

The formulas above are worth keeping as an implementation crib; the paper is not
evidence that OU-based pairs trading works, so it is not stored. 1811.09312 gives the
same estimation step done properly, plus optimised thresholds and real costs.

## Practical ordering for implementation

1. Spread construction — factor/eigenportfolio residuals (1908.02164) if trading a
   wide universe; a cointegration test on a shortlist (Engle-Granger / Johansen) if
   trading a handful of instruments.
2. OU parameter estimation — noise-robust if intraday (1811.09312); plain AR(1) fit is
   only defensible on daily bars.
3. Half-life `= ln2/θ` as the first gate: discard any spread whose half-life exceeds
   the intended holding horizon.
4. Entry/exit from cost-aware optimisation (1811.09312), not a fixed z-score.
5. Regime awareness — expect the edge to concentrate in high-volatility periods
   (1908.02164) and to switch regime (2309.00875).
6. Validation — cost estimates from half-spreads, Ledoit-Wolf Sharpe test, and White's
   Reality Check over every variant tried (2309.00875).
