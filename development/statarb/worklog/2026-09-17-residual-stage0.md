# 2026-09-17 — `residual.py`, Stage 0 of the residual redesign

## Subject

Build the first stage of [RESIDUAL.md](../plan/RESIDUAL.md): measure whether the
equity residual mean-reverts at all, before any portfolio machinery is written.
The plan sequences it first precisely because it is cheap and falsifying — a day
of measurement gating a month of building.

Stages 1 to 4 were left alone. They are not blocked on anything missing; they are
sequenced behind this answer.

## Status

**Done, and the premise survives. 56 checks in a new suite, 4 mutations caught.**

| Item | Status |
|---|---|
| `residual.py` built | ✅ measurement only, no signal, no trading |
| Stage 0 verdict | ✅ lift **+2.11% ± 0.40%, t = 5.27** over 78 windows |
| Null calibrated to nominal size | ✅ 5.7% against a nominal 5% |
| `verify_residual.py` | ✅ 56 checks, 8 groups |
| Mutation test | ✅ 3 deliberate defects, all caught, 5 of 5 affected groups fired |
| Sensitivity to the searched parameter | ✅ t ∈ [3.36, 6.14] across 9 settings |
| Result logged | ✅ run #1 in `logs/residual.csv` |

## What the measurement says

160 equity names with 5,000+ bars, 5,189 common bars, 2006-01-26 to 2026-09-14.
Fifteen factors fitted on 252 bars; residual accumulated over the 60 bars after.

```
                                     real   shuffled       lift
  unit root rejected at 5%           7.8%       5.7%      +2.1%
  median ADF p-value                0.506      0.529     -0.023
  OU regime is reverting            94.1%      94.5%      -0.3%
  half-life, median (bars)            8.2        9.4       -1.2

  lift +2.11% +/- 0.40% per window over 78 windows, t = 5.27
```

The residual reverts more than chance, by five standard errors, and its half-life
is shorter than the null's. That is all it says. It is not an edge and does not
license a position; Stage 1 asks whether the aggregate signal is positive gross,
and §1.3 of the plan records that financing, not signal, has killed every
candidate this project has produced.

## The one finding that mattered

The first version followed the paper literally and fitted the loadings on the
same sixty bars it then tested. It reported **+0.3% at t = 0.84** — a kill. The
same data, with the residual accumulated over the sixty bars *after* the fit
window, reports **+2.1% at t = 5.27**.

Two separate defects were stacked in the in-sample form:

- **The null was inflated.** Cumulated OLS residuals must return to zero at the
  end of the window they were fitted on, so the accumulated residual is closer to
  a Brownian bridge than to a random walk, and a bridge looks mean-reverting by
  construction. The shuffled null rejected at **8.2%** against a nominal 5%.
- **The signal was erased.** Sixteen fitted parameters on sixty observations
  absorb the very deviation the residual is supposed to carry.

Both push the same way, so the two errors did not cancel — they compounded into a
false kill. The forward construction fixes both at once and has the side benefit
of being the only version a live implementation could actually hold.

This is the reverse of the failure mode the plan warned about in §5 ("three new
places for a defect to flatter results"). Here the defect would have *understated*
the result and stopped the work. Worth recording: the assumption that pipeline
defects always flatter is itself not safe.

## Why the null is not optional

`residual.py` computes the shuffled null on every run and has no flag to skip it.
Everything above explains why: the construction produces apparent reversion on
data with no time structure at all, so the real number is unreadable on its own.
The null is what makes it a measurement rather than a number.

The permutation reorders the date index **jointly across all names**, which
leaves every contemporaneous correlation exactly as it was — PCA still finds the
same factors, and a residual is still a residual — while removing the ordering,
which is the only thing the OU fit and the ADF test read. Shuffling each name
independently would also destroy the cross-sectional structure and leave PCA
fitting noise, which is a different and easier question.

## The unit of evidence is the window, not the name

The first version reported 12,640 "observations" and a lift of +0.3% with no
error bar at all, then declared a pass on the strength of the sign. Both parts
were wrong.

The 160 residuals inside one window share a single factor estimate and are
cross-sectionally correlated, so counting them as 160 independent tests
understates the error by roughly √160. The lift is now paired per window — both
sides measured on the same windows, so the large window-to-window variation
cancels instead of being charged to the difference — and its standard error taken
across the 78 windows. The pass bar is two standard errors, the same one the
backtest engine already applies to every mean it prints, rather than a second and
laxer one invented here.

## Sensitivity

`--factors` is a searched parameter and every value is a trial, so the point of
the sweep is not to find the best setting but to show the verdict does not turn
on one.

| factors | forward window | real | null | lift | t |
|---|---|---|---|---|---|
| 3 | 60 | 7.2% | 5.8% | +1.36% | 3.40 |
| 5 | 60 | 7.4% | 5.8% | +1.54% | 3.68 |
| 10 | 60 | 7.3% | 5.7% | +1.61% | 3.92 |
| 15 | 60 | 7.8% | 5.7% | +2.15% | 5.12 |
| 20 | 60 | 7.7% | 5.6% | +2.09% | 5.05 |
| 30 | 60 | 7.6% | 5.7% | +1.92% | 5.05 |
| 15 | 40 | 8.9% | 6.1% | +2.73% | 6.14 |
| 15 | 90 | 6.5% | 5.2% | +1.31% | 3.36 |
| 15 | 120 | 6.6% | 5.1% | +1.44% | 3.66 |

Every setting passes. The null floor sits at 5.1–6.1% throughout, which is the
independent confirmation that the forward construction faces its nominal null
regardless of how the factors are chosen.

## Verification

Eight groups, 56 checks. Two carry the weight:

- **Null calibration** — the shuffled null must reject near 5%. This is the check
  that catches the in-sample construction, and it did: re-running with the
  loadings fitted in-sample fails it immediately.
- **No look-ahead** — bars after the forward window must not change the residual;
  bars before the fit window must not either; and a single poked forward bar must
  move its own row and no other. That last one is the discriminating check,
  because if the loadings had seen the forward window, one changed bar there
  would shift every row.

The rest cover the ground truth (a planted white-noise residual level is detected
loudly, a planted random walk is not, and the detected lift falls monotonically
as the planted level approaches a unit root), the correlation-versus-covariance
decomposition, the hand-computed lift statistic, the permutation's properties,
the OU regime labels, and the input guards.

Mutation test — three deliberate defects, all caught:

| Mutation | Caught by |
|---|---|
| Loadings fitted in-sample | look-ahead group, null calibration |
| Covariance instead of correlation | factor group, 2 checks |
| Permutation returns its input | shuffle group (3 checks), null calibration |

One check was rewritten after failing for a reason worth keeping. A lift that is
identical in every window has no spread to estimate from, but floating point puts
its standard error at about 1e-17 rather than at zero, so the original guard
(`se > 0`) passed and produced a **t of 1.0e16** — an overwhelming result
manufactured entirely by rounding. That case is now refused outright rather than
reported, because windows that all return the same share mean the real and
shuffled sweeps were handed the same input, which is a defect to find rather than
a result to print.

## Incidental finding

`EQR` holds 14 bars in the store and `AVB` is similarly truncated; neither appears
in the current Nasdaq Trader symbol directory. Both are in
`instruments.py`'s `reits` sector. This is the same failure already documented
there for ANSS, HES, K, MRO, SKX and X — names taken over, whose series a pair
would silently truncate to. `load_panel` filters on bar count *before* the join
for exactly this reason: either name alone would have cut the twenty-year panel
to a fortnight. The sector list itself has not been edited.

## Next

Stage 1 — form the equal-weight portfolio of all residual signals and measure
expectancy across names rather than per name. Kill criterion: aggregate gross
expectancy at or below zero **before costs**, since `√breadth` multiplies the
edge and multiplying zero gives zero.
