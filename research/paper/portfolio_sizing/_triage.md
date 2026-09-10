# Topic 6 — Portfolio Construction Layer and Position Sizing

Scope: turning a set of signals into positions of a specific size. Three sub-problems, one
paper each: estimating the covariance matrix you are about to invert, deciding how much to
trade given that trading costs money, and deciding total leverage.

Source: arXiv API (literature_search_arxiv skill). Each paper was read before deciding.

## Kept

### 1709.06296 — Large-Scale Portfolio Allocation Under Transaction Costs and Model Uncertainty (Hautsch & Voigt, 2017, rev. 2018)
`1709.06296_allocation_under_transaction_costs.pdf` · https://arxiv.org/abs/1709.06296

The single most useful result in this topic: **turnover penalisation and covariance
shrinkage are the same operation**, with the strength of the penalty governed by the
transaction cost. Incorporating costs *ex ante* shifts the optimum toward a regularised
version of the efficient allocation — so paying attention to costs is not a separate
post-processing step, it is how you regularise a noisy covariance matrix.

The distinction the paper draws is the one that matters in practice: most studies add
transaction costs **ex post**, asking whether a strategy would have survived them. Real
desks include them **ex ante**, inside the optimisation. The two give different portfolios,
not just different reported returns.

Empirical setting: all S&P 500 constituents over more than 10 years, combining predictive
distributions from high-frequency and low-frequency data, with parameter and model
uncertainty handled explicitly, evaluated on out-of-sample utility net of costs.

Two findings to carry over:

- Turnover penalisation is **more effective than the commonly used shrinkage methods** at
  producing well-performing portfolios.
- Strategies that do not account for costs ex ante **fail to produce positive Sharpe
  ratios** once costs are applied — the failure is not marginal.
- Using high-frequency information yields significantly higher Sharpe ratios, attributed to
  time variation that lower-frequency estimates miss.

### 1610.08104 — Cleaning Large Correlation Matrices: Tools from Random Matrix Theory (Bun, Bouchaud & Potters, 2016)
`1610.08104_cleaning_correlation_matrices_rmt.pdf` · https://arxiv.org/abs/1610.08104

The reference for the estimator every mean-variance or beta-neutral construction depends
on. Written at Capital Fund Management, 165 pages, review format — treat it as a manual to
consult rather than a paper to read front to back.

Why it earns a place despite its length: it quantifies the exact failure mode of using a
sample covariance matrix in an optimiser. With `q = N/T`,

    Tr E⁻¹ = Tr C⁻¹ / (1 − q)

for a wide class of processes — meaning the in-sample risk of an optimised portfolio
understates true risk by a factor `1/(1−q)`. At `N/T = 0.5` the optimiser is lying to you
by a factor of two, and no amount of backtest care fixes it, because the error is in the
estimator rather than the protocol.

Contents that are directly usable: the Marchenko-Pastur equation for the spectrum of a
noisy correlation matrix, eigenvector (not just eigenvalue) statistics, edge and outlier
statistics for deciding how many eigenvalues are signal, and the construction of
**Rotationally Invariant Estimators (RIE)** — the optimal shrinkage function applied to
eigenvalues when there is no prior on the structure of the underlying process. The review
establishes empirically that RIE beats all previously proposed cleaning methods on
financial data, including for the out-of-sample risk of optimised portfolios.

Relationship to the other two: this is the estimator, 1709.06296 is the argument that
turnover penalisation can substitute for part of it, and
`../neutrality/1810.08384_portfolio_construction_matters.pdf` uses simple eigenvalue
truncation (top `k` factors) as the cheap version of the same idea.

### 0902.2965 — Optimal Leverage from Non-Ergodicity (Peters, 2009, rev. 2010)
`0902.2965_optimal_leverage_non_ergodicity.pdf` · https://arxiv.org/abs/0902.2965

Sizing, and specifically why the usual reporting metrics cannot answer the sizing question.

The core point is that multiplicative models are **non-ergodic**, so the ensemble-average
return differs from the time-average return experienced in a single realisation — and an
investor has exactly one realisation. Classical treatments use ensemble averages; the Kelly
result comes from time averages. For geometric Brownian motion the time-average growth rate
is

    ḡ = μ − σ²/2

which is maximised at a finite optimal leverage, whereas the ensemble-average growth rate is
**linear in leverage** and therefore rewards unlimited leverage. That is the mechanism by
which a metric can incentivise a position size that destroys the account.

The consequence worth pinning to the wall: the **Sharpe ratio is insensitive to leverage**.
It cannot tell you how large to trade, so a strategy selected and reported purely by Sharpe
has an unanswered sizing question. The paper discusses the relation between the two
explicitly.

Also practical: it treats estimation of the growth rate from a finite sample of length `T`,
with the estimator's standard deviation scaling as `σT^(-1/2)` — i.e. how long a track record
must be before an optimal-leverage estimate means anything. Pairs directly with the
minimum-track-record-length material under Topic 7.

## Rejected

### 2402.15588 — Sizing the Bets in a Focused Portfolio (Vukčević & Keser, 2024)
https://arxiv.org/abs/2402.15588

A generalised Kelly optimiser with genuinely practical constraints — no shorting, capped
leverage, a limit on the risk of permanent capital loss, and a maximum individual allocation
— plus released software and an observation about excessive diversification drawn from a
worked five-company example.

Rejected for this project because the inputs are the wrong kind. The model takes, per
candidate business, a set of **subjectively estimated scenarios** (probability plus intrinsic
value) from fundamental analysis over a very long horizon, explicitly in the Buffett/Munger
focused-investing tradition. The paper says outright it does not address finding candidates,
only allocating among them. For non-directional systematic strategies the sizing inputs are
estimated moments and cost curves, not scenario trees, so the optimiser has nothing to
consume. Its validation is a numerical example, not a backtest.

The constrained-Kelly formulation itself (log growth objective with inequality constraints
`I(f) ≤ 0`) is reusable if a constrained sizing optimiser is ever needed; for the growth-rate
mathematics, 0902.2965 is the better source.

## Practical ordering for implementation

1. Never invert a raw sample covariance matrix. Estimate `q = N/T` first — it tells you how
   badly in-sample risk is understated — then clean with a rotationally invariant estimator,
   or with top-`k` eigenvalue truncation as the cheap approximation (1610.08104).
2. Put transaction costs inside the optimisation, not in a post-hoc net-of-costs table. The
   turnover penalty doubles as regularisation, so this step partly replaces separate
   shrinkage tuning (1709.06296).
3. Set leverage from the time-average growth rate, not from Sharpe, and treat the finite-`T`
   estimation error on that growth rate as a reason to size below the theoretical optimum
   (0902.2965).
