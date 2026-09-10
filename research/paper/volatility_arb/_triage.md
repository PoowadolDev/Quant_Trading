# Topic 3 — Volatility Arbitrage

Scope: strategies whose PnL comes from the second moment rather than direction. The
governing identity for a delta-hedged option is

    PnL ≈ ½ ∫ Γ_t S_t² (σ²_realized,t − σ²_implied) dt

so the work splits into three jobs: fit a usable, arbitrage-free implied surface;
measure the variance/tail risk premium without letting estimation artefacts create it;
and hedge the position so that the gamma term above is actually what you collect.

Source: arXiv API (literature_search_arxiv skill). Each paper was read before deciding.

## Kept

### 1204.0646 — Arbitrage-free SVI Volatility Surfaces (Gatheral & Jacquier, 2012, rev. 2013)
`1204.0646_arbitrage_free_svi_surfaces.pdf` · https://arxiv.org/abs/1204.0646

The standard reference for fitting the surface you then trade against. SVI is popular
because total implied variance is linear in log-strike `k` as `|k| → ∞`, consistent with
Roger Lee's moment formula, and because the large-maturity limit of the Heston smile is
exactly SVI — but a naively calibrated SVI smile can be arbitrageable, which quietly
poisons any rich/cheap signal computed from it.

What the paper delivers:

- Necessary and sufficient conditions for absence of **calendar spread arbitrage**
  (total variance `w(k,t)` increasing in `t`) and for absence of **butterfly arbitrage**
  (non-negative density; call prices decreasing and convex in strike).
- A large class of SVI surfaces with a simple **closed-form** representation that is
  guaranteed free of static arbitrage, plus three equivalent slice parameterisations
  with the exact mapping between them.
- A concrete calibration algorithm that removes butterfly arbitrage when it appears,
  and interpolation/extrapolation rules that keep the surface arbitrage-free.
- A worked numerical fit to SPX options data.

Why it applies: this is the piece of infrastructure every other vol-arb idea sits on.
It is closed-form, so it is fast enough to refit intraday, and the arbitrage checks are
cheap gates that catch bad quotes and bad fits before they become "signals".

### 1602.00865 — Tail Risk Premia for Long-Term Equity Investors (Rauch & Alexander, 2016)
`1602.00865_tail_risk_premia_moment_swaps.pdf` · https://arxiv.org/abs/1602.00865

How to *measure* the premium you intend to harvest, without the measurement itself
creating the result. Uses the discretisation-invariant sub-class of moment swaps with
Neuberger's aggregating property, so variance, skewness and kurtosis premia estimated
at different sampling frequencies remain comparable — the usual estimators do not, and
the paper shows the resulting distortions in prior work.

Empirical study: S&P 500, 18 years of daily data, horizons from 1 to 6 months, with an
explicitly careful data-construction methodology aimed at avoiding artefacts.

Findings that matter for signal design: momentum is the dominant driver of both the
skewness and kurtosis risk premia (which are strongly negatively correlated with each
other), while the variance risk premium responds positively to size and negatively to
growth. The correlation between the variance premium and the tail premia is lower than
previously reported, especially at high sampling frequency — meaning a short-variance
book and a short-tail book are less redundant, and less jointly hedged, than the older
literature suggests.

### 1104.4010 — Model-Independent Hedging Strategies for Variance Swaps (Hobson & Klimmek, 2011)
`1104.4010_model_independent_variance_swap_hedging.pdf` · https://arxiv.org/abs/1104.4010

The correction to the textbook story. In the idealised case — continuous monitoring,
continuous paths — a variance swap is exactly replicated by a static portfolio of puts
and calls plus a dynamic position in the asset (this is the basis of the VIX contract).
Real contracts are **discretely monitored** and real assets **jump**, and then that
replication is no longer exact.

The paper derives model-independent, no-arbitrage upper and lower bounds on the variance
swap price along with the corresponding super- and sub-replicating strategies, using only
the observed prices of vanillas — no model for the underlying at all — and characterises
which bounds are optimal. The form of the hedge depends critically on the swap's kernel
(squared simple returns, squared log returns, squared price differences), and the paper
shows that downward jumps contribute asymmetrically for the log-return kernel.

Why it applies: it is not a strategy but a risk control. If you sell variance and hedge
with the log-contract portfolio, this tells you the size and direction of the gap you
are carrying, and gives a hedge that holds pathwise even with jumps. Sell at the upper
bound with the super-replicating hedge and you cannot lose under any scenario.

### 2504.06208 — Deep Hedging with Options Using the Implied Volatility Surface (François, Gauthier, Godin & Pérez-Mendoza, 2025)
`2504.06208_deep_hedging_implied_vol_surface.pdf` · https://arxiv.org/abs/2504.06208

Reinforcement-learning hedging of an index option book, where the state includes
characteristics of the **full IV surface** rather than just ATM or short-term vol, and
where the agent may hedge with options as well as the underlying.

Reasons it survives the "would I run this" test:

- **Transaction costs are in the objective**, not bolted on afterwards: proportional
  rates `κ₁` on the underlying and `κ₂` on the hedging option, stress-tested at
  `κ₂ ∈ {0.5%, 1%, 1.5%, 2%}`.
- Risk measures include **CVaR₉₅**, not just MSE, so the tail is priced.
- Benchmarks are strengthened before comparison — delta and delta-gamma hedging with
  no-trade regions tuned separately per risk measure — rather than being straw men.
- Tested on **historical out-of-sample** straddles, 2020-2023, a period spanning both a
  volatility shock and a calm regime.
- The strategy explicitly accounts for the variance risk premium embedded in the
  hedging instruments, which is the term that makes hedging with options different from
  hedging with the underlying.

Caveat: results depend on the market simulator used for training (joint dynamics of
S&P 500 returns and the IV surface), so the simulator is part of the strategy and would
need re-validation on any other underlying.

## Rejected

### 2609.01183 — Harvesting the Variance Risk Premium in Nuclear and Energy Equities (Miao & Sorokina, 2026)
https://arxiv.org/abs/2609.01183

Systematic cash-secured short-put strategy on ~45 nuclear/energy-adjacent names,
OptionMetrics + CRSP, 2000-2024, 0.30-delta / 45-DTE put selection.

The reported headline is annualised return 18.7% at 2.4% volatility, **Sharpe 7.81 and
maximum drawdown 0.0%** over 300 months, versus 15.4% for the equal-weight stock
benchmark. A short-put book cannot have a zero drawdown across 2008 and 2020; the number
is an artefact of how returns are aggregated, and it invalidates the headline comparison.
Specifically:

- Monthly portfolio return is defined as the equal-weight mean of *ticker-level average
  trade returns* for that month, with `trade return = pnl / strike`. Averaging trade
  returns and dividing by the full cash-secured strike smooths away the path, so the
  reported volatility and drawdown describe the averaging procedure more than the book.
- PnL is entry mid minus exit mid. **No bid-ask cost and no commissions** — for
  single-name equity options, especially the small names the paper says carry the
  highest IV/RV ratios, the half-spread is a large fraction of the premium collected.
- **Early assignment is not modelled**, acknowledged as a simplification.
- The VRP t-statistics are computed on overlapping 21-day forward realised-vol windows;
  the authors themselves note effective `n` is overstated up to ~21-fold and that a
  `/√21` correction pulls the best names down from `t ≈ 12.7` to `t ≈ 2.8`.

Not saved as a tradable result. Two components are still worth reusing and are recorded
here so the paper does not need to be re-read: the GARCH(1,1) realised-vol estimator with
a **per-stock long-run anchor** `ωᵢ = r̄ᵢ²(1 − α − β)` (α = 0.09, β = 0.90), which the
authors adopt because EWMA (`ω = 0`) collapses toward zero in quiet periods and spuriously
inflates the IV/RV ratio; and the ATM IV proxy defined as the open-interest-weighted
average IV of puts with `|δ| ∈ [0.40, 0.60]` and `DTE ∈ [15, 45]`.

## Practical ordering for implementation

1. Fit the surface with arbitrage-free SVI (1204.0646); treat butterfly/calendar
   violations as a data-quality alarm, not something to smooth over.
2. Compute the premium with discretisation-invariant estimators (1602.00865) so the
   number does not change when you change sampling frequency.
3. Size and hedge the position with costs and tail risk in the objective (2504.06208).
4. Bound the residual jump/discrete-monitoring risk of any variance exposure with the
   model-independent super-hedge (1104.4010).
5. Before believing any short-vol backtest, check it against the failure list in the
   rejection above — mid-price fills, notional-denominated returns, and overlapping-window
   t-statistics are the three that most often manufacture a premium that is not there.
