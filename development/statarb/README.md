# statarb — non-directional pair trading

Research and machinery for a market-neutral bot that trades the *relationship* between two
instruments rather than the direction of either. Forex first, paper only.

Four kinds of thing live here, kept apart on purpose: the plan, the code, write-ups of what
was done, and the output the scripts produce.

```
statarb/
├── plan/        what to build and why          PLAN.md, STEP1.md, STEP2.md
├── code/        the scripts                    run these
├── costs/       broker cost profiles           one JSON per broker
├── logs/        one row per run                trials.csv, backtests.csv
├── worklog/     what was done, for a human     summaries with diagrams
└── studies/     what the scripts produced
    ├── pairs/       pair_report.py output
    └── backtests/   backtest.py output
```

The distinction that matters: **`worklog/` is written for you to read, `studies/` is written
by a script.** A worklog entry explains a stretch of work; a study is one run of one script
with one set of parameters, and the row in `logs/` that points at it.

## Start here

| Question | File |
|---|---|
| What is being built, and in what order? | [plan/PLAN.md](plan/PLAN.md) |
| What happened in step 1? | [worklog/step1-summary.html](worklog/step1-summary.html) |
| Is this pair worth trading? | `code/pair_report.py` |
| Does it survive costs and financing? | `code/feasibility.py` |
| What would it have earned? | `code/backtest.py` |

## Running

Scripts resolve their own paths through `code/paths.py`, so they work from any directory.

```bash
cd development/statarb/code

python pair_report.py -s USDNOK,USDZAR                    # is there a relationship?
python costs.py show --broker demo --holding-bars 7       # what does trading it cost?
python feasibility.py -s USDNOK,USDZAR --broker demo      # does the edge survive?
python backtest.py -s USDNOK,USDZAR --broker demo         # what would it have earned?

python verify_pair_report.py                              # 72 checks
python verify_backtest.py                                 # 77 checks
```

Every script takes `--help`, `--dry-run` and `--json`. Parameters are typed by hand
deliberately: one run is one trial, each is logged, and the validation in step 4 needs an
honest count of them.

## State

| Step | What | State |
|---|---|---|
| 0 | Structure study | ✅ one candidate survived, `USDNOK~USDZAR` |
| 1 | Cost model and backtest engine | ✅ engine done, candidate fails at −267 bps |
| 2 | Relationship engine and health monitor | 🟡 next |
| 3–7 | Signal, validation, paper, live, other assets | ⬜ |

The candidate's gross result is negative before any cost is charged, so the failure is in
the signal, not the fee schedule. Step 2 is where a better hedge ratio and a real
cointegration test would either rescue it or bury it.

## Conventions

- **Canonical symbols.** `EURUSD`, not `EURUSD=X`. `GOLD`, not `GC=F`. The `marketdata`
  package translates per source.
- **Three kinds of parameter.** *Structure* is chosen once and makes runs comparable;
  *searched* values each count as a trial; *given by reality* comes off a broker sheet and
  is not a knob to turn until something passes.
- **Exit codes carry the verdict.** 0 accepted or profitable, 3 rejected or a net loss,
  2 a usage error. Sweeping many pairs and keeping the zeros is a valid way to work.
- **Costs are still a placeholder.** `costs/demo.json` is marked estimated and every report
  that uses it says so.

Data loading, storage and quality live next door in
[`../marketdata`](../marketdata/README.md).
