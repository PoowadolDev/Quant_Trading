---
name: factor-residual
description: >
  Remove common movement from a universe of returns with a PCA factor model and
  test whether what is left mean-reverts more often than chance. Covers the
  eigenportfolio decomposition, the forward residual construction, the
  Ornstein-Uhlenbeck fit per name, the unit-root test, and the shuffled null
  that makes the result readable. Use whenever the user asks about factor
  residuals, eigenportfolios, residual mean reversion, whether a cross-section
  has anything tradable in it, how to trade many names at once instead of one
  pair, or about Avellaneda-Lee style statistical arbitrage — including phrases
  like "residual stat arb", "PCA factors", "does the residual revert", "trade
  the cross-section", "factor neutral", "eigenportfolio", "Stage 0", or before
  building any signal on a residual. Never fit a factor model and test its own
  residual on the same bars while this skill applies; `residual.py` measures
  forward because the in-sample version inflates the null and erases the signal
  at the same time.
---

# Factor residual — decompose, accumulate forward, test against a null

| File | Role |
|---|---|
| `residual.py` | fit the factor model, build forward residuals, test for reversion |
| `verify_residual.py` | 79 checks across ten groups, covering this and `ic.py` |

## Working directory

```bash
cd development/statarb/code
```

## The constraint everything else follows from

> The residual must be accumulated over bars **after** the window its loadings were
> fitted on. Not as a refinement — as the difference between a measurement and an
> artefact.

Cumulated in-sample OLS residuals are constrained to return to zero at the end of the
window that fitted them, which makes the accumulated residual a Brownian bridge. A bridge
looks mean-reverting by construction. Run the pipeline on data with no time structure at
all and it still reports reversion.

Measured on this project's 160-name equity panel:

| construction | shuffled null rejects | real lift | t |
|---|---|---|---|
| in-sample, as the papers present it | **8.2%** | +0.3% | 0.84 |
| forward, as `residual.py` does it | **5.7%** | +2.1% | **5.27** |

The in-sample version inflates the null *and* erases the signal. Both errors push the same
way, so they compound into a false kill. The forward residual is also the only one a live
implementation could hold, so the honest measurement and the tradable object are the same
thing.

## Workflow

### 1. Check the universe is wide enough

A factor model needs a cross-section. With 15 names the leading eigenvector is not
separable from noise, so the "factor" *is* estimation error and the residual inherits it
rather than being cleaned by it. Forex (15) and crypto (18) cannot support this method.
Equities (160 with 5,000+ bars) can.

### 2. Measure reversion before building anything

```bash
python residual.py
python residual.py --factors 5 --step 21
python residual.py --min-bars 3000 --json
```

Exit codes: `0` the residual reverts by more than two standard errors, `3` it does not —
which is a **result**, not a failure — `2` usage error.

### 3. Read the null column, not the real column

The real number alone is unreadable. The comparison is the measurement.

## Options

### Selection

| Flag | Default | Meaning |
|---|---|---|
| `-a, --asset-class` | `equity` | only equities have a wide enough cross-section |
| `-t, --timeframe` | `1d` | |
| `--min-bars` | `5000` | applied per series **before** the join |
| `--source` | none | restrict to one feed |

`--min-bars` filters before joining on purpose. `EQR` sits in the store at 14 bars and
`AVB` is similarly truncated — both were taken over and are absent from the current
listing directory. Either one alone would cut a twenty-year panel to a fortnight.

### Structure — choose once, not per run

| Flag | Default | Meaning |
|---|---|---|
| `--pca-window` | `252` | bars the factor model is estimated on |
| `--ou-window` | `60` | bars **after** the fit window the residual is accumulated over |
| `--step` | `63` | exceeds `--ou-window` so tested residuals never overlap |
| `--adf-lags` | `1` | fixed; the choice moves the rejection rate under a percentage point |

### Searched — every value is a trial

| Flag | Default | Meaning |
|---|---|---|
| `--factors` | `15` | principal components removed |
| `--level` | `0.05` | significance level |
| `--null-draws` | `3` | permutations averaged into the null |
| `--seed` | `0` | |

### Output

`--json` · `--log` · `--no-log` · `-q` · `-v` · `--store`

## Reading the output

```
equity residual reversion   160 names   5,189 common bars   2006-01-26 to 2026-09-14
  15 factors fitted on 252 bars, residual accumulated over the 60 bars after, stepped 63

                                     real   shuffled       lift
  residuals tested                 12,480     37,440
  unit root rejected at 5%           7.8%       5.7%      +2.1%
  OU regime is reverting            94.1%      94.5%      -0.3%
  half-life, median (bars)            8.2        9.4       -1.2

  lift +2.11% +/- 0.40% per window over 78 windows, t = 5.27
```

**The null at 5.7% is the line to check first.** The forward construction faces the plain
ADF null, so it must land near the nominal 5%. Anything approaching 8% means the in-sample
bug is back.

**The unit of evidence is the window, not the name.** The 160 residuals inside one window
share a single factor estimate and are cross-sectionally correlated, so counting them as
160 independent tests understates the error by roughly the square root of 160. The lift is
paired per window and its standard error taken across windows.

**`reverting` at 94% is not a result.** It is what an OU fit reports on almost any series;
the null says 94.5%. Only the *lift* carries information.

## Verifying

```bash
python verify_residual.py          # 79 checks, about four minutes
python verify_residual.py -v
```

Ten groups: ground truth, null calibration, look-ahead, the factor step, the lift
statistic, the permutation, OU scoring, input guards, information coefficient, breadth.

Two carry the weight. **Null calibration** catches the in-sample construction — re-running
with loadings fitted in-sample fails it immediately. **Look-ahead** checks that one poked
forward bar changes its own row and no other, which is exactly how a leak would present.

Mutation-tested: loadings fitted in-sample, covariance instead of correlation, and a
permutation that returns its input — all three caught.

One check was rewritten after passing for the wrong reason. A lift identical in every
window has no spread, but floating point puts its standard error at about 1e-17 rather
than zero, so a `se > 0` guard passed and produced a **t of 1.0e16**. That case is now
refused outright.

A second check asserted IC falls monotonically as the planted level approaches a unit
root, and failed: measured 0.324 at phi = 0 against 0.374 at phi = 0.7, where theory says
0.707 against 0.645. The stationary level variance is `sigma^2/(1 - phi^2)`, so the higher
phi carries more amplitude against constant estimation noise and the signal-to-noise gain
outweighs the theoretical loss. The ordering is now asserted only where the arithmetic
supports it.

## Rules

- Never fit the factor model and test its residual on the same bars.
- Never report the real rejection share without the shuffled null beside it.
- Never run this on a universe below about 50 names; the factor would be noise.
- Never treat "94% reverting" as evidence — compare it with the null, which says the same.
- Never read a passing lift as an edge. It says the object exists, nothing more.

Related: **ic** measures whether a signal built on these residuals predicts anything;
**portfolio** sizes them; **pipeline** runs the whole sequence. Plan:
`development/statarb/plan/RESIDUAL.md`.

A passing lift here is a property of the data, not a strategy. It has been charged no
spread and no financing, and the panel is survivor-filtered, so it is an upper bound.
