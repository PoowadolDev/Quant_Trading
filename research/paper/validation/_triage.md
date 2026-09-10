# Topic 7 — Validation Mathematics

Scope: deciding whether a result is real. This is where non-directional strategy research
usually dies, because the same properties that make these strategies attractive — many
candidate pairs, many parameter settings, short holding periods, thin per-trade edge — also
make it easy to manufacture a Sharpe ratio out of search luck.

Source: arXiv API (literature_search_arxiv skill). Each paper was read before deciding.

Note: this repository already holds several papers on backtest overfitting at the
`research/paper/` root, with digests under `research/wiki/`. They are not duplicated here.
The three papers below cover angles those do not: setting rule parameters without a
backtest at all, correcting for search across a large strategy population, and a
data-snooping test built for discrete p-values.

## Kept

### 1408.1159 — Determining Optimal Trading Rules Without Backtesting (Carr & López de Prado, 2013, rev. 2014)
`1408.1159_optimal_trading_rules_without_backtesting.pdf` · https://arxiv.org/abs/1408.1159

Attacks the problem at the source. Profit-taking and stop-loss thresholds are the classic
overfitting vector: calibrating them on a backtest targets specific in-sample observations,
so the "optimal" pair is fitted to noise and underperforms live. Rather than measuring how
badly a search overfitted, this paper computes the **Optimal Trading Rule (OTR)** — the
profit-taking and stop-loss pair that maximises Sharpe ratio — analytically from an assumed
mean-reverting (Ornstein-Uhlenbeck) process for the traded quantity, without running
alternative configurations on historical data at all.

The authors are explicit that they do not derive a closed-form solution and determine the
OTR numerically; the appendices contain a **Python implementation**.

Direct relevance to this repository: any strategy with take-profit / stop-loss parameters —
grid trading, the Wyckoff phase logic, volume-anomaly entries — currently has those levels
set by search. This gives a way to derive them from the estimated OU parameters of the
spread or price process instead, which removes those degrees of freedom from the backtest
rather than penalising them afterwards. It also pairs directly with the half-life and
`σ_eq = σ/√(2θ)` machinery in `../statarb/_triage.md`.

### 2311.10685 — High-Throughput Asset Pricing (Chen & Dim, 2023, rev. 2025)
`2311.10685_high_throughput_asset_pricing.pdf` · https://arxiv.org/abs/2311.10685

The most consequential result here, and it contradicts the standard advice. The usual
prescription is to *mine less* — restrict the search to theory-motivated patterns. This
paper's prescription is to **mine rigorously**: search systematically, then condition the
results on the fact that they came from a search, using empirical Bayes.

Setup: 136,000 long-short strategies built from accounting ratios, past returns, and — as a
deliberate null control — **ticker symbols**. Empirical Bayes measures the distance between
the empirical t-statistic distribution and the standard normal null, per strategy family.
The ticker-symbol families have t-stats indistinguishable from the null (as they must), while
accounting-ratio families are too fat-tailed to be consistent with it. That contrast is
visible by inspecting the t-stat distributions, which makes the method auditable rather than
a black box.

Findings that change how you evaluate a strategy population:

- EB predictions are **unbiased**: in almost all of 120 portfolios, predicted returns land
  within 2 standard errors of realised out-of-sample means.
- The approach **matches the out-of-sample performance of strategies published in top
  journals while eliminating look-ahead bias**.
- **Multiple-testing methods popular in finance fail to identify most out-of-sample
  performers.** Specifically, FDR-controlling t-stat hurdles of the Harvey-Liu-Zhu type are
  so conservative that thousands of strategies with real out-of-sample performance are
  discarded. Over-correction has a cost, and this quantifies it.
- Predictability concentrates in accounting strategies, small stocks, and pre-2004 periods,
  consistent with limited-attention theories — i.e. expect the edge to have decayed where
  attention arrived.

Replication code is published: https://github.com/chenandrewy/high-throughput-ap

### 1811.06766 — Technical Analysis and Discrete False Discovery Rate (Sermpinis, Hassanniakalager, Stasinakis & Psaradellis, 2018, rev. 2019)
`1811.06766_discrete_false_discovery_rate_technical_rules.pdf` · https://arxiv.org/abs/1811.06766

The data-snooping test built for exactly the situation a rule-based repository is in:
thousands of technical rules, evaluated on the same history, with **discrete p-values** —
which is what you get from bootstrap or permutation tests on a finite sample, and which the
standard FDR machinery handles badly by assuming continuous p-values.

The contribution is **DFDR+/-**, a discrete false discovery rate procedure that is adaptive,
more powerful than existing data-snooping controls, and accommodates discreteness directly.
It is the natural companion to White's Reality Check and Hansen's SPA test when the number
of candidate rules is in the thousands rather than the dozens.

Empirical scope: more than 21,000 technical trading rules across 12 categorical and
country-specific MSCI markets, 2004-2015, on rolling-forward structures of several lengths,
with profitability, **persistence** and robustness examined separately — persistence being
the property that distinguishes a rule from a lucky window.

Conclusions worth carrying: technical analysis retains short-term value in advanced,
emerging and frontier markets after snooping correction; performance depends on financial
stress, the economic environment, and market development, so a rule validated in one regime
should not be assumed to hold in another; and a cross-validation exercise shows the
importance of **frequent rebalancing** and the high variability of profitability.

## Rejected

### 2608.23808 — Equity Strategy Backtesting: Luck or Edge? The MinervaScore (Santoni, Jouanne & Scullin, 2026)
https://arxiv.org/abs/2608.23808

A composite 0-100 robustness grade aggregating five gates — Deflated Sharpe Ratio,
Probability of Backtest Overfitting, Superior Predictive Ability, Minimum Track Record
Length, and a regime-stability diagnostic — into a single score with a binary "Robustness
Seal" awarded only when all five gates pass, calibrated on 359,062 production backtest
records.

Rejected on the paper's own evidence, which the authors report honestly:

- In a **pre-registered test on unseen real-market data, the score showed no significant
  forward relationship** (Spearman ρ = 0.013, one-sided permutation p = 0.40).
- On synthetic data with known ground truth it separates signal from luck well
  (AUROC 0.989), but its improvement over the **corrected DSR-alone baseline is modest** —
  so the aggregation adds little over one of its own components.
- The authors explicitly present it as "an auditable validation and reporting layer, rather
  than as evidence of demonstrated real-market predictability".

The useful takeaway is the null result itself: **compute the Deflated Sharpe Ratio properly
and you have most of what a composite score provides.** The five-gate list is still the right
checklist to run individually — DSR, PBO, SPA, MinTRL, regime stability — just do not compress
them into one number and treat the number as a forecast.

## Checklist this topic implies

1. Remove free parameters instead of penalising them where possible — derive profit-taking
   and stop-loss from the estimated process rather than searching for them (1408.1159).
2. When many candidates are searched, condition on the search. Empirical Bayes gives unbiased
   predicted performance; blunt FDR hurdles throw away real winners (2311.10685).
3. For thousands of rules tested on one history with bootstrap p-values, use DFDR+/- rather
   than continuous-p-value FDR, and report **persistence** separately from profitability
   (1811.06766).
4. Report the individual gates — Deflated Sharpe Ratio, PBO, SPA / Reality Check, minimum
   track record length, regime stability — and do not aggregate them into a single grade
   (2608.23808's own null result).
5. Purged K-fold cross-validation with an embargo whenever labels overlap in time; plain
   cross-validation leaks. See also the overfitting papers already at `research/paper/` root
   and their digests in `research/wiki/`.
