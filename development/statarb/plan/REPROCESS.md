# Reprocess — plan, progress, and how to resume

**Paused 2026-09-18 after step 3 of 11. Steps 1–3 done and verified. Resume at step 4.**

This file is both the plan and the bookmark. Everything needed to pick the work back up is
here: what was decided, what changed, the exact numbers that must still reproduce, and the
next command to run.

---

## Why this is happening

Four requests: reprocess everything, delete unnecessary `.md` and code, produce **one** HTML
instead of five duplicating ones, and make stages 00–21 all run — deleting `pipeline.py` and
redesigning it.

Exploration confirmed all four and quantified them.

**The reports duplicate work, not just headings.** For a single pair, `bt.run_backtest` is
executed with identical base parameters by `backtest.py` (once), `signal_report.py` (~7
times, once per threshold grid cell) and `validation_report.py` (~21 times). The equity chart
is emitted byte-identically in three reports; the per-trade histogram in two. The hedge ratio
β is computed four different ways with no reconciliation. `studies/` held **93 files, 18 MB**,
with `XLP~XLB` alone described by nine pages. **No report links to any other and nothing reads
an HTML file back.**

**Stages 16–21 are blocked by three missing things, not by arity alone.** Everything in
`backtest.py` below line 288 is already cross-sectional-safe. But: there is no cross-sectional
decision function; no stored sequence of target weights (`portfolio.size_across_dates` loops
formation dates and **discards every `Book`**, keeping three scalars); and no rebalance-event
concept — `Trade` has `direction`, `entry_z`, `exit_z`, all of which presuppose a position
with a discrete lifetime.

**The docs disagree with themselves.** Six different figures are in use for the pair-test
count that every deflated Sharpe divides by — 850, 1,300, 3,629, 4,009, 4,162, 6,440. Check
counts disagree five ways. `STEP2.md` still lists `factors.py` as deferred; it was built as
`residual.py`, and no STEP file mentions `residual.py`, `ic.py` or `scorecard.py`.

## Decisions taken

1. Consolidate `plan/` from 8 files to 3: `PLAN.md`, `METHOD.md`, `FINDINGS.md`. One
   authoritative trial count, derived from the logs rather than typed.
2. Move `studies/` and `worklog/` to `_archive/` first, verify the new code reproduces them,
   then delete. Nothing deleted before its replacement is proven.
3. One pipeline covering both tracks, pair and residual.

---

## Progress

| # | Step | State |
|---|---|---|
| 1 | Archive originals | ✅ done |
| 2 | Close the duplications | ✅ done |
| 3 | Extract `report_style.py` | ✅ done |
| 4 | N-arity cost variants + `verify_replay.py` skeleton | ⬜ **next** |
| 5 | `portfolio.weight_series()` | ⬜ |
| 6 | `replay.py` | ⬜ |
| 7 | `research.py`, pair track | ⬜ |
| 8 | `research.py`, residual track | ⬜ |
| 9 | Delete old report generators and the dead list | ⬜ |
| 10 | Docs to 3 files | ⬜ |
| 11 | Delete `_archive/` | ⬜ |

### Step 1 — archive ✅

`development/statarb/_archive/2026-09-18/` holds **120 files, 18 MB**: `studies/`, `worklog/`
and the 8 original `plan/*.md`. Originals are still in place; nothing has been deleted.

`logs/*.csv` deliberately stay where they are. `deflated_sharpe.count_trials` reads them to
charge the multiple-testing denominator, and that is the one number that must never be lost.

### Step 2 — duplications closed ✅

Done **before** the refactor on purpose: unifying a formula two modules compute differently
either changes nothing (proving they agreed) or changes a published number (proving they did
not), and the existing suites are what make that question cheap to ask.

| duplication | outcome |
|---|---|
| **`sigma_eq` by two algebraic routes** — `pair_report._fit_ou` vs `strategy.py` | **Agree to 2.0e-16**, machine epsilon. No published number moves. Now locked by a permanent check |
| hedge fit in `strategy.py` (the production decision path) and `cointegration.py` | routed through `relationship.ols_beta` |
| PCA loading fit, byte-identical in `ic.py`, `portfolio.py`, `residual.py` | → new `residual.fit_loadings()` |
| `purged_cv.py:132` | **deliberately not unified** — `score_fold` fits a predicted-vs-actual slope, not a hedge ratio between two price series. Same reasoning `relationship.py` gives for leaving the OU fit alone |

`sigma_eq` is the denominator of every z-score the strategy trades and the multiplier in every
expected-move figure this project has published. It was computed in two places for the whole
life of the repo with nothing comparing them. `verify_backtest.test_sigma_eq_agreement` now
does, across the AR range and through `fit_relationship` itself.

**A bug was introduced and caught before it ran.** The patch that routed the three PCA copies
through the new helper replaced the helper's *own body* with a call to itself — infinite
recursion — because the helper contained the first occurrence of the pattern being replaced.

### Step 3 — `report_style.py` ✅

**353 lines**, holding `CSS`, `EXTRA_CSS`, `line_chart`, `histogram`, `bar_chart`,
`waterfall_chart`, `state_timeline`, `_row`, `_grid_and_ticks` and the `W/H/PAD_*` constants.

`EXTRA_CSS` had been forked three ways: `.big` with gaps of 14px, 18px and 18px and margins of
14px, 6px and 6px; `text.barlab` with `fill:var(--muted)` in one file and `fill:var(--fg)` in
another. Nobody chose those differences — they are what happens when a block is pasted three
times. One definition now.

`pair_report.py` went from **888 to 712 lines** and re-exports every name, so the twenty-one
existing importers keep working unchanged while the reports are consolidated.

---

## Reproduction gates — re-run these before and after any further change

These are the contract. If any of them moves, the change is wrong.

```bash
cd development/statarb/code

# pair engine, bit-for-bit
python backtest.py -s NUE,STLD -a equity --broker equity --brief --no-trial-log
#   103 trades, 57% winners, 15.7 bars held on average
#   gross +6,448.2  transaction -309.0  carry -2,506.2  net +3,633.0 bps

# residual track Stage 0, bit-for-bit
python residual.py --no-log
#   160 names, 5,189 common bars
#   lift +2.11% +/- 0.40% per window over 78 windows, t = 5.27

# crypto screen funnel, bit-for-bit
python screen.py -s "$(cat ../../../crypto_universe.txt)" -a crypto --no-research-log --no-log
#   cointegrated 400 / out of sample 51 / still there now 11 / stable 9 / hedged 6 / reverting 6
```

### Suite counts as of the pause — 840 total

| suite | checks |
|---|---|
| `verify_signal` | 189 |
| `verify_backtest` | **131** (was 118; +13 from the `sigma_eq` group) |
| `verify_relationship` | 123 |
| `verify_validation` | 123 |
| `verify_residual` | 79 |
| `verify_pair_report` | 72 |
| `verify_portfolio` | 70 |
| `verify_scorecard` | 53 |

---

## Resume here — step 4

### 4. N-arity cost variants

`_carry_bps` and `_turn_cost` in `backtest.py` (lines 261–285) are already a per-leg sum:

```python
for symbol, units in ((a, pos_a), (b, pos_b)):
    total += abs(units) * cost.carry_bps("long" if units > 0 else "short")
return total / (1.0 + abs(beta))
```

The arithmetic is arity-agnostic. Three things are pair-specific: the iterable is a hard-coded
2-tuple (→ `zip(symbols, weights)`), the weights come from `sig.leg_weights` which returns two
floats (→ take the vector directly), and the normaliser is `1 + |beta|` (→ `sum(|w|)`).

**Add N-arity variants; do not change the existing signatures.** `carry_per_night_bps`,
`cheaper_direction` and `round_trip_bps` have ten external call sites in `screen.py`,
`signal_report.py`, `thresholds.py` and `verify_signal.py`. `cheaper_direction` has no
cross-sectional meaning at all — it picks the cheaper side of *a* spread.

### 5. `portfolio.weight_series()`

```python
def weight_series(returns, names, args, *, every: int) -> tuple[np.ndarray, list[int]]
```

`assemble(returns, names, end, args)` already returns a gated, factor-neutral, gross-budgeted
weight vector at any formation date. `size_across_dates` (portfolio.py:511) loops dates and
keeps only `net_share`, `len(held)` and `gross`. Keep the weights instead. Cadence is `every`
bars tied to the signal horizon, not `np.linspace`. `neutralise` can raise mid-loop when held
names ≤ factors or the projection annihilates the book — catch per date, record, skip.

### 6. `replay.py`

```python
def replay_weights(prices, weights, profile, *, bars_per_night, lag=1) -> Result
```

**Do not mutate `run_backtest`.** Reuse everything below line 288 — `drawdown`,
`sharpe_ratio`, `underwater_bars`, the equity accumulation, `summarise` — all of which take
1-D arrays and do not care how positions were formed.

`Rebalance` replaces `Trade` for this path: `bar`, `time`, `names_changed`, `turnover`,
`gross_before/after`, `net_before/after`, `cost_bps`, `carry_bps`. A continuously resized book
has no entry, no exit and no direction, and forcing it into `Trade` would make `direction` a
lie.

**The trap that needs its own check:** `portfolio` fits weights on **log** returns, one row
shorter than the panel; `run_backtest` accrues P&L on **simple** returns. The offset must be
reconciled deliberately.

### 7–8. `research.py`

One script, one page, stages 00–21, both tracks. Every stage runs; nothing is skipped because
an earlier one failed. The ~28 redundant `run_backtest` calls collapse to one per genuinely
distinct configuration. Output `studies/research-{track}-{name}-{date}.html`.

**No overall score** — the `STEP4.md` refusal and `verify_validation.test_no_aggregation`
stand.

Two stages honestly report `NOT_EVALUABLE` on the residual track and say why: **PBO**, because
`overfit.cscv` needs ≥2 configurations and the residual track deliberately sweeps nothing —
inventing an axis to fill the box would be manufacturing trials to satisfy a gate; and
**Benjamini-Hochberg**, which is screen-level and needs per-name p-values the residual track
does not produce by design.

### 9. Delete — every item has a `grep` behind it

| what | evidence |
|---|---|
| `logs/*.bak`, 11 files | zero references; `-nowindow` predates the reserved-window columns, `-v1` predates the `triallog` guard |
| 8 of 11 `logs/dump-*.csv` | zero references. Keep `dump-equities`, `dump-fx`, `dump-crypto-1d` — read by `multiple_testing` |
| `worklog/mockup-pair-AUDUSD-NZDUSD.html`, 191 KB | predates `pair_report.py`; nothing links it |
| `data/stats_list.csv`, 1.9 MB | **zero code references**, not in `paths.py`, not in the README tree |
| `screen.grade()` | added, never called, not even by a check |
| `pair_report.price_series()` | used only by the `build_html` being deleted |
| `docs/diagrams/research-pipeline.md` | stale: "595 checks across five suites", no node for six modules |

`contribution.py` is **not** deleted. It is genuinely uncalled in production, but the results
in `SCORECARD.md` §6 came from it and step 7 wires it in. Being uncalled is the bug, not the
module.

### 10. Docs — 8 to 3

| new | absorbs |
|---|---|
| `PLAN.md` | status board, 24-stage map, where the search has been |
| `METHOD.md` | `RESIDUAL.md` §2, `SCORECARD.md`, `STEP1–4.md` |
| `FINDINGS.md` | every measured result and every death, plus `REPROCESSING.md`'s risk register |

Three worklog chains are already superseded and collapse to their last entry: crypto
(`2026-09-16-crypto-screen` → `crypto-hunt` → `crypto-wide-screen`), Step 3 (`step3` →
`step3-audit` → `crosscheck`), and `2026-09-14-screening`, which `screen-rebuild` retracts.

**One number, derived not typed.** The trial and check counts go in `PLAN.md` once, computed
at write time from `logs/screens.csv` and the suites, with the command recorded beside the
figure. Six hand-maintained copies is how six different answers happened.

### 11. Delete `_archive/` — only after the gates above pass

---

## Files changed so far

**New:** `code/report_style.py`, `code/scorecard.py`, `code/contribution.py`,
`code/verify_scorecard.py`, `plan/REPROCESSING.md`, `plan/SCORECARD.md`, this file.

**Modified:** `code/pair_report.py` (888→712), `code/strategy.py`, `code/cointegration.py`,
`code/residual.py`, `code/ic.py`, `code/portfolio.py`, `code/screen.py`, `code/triallog.py`,
`code/pipeline.py`, `code/verify_backtest.py`, `plan/RESIDUAL.md`.

**Archived, not deleted:** `_archive/2026-09-18/` — 120 files.

## Risks carried forward

- **The pair engine moving.** `NUE~STLD` reproducing bit-for-bit is the gate.
- **Cost profiles for ~160 names.** `_carry_bps` raises per missing name; the equity profile
  covers 10. Stage 14 must report the shortfall rather than silently pricing at zero.
- **One page from 18 MB of source.** Old pages ran 65 KB–688 KB, mostly inline SVG path data.
  Charts need decimating to a width budget and the size checked.
- **`research.py` becoming the new god-module.** It replaces five files; the guard is that it
  computes nothing itself — every number comes from an existing verified module and it only
  arranges them.
