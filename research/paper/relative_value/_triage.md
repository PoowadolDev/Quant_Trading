# Topic 5 — Relative Value / Dispersion / Carry

Scope: trades between two prices of the same risk, held so that the outright direction
cancels. Three families are covered here: dispersion (index volatility against the
volatility of its components, i.e. a correlation trade), the perpetual-futures basis and
funding carry, and the forward-looking correlation matrix that dispersion signals depend on.

Source: arXiv API (literature_search_arxiv skill). Each paper was read before deciding.

## Kept

### 2212.06888 — Fundamentals of Perpetual Futures (He, Manela, Ross & von Wachter, 2022, rev. 2024)
`2212.06888_fundamentals_of_perpetual_futures.pdf` · https://arxiv.org/abs/2212.06888

The most directly applicable paper in this topic, and the one to start from for crypto
carry. Perpetuals have no expiry, so nothing forces convergence to spot; instead longs pay
shorts a funding rate proportional to the gap. That makes the classic cash-and-carry
argument inapplicable without extra structure, which is exactly what the paper supplies.

- **No-arbitrage price in frictionless markets**: `F_t = (1 + r/κ) S_t` (for an underlying
  paying no interest), derived from the absence of *random-maturity* arbitrage — the right
  notion for a contract the holder can close at a time of their choosing.
- **No-arbitrage band with costs**: `λS_t − C ≤ F_t ≤ λS_t + C`, where `C` is the round-trip
  trading cost. This is the operational form: when the deviation exceeds `C`, there is a
  trade; inside the band there is not. The band is calibrated to **actual Binance fees**.
- **Empirical results**: deviations in crypto are much larger than in traditional currency
  markets, comove across currencies, and shrink over time (the market is maturing — expect
  the edge to decay). The implied threshold strategy gives a **Sharpe of 1.8 on Bitcoin
  perpetuals under the high trading costs typical of retail-tier fees**, with annualised
  return, volatility, maximum drawdown, alpha and t-stat all reported rather than just a
  Sharpe.

Data is from CoinGecko with exchanges known for misrepresenting volume excluded — a
sanity step most crypto papers skip. The trade itself (long spot, short perp, collect
funding) is delta-neutral, so this is a genuine carry harvest rather than disguised beta;
the residual risks are funding-path reversal and liquidation, not direction.

### 1004.0125 — Variance Dispersion and Correlation Swaps (Jacquier & Slaoui, 2010)
`1004.0125_variance_dispersion_correlation_swaps.pdf` · https://arxiv.org/abs/1004.0125

Answers the question that decides whether a dispersion trade is a correlation trade: why
the implied correlation embedded in a variance-swap dispersion trade differs from the
strike of a correlation swap of the same maturity.

The result is a clean PnL decomposition. The PnL of a dispersion trade equals

    (implied correlation − realised correlation) × average component variance   +   a volatility term

and the second term is of **volga order** (second derivative with respect to volatility).
So the observed correlation spread is fully explained by the volga of the dispersion trade
— it is not a mispricing to be arbitraged, it is the price of a convexity exposure you are
carrying whether or not you intended to.

Also worth the read for the practical construction section: the trade can be built on
variance swaps or gamma swaps, and the **weighting scheme changes the exposure** —
vega-flat (index vega equals summed component vega), gamma-flat, and theta-flat weightings
are each worked through, with the note that one of the schemes commonly assumed in the
literature is not the one actually used. Choosing the weighting is choosing which greek
you are neutral to.

No empirical study; this is an identity plus a construction guide, which is what makes it
usable regardless of market or period.

### 2107.00427 — Feasible Implied Correlation Matrices from Factor Structures (Schadner, 2021)
`2107.00427_feasible_implied_correlation_matrices.pdf` · https://arxiv.org/abs/2107.00427

The infrastructure piece for any cross-sectional correlation signal. Extracting a full
implied correlation matrix from options is **under-determined** — far fewer liquid options
than correlation pairs — so existing models close the system with assumptions that can
produce matrices that are not positive semi-definite or not economically sensible. A
signal computed from an infeasible matrix is noise with a plausible sign.

Two usable methods:

- **Quantitative**: reformulate as a *nearest correlation matrix* problem solved with a
  spectral projected gradient method under inexact restoration. Usable stand-alone, or as
  a **repair step to restore positive semi-definiteness of any other model's estimate** —
  which is how it would most likely enter an existing pipeline.
- **Economic**: translate expected correlations between stocks and risk factors (CAPM,
  Fama-French) into a feasible implied correlation matrix, keeping the result consistent
  with the factor structure rather than fighting it.

Empirical work on monthly S&P 100 and S&P 500 option data, 1996-2020, including a
comparison of the SPGM solver against an SQP-based alternative.

## Rejected

### 2209.03307 — A Primer on Perpetuals (Angeris, Chitra, Evans & Lorig, 2022)
https://arxiv.org/abs/2209.03307

Continuous-time market with **no arbitrage and no transaction costs**, deriving model-free
funding and discount rates for two perpetual contract designs plus replication strategies
for the short side, with semi-robust extensions when prices jump.

Rejected for this purpose because it solves the *inverse* problem: it assumes no arbitrage
and derives the funding rate consistent with a given pricing function. As 2212.06888 points
out directly, funding-rate mechanisms are predetermined and fixed for traders, and prices
deviate from the designer's intended function because of limits to arbitrage — so the
inverse direction gives nothing to trade against, and the zero-cost assumption removes the
band that decides whether a deviation is actionable.

Keep the citation for a different job: if the task is ever to **design or price** a
perpetual contract (an everlasting option, a perpetual variance swap, a leveraged-ETF-like
payoff), this is the correct reference, and its examples connect perps to variance swaps
and leveraged ETFs explicitly.

## Gap not covered

No usable paper found for **fixed-income relative value** — the PCA level/slope/curvature
decomposition of the yield curve and butterfly weights set so that PC1 and PC2 exposures
vanish. Searches returned term-structure *forecasting* with machine learning
(`2606.26815`) and credit CDS-bond basis measures (`0912.4618`), neither of which is the
curve-RV construction. Low priority unless government-bond or swap trading is actually in
scope; if it becomes relevant, the material is in practitioner texts rather than on arXiv.

## Practical ordering for implementation

1. Crypto carry is the lowest-hanging trade here: compute the band `λS_t ± C` with your own
   fee tier as `C`, and only act outside it (2212.06888). Track deviation decay over time —
   the paper documents it shrinking.
2. For dispersion, decide the weighting scheme first, because it fixes which greek is
   neutral, then treat the residual volga as a known carried exposure rather than a surprise
   (1004.0125).
3. Never feed a raw implied correlation matrix into a dispersion signal — run the nearest-
   correlation repair so the matrix is positive semi-definite and factor-consistent
   (2107.00427).
