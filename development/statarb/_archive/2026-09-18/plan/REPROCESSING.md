# Repository Reprocessing Report

**Written 2026-09-18.** A reprocessing audit of the statistical arbitrage research system,
produced before any refactoring code, as the brief requires. Its purpose is not to make the
project look more sophisticated. It is to say where the system is currently easy to fool.

The conclusion in one line: **the machinery is sound and the research frame is not.** 17,198
lines and 698 verification checks sit on top of a universe definition that cannot survive
scrutiny and an execution engine that cannot express the strategy the project has decided to
pursue.

---

## 1. Current architecture

Three layers, one of which is doing a job it was not shaped for.

```
  development/marketdata/           data layer, asset-class agnostic
    cli.py  feeds.py  store.py  validate.py  instruments.py  report.py
        |  Parquet, store/{class}/{symbol}/{timeframe}/{source}.parquet
        v
  development/statarb/code/         research layer, 31 scripts, 17,198 lines
        |
        +-- relationship   cointegration.py  hedge.py  relationship.py  health.py
        +-- factor         residual.py  ic.py
        +-- signal         strategy.py  thresholds.py  outcomes.py
        +-- portfolio      portfolio.py  risk.py  sizing.py
        +-- economics      costs.py  feasibility.py
        +-- execution      backtest.py
        +-- search         screen.py  basket_screen.py  pair_report.py
        +-- validation     multiple_testing.py  deflated_sharpe.py  overfit.py  purged_cv.py
        +-- orchestration  pipeline.py
        +-- reporting      pair_report.py (also the CSS/SVG module)  *_report.py
        +-- plumbing       paths.py  triallog.py
        v
  logs/*.csv   studies/*/*.html
```

Two things are worth naming immediately.

**`pair_report.py` has three jobs.** It is the Step 0 pair study, the HTML/CSS/SVG style
module every other report imports (`CSS`, `line_chart`, `histogram`, `_row`), and the home of
`UserError` and `_fit_ou`. Twenty-one modules import it. That is a load-bearing tangle: a
module named for one strategy family is a hard dependency of the entire reporting and error
layer, including the cross-sectional code.

**`pipeline.py` orchestrates only the residual track.** The pair track has no orchestrator,
which is why the research sequence has in practice varied per session — screen then backtest
on one occasion, screen then multiple-testing then portfolio on another. Order that is not
code is order that drifts.

---

## 2. Current data flow

```
Binance / Yahoo / Dukascopy
   -> marketdata download        incremental merge, de-duplicating
   -> Parquet store              path carries the metadata; catalogue rebuilt by scanning
   -> marketdata validate        OHLC sanity, close-spike, gap share
   -> ParquetStore.read / aligned_panel
   -> pair_report.load_prices    TWO symbols, inner-joined
      or residual.load_panel     N symbols, min-bars filter before the join
   -> np.log -> np.diff          returns
```

The split at the fourth step is the architectural fault line. `load_prices` is the pair
path and refuses anything other than two symbols; `load_panel` is the cross-sectional path.
They do not share a loader, a validation step, or a calendar convention.

**Known data defects, already catalogued and gated.** Yahoo FX has 1–3% malformed OHLC bars
so high/low work is refused there; sixteen close-spike bars were found across five FX symbols
after one of them supplied 34% of a pair's profit; Yahoo FX volume is always zero; Yahoo
intraday history is capped; `USDT` is not `USD`. This catalogue is a genuine strength and
should be preserved intact.

---

## 3. Current research flow

Two flows exist. Only one is encoded.

**Pair track, as practised (not enforced anywhere):**
```
screen.py -> pair_report.py -> cointegration.py/hedge.py/health.py
          -> backtest.py -> outcomes.py/thresholds.py/sizing.py
          -> multiple_testing.py/deflated_sharpe.py/overfit.py/purged_cv.py
```

**Residual track, enforced by `pipeline.py` stages 00–21:**
```
residual.py -> ic.py -> portfolio.py -> (stage 16 blocked) -> validation
```

The residual track stops at stage 16 because `backtest.py` cannot replay a cross-sectional
book. That single blockage is why stages 16–21 read `NOT RUN` on every pipeline report.

---

## 4. Pair-specific assumptions

Audited directly. The assumptions fall into three grades, and the distinction matters for
how much work each implies.

### Grade A — genuinely two-leg, needs redesign

`strategy.py`, the decision function shared with live trading:

```python
@dataclass(frozen=True)
class Fit:
    beta: float       # scalar
    alpha: float
    mu: float
    sigma_eq: float

def fit_relationship(prices, *, use_log, at):
    a, b = prices.columns                       # exactly two

def target_position(history, state, params) -> Target:
    last_a, last_b = float(last.iloc[0]), float(last.iloc[1])

def leg_weights(position: int, beta: float) -> tuple[float, float]:
```

`SignalState.position` is an `int` in `{-1, 0, +1}`. There is no representation for a weight
vector anywhere in the contract. A cross-sectional strategy cannot be expressed through this
interface at all — it is not a matter of relaxing a guard.

`backtest.py`'s bar loop, same grade:

```python
a, b = prices.columns
simple = np.vstack([np.zeros(2), values[1:] / values[:-1] - 1.0])
...
pos_a, pos_b = sig.leg_weights(current, current_beta)
bar_gross = (pos_a * simple[t, 0] + pos_b * simple[t, 1]) / denom * 1e4
```

`current` is a scalar, `current_beta` is a scalar, the two legs are indexed positionally.
`Trade` records `direction`, `entry_z`, `exit_z` — all scalar concepts with no cross-sectional
analogue.

### Grade B — written two-leg, but the math already generalises

This is the good news, and it is substantial. The cost model:

```python
def _carry_bps(profile, a, b, position, beta):
    pos_a, pos_b = sig.leg_weights(position, beta)
    total = 0.0
    for symbol, units in ((a, pos_a), (b, pos_b)):
        total += abs(units) * cost.carry_bps("long" if units > 0 else "short")
    return total / (1.0 + abs(beta))

def _turn_cost(profile, a, b, old, new, old_beta, new_beta):
    for symbol, delta in ((a, abs(new_a - old_a)), (b, abs(new_b - old_b))):
        total += delta * (cost.spread_bps() + cost.commission_bps)
    return total / denom
```

The loop is over a 2-tuple but the arithmetic is `sum over legs of |units| x rate`,
normalised by gross. Generalising is replacing the tuple with `zip(symbols, weights)` and
`1 + |beta|` with `sum(|w|)`. **The transaction cost model does not need rewriting** — it
needs its iterable widened. The brief calls the cost model an existing strength; that is
correct and it is more portable than it looks.

### Grade C — already N-asset

- `relationship.ols_hedge`, `relationship.build_spread_n` — many legs
- `risk.effective_bets`, `risk.correlation_matrix`, `risk.worst_correlation` — take a
  correlation matrix of any size
- `basket_screen.py` — 2 to 5 legs, with an N-leg `net_exposure`
- `residual.py`, `ic.py`, `portfolio.py` — built cross-sectional from the start
- `drawdown`, `sharpe_ratio`, `underwater_bars`, `risk_metrics` — operate on equity arrays
  and are indifferent to how the positions were formed

---

## 5. Existing reusable components

Preserve and share between both strategy families:

| Component | Where | Why it is reusable |
|---|---|---|
| Data layer | `development/marketdata/` | already asset-class agnostic |
| Defect catalogue | `marketdata/validate.py`, MANUAL | measured, specific, hard-won |
| Cost model | `costs.py`, `_carry_bps`, `_turn_cost` | per-leg summation, Grade B |
| Equity accounting | `backtest.py` drawdown/Sharpe/underwater | array-based |
| Trade ledger + waterfall | `Result`, `summarise`, `waterfall_chart` | gross/cost/carry/net split is the right decomposition |
| Breadth | `risk.effective_bets` | participation ratio, correct and already used by two callers |
| OU sizing | `portfolio.size_from_ou`, `sizing.growth_optimal_leverage` | one implementation, two book types |
| Validation gates | `multiple_testing.py`, `deflated_sharpe.py`, `overfit.py`, `purged_cv.py` | take return series, mostly strategy-agnostic |
| Schema guard | `triallog.append` | prevents the silent column-shift it was written for |
| Report style | `pair_report.CSS` + SVG primitives | self-contained HTML, no JS, dark mode |
| Research log | `logs/pair_research.csv` | result + parameters per row, `survived` labelled |

---

## 6. Missing components

Ordered by how much else they block.

1. **Point-in-time universe.** Nothing. The term appears in no production module. `U(t)` does
   not exist; every study uses `U(today)`.
2. **Strategy-agnostic execution.** No interface accepting a time series of target weight
   vectors. This blocks stages 16–21 of the residual track entirely.
3. **Forecast covariance.** `risk.py` measures realised correlation only. No `Sigma_t`, no
   shrinkage, no factor covariance `B Sigma_F B' + D`.
4. **Prospective trial registration.** `triallog.append` records a run *after* it happens.
   Trial counts are reconstructed from `logs/` afterwards — exactly what the brief forbids.
5. **Frozen research specification.** No artefact declares universe, horizon, metrics and
   rejection criteria *before* a campaign, and nothing distinguishes EXPLORATORY from
   CONFIRMATORY.
6. **Reserved final dataset.** `screen.py --holdout` reserves windows *within* a screen, and
   `backtest.py --split` divides in/out of sample. Neither is a dataset untouched until a
   final decision.
7. **Residual diagnostics suite.** Partial. ADF and OU exist; KPSS, autocorrelation
   structure, skew/kurtosis/tails and rolling stability of loadings do not.
8. **Stability report.** Parameter sensitivity has been measured ad hoc. Loading stability,
   IC stability and turnover stability have not.
9. **Systematic cost stress.** No base/+25%/+50%/+100% sweep.
10. **Rejection taxonomy.** Failures are prose in worklogs, not the codes the brief asks for.

---

## 7. Components to refactor

| Component | Problem | Change |
|---|---|---|
| `strategy.py` | scalar position, two columns | introduce a `TargetWeights` return type; keep `target_position` as the pair implementation of a shared protocol |
| `backtest.py` bar loop | scalar `current`/`current_beta`, positional leg indexing | carry a weight vector; both families feed the same accounting |
| `_carry_bps` / `_turn_cost` | 2-tuple iterable | `zip(symbols, weights)`, denominator becomes gross |
| `pair_report.py` | study + style module + `UserError` + `_fit_ou` in one file | extract `report_style.py` and `errors.py`; leave the study behind |
| `risk.py` | realised correlation only | add a covariance layer beside it, do not replace `effective_bets` |
| `feasibility.py` | single-spread ALIVE/DEAD | accept portfolio expected gross vs expected cost |
| `health.py` | pairwise cointegration p-value | cross-sectional analogue: rolling IC decay and loading stability |
| `triallog.py` | retrospective | add `register()` before a campaign; `append()` stays |
| `pipeline.py` | residual only | accept either family; `--book` for pairs |

---

## 8. Components to deprecate

Deprecate means "stop treating as the main path", not delete. No research history is removed.

| Component | Why | Disposition |
|---|---|---|
| Equity pair screening as the primary search | 4,162 pair tests, measured early/late cointegration independence (5 observed vs 5.9 expected) | keep runnable, demote in docs |
| Crypto pair screening as the primary search | 2,431 tests, late-window gate found 11 against 11.1 expected | same |
| `--holdout 0` | restores the pre-2026-09-14 behaviour that produced two false candidates | warn louder, or remove |
| `--min-healthy-share 0.10` | fitted to four points; documented as passing a pair the monitor calls broken 69% of the time | mark provisional in code, not only in PLAN.md |
| Threshold sweeps as a default habit | the `XLP~XLB` surface ran −3,678 to +3,747 across twelve cells | OU sizing already removes the sweep; make that the default path |

Historical results get classified rather than deleted, using the brief's taxonomy:
`REJECTED_STATISTICAL`, `REJECTED_ECONOMIC`, `REJECTED_OOS`, `REJECTED_COST`,
`REJECTED_STABILITY`. `logs/pair_research.csv` already has a `survived` column; it becomes a
`rejection_code` column.

---

## 9. Components to preserve

Preserve unchanged, and resist the urge to "improve" them:

- The **gross / transaction / carry / net** decomposition. It is the reason every failure in
  this project has an identified cause rather than a shrug.
- The **noise-floor beside every count**. `screen.py` printing "noise alone would give about
  114" next to "400" is what turned a crypto result from a discovery into a measurement.
- The **refusal to aggregate gates into one score**, asserted by `verify_validation.py`.
- The **shuffled null** in `residual.py` and `ic.py`, and the discipline of computing it on
  every run with no flag to skip.
- The **mutation-testing habit**. Twenty-nine deliberate defects across the suites, all
  caught. Several checks were rewritten after passing for the wrong reason, and those
  rewrites are documented in the code.
- The **`triallog` schema guard**.
- The **data defect catalogue**.

---

## 10. Current test coverage

698 checks across seven suites. Counted from the files:

| Suite | Checks | Covers |
|---|---|---|
| `verify_backtest.py` | 117 | `strategy.py`, `backtest.py`, costs, carry, look-ahead |
| `verify_signal.py` | 172 | `outcomes.py`, `thresholds.py`, `risk.py`, `sizing.py` |
| `verify_relationship.py` | 107 | `cointegration.py`, `hedge.py`, `health.py` |
| `verify_validation.py` | 99 | the four validation gates |
| `verify_residual.py` | 77 | `residual.py`, `ic.py`, breadth |
| `verify_pair_report.py` | 65 | `pair_report.py`, `screen.py` |
| `verify_portfolio.py` | 61 | `portfolio.py`, OU sizing, projection, pair books |

**Research-correctness checks — the valuable kind.** The null-calibration check in
`verify_residual.py` catches an in-sample residual construction by detecting that the
shuffled null rejects at 8.2% instead of 5%. The look-ahead group confirms that one poked
forward bar changes its own row and no other. `verify_backtest.py`'s fill-lag guard requires
results to get monotonically worse as the fill is delayed. `purged_cv.py` is verified against
a deliberately planted leak that plain k-fold must score highly and purged must not.

**Implementation-detail checks — the weaker kind.** Checks that pin a value a previous run
produced, without an independent derivation. The project has already caught itself doing
this: three checks in `verify_backtest.py` passed a mutation test for the wrong reason, and a
`verify_portfolio.py` check reported a 6.78x shrink against an expected 2.83x and still
passed on its endpoints.

**What no existing test can catch.** Neither the fill-lag guard nor the purged-CV leak test
detects a survivorship-biased universe or a point-in-time violation. Both operate *within* a
given panel and take the panel's membership as given. This is the largest hole in the suite
and no number of additional statistical tests closes it.

---

## 11. Research-validity risks

Ranked by how much of the existing evidence each one threatens.

**R1 — Survivorship, unbounded.** The equity panel is every name with 5,000+ bars *as of
today*; the SPX screen used *current* index membership over 2006–2026. `EQR` sits in the
store at 14 bars and `AVB` is similarly truncated, both taken over. The bias inflates
positive results. Zero-survivor screens are therefore conservative under it — but **every IC
and lift measured on the residual track is an upper bound**, including the results this
project is currently building on: Stage 0's +2.11% lift and Stage 1's IC of 0.0214. The
shuffled null does not correct for it, because the permutation reorders dates and leaves the
cross-section exactly as it was.

**R2 — Trial count reconstructed, not registered.** 6,440 logged pair tests, counted
afterwards from `logs/screens.csv`. Threshold sweeps, universe variants and timeframe
variants are not separately counted. The real denominator is larger than the recorded one,
which means every deflated Sharpe computed so far is *optimistic*.

**R3 — Validation rules changed after seeing results.** The holdout gate was "at least one
reserved window must reject", then became "the late window decides" after `NUE~STLD` passed
on its early window. The change was correct and well-argued. It was also made after seeing
the result, which is the pattern the brief forbids and which no amount of correctness
retrospectively fixes.

**R4 — No reserved final dataset.** Every window has now been looked at. There is nothing
left that is genuinely untouched for a final decision.

**R5 — Cost estimates flatter in the direction that matters.** Eight crypto profiles were
added at BTC's 1 bp spread for small-cap alts; `ANKR-USDT` trades near $0.0045 where one tick
is a large fraction of a basis point. Marked `estimated`, but the backtests that used them
read as the best in the project.

**R6 — Residual results rest on one panel.** Stage 0 and Stage 1 are one universe, one
frequency, one factor count family. Sensitivity across factor counts was measured; across
universes and regimes it was not.

---

## 12. Proposed target architecture

```
                         shared, strategy-agnostic
  +---------------------------------------------------------------+
  |  marketdata  ->  PIT universe U(t)  ->  research dataset       |
  |  costs  |  execution  |  accounting  |  risk/covariance        |
  |  validation gates  |  trial registry  |  reporting             |
  +---------------------------------------------------------------+
        ^                                          ^
        |                                          |
  PairStrategy                          CrossSectionalResidualStrategy
  A/B -> hedge -> spread                N -> factors -> residuals
      -> OU -> z -> 2 legs                  -> signal -> rank -> weights
        |                                          |
        +------------------+-----------------------+
                           v
              Strategy protocol:
              target_weights(history, state, params) -> dict[symbol, float]
```

The protocol is the whole refactor. A pair returns `{a: +1, b: -beta}`; a residual book
returns 160 entries. Everything below the protocol is shared; everything above it is
strategy-specific. The existing `target_position` becomes the pair implementation rather
than the interface.

Research pipeline, renumbered to the brief's target with dependencies preserved:

```
00 Spec (frozen)  01 Data  02 Quality  03 PIT Universe  04 Dataset  05 EDA
06 Factor def     07 Factor model      08 Residuals     09 Diagnostics
10 Signal         11 IC/ICIR/decay     12 Portfolio     13 Risk/covariance
14 Breadth        15 Costs             16 Backtest      17 IS  18 OOS
19 Walk-forward   20 Robustness        21 Multiple testing
22 Reserved final test                 23 Research decision
```

---

## 13. Migration plan

Incremental. Each milestone states: existing behaviour, problem, new design, migration,
tests. No milestone is allowed to break a passing suite unless the behaviour change is
deliberate and named.

| # | Milestone | Existing behaviour | Migration |
|---|---|---|---|
| M1 | PIT universe | `U(today)` implicit in both loaders | new `universe.py` producing `U(t)`; loaders take an as-of date; old behaviour available behind an explicit flag that warns |
| M2 | Strategy protocol | `target_position` returns scalar | add `target_weights`; `target_position` becomes a thin pair adapter; `verify_backtest` must stay green |
| M3 | N-asset execution | scalar bar loop | vector loop; pair path routed through it and required to reproduce existing results **bit-for-bit** before the old path is removed |
| M4 | Cost generalisation | 2-tuple iterables | `zip(symbols, weights)`; pair results must not move |
| M5 | Trial registry | retrospective `append` | `register()` before a campaign; reconcile against existing logs |
| M6 | Covariance layer | realised correlation | `Sigma_t = D C D` with shrinkage; `effective_bets` untouched |
| M7 | Diagnostics + stability | ADF/OU only | KPSS, autocorrelation, rolling loading/IC/turnover stability |
| M8 | Reserved final set | none | carve and seal; access requires an explicit unseal recorded in a log |
| M9 | Economic gate | implicit | `expected gross > expected cost + buffer`, reported per model |
| M10 | Spec freeze + taxonomy | prose worklogs | `SPEC.md` per campaign; `rejection_code` column |

**M3 carries the most risk** and gets the strongest guard: the pair path must reproduce
existing backtest results exactly through the new engine before the old loop is deleted. If
the numbers move, the refactor is wrong and the old path stays.

---

## 14. Dependency order

```
M1 PIT universe
   |  (everything equity-based is untrustworthy until this lands)
   v
M2 Strategy protocol ---> M4 Cost generalisation
   |                          |
   v                          v
M3 N-asset execution <--------+
   |  (unblocks stages 16-21 for the residual book)
   v
M6 Covariance ---> M9 Economic gate
   |
   v
M7 Diagnostics/stability ---> M8 Reserved final set ---> M10 Spec + taxonomy
                                     ^
M5 Trial registry -------------------+
   (independent; can land any time, and the earlier the better
    because its value is proportional to how much is run after it)
```

M5 has no dependencies and the highest value-per-hour: every campaign run before it exists
is a campaign whose denominator has to be reconstructed.

---

## 15. First implementation milestone — M1, point-in-time universe

**Why first.** It is P0 #1 in the brief and it is the only item that changes the
trustworthiness of results already obtained. Everything else improves what happens next; this
one tells us whether what already happened means anything. It is also the risk with no
statistical remedy — no test in the 698 can detect it from inside a panel.

**Scope.**

- New `code/universe.py` exposing `members(as_of: date) -> set[str]` and
  `eligible(symbol, as_of) -> bool`, backed by a stored membership table with listing and
  delisting dates.
- `residual.load_panel` and `pair_report.load_prices` accept an as-of date and build the
  panel from `U(t)`, not `U(today)`.
- The backtest asserts `AvailableTime(data) <= SignalTime <= ExecutionTime` as an
  **invariant**, raising rather than warning.
- Where genuine PIT data cannot be obtained, the universe is explicitly marked
  `PIT_UNAVAILABLE` and every downstream report carries that label. The brief permits
  restricting scope instead of faking coverage; it does not permit silence.

**The honest constraint.** Real point-in-time index membership and delisting history is
commercial data (CRSP, Compustat). This project has Yahoo and Binance. Binance
`exchangeInfo` lists *current* symbols only — delisted coins vanish from it, so crypto
carries survivorship too. Free approximations exist: the Nasdaq Trader directory gives
current listings with a daily file that can be archived forward from today, and `EQR`/`AVB`
were detected precisely by diffing the store against it.

**So M1 splits in two, and the split should be explicit rather than discovered later:**

- **M1a, achievable now.** Build the framework, mark the current equity universe
  `PIT_UNAVAILABLE`, enforce the timestamp invariant, and begin archiving the listing
  directory daily so that PIT coverage accrues from today forward.
- **M1b, requires a data decision.** Either acquire historical constituent data, or formally
  restrict confirmatory equity research and designate the existing residual results
  EXPLORATORY.

**Tests added.** As-of membership excludes a name listed later; a delisted name is present
before its delisting and absent after; a panel built as-of an earlier date never contains a
symbol whose listing postdates it; the timestamp invariant raises on a constructed violation;
`PIT_UNAVAILABLE` propagates into every report that consumes the universe.

**Known limitation, stated up front.** M1a does not retroactively fix the existing equity
results. It bounds them and labels them. Retroactive correction needs M1b.

**Next gate.** M1 is complete when a panel can be built as of any historical date without
reference to today's universe, or the research scope is formally restricted and every
affected result is relabelled. Until one of those holds, equity residual findings —
including Stage 0's lift and Stage 1's IC — remain upper bounds rather than measurements.

---

## What this report does not claim

It does not claim the existing results are wrong. It claims they are **unbounded above** and
that the system cannot currently tell the difference. That distinction is the entire purpose
of the exercise, and a system that cannot make it is a system that can be fooled.
