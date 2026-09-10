# Topic 1 — Neutrality Construction (beta / factor / sector neutral portfolios)

Scope: how a raw cross-sectional signal is turned into a portfolio with zero market
(and optionally sector/factor) exposure. This is the step that makes a strategy
non-directional; the signal itself is taken as given.

Source: arXiv API (literature_search_arxiv skill). Each paper below was read before
the keep/reject decision — the test applied was "can this be implemented and trusted
on live capital", not "is this interesting".

## Kept

### 1810.08384 — Portfolio Construction Matters (Ciliberti & Gualdi, Capital Fund Management, 2018)
`1810.08384_portfolio_construction_matters.pdf` · https://arxiv.org/abs/1810.08384

Compares five construction schemes applied to the *same* momentum signal: Fama-French
top/bottom 30% tercile, cash-neutral proportional-to-signal, crude beta rescaling,
constrained beta-optimal, and eigenvalue-truncated Markowitz.

Directly usable results:

- Closed-form beta-neutral projection that needs **no matrix inversion**:
  `x = p - (wᵀCp / wᵀCw) · w`, where `p` is the ranked predictor, `C` the covariance
  matrix and `w` the index weight vector. This is the solution of
  `min (p-x)ᵀC(p-x)` s.t. `β·x = 0`, using `β ∝ Cw`.
- Markowitz with the covariance matrix truncated to its top `k` eigenvectors:
  `C ≈ σᵢσⱼ(Σ_{α≤k} λ_α v^α_i v^α_j + ε²δᵢⱼ)`, with `ε²` set so total variance is
  preserved (`Tr C = Σσᵢ²`). Tested up to `k = 5`.
- Measured effect on the same signal: Sharpe 0.34 (Fama-French terciles) versus 1.19
  (truncated Markowitz, `k = 5`), t-stat > 3 for the latter and only 1.8 for the
  former. Replicated on CRSP US data back to 1927 and across US / Canada / Europe /
  Japan / Australia pools, with a causal liquidity-based universe (top-N by 3-month
  ADV, refreshed quarterly). Transaction costs are treated in a later section.

Why it is worth applying: the paper isolates portfolio construction as the variable
and shows it moves Sharpe by more than most signal research does, using an estimator
cheap enough to run daily. The claims are supported over ~90 years of data and five
regions, so the effect is not a single-sample artefact.

## Rejected

### 2604.16773 — Topological Risk Parity (Nayar et al., FMI Technologies, 2026)
https://arxiv.org/abs/2604.16773

Rooted minimum-spanning-tree allocator for long/short market-neutral portfolios; a
"Semi-Supervised" variant anchors SPY as root and the 11 sector ETFs as the second
layer, then multiplies each asset's signal by a topological factor and L1-normalises
to target leverage. Conceptually attractive — unlike Hierarchical Risk Parity it
handles signed signals and does not propagate a parent's weight fully to its children,
which is meant to survive within-cluster correlation spikes.

Not kept: the paper contains **no backtest and no empirical section at all**. Its own
stability theorem is explicitly conditional and states that changes in the MST, root,
or active set "should be handled empirically" — i.e. the failure mode most likely to
bite in production is left open. With 1810.08384 offering a validated alternative for
the same job, this is an idea to revisit if it is ever published with results.

## Cross-reference

`../statarb/1908.02164_statarb_multiple_cointegrated_stocks.pdf` also belongs to this
topic: it solves the HJB portfolio problem twice, once unconstrained and once with an
explicit market-neutrality constraint, so it shows the cost of imposing neutrality
inside an optimal-control formulation.
