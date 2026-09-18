# Residual statistical arbitrage — plan to redesign the search

**Status: Stages 0 and 1 built and passed, 2026-09-17. Stage 2 (costs) is next, and is the
one most likely to end the work.** This document argues that the
project's search design, not its machinery, is why 3,629 pair-tests produced zero survivors, and
sets out what to change, what not to change, and how to find out cheaply whether the change works.

Stage 0 is now measured rather than proposed: `residual.py` reports that the equity residual
rejects a unit root **2.11% ± 0.40% more often than the same pipeline on shuffled dates, t =
5.27** over 78 non-overlapping windows and 160 names. The premise survives. See §4 for what that
does and does not license.

Written 2026-09-17, after the crypto and forex searches and after reading
[1901.09309](../../../research/wiki/statarb_residual/1901.09309_highdim_statarb_factor_models_stochastic_control_digest.md)
(Guijarro-Ordonez, Stanford).

---

## 1. Root causes

Five, in order of how much they explain. The first is the one that matters; the others are real
but secondary.

### 1.1 Breadth of one — the governing constraint

The Fundamental Law of Active Management gives

```
Information Ratio  ≈  IC × √breadth
```

where `IC` is skill per bet and `breadth` is the number of independent bets. For statistical
arbitrage the information coefficient is small by nature — roughly **0.02 to 0.05**. That is not
a deficiency to be fixed; it is what the edge *is*. A relationship that reliably predicted more
would have been arbitraged away.

Small `IC` becomes money only through large `breadth`. To reach an IR of 2 at IC = 0.03 requires
breadth of about 4,400. Real desks run 500 to 5,000 positions simultaneously and turn them over
continuously.

This project's candidates:

| pair | trades | span | trades/year |
|---|---|---|---|
| `AUDUSD~USDNOK` | 56 | 21 years | 2.7 |
| `DOT~FIL` | 30 | 6 years | 5.1 |
| `AUDUSD~NZDUSD` | 37 | 21 years | 1.8 |

Breadth is effectively **one**. At IC = 0.03 with 37 bets the expected Sharpe is about **0.18**.
Measured on `AUDUSD~USDNOK`: **0.28 ± 0.22**. The engine agreed with the arithmetic.

This is the decisive point. The repeated `mean/standard error` readings of +1.28 and +1.32 are
not a run of bad luck across different pairs — they are the same structural fact printing itself
each time. **No choice of pair fixes it, because the problem is that there is one pair.**

### 1.2 The wrong model class

Level cointegration requires two instruments to hold a **stable long-run price ratio**. That is a
strong assumption and most instruments violate it.

`DOT~FIL` is the clean demonstration: its hedge ratio walked **0.436 → 0.785 → 0.748 → 0.847 →
0.860 → 1.291** across 2021–2026, monotonically, and never returned. A ratio that wanders is
noise around a relationship; a ratio that walks steadily one way is a relationship turning into a
different one. Crypto and forex both reprice relatively and permanently.

The pooled p-values looked strong (0.0002) precisely because pooling eras with different betas
manufactures a slow-moving residual. No single year rejected at 5% except 2022.

### 1.3 Financing, not signal

The recurring cause of death, across asset classes and years:

| pair | gross | carry | net |
|---|---|---|---|
| `SPY~DIA` | +205 | −752 | loss |
| `EURUSD~GBPUSD` | +343 | −462 | −186 |
| `XLP~XLB` (unseen 20y) | +528 | −754 | loss |

Holding 13–50 bars at retail financing means carry scales with the holding period while the
edge does not. A spread that moves 0.3% cannot pay for forty nights of carry whatever its
p-value says.

### 1.4 Selection bias is punitive at N = 1

Twenty-one screens, 3,629 pair-tests. Every one of those trials must be charged to whichever
single pair survives, and the deflated-Sharpe benchmark grows with the logarithm of the trial
count. `DOT~FIL` went from a probabilistic Sharpe of 89.7% to a deflated 0.1% on 79 trials;
`AUDUSD~USDNOK` from 98.3% to 7.1% on 85.

A portfolio strategy is not asked this question. It does not need any individual name to be
significant — it needs the **average** to be positive. Our gates ask "is this one pair real?",
which is the wrong shape of question for the strategy that actually works.

### 1.5 Two measurement defects, both found and fixed this week

Recorded because they inflated results silently and would have again.

- **Bad close prints.** Sixteen bars across five forex symbols, each a >10% jump reversing the
  next bar. One such bar produced the single largest trade in `AUDUSD~USDNOK` — **+881.9 bps,
  34% of all its profit**. Now detected by `marketdata`'s `close-spike` check.
- **Forex neutrality measured in the wrong space.** All 28 negative-beta pairs scored exactly
  100% net exposure because the gate assumed both legs were quoted the same way round. Fixed by
  `hedge.fx_net_exposure`, which sums exposure per currency.

Neither is a root cause of the zero-survivor result, but both show that **defects in this
pipeline flatter results rather than break them**, which is the dangerous direction.

---

## 2. What to apply

Four ideas from 1901.09309, assessed one at a time. Not all of them survive contact with our
constraints, and the ones that do not are recorded as such rather than quietly adopted.

### 2.1 Trade factor residuals, not price-level spreads — **adopt**

Fit a factor model to *returns* across a universe, and trade the residual:

```
dR_t = Λ dF_t + dX_t          factor model on returns
dX_t = A(μ − X_t) dt + σ dB_t  residuals mean-revert (OU)
```

The tradable object is `X_t`, the accumulated idiosyncratic return after factors are removed.

**Pros.**
- Removes the stable-price-ratio assumption entirely. The factor model absorbs common movement
  each period; only the idiosyncratic part must revert. A permanent repricing changes what the
  factor explains and leaves the residual's equilibrium intact.
- Produces a signal for **every name in the universe simultaneously**, which is the breadth fix.
  160 equities gives 160 concurrent signals rather than one pair.
- It is what the field actually does. Avellaneda & Lee (2010) built this on US equities; this is
  the mainstream construction, not an exotic one.

**Cons.**
- Requires large N. See §3 — this rules out our forex and crypto universes outright.
- The residual is only as clean as the factor model. A misestimated `Λ` means the residual
  inherits estimation error instead of being cleaned by it.
- Constant loadings are assumed for tractability. The paper states this openly (footnote 2).
  Real loadings drift.

**One departure from the paper, measured in Stage 0.** The residual is accumulated over the bars
*after* the fit window, never over the fit window itself. Avellaneda & Lee and 1901.09309 both
present the in-sample form; on this data it inflates the shuffled null from 5% to 8.2% through a
Brownian-bridge artefact and erases the real signal at the same time. The forward residual is
also the only one a live implementation could hold, so the honest measurement and the tradable
object turn out to be the same thing. Everything downstream inherits this choice.

### 2.2 Closed-form neutrality — **adopt; built 2026-09-17**

With `c_ik = Σ_j Λ̃_jk Λ_ij`, the fixed portfolio `p̃_i = (−c_i1, …, 1−c_ii, …, −c_iN)` earns
exactly residual *i* and is factor-neutral.

**Pros.**
- Neutrality is an **algebraic identity**, not a fitted quantity, so it cannot silently drift.
  This directly addresses the failure mode behind our 28 mis-scored forex pairs and behind
  `BNB~LINK`, which had the lowest p-value in its universe and 67% net exposure.
- No matrix inversion and no numerical optimiser, so it scales to hundreds of names.
- Sparse factor models make each neutral portfolio touch few assets, which lowers rebalancing
  cost (Remark 2.1).

**Cons.**
- Neutral to the *estimated* factors. If `Λ` is wrong, the construction is exactly neutral to
  the wrong thing, and nothing inside the construction reveals it. Needs an external check.

**Built in `portfolio.py`, in the projection form rather than the `c_ik` form.** Rather than
constructing one fixed portfolio per residual, the book's weight vector is projected onto
the null space of the loadings, `w ← w − Λᵀ(ΛΛᵀ)⁻¹Λw`, which reaches the same place — zero
exposure to every estimated factor — while leaving the OU sizing of §2.3 to decide the
weights. Solved by least squares, because `ΛΛᵀ` is near-singular whenever two components are
nearly collinear.

Measured on the 160-name panel:

| | before | after |
|---|---|---|
| factor exposure ‖Λw‖ | 1.040 | **2.25 × 10⁻¹⁵** |
| net exposure, last bar | +47.4% | **+8.2%** |
| standard deviation of net over 12 dates | 7.8% | **3.6%** |
| dates breaching the 10% cap | ~1 in 5 | **none** |

The cap was not moved. Post-projection weights correlate **+0.910** with their
pre-projection values, which is what says the projection removed unintended exposure rather
than signal — and that number is printed on every run rather than assumed.

**One trap found while building it.** Projected over all 160 names, the operation puts
weight back on every name the uncertainty haircut closed and on the one the heavy-loading
gate dropped: 70 gated names became a book of 160. The projection now runs only over the
held subspace, which still reaches exact neutrality because the null space of a 15×70
loading matrix has 55 dimensions.

### 2.3 Derive position size instead of searching a threshold — **adopt, with a caveat**

The optimal allocation is affine in `A(μ − X_t)`, so "enter at 2σ, exit at 0.5σ" is replaced by
a continuous function of distance-from-mean and reversion speed.

**Pros.**
- Removes a searched parameter. Every swept threshold is a trial; the deflation benchmark grows
  with `log N` of the trial count. Dropping a five-value entry sweep divides the trial count by
  five.
- The non-myopic term correctly shrinks the position as the horizon approaches — a fixed
  threshold cannot express that.

**Cons.**
- Trades one free parameter for three **estimated** ones (`A`, `μ`, `σ`). An overstated
  reversion speed produces systematic oversizing, and there is no threshold to cap it.
- The verification conditions (`4·max‖Λ₀‖ < 1`, `32·max‖Λ₁‖ < 1`) can fail, and then the
  exponential-utility solution is not valid. Must be checked, not assumed.

### 2.4 The aim-portfolio cost solution — **do not adopt as-is**

The paper charges `½ I'CI` — a **quadratic** cost in trading *rate*, which models **price
impact**.

**Why not.** We do not pay price impact. At our size we pay a **fixed** bid-ask spread plus
commission per round trip — 21 bps on Binance, and a broker-sheet spread in forex. A cost that
is constant in size has a different optimal policy: a **no-trade band**, not continuous tracking
toward a moving aim. Adopting the paper's solution would optimise against a cost we do not face
while ignoring the one we do.

**What to take instead.** The *principle* — that costs should change what you trade toward, not
merely be subtracted afterwards — and the finding that higher costs justify moving toward the
target more slowly. The correct formulation for a fixed per-trade cost is the no-trade-band
literature (Leung & Li 2015 is in the references and is the two-asset version).

This matters because financing is our documented cause of death. Getting the cost model wrong
here would repeat the mistake in a more sophisticated disguise.

---

## 3. The binding constraint: which universe can support this

Measured from the store on 2026-09-17:

| asset class | series | usable N | verdict |
|---|---|---|---|
| equity | 256 | **160 with ≥5,000 bars** | viable, N/T ≈ 0.03 |
| crypto | 18 | 18 | too small |
| forex | 15 | 15 | too small |

PCA estimation error grows with `N/T`, but the deeper problem at small N is different: with 15
names the leading eigenvector is not meaningfully separated from noise, so the "factor" would
*be* estimation error and the residual would inherit it rather than be cleaned by it.

**This is the plan's most consequential finding. The two markets this project has spent its
recent effort on — forex and crypto — are structurally unable to support the fix. The equity
universe, which was searched early and set aside, is the only one that can.**

Forex and crypto are not thereby excluded from the project forever; they are excluded from
*this method* until either the universe is much wider or a different factor structure is used
(for forex, currency factors rather than PCA — a small number of named drivers, which
`instruments.py` already models).

### Crypto, tested 2026-09-18 — the N constraint lifted, and the signal was still not there

The store went from 18 crypto series to 243, so the reason recorded above expired and the
claim became testable. It was tested on two panels, both counted as trials:

| panel | names | common bars | windows | Stage 0 lift | t |
|---|---|---|---|---|---|
| 2,000+ bars | 68 | 1,702 | 23 | +2.02% ± 1.13% | 1.80 — fails |
| 2,500+ bars | 29 | 2,499 | 35 | **+2.79% ± 1.06%** | **2.64 — passes** |

The narrow panel fails for want of power rather than want of effect: its point estimate is
within noise of the equity panel's +2.11%, but 23 windows cannot resolve it. On the deeper
panel the effect *rose* while the error fell, which is what a real effect does when measured
better and the opposite of what a mined one does.

**Stage 1 then fails.** IC at the five-bar horizon is **+0.0381 ± 0.0271, t = 1.40**, against
equities' +0.0214 ± 0.0077 at t = 2.79. The lift over the shuffled null is weak at every
horizon tested (best t = 1.18 at ten bars) and *negative* at one bar. Breadth is healthy —
23.4 independent bets from 29 names, 81% of the cross-section — and cannot help: `IC x
sqrt(breadth)` multiplies the skill, and multiplying something indistinguishable from zero
by any breadth gives the same.

So crypto reverts, weakly and only on the deeper panel, and no signal built on that reversion
predicts. **The residual track is closed for crypto at Stage 1**, on the same kill criterion
equities passed. The pair track was closed the day before: 2,278 pairs, 6 screen survivors,
0 held by the allocator, and deflated Sharpes of 1.7% and 55.7% for the two leaders.

Two tracks, two markets, four independent gates, and the only market with a signal that
clears Stage 1 remains equities — where the survivorship bound of §04 still applies.

---

## 4. Order of work — measurement before machinery

Deliberately staged so the cheap, falsifying test comes first. Each stage has a **kill
criterion**: a result that stops the work rather than prompting a parameter change.

### Stage 0 — Does the residual revert at all? *(measurement, no trading)* — **done, passed**

Fit PCA on daily equity returns across the 160-name universe, build residuals, estimate OU
parameters per name. Report the cross-sectional distribution of half-lives and the share of
names whose residual rejects a unit root.

- **Cost:** low. One script, reuses `relationship.py`, `cointegration.py`, `marketdata`.
- **Kill criterion:** if the share of reverting residuals is at or below what shuffled returns
  produce, stop. The premise is wrong and no amount of portfolio construction rescues it.
- **Why first:** it is a property of the data, testable without a signal, a cost model, or a
  backtest. If this fails, everything downstream is wasted.

**Result — `code/residual.py`, 56 checks in `verify_residual.py`, run #1 in `logs/residual.csv`.**

160 names, 5,189 common bars, 2006-01-26 to 2026-09-14, 15 factors on 252 bars, residual
accumulated over the 60 bars after.

| | real | shuffled | lift |
|---|---|---|---|
| unit root rejected at 5% | 7.8% | 5.7% | **+2.1%** |
| half-life, median | 8.2 bars | 9.4 bars | −1.2 |
| OU regime reverting | 94.1% | 94.5% | −0.3% |

Lift **+2.11% ± 0.40% per window, t = 5.27** over 78 windows, null averaged over three
permutations. Stable across the searched parameter: t ranges 3.36 to 6.14 over factors
∈ {3, 5, 10, 15, 20, 30} and forward windows ∈ {40, 60, 90, 120}, with the null floor at
5.1–6.1% throughout. The conclusion is not a knife-edge on any one setting.

**One design change was forced by the measurement, and it is the reason this stage produced an
answer at all.** The residual must be accumulated over bars *after* the window the loadings were
fitted on. Fitting and testing on the same bars — how the paper presents it — breaks the
measurement twice: cumulated in-window OLS residuals are constrained to return to zero, forming a
Brownian bridge that lifts the shuffled null from a nominal 5% to **8.2%**; and sixteen fitted
parameters on sixty bars absorb the deviation the residual is supposed to carry. Measured
in-sample the lift is **+0.3% at t = 0.84**; the same data measured forward gives **+2.1% at t =
5.27**. The in-sample version simultaneously inflated the null and erased the signal, and would
have produced a false kill.

**What this licenses: nothing except Stage 1.** It says the object exists, not that trading it
pays. A 2.1% lift in unit-root rejection is not an edge, and §1.3 says financing is what has
killed every candidate so far.

### Stage 1 — Is the *aggregate* signal positive? — **done, passed**

Form the equal-weight portfolio of all residual signals. Measure expectancy across names, not
per name.

- **Kill criterion:** aggregate gross expectancy at or below zero **before costs**. If the
  average residual does not pay gross, breadth cannot save it — `√breadth` multiplies the
  edge, and multiplying zero gives zero.
- **Why second:** this is the hypothesis. Everything in §1.1 says the aggregate is the right
  unit of measurement; this stage measures it directly.

**Result — `code/ic.py`, verified in groups 9 and 10 of `verify_residual.py` (79 checks).**

The aggregate question is answered more directly by the information coefficient than by an
equal-weight portfolio: the IC *is* "does the signal predict the forward return", asked
across the whole cross-section at once.

| horizon (bars) | IC | std err | t | ICIR | implied IR |
|---|---|---|---|---|---|
| 1 | +0.0076 | 0.0074 | 1.03 | 0.067 | 1.39 |
| 2 | +0.0119 | 0.0074 | 1.61 | 0.105 | 1.54 |
| 3 | +0.0190 | 0.0076 | 2.50 | 0.163 | 2.00 |
| **5** | **+0.0214** | **0.0077** | **2.79** | **0.182** | **1.74** |
| 10 | +0.0237 | 0.0074 | 3.19 | 0.208 | 1.37 |
| 20 | +0.0328 | 0.0075 | 4.38 | 0.286 | 1.34 |

Null IC is ≈ 0 at every horizon, as it must be.

**The two numbers §1.1 argued from are now measured rather than cited.**

- **IC = 0.0214** at the primary horizon. The literature range quoted throughout this
  document was 0.02–0.05; the measured value lands at its bottom edge. It was an assumption
  and is now an observation.
- **Breadth = 132.2** independent bets from 160 names — 83% of the cross-section, via the
  participation ratio of the residual correlation matrix. The 17% shortfall is real and
  locatable: `CCL~RCL`, two cruise lines, still correlate at +0.50 after fifteen factors are
  removed.

Together, `IR = IC × √breadth ≈ 1.7` a year. Compare with §1.1's arithmetic for the pair
track — breadth of one, expected Sharpe 0.18, measured 0.28 ± 0.22. **That is the redesign's
entire claim, and it now has both terms measured on this project's own data.**

**IC rises with horizon rather than decaying.** From 0.0076 at one bar to 0.0328 at twenty.
Not a defect: the residual's median half-life is 8.2 bars, so a one-bar forward return is
mostly noise while a twenty-bar one captures the reversion. The primary horizon is declared
from that half-life, not selected by reading the table — choosing it afterwards would be
selection and Step 4 charges for it.

**Two defects found by running it, both in the measurement rather than the data.** Breadth
was originally computed on whichever horizon came first, giving 236 rows for 160 names; at
that ratio the sample correlation eigenvalues are spread by noise and the participation
ratio is deflated, and the reported breadth moved between 59.7 and 132.2 according to a
setting with nothing to do with breadth. It now has a dedicated tiled pass and refuses below
two rows per name. Separately, the exit code was decided by the shortest horizon, which is
the worst one for this signal.

**What this does not license.** The panel is survivor-filtered and nothing has been charged
a spread, so the implied IR is an upper bound twice over. §1.3 records that financing, not
signal, has killed every candidate this project has produced, and that is Stage 2.

### Stage 2 — Does it survive our cost structure?

Charge the real fixed spread and commission per name, per rebalance, with a no-trade band
rather than the paper's quadratic solution (§2.4).

- **Kill criterion:** net expectancy at or below zero at realistic turnover. Given §1.3 this is
  the most likely stage to fail, and failing here is informative rather than disappointing.

### Stage 3 — Then, and only then, validation

Run the Step 4 gates on the **portfolio**, not on individual names — the question is whether the
aggregate result survives the search that produced it.

### Stage 4 — Portfolio construction and sizing

`portfolio.py`, currently deferred in [STEP3.md](STEP3.md) for lack of two candidates, becomes
the main task rather than an afterthought. Risk sizing via `sizing.py` on the aggregate.

---

## 5. Pros and cons of the whole redirection

### For

- It addresses the **measured** root cause rather than a guessed one. The Sharpe arithmetic in
  §1.1 predicts what we observed, which is unusually strong evidence for a diagnosis.
- It reuses most of the machinery. `marketdata`, `costs`, `backtest`, `relationship`,
  `deflated_sharpe`, `overfit`, `purged_cv` and the 629-check suite all still apply. What
  changes is the **signal construction and the unit of evaluation**, not the plumbing.
- It removes searched parameters rather than adding them, which lowers rather than raises the
  selection-bias burden.
- The failure modes are documented in advance, including by the paper's own author.

### Against

- **More machinery means more ways to be wrong.** A PCA factor model, an OU estimator per name,
  and a portfolio construction layer are three new places for a defect to flatter results. This
  project has now found defects that inflate results in two consecutive weeks. That rate should
  be assumed to continue.
- **The paper is not evidence of edge.** Its simulations assume perfectly known parameters; the
  author states plainly that the strategies "will always produce benefits by construction" in
  that setting and that this "might not apply under parameter misspecification". Real-data work
  is deferred to a separate paper. We are taking the construction, not a result.
- **It abandons the markets the project was built for.** The stated goal was forex first. This
  plan says forex cannot support the method at 15 instruments.
- **Retail cost structure remains a ceiling.** Breadth improves the cost-to-edge ratio because
  costs are charged per trade while the edge scales with the number of bets — but it does not
  eliminate the gap to a desk financing at OIS and paying ~1 bp a side.
- **Estimation risk replaces search risk.** We stop searching thresholds and start estimating
  `Λ`, `A`, `μ`, `σ`. That is a better trade, but it is a trade, not a free gain.

### The honest summary

This is the first change in the project aimed at a cause that was **measured** rather than
suspected. It is more likely to work than another screen. It is still likely to fail — most
things do — and Stage 0 is designed so that finding out costs a day rather than a month.

---

## 6. What this plan does not do

| Tempting | Why not |
|---|---|
| Re-screen forex or crypto with the new method | N = 15 and 18. The factor would be noise. §3 |
| Adopt the paper's quadratic cost solution | It models price impact; we pay fixed spread. §2.4 |
| Use the deep-learning variant (2106.04028) first | Reintroduces a large hyperparameter search — the exact thing §2.3 removes. Read it for its real-data evidence, implement the closed form |
| Skip Stage 0 and build the portfolio layer | The premise is untested. A day of measurement gates a month of building |
| Treat a positive aggregate as permission to trade | Step 4 still applies, at the portfolio level. Surviving it means the evidence is not yet against you |
