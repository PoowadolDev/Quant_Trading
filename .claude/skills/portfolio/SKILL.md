---
name: portfolio
description: >
  Turn several mean-reverting series — a book of named pairs, or a whole
  residual cross-section — into position sizes derived from the fitted process
  rather than from a threshold somebody chose, then refuse the book if it
  breaches a cap. Covers Ornstein-Uhlenbeck sizing, the uncertainty haircut
  applied before any size is taken, the unit-root test that stops a random walk
  being sized as if it reverted, factor neutralisation by projection, the
  heavy-loading gate, gross and net exposure budgets, independent-bet counting
  and the drawdown kill switch. Use whenever the user asks how to hold more than
  one pair at once, how to combine many signals into a book, what weight each
  relationship should carry, how to split capital across pairs, how to size
  without an entry threshold, whether a book is really market-neutral, or how
  concentrated a portfolio is — including phrases like "portfolio
  construction", "more than one pair", "manage a book", "position weights", "how
  much of each", "split capital", "OU sizing", "is the book neutral", "net
  exposure", "allocate across names", or before running a multi-relationship
  strategy through a backtest. Never pick a z-score
  entry threshold or hand-weight a book while this skill applies; `portfolio.py`
  derives the size from theta, mu and sigma, and every threshold removed is a
  trial Step 4 no longer has to charge.
---

# Portfolio — size from the process, not from a threshold

| File | Role |
|---|---|
| `portfolio.py` | fit OU per series, derive weights, neutralise, apply the book-level caps |
| `risk.py` | the book loader (`parse_book`, `load_book`) and the caps |
| `verify_portfolio.py` | 70 checks across nine groups |

## Working directory

```bash
cd development/statarb/code

python portfolio.py                                        # residual cross-section
python portfolio.py --book NUE~STLD:equity,HBAN~KEY:equity  # a book of named pairs
python portfolio.py --dates 12 --json                      # is the last bar typical?
```

## Two book types, one sizing rule

A pair spread and a factor residual are the same kind of object: a series that reverts to
its own mean. `w = theta(mu - X)/sigma^2` applies to either, and both modes call the same
`size_from_ou`, so they cannot drift apart.

| mode | input | what is sized |
|---|---|---|
| residual | the stored panel | 160 PCA residuals |
| pair | `--book A~B:class[,...]` | each hedged spread, refit on a rolling window |

Pair mode is why this script exists at all. `risk.py` can *check* a book of pairs but
refuses to weight one — `book_equity` says outright *"Equal weights because sizing is
`sizing.py`'s job"* — and `sizing.py` sizes one pair against the full equity in isolation
from the others. Nothing else in the project turns several relationships into capital
shares.

## Why it exists

`STEP3.md` deferred this script with the reason "needs two candidates to mean anything, and
there are none". That reason expired when the residual track replaced one pair with a
cross-section. There are 160 concurrent signals, and combining them is the entire point of
the redesign.

> Every earlier position in this project was sized by a swept threshold — enter at
> `z = 2.0`, exit at `0.5` — with the pair of numbers chosen by trying several. Here the
> size is a consequence of the fitted process instead.

```
dX      = theta(mu - X)dt + sigma dB     the residual, fitted per name
drift_i = theta_i(mu_i - X_i,t)          expected return from where it sits now
w_i     = drift_i / sigma_i^2            growth-optimal
```

The last line is not a new formula. The growth-optimal leverage of a bet with mean `mu` and
deviation `sigma` is `mu/sigma^2`, and the OU drift supplies the mean. Kelly sizing and OU
sizing are the same arithmetic reached from two directions, so this script calls
`sizing.growth_optimal_leverage` rather than writing a second copy that can drift out of
agreement with the first.

**What it costs.** One free parameter is exchanged for three estimated ones. An overstated
reversion speed now oversizes with no threshold left to cap it, which is why the two guards
below are not optional.

## Workflow

### 1. The uncertainty haircut comes before the size, not after

`sizing.lower_bound_mean` discounts the drift by its own standard error before it is
allowed to size anything. Every parameter in this project has moved by a factor of several
across windows; full-confidence sizing on an estimate that unstable is a way to lose the
account while being right on average.

A haircut larger than the estimate **closes** the position. It must never reverse it — the
magnitude is haircut and the sign put back afterwards, so a negative magnitude cannot flip
a long into a short.

### 2. The heavy-loading gate is the paper's own documented failure

The construction this comes from records where it breaks: the largest factor loadings
produce the largest positions and, once transaction costs are charged, heavy losses. A name
whose loading norm is far above the cross-section is the analogue of a pair with a large
hedge ratio, and this project has already been burned once by not having that gate.

The threshold is a multiple of the median, not an absolute number, because the scale of a
loading depends on how many factors were removed.

### 3. Neutrality is algebra, not luck

Originally the residual book was neutral only because independent drifts cancelled, and net
over gross therefore scaled as `1/sqrt(N)`:

| names | predicted | measured |
|---|---|---|
| 160 | 7.9% | 7.8% standard deviation, mean +1.8% |
| 20 | 22% | 18.9% |

That is cancellation, not neutrality, and on one date it left the book +47% net. The weight
vector is now projected onto the null space of the factor loadings:

```
w_neutral = w - L' (L L')^-1 L w
```

so the book's factor exposure `L w` is zero to floating point. Measured effect:

| | before | after |
|---|---|---|
| net on the last bar | +47.4% | **+8.2%** |
| standard deviation of net across 12 dates | 7.8% | **3.6%** |
| dates breaching the 10% cap | about 1 in 5 | **none** |
| weight correlation with pre-projection | — | +0.910 |

The cap was **not** moved. The correlation of +0.910 is what says the projection removed
unintended exposure rather than signal, and it is reported on every run for that reason.

**The projection runs only over names the gates already allow.** Run over all 160 it puts
weight back on every name the haircut closed and on the one the heavy-loading gate dropped
— measured, 70 gated names became a book of 160, silently removing the gate.

### 4. Reversion has to be tested, not fitted — in pair mode

The OU fit calls a series reverting whenever its AR(1) coefficient lands in (0, 1), and on
a few hundred points a random walk does that as a matter of course, the estimate being
biased downward by about `1 - c/n`. Six pure random walks tested here came back `reverting`
every time with half-lives of 26 to 51 bars, and two were sized at −2.98 and +5.72.

So **pair mode** puts every spread through a unit-root test first. A handful of pairs has a
breadth of a handful; each one has to be real, and a `--book` is whatever the caller names.

**The residual cross-section is deliberately exempt**, and that asymmetry is
`RESIDUAL.md` §1.4 rather than an inconsistency. A portfolio of 160 residuals *"does not
need any individual name to be significant — it needs the average to be positive"*, and the
aggregate evidence is Stage 0's lift over a shuffled null and Stage 1's IC. Applied to the
residuals the gate admits about 8% of names — exactly the measured rejection rate — leaving
10 names against 15 factors and no book at all.

## Options

### Selection

| Flag | Default | Meaning |
|---|---|---|
| `--book` | none | `A~B:class[:broker]`, comma separated; switches to pair mode |
| `-a, --asset-class` | `equity` | residual mode |
| `-t, --timeframe` | `1d` | |
| `--min-bars` | `5000` | applied per series before the join |
| `--start`, `--end` | none | |

### Structure — choose once, not per run

| Flag | Default | Meaning |
|---|---|---|
| `--pca-window` | `252` | bars the factor model is estimated on |
| `--signal-window` | `60` | trailing bars the residual is accumulated over |
| `--factors` | `15` | principal components removed |
| `--step` | `21` | used only for the breadth sample, which tiles the panel |
| `--neutralise` / `--no-neutralise` | on | project onto the null space of the loadings |
| `--fit-window` | `250` | pair mode: bars the hedge ratio is refit on |
| `--rehedge-every` | `5` | pair mode: bars between hedge refits |

### Given by reality

| Flag | Default | Meaning |
|---|---|---|
| `--gross` | `1.0` | gross exposure budget; scaling is uniform, so it sets how much of the book to hold and not its shape |

### Gates — every value is a trial

| Flag | Default | Meaning |
|---|---|---|
| `--confidence` | `1.0` | standard errors of haircut on the drift |
| `--max-loading-multiple` | `3.0` | a name above this multiple of the median loading norm is not held |
| `--max-net` | `0.10` | net over gross; calibrated for a 160-name panel |
| `--max-correlation` | `0.70` | largest absolute correlation between two residuals |
| `--min-effective-bets` | `20.0` | independent bets the cross-section must contain |
| `--unit-root-level` | `0.05` | **pair mode only**; see workflow step 4 |
| `--min-pair-bets` | `1.5` | pair mode: independent bets the book must contain |
| `--max-leg-net` | `0.35` | pair mode: net exposure one relationship may carry |

### Output

`--json` · `--show` · `--dates N` · `--dry-run` · `--log` · `--no-log` · `-q` · `-v`

`--dates` sizes at N evenly spaced formation dates and reports the spread of net
exposure. Sizing only the last bar is what let one unusual date decide a verdict.

## Reading the output

```
  160 residuals fitted, 70 held, 90 at zero
  gross 1.000   net +0.0815 (+8.2% of gross)   132.2 independent bets

  name       regime        half-life         X      drift    haircut    weight
  ED         reverting           2.4   -0.0179   +0.00328   +0.00268   +0.1189
  WCN        reverting           2.1    0.0178   +0.00755   +0.00635   +0.0699

  not held: 1 explosive, 89 reverting

  factor-neutralising: exposure ||Lw|| 1.040e+00 -> 2.253e-15
  cost of the projection: weights correlate +0.9100 with their pre-projection values,
  gross 1053.406 -> 1133.206 before rescaling.

  ACCEPTED — 70 positions, gross 1.00, net +8.2% of gross, 132.2 independent bets.
```

And in pair mode, on the five candidates from screen #22:

```
  5 pairs fitted, 1 held, 4 at zero

  name                 regime        half-life         S      drift    haircut    weight    beta
  HBAN~KEY             reverting          22.3    0.5430   +0.00745   +0.00454   +1.0000   0.386

  not held: 2 explosive, 2 unidentified

  REFUSED — 1 breach(es):
    - HBAN~KEY is 44% net exposed, above the 35% cap, so most of its risk is directional
```

**`unidentified` is not `explosive`.** Explosive means the series walks away; unidentified
means the OU fit reported a half-life the unit-root test cannot distinguish from a random
walk's small-sample bias. Four of these five pairs died at the late-window gate in screen
#22, and the allocator refuses them for consistent reasons.

**The `drift` and `haircut` columns beside each other are the point.** The gap between them
is what the uncertainty discount removed. When it closes to zero the position closes too.

**"89 reverting but not held" is not a contradiction.** Those names revert but their drift
did not survive its own standard error. That is the haircut working.

**A refusal is a result.** The example above is real: at the last bar the haircut bit hard,
70 names survived instead of the usual 155, and the survivors happened to be one-sided. The
gate caught a book that was not neutral. Across eleven other formation dates the same code
produced a mean net of +1.8%.

## Verifying

```bash
python verify_portfolio.py         # 45 checks, about three minutes
python verify_portfolio.py -v
```

Seven groups: the sizing identity, magnitude, regimes, heavy loadings, scaling, book-level
caps, and input guards.

The identity group checks that every weight equals `sizing.growth_optimal_leverage` of the
haircut drift to within 1e-9 — against `sizing.py`'s own function, not a second copy of the
formula. The magnitude group checks that doubling the deviation quarters the size exactly,
that raising the haircut never raises gross, and that a haircut exceeding the drift closes
rather than reverses.

Mutation-tested: haircut skipped, haircut allowed to reverse the sign, heavy-loading gate
turned into a no-op, and the gross budget ignored — all four caught.

One check was rewritten twice. It asserted net over gross shrinks as the square root of the
panel width, and a first version compared single draws and measured 6.78x against an
expected 2.83x, because `|net/gross|` is a folded mean-zero quantity and the ratio of two
draws of it is mostly noise. A second version averaged five seeds and printed
`26.6% -> 5.4% -> 23.7% -> 9.1%` — no decay at all — yet the endpoints happened to give
2.92x and the bound passed. The law runs on names *held*, which the haircut decides
independently of panel width, so the magnitude claim was dropped and only the direction is
asserted, over twelve seeds.

## Rules

- Never pick an entry or exit threshold here. The size is continuous in the drift.
- Never size a name outside the reverting regime; `theta` is zero there by design.
- Never skip the uncertainty haircut, and never let it reverse a position's sign.
- Never compare net exposure with zero. Compare it with `1/sqrt(N)`.
- Never report a book without saying how many names were fitted, held and zeroed.
- Never let the projection run over names the gates closed; it silently removes the gates.
- Never demand per-name significance of a residual cross-section — that is the breadth the
  redesign exists to buy, and RESIDUAL.md 1.4 is explicit about it.
- Never size a pair without the unit-root test. The OU fit calls random walks reverting.
- Never treat an accepted book as a result. Nothing here has been charged a spread.

Related: **ic** measures whether the signal being sized predicts anything; **factor-residual**
builds the residuals; **sizing** owns the growth-optimal arithmetic and the haircut;
**tradingcosts** charges what this has not. Plan: `development/statarb/plan/STEP3.md`.

An accepted book is the position as it stands on one bar. What it would have earned is a
different question, and financing rather than signal has killed every candidate so far.
