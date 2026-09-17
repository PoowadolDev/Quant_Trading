# Topic — Residual / factor-based statistical arbitrage (not level cointegration)

Scope: statistical arbitrage where the tradable signal is the **residual of a factor model on
returns**, rather than a cointegrating combination of **price levels**. This is a different
model class from `statarb/`, not a refinement of it, and it exists as its own folder because
the distinction is the one this project's own results turned on.

Source: arXiv, located via the OpenAlex API and downloaded with the `literature_search_arxiv`
skill's download script. Each paper below was read before the keep/reject decision — the test
applied was "can this be implemented and trusted on live capital", not "is this interesting".

## Why this topic was opened, 2026-09-17

The project's own search had by this date run 21 logged screens over 3,629 pair-tests across
forex, crypto, equities, indices and commodities, with **zero survivors**. The failure analysis
identified three causes, and all three are addressed by this literature rather than by more
screening:

1. **Breadth.** Information ratio scales as $IC\times\sqrt{\text{breadth}}$. With an
   information coefficient of 0.02–0.05, typical of statistical arbitrage, a Sharpe worth
   having needs hundreds to thousands of simultaneous positions. Every candidate this project
   produced traded 30–74 times over 6–24 years, i.e. breadth of roughly one. The measured
   Sharpes (0.28 ± 0.22 on `AUDUSD~USDNOK`) match what that arithmetic predicts, so the
   machinery was reporting correctly and the search design was wrong.
2. **The wrong model.** Level cointegration requires a stable long-run price *ratio*.
   `DOT~FIL`'s hedge ratio walked monotonically from 0.436 to 1.291 and never returned; crypto
   relative valuations reprice permanently. A residual construction does not need that
   assumption.
3. **Financing.** The recurring cause of death was carry, not signal: `SPY~DIA` +205 gross
   against −752 carry, `EURUSD~GBPUSD` +343 against −462, `XLP~XLB` +528 against −754.

## Kept

### 1901.09309 — High-dimensional statistical arbitrage with factor models and stochastic control (Guijarro-Ordonez, Stanford, 2019, rev. 2021)
`1901.09309_highdim_statarb_factor_models_stochastic_control.pdf` · https://arxiv.org/abs/1901.09309
Digest: [`../../wiki/statarb_residual/1901.09309_highdim_statarb_factor_models_stochastic_control_digest.md`](../../wiki/statarb_residual/1901.09309_highdim_statarb_factor_models_stochastic_control_digest.md)

Addresses all three causes above in one framework, with closed-form strategies.

Directly usable results:

- **Market-neutral portfolios with no optimiser and no matrix inversion.** With
  $c_{ik}=\sum_j\tilde\Lambda_{jk}\Lambda_{ij}$, the fixed portfolio
  $\tilde p_i=(-c_{i1},\dots,1-c_{ii},\dots,-c_{iN})$ earns exactly the $i$-th residual and is
  factor-neutral *by construction*. Neutrality is an algebraic identity, so unlike a fitted
  hedge ratio it cannot silently drift — which is precisely the failure mode that produced
  this project's 28 negative-beta forex pairs scoring 100% net exposure.
- **Position size derived rather than searched.** The optimal allocation is affine in
  $A(\mu-X_t)$, so the entry threshold stops being a free parameter. This matters beyond
  elegance: every swept threshold is a trial, and the deflated-Sharpe benchmark grows with
  $\log N$ of the trial count. Removing the sweep removes a whole dimension of selection bias.
- **Costs change what you trade toward, not just how much.** Under quadratic costs the optimum
  tracks an **aim portfolio** that is a forward-looking average of *future* frictionless
  optima, at rate $\sqrt{\gamma/\lambda}\tanh(\sqrt{\gamma/\lambda}(t-T))$ — a single scalar
  governing the cost/aggression trade-off.
- **A documented failure regime.** Heavier factor loadings mean larger $p$, more leverage, and
  at the largest $p$ *combined with* transaction costs, heavy losses (Figure 5(c),(i)). This is
  a known-answer test for any implementation, and the analogue of a large hedge ratio in a pair.

The honest limitation, in the author's own words: the simulations assume perfect specification
and known parameters, so *"the derived strategies will always produce benefits by
construction… This situation, however, might not apply under parameter misspecification."*
Real-data experiments are deferred to a separate paper. **The profits in Section 5 validate the
control algebra, not an edge** — which is exactly the distinction this project exists to
enforce, so the paper is being read for its construction and its cost treatment, not as
evidence that the method makes money.

## Pending

### 2106.04028 — Deep Learning Statistical Arbitrage (Guijarro-Ordonez, Pelger & Zanotti, 2022)
`2106.04028_deep_learning_statistical_arbitrage.pdf` · https://arxiv.org/abs/2106.04028
Downloaded, 68 pages, **not yet digested.**

Same lead author. Constructs arbitrage portfolios as residual portfolios from *conditional
latent* asset-pricing factors, extracts time-series signals with a convolutional transformer,
and forms an optimal trading policy under constraints — with a comprehensive empirical study on
**daily US equities**, which is the real-data evidence 1901.09309 explicitly defers.

Read this one for the empirical side; read 1901.09309 for the implementable analytics. The
machine-learning signal extraction is the part least transferable to this project as it stands,
since it needs infrastructure the project does not have and reintroduces a large hyperparameter
search — the very thing the closed-form approach removes.

## Rejected

None yet. Only two papers have been assessed in this topic.

## Practical ordering for implementation

1. **Factor construction and residuals** — Algorithm A of the digest. Fit PCA across a
   universe, build $\tilde p_i$, accumulate $X_t$, estimate $A,\mu,\sigma$. This alone replaces
   the project's screening premise and is testable against the existing machinery.
2. **Portfolio sizing** — Algorithm B, frictionless, to confirm the residuals behave before any
   cost model is layered on.
3. **Cost-aware tracking** — Algorithm C, which is where this project's candidates have always
   died and therefore where the method must prove itself.
4. Only then consider 2106.04028's learned signals, and only with the trial count charged.
