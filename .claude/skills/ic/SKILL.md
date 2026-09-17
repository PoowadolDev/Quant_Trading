---
name: ic
description: >
  Measure how much skill a cross-sectional signal carries and how many
  independent bets it spreads over, so the fundamental law of active management
  can be checked rather than cited. Covers the information coefficient, the
  ICIR, the decay profile across forward horizons, breadth as the participation
  ratio of the residual correlation matrix, and the implied information ratio
  that follows from the two. Use whenever the user asks how much edge a signal
  has, what the IC is, whether a signal predicts, how fast it decays, how many
  independent bets a book really contains, how many positions are needed to
  reach a given Sharpe, or about the fundamental law of active management —
  including phrases like "what is the IC", "information coefficient", "ICIR",
  "signal decay", "how many bets", "breadth", "IR equals IC times root
  breadth", "is the signal any good", or before sizing anything on a
  cross-sectional signal. Never quote an information coefficient from the
  literature as though it were a property of this system while this skill
  applies; `ic.py` measures it, and the measured value is what Step 4 will be
  asked about.
---

# IC — skill per bet, bets per year, and what the two imply together

| File | Role |
|---|---|
| `ic.py` | information coefficient, ICIR, decay profile, breadth, implied IR |
| `verify_residual.py` | groups 9 and 10 cover this script; 79 checks in total |

## Working directory

```bash
cd development/statarb/code

python ic.py
python ic.py --horizons 1,5,20 --primary-horizon 5
python ic.py --json
```

## Why it exists

The whole redesign in `RESIDUAL.md` rests on one piece of arithmetic:

```
IR  ~  IC x sqrt(breadth)
```

and until this script existed the project supplied neither term. `IC = 0.02-0.05` was
quoted throughout as though it were a property of this system. It is a range from the
literature. Breadth was argued from the number of names rather than measured.

Both are now measured. On the 160-name equity panel: **IC 0.0214 +/- 0.0077 at a five-bar
horizon, t = 2.79, breadth 132.2 of 160 names**, giving an implied IR of about 1.7 a year
before costs and on a survivor-filtered panel.

## Workflow

### 1. Form the signal before the forward window, never across it

At each formation date the loadings come from the bars *before* it and are applied
unchanged to the bars *after*. The signal is the standing residual scaled by its own
variation, with a negative sign because a residual that has run up is the expensive one:

```
signal_i,t    = -X_i,t / sd(X_i)
forward_i,t,h = sum of residual returns over (t, t+h]
IC_t          = rank correlation of signal against forward, across names
```

### 2. Read the decay profile, not one number

On this panel IC **rises** with horizon rather than decaying — 0.0076 at one bar to 0.0328
at twenty. That is not a defect. The residual's measured half-life is about eight bars, so
a one-bar forward return is mostly noise and a twenty-bar one captures the reversion.

### 3. Declare the primary horizon from the half-life, not from the table

`--primary-horizon` decides the exit code. Set it from the half-life `residual.py`
measured, which is an independent measurement. Reading the horizon table and taking the
best row is selection, and Step 4 charges for it.

## Options

### Selection

| Flag | Default | Meaning |
|---|---|---|
| `-a, --asset-class` | `equity` | |
| `-t, --timeframe` | `1d` | |
| `--min-bars` | `5000` | applied per series before the join |

### Structure — choose once, not per run

| Flag | Default | Meaning |
|---|---|---|
| `--pca-window` | `252` | bars the factor model is estimated on |
| `--signal-window` | `60` | trailing bars the residual is accumulated over |
| `--step` | `21` | bars between formation dates; raised to the horizon when longer |
| `--bars-per-year` | `252` | annualises the implied ratio only |

### Searched — every value is a trial

| Flag | Default | Meaning |
|---|---|---|
| `--factors` | `15` | principal components removed |
| `--horizons` | `1,2,3,5,10,20` | reported as a decay profile |
| `--primary-horizon` | `5` | the one horizon that decides the exit code |
| `--null-draws` | `2` | permutations averaged into the null |

### Output

`--json` · `--log` · `--no-log` · `-q` · `-v` · `--store`

## Reading the output

```
  horizon  windows       IC   std err       t    ICIR   IC>0  implied IR
        1      236   0.0076    0.0074    1.03   0.067    53%        1.39
        5      235   0.0214    0.0077    2.79   0.182    58%        1.74
       20      235   0.0328    0.0075    4.38   0.286    63%        1.34

  horizon   IC real   IC null      lift   lift t
        5    0.0214   -0.0033   +0.0247     2.80

  breadth: 160 residuals contain 132.2 independent bets (83% of the cross-section)
  measured on 4,935 tiled residual bars, 30.8 per name
  most correlated residual pair CCL~RCL at +0.504
```

**IC and ICIR are different questions.** IC is how much skill each bet carries; ICIR is how
consistent that skill is across formation dates. ICIR divides by the standard deviation,
the t-statistic divides by the standard error, and on n windows they differ by exactly the
square root of n. Reporting one as the other overstates consistency by that factor.

**Breadth is measured, not counted.** 160 names is not 160 bets. The participation ratio
of the residual correlation matrix says 132.2, and the 17% shortfall is real: `CCL~RCL` are
two cruise lines whose residuals still correlate at +0.50 after fifteen factors. That is
the factor model failing to separate them, and it is visible only because breadth is
measured.

**The `rows per name` line is a guard, not decoration.** A correlation matrix estimated on
too few rows has eigenvalues spread by sampling noise alone, which deflates the
participation ratio. An early version measured breadth on whichever horizon came first and
reported **59.7 bets on 236 rows** against **132.2 on 4,935** — a number that moved by a
factor of two according to a setting with nothing to do with breadth. Breadth now gets its
own tiled pass and refuses to report below two rows per name.

**The implied IR is an upper bound twice over.** It is before costs, and the panel is
survivor-filtered. The shuffled null does not correct for survivorship — the permutation
reorders dates and leaves the cross-section exactly as it was.

## Verifying

```bash
python verify_residual.py          # 79 checks; groups 9 and 10 are this script
```

Group 9 plants a known signal: a white-noise residual level is maximally reverting and must
give a large positive IC; a random-walk level must give none; and the sign convention is
checked by confirming that inverting the signal inverts the IC. Group 10 checks breadth
returns N for independent residuals, 1 for ten copies of one series, falls as a common
factor is blended in, and refuses a sample with too few rows per name.

## Rules

- Never quote an IC from the literature as a property of this system. Measure it.
- Never report IC without its standard error; on a few hundred windows they are comparable.
- Never confuse ICIR with the t-statistic — they differ by the square root of the window count.
- Never count names as bets. Measure breadth and expect a shortfall.
- Never choose the primary horizon by reading the decay table.
- Never present an implied IR as achievable. It is before costs, on survivors.

Related: **factor-residual** builds the residuals this measures; **portfolio** turns the
signal into sizes; **validation** charges the trial count. Plan:
`development/statarb/plan/RESIDUAL.md`.

A positive IC means the signal predicts. It does not mean the strategy pays — financing,
not signal, has killed every candidate this project has produced.
