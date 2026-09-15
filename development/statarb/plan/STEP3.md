# Step 3 — Signal, risk and sizing, split into runnable pieces

Step 3 in `PLAN.md` is the layer that turns a relationship into positions: where to enter,
where to leave, how much to hold, and when to stop. This file splits it into five scripts
run by hand from the command line, in the same style as Step 1 and Step 2.

> **Order set 2026-09-14 after measuring, not guessing.** The same question was asked of
> each candidate component that was asked in Step 2: *what would this have caught that the
> current pipeline missed?* The answers moved the trade-outcome model to the front and
> pushed threshold optimisation behind it, because the measurement below shows that
> optimising thresholds on the numbers the pipeline currently produces would be optimising
> a quantity that is wrong by an order of magnitude.

| Order | Script | Why here | State |
|---|---|---|---|
| 1 | `outcomes.py` | the expected move the whole pipeline is built on over-predicts by 10× to 68×, and nothing measures it | ✅ built |
| 2 | `thresholds.py` | entry, exit and **maximum holding period**, from measured outcomes and the financing constraint | ✅ built |
| 3 | `risk.py` | spreads that look independent share legs; without this a book is concentrated while appearing diversified | ✅ built |
| 4 | `sizing.py` | growth-optimal leverage; Sharpe is leverage-invariant and cannot answer this | ✅ built |
| 5 | `verify_signal.py` | none of the above is trustworthy unverified | ✅ 185 checks green |
| — | `signal_report.py` | all three questions on one page, the way every other step reports | ✅ built |
| — | `triallog.py` | the CSV schema guard, extracted so there is one copy of it | ✅ built |
| 6 | `portfolio.py` | needs two candidates to mean anything, and there are none | ⬜ deferred |

**Built and verified 2026-09-14.** 185 checks in `verify_signal.py`, bringing the project
to **418 across four suites**. The suite was then mutation-tested: fifteen deliberate
defects were introduced one at a time — an inverted haircut, a dropped edge requirement, a
kill switch reporting the last breach instead of the first — and all fifteen were caught.
Two of them were only caught after a fixture was fixed, because the original fixtures could
not tell the right answer from the wrong one. A suite that has never been shown to fail is
not evidence.

**Step 3 does not need a candidate to be built or verified.** Every component above can be
checked against a simulated Ornstein-Uhlenbeck process with a known θ, μ and σ, where the
right answer is known in advance and any disagreement is a defect rather than a market
regime. This matters: waiting for a live candidate before building the decision layer would
mean discovering these defects with money at risk instead of with a random number
generator. Step 2 was verified this way and it is why its defects were found early.

---

## What the investigation found

### 1. The expected move is wrong by one to two orders of magnitude

Every edge number in this project comes from the same formula:

```
expected move = (entry_z - exit_z) * sigma_eq
```

`pair_report.py` reports it as `expected_move_bps`, `feasibility.py` divides it by cost to
produce its ALIVE / MARGINAL / DEAD verdict, and both gates in Step 0 and Step 1b depend
on it. **It has never been compared with what a trade actually earned.**

Comparing it against the realised gross per trade from the backtest, on every pair that has
ever been a candidate:

| Pair | σ_eq as fitted | σ_eq as traded | Predicted move | Realised per trade | Over by |
|---|---|---|---|---|---|
| `XLP~XLB` | 1,544 | 269 | 404 | +40.3 | 10× |
| `SPY~DIA` | 353 | 182 | 273 | +4.0 | 68× |
| `ALL~TRV` | 847 | 542 | 813 | −71.2 | wrong sign |
| `EURUSD~GBPUSD` | 228 | 109 | 164 | +8.1 | 20× |
| `AUDUSD~NZDUSD` | 182 | 125 | 188 | −29.0 | wrong sign |
| `USDNOK~USDZAR` | 328 | 239 | 359 | −2.2 | wrong sign |

All figures in basis points. "As fitted" is the static in-sample OU fit the reports use;
"as traded" is the median of the same fit taken on the trailing 250-bar window the backtest
actually refits on. Predicted move is `1.5 × σ_eq as traded`, which is the generous version.

Two separate errors are stacked here:

**The static fit overstates the spread's scale by 1.4× to 5.7×,** and its half-life by 2.4×
to 15× — `XLP~XLB` is fitted at 260.6 bars and traded at 17.1. A single OU process fitted
to years of a drifting spread measures the drift, not the oscillation.

**Even after correcting for that, the prediction is 10× to 68× too large where it has the
sign right at all.** The formula gives the payoff of a trade that opens at `entry_z` and
runs to `exit_z`. Some trades do not: they hit the stop, they hit the maximum holding
period, or the relationship breaks while the position is open. The pipeline has no model of
how often that happens and what it costs, and the backtest reports a win rate without
reporting the average win or the average loss — so the claim has never been checkable.

### 2. Feasibility is not the binding constraint

Inverting the cost arithmetic gives the entry threshold at which a trade would break even —
the z below which it cannot pay for its own financing:

| Pair | Half-life | Transaction | Carry over the hold | Break-even z | Highest z reached | Bars at or beyond |
|---|---|---|---|---|---|---|
| `XLP~XLB` | 260.6 | 6 | 464 | 0.80 | 2.80 | 50.1% |
| `SPY~DIA` | 48.8 | 4 | 87 | 0.76 | 4.24 | 47.6% |
| `ALL~TRV` | 53.0 | 6 | 102 | 0.63 | 2.52 | 67.7% |
| `EURUSD~GBPUSD` | 46.7 | 2 | 26 | 0.62 | 3.16 | 49.9% |
| `AUDUSD~NZDUSD` | 49.7 | 5 | 27 | 0.68 | 6.86 | 55.6% |
| `USDNOK~USDZAR` | 4.9 | 11 | 3 | 0.54 | 7.70 | 56.3% |

Every pair breaks even below z = 0.8 and spends half its life beyond that. **On this
arithmetic all six are comfortably feasible, and all six lose money.** The gap is not
between the move and the cost; it is between the move the model predicts and the move the
trade collects. That is what `outcomes.py` exists to measure, and it is why it comes first.

### 3. Holding period is the one lever that has ever worked

Financing has killed every candidate in this project. The one exception is a change of bar
size: `XLP~XLB` on hourly bars paid **−75 bps of carry against −1,058 on daily**, because
the average hold fell from 16 days to 2.5. The pair is still dead on every other test, but
the mechanism is the only thing that has ever moved the financing term, and the exit rule
is what controls it. That makes maximum holding period a first-class parameter in
`thresholds.py` rather than a detail of the backtest.

---

## 1. `outcomes.py` — what actually happens to a trade

**The gap this closes.** The pipeline predicts a payoff and never checks it. This script
takes every entry a strategy would have made and classifies how it ended.

```bash
python outcomes.py -s XLP,XLB -a index --broker etf
python outcomes.py -s XLP,XLB -a index --broker etf --entry-z 1.5,2.0,2.5 --json
```

Reports, per configuration:

- **how each trade ended** — reached the exit threshold, hit the stop, hit the maximum
  holding period, or was still open when the data ran out, as counts and shares
- **average win and average loss in basis points, separately**, and the ratio between them
- **completion rate** — the share of entries that reached the exit, which is the number the
  expected-move formula silently assumes is 100%
- **predicted against realised** — `(entry_z − exit_z) × σ` beside the mean realised gross,
  with the ratio printed, so the 10×-to-68× gap is visible rather than inferred
- **time to exit**, as a distribution, against the fitted half-life

**Verified against** a simulated OU process with known parameters, where the completion
rate and expected payoff can be derived rather than measured. On a true OU process the
predicted and realised figures must agree within sampling error; if they do not, the script
is wrong, not the market.

**Done when:** the backtest's gross figure can be reconstructed from the outcome breakdown,
and the reconstruction is a verification check rather than a claim.

## 2. `thresholds.py` — entry, exit and maximum hold

**Depends on `outcomes.py`.** Choosing thresholds before the payoff is measured is choosing
them against a number that is wrong.

This is deliberately **not an optimiser**. Sweeping entry thresholds over 28 years of
`XLP~XLB` gave a net ranging from −3,678 to +3,747 bps with three positive cells out of
twelve; the surface is noise and fitting it produces a number that will not repeat. What
this script produces instead is a **bound** and a **default**:

- **the break-even threshold** — the z below which a trade cannot pay for its own financing,
  computed from measured cost and measured holding time, as in the table above. A hard gate,
  not a tuned value.
- **the maximum holding period the financing allows** — invert the carry: given the nightly
  debit and the expected move, how many nights can be paid for? A spread whose half-life
  exceeds that number cannot be traded at that bar size, whatever its statistics say. This
  is the hourly-versus-daily question stated as arithmetic instead of discovered by trial.
- **an exit rule stated once**, defaulting to the half-life measured on the trailing window
  rather than on the whole sample, because the two differ by up to 15×.

Every value it emits is logged as a trial, because Step 4 needs an honest count and this is
where trial counts usually get lost.

**Done when:** given a pair and a cost profile it prints a feasible region or states that
there is none, and the backtest can be run from its output without a parameter being chosen
by hand.

## 3. `risk.py` — caps, correlation between spreads, kill switch

**The gap this closes.** Two spreads that share a leg are one bet. Forex made this concrete:
twelve pairs resolve to eight independent directions, so a book of `EURUSD~GBPUSD` and
`AUDUSD~NZDUSD` is less diversified than it looks, and a screen that counts them as
independent tests overstates its own significance. Nothing in the pipeline measures this.

- **per-relationship cap**, gross and net, with net exposure from `hedge.py`'s
  `net_exposure()` so one definition serves both the gate and the risk layer
- **correlation between spread returns**, and the rank of the spread covariance matrix — the
  number that says how many bets a book of N relationships really contains
- **drawdown kill switch**, stated in basis points against a defined starting equity, with
  the rule for re-entry written down rather than left to judgement
- **shared-leg detection**, which is the cheap version of the above and catches the obvious
  cases before any statistics are needed

Independent of scripts 1 and 2 — it can be built in parallel.

**Done when:** given a set of relationships it reports how many independent bets they
contain, and refuses a book that exceeds any cap.

## 4. `sizing.py` — how much

Growth-optimal leverage from the time-average growth rate `ḡ = μ − σ²/2`, scaled down
fractionally for parameter uncertainty (`research/paper/portfolio_sizing/0902.2965`).
Sharpe is leverage-invariant and cannot answer the sizing question.

The fractional scaling is not decoration. Every parameter feeding `μ` and `σ` in this
project has been shown to move by a factor of several across windows; full-Kelly sizing on
an estimate that unstable is a way to lose the account while being right on average.

**Depends on `outcomes.py`** for `μ` and `σ`, which must come from realised trade outcomes
rather than from the OU closed form, for the reason the investigation gives.

**Done when:** the position size for a given relationship and equity is a function of logged
inputs with no free constant.

## 5. `verify_signal.py` — the suite

Same standard as the three existing suites: every claim in scripts 1 to 4 becomes a check,
each check fails loudly, and the suite runs in seconds. Targets around 60 checks, bringing
the project total past 280.

The checks that matter most:

- **the OU round trip** — simulate a process with known θ, μ, σ; `outcomes.py` must recover
  the completion rate and expected payoff that theory predicts
- **the financing inversion** — construct a cost profile where the answer is known by hand
  and confirm `thresholds.py` reproduces it
- **rank detection** — build three spreads from two independent factors and confirm
  `risk.py` reports two bets, not three
- **sizing monotonicity** — doubling the estimated variance must at least halve the size,
  and no input may produce a size that is negative, infinite, or NaN

**Verified in isolation**, with `backtest`, `costs` and `strategy` refused at the import
hook, so the dependency runs one way only.

## 6. `portfolio.py` — deferred, with the reason

Combining relationships into a book needs at least two relationships. There are none. Built
now it would be tested on a book of one, which tests nothing. It comes back when `risk.py`
has more than one thing to hold.

---

## What Step 3 will not do

| Tempting | Why not |
|---|---|
| Optimise entry and exit for net profit | The surface is noise: −3,678 to +3,747 bps across twelve cells on 28 years. Fitting it produces a number that will not repeat, and Step 4 exists to catch exactly this |
| Add a machine-learned signal | The linear version has not been shown to work, and an unexplainable loss is worse than an explainable one |
| Trade the candidates that exist now | `XLP~XLB` is rejected. `ALL~TRV` has never been tested on an unseen window and is a screen output until it is |
| Wait for a candidate before building | The decision layer can be verified against simulated processes with known answers, and finding its defects there costs nothing |

## What the build found

Three things came out of writing these that were not visible before.

### Completion falls as the threshold rises, and the model says the opposite

`outcomes.py` on `XLP~XLB`, twenty-eight years:

| entry z | trades | reached the exit | predicted move | realised per trade |
|---|---|---|---|---|
| 1.5 | 134 | 31% | 269 | +44.1 |
| 2.0 | 75 | 27% | 404 | +40.3 |
| 2.5 | 30 | 17% | 539 | −80.3 |
| 3.0 | 11 | 18% | 673 | −96.8 |

The formula says a wider entry earns more, because the move from `entry_z` to `exit_z` is
longer. The trades say the opposite. What grows with z is not the size of the reversion but
the chance there is no reversion left to catch: at z = 3.0, nine of eleven trades ended at
the stop. **A large deviation is evidence the relationship has broken, and the pipeline has
been reading it as evidence of opportunity.**

### The modelled floor loses money; the measured one does not

`thresholds.py` originally inverted the cost arithmetic and reported the z below which a
trade cannot pay. On `XLP~XLB` that floor is z = 0.61. Traded, it produces:

```
entry 0.61   339 trades   gross +4,124   carry -3,609   net  -501
entry 1.50   116 trades   gross +5,803   carry -2,041   net +3,414
```

The floor was correct about what it computed and wrong about what it implied. It charges
financing for the fitted half-life and credits a move that only arrives if the trade
completes — and 27% of them do. So the script now reads the floor off trades that were
actually placed: it replays the strategy at each threshold on a grid and takes **the lowest
threshold whose own trades earned `--min-edge` times their own cost**, with the modelled
floor printed beside it for comparison.

Lowest, not best. Picking the most profitable cell of a swept grid is the behaviour Step 4
exists to catch. A boundary moves less than a maximum.

**This floor is still in-sample to the grid it was read off.** It needs the same
unseen-window treatment that killed `XLP~XLB`, and until it has had it, +3,414 is a number
about the past.

### Sizing rejects the candidate on its own

On net returns, `XLP~XLB` has a mean of +23.2 bps per trade with a per-trade deviation of
309.5 across 75 trades — a standard error of 35.7. One standard error below the estimate is
−12.6. **Seventy-five trades do not establish that the mean is positive**, so the
growth-optimal size is zero, arrived at without reference to any of the earlier evidence.

---

## Order of work

1. `outcomes.py`, because every number downstream depends on a quantity it shows to be wrong
2. `risk.py` in parallel, because it depends on nothing above it
3. `thresholds.py`, once outcomes are measurable
4. `sizing.py`
5. `verify_signal.py` alongside each of the above, not after all of them

In parallel with all of it, and not part of Step 3: give `ALL~TRV` the twenty-year
treatment that killed `XLP~XLB`, and re-screen with a requirement for an economic link
rather than a p-value alone.
