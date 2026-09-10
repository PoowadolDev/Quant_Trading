# Topic 4 — Market Making / Order Flow

Scope: quoting both sides continuously and earning the spread, while inventory risk and
adverse selection try to take it back. Non-directional by construction — the target
inventory is flat — so the mathematics is about where to place quotes, how hard to skew
them against inventory, and how to fold a price forecast in without turning the book
into a directional bet.

Source: arXiv API (literature_search_arxiv skill). Each paper was read before deciding.

## Kept

### 1105.3115 — Dealing with the Inventory Risk: A Solution to the Market Making Problem (Guéant, Lehalle & Fernandez-Tapia, 2011, rev. 2012)
`1105.3115_gueant_lehalle_inventory_risk.pdf` · https://arxiv.org/abs/1105.3115

The paper that makes the Avellaneda-Stoikov framework usable in production. Same setup —
reference price `S_t` is Brownian with volatility `σ`, order arrival intensity decays with
the distance of the quote from `S_t`, the maker maximises expected utility of PnL over a
finite horizon — but with two results that matter operationally:

- The HJB equations are transformed into a **system of linear ODEs**, so no PDE has to be
  solved numerically at runtime. The problem is solved *with inventory constraints*, which
  is the realistic case (position limits, margin).
- A **closed-form approximation of the optimal quotes** derived from a spectral
  characterisation, plus the asymptotic behaviour of the quotes. This is the form a quoting
  engine can actually evaluate every tick.

One author was Head of Quantitative Research at Crédit Agricole Cheuvreux, and it shows in
what the paper chooses to deliver: explicit formulas rather than a numerical scheme.
Treat this as the baseline quoting model, and Avellaneda-Stoikov as its predecessor.

### 1206.4810 — High-Frequency Market-Making with Inventory Constraints and Directional Bets (Fodra & Labadie, 2012)
`1206.4810_inventory_constraints_directional_bets.pdf` · https://arxiv.org/abs/1206.4810

Extends both Avellaneda-Stoikov and 1105.3115 to a **general, non-martingale mid-price**
under exponential or linear PnL utility. This is the hook for putting a signal into the
quotes: if you expect prices up, you post asymmetric quotes that favour your bid being
hit. Written at a quant fund (EXQIM), and explicit about preferring "explicit controls
that minimise potential losses (a sub-solution)" over "highly implicit,
numerically-intensive controls that optimise the PnL" — the right trade for live code.

The practical contribution is an **inventory-risk-aversion parameter** that penalises
ending the day with non-zero inventory. It gives direct control of inventory and indirect
control over the moments of the PnL distribution (variance, skewness, kurtosis, VaR), so
it functions as a risk-reward dial rather than a black box. Quantified on a mean-reverting
mid-price: relative to the martingale benchmark, the maker can take +15% mean PnL with
much larger inventory and PnL risk, or give up 5% of benchmark PnL and **more than double
the Sharpe ratio**.

Caveat: numerical simulation only, no historical backtest. Kept anyway because what it
provides is a control formula and an explicit risk trade-off curve, not a claimed edge —
the same category of artefact as an arbitrage-free surface parameterisation.

### 2101.03086 — Market Making with Stochastic Liquidity Demand (Capponi, Figueroa-López & Yu, 2021)
`2101.03086_stochastic_liquidity_demand_forecasts.pdf` · https://arxiv.org/abs/2101.03086

Discrete-time LOB model with an **explicit characterisation** (closed form) of the optimal
quotes. The number of filled orders per period is linear in the distance between the
fundamental price and the quote, but with **random slope and intercept** — demand itself
is stochastic, which is closer to reality than a fixed arrival-intensity curve. The maker
pays an end-of-day liquidation cost from linear price impact, which is what actually
enforces flat-at-the-close behaviour.

The reason to keep it alongside 1105.3115: the optimal placement **incorporates forecasts
of future fundamental-price changes** in a parsimonious way, so any external alpha (time
series or ML) plugs into the quoting rule through a single term `Δ_{t_k}` rather than
being bolted on as a separate overlay.

Structural findings that translate into quoting behaviour: randomness in the demand slope
*reduces* the inventory-management motive; positive correlation between demand slope and
investors' reservation prices *widens* spreads; and simultaneous arrival of buy and sell
market orders reduces the shadow cost of inventory, pushes the maker to reduce price
pressure to execute larger flows, and creates nonlinear intraday spread patterns. The
empirical study shows the strategy beating variants that ignore demand randomness,
simultaneous two-sided arrivals, and local drift.

### 1804.04216 — Market Making via Reinforcement Learning (Spooner, Fearnley, Savani & Koukorinis, 2018)
`1804.04216_market_making_via_reinforcement_learning.pdf` · https://arxiv.org/abs/1804.04216

The empirical counterweight to the three stochastic-control papers, and unusually honest
about its own limits.

Setup: a LOB simulation **reconstructed from real historical data** — 10 securities across
4 sectors, 8 months of 2010, 5 levels of book depth. Agent orders join the back of the
queue at their price level, and cancellations are assumed uniformly distributed through
the queue, so **queue position is modelled** rather than assumed away. The paper explicitly
flags the limitation that the agent's orders cannot affect the replayed market, and argues
it is acceptable only because the modelled size is negligible — the correct caveat, stated
rather than hidden. Learning is temporal-difference with a linear combination of tile
codings.

The result worth carrying over is about the **reward function**, not the algorithm: the
"natural" choice (incremental PnL) rewards speculation, so the agent takes directional
positions and produces a volatile equity curve. Dampening the speculative component of
reward makes the learned policy target near-zero inventory and produces a materially
smoother curve. Out-of-sample per-security results (Table 6) show the consolidated agent
holding far smaller mean absolute positions than the benchmarks — single-digit to low
hundreds of units versus thousands — with better risk-adjusted PnL on most names, **but it
loses on 2 of 10 securities** (ING.AS, NOK1V.HE), which the paper reports plainly.

## Rejected

### 2109.15110 — Deep Hawkes Process for High-Frequency Market Making (Kumar, 2021)
https://arxiv.org/abs/2109.15110

Models order arrivals with a Deep Hawkes process, creating a feedback loop between arrivals
and the state of the book with self- and cross-excitation, and accounts for cancellations
that change queue position. Conceptually the right machinery for order-flow clustering.

Not kept because the evidence is entirely **internal to a simulator the author also
designed**: the strategy is evaluated on simulated limit order markets, validated only by
reproducing stylised facts, and the comparison is against a weak baseline (a probability
density estimate of the fundamental price). There is no historical backtest and no
real-data out-of-sample result, so nothing here supports deploying it. 1804.04216 does the
data-driven version of the same job with real book reconstruction and honest failure cases.

## Gap not covered by these papers

Adverse selection is discussed qualitatively in all four but none of them gives a usable
**flow-toxicity estimator**. The relevant tooling — Kyle's `λ` as price impact per unit
signed flow, Glosten-Milgrom Bayesian updating on informed-trader probability, VPIN — is
mostly outside arXiv. Worth sourcing separately before quoting live, because it is the
mechanism that turns a profitable backtest into a losing book.

## Practical ordering for implementation

1. Baseline quotes from the closed-form approximation with inventory constraints
   (1105.3115).
2. Add the inventory-risk-aversion dial and tune it against the PnL moments you can
   tolerate, not against mean PnL (1206.4810).
3. Feed any price forecast in through the placement rule itself (2101.03086), and let the
   demand-slope randomness relax the inventory term rather than over-skewing.
4. Validate on a book reconstructed from real data with queue position modelled, using a
   dampened reward or an equivalent inventory penalty, and report per-instrument results
   including the losers (1804.04216).
5. Source an adverse-selection measure separately — see the gap above.
