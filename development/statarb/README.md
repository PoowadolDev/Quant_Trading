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
    ├── pairs/           pair_report.py output
    ├── backtests/       backtest.py output
    └── relationships/   relationship_report.py output
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
| Did the trades do what was predicted? | `code/outcomes.py` |
| Where can it be entered at all? | `code/thresholds.py` |
| How many bets does this book hold? | `code/risk.py` |
| How much should be held? | `code/sizing.py` |
| How many tests were really run? | `code/multiple_testing.py` |
| Is this Sharpe worth the search behind it? | `code/deflated_sharpe.py` |
| Was the winning parameter chosen, or lucky? | `code/overfit.py` |
| Does the score survive purging? | `code/purged_cv.py` |
| All three, on one page | `code/signal_report.py` |

## Running

Scripts resolve their own paths through `code/paths.py`, so they work from any directory.

```bash
cd development/statarb/code

python pair_report.py -s USDNOK,USDZAR                    # is there a relationship?
python costs.py show --broker demo --holding-bars 7       # what does trading it cost?
python feasibility.py -s USDNOK,USDZAR --broker demo      # does the edge survive?
python backtest.py -s USDNOK,USDZAR --broker demo         # what would it have earned?

python relationship_report.py -s SPY,DIA -a index          # is it real, and still alive?
python screen.py -u equities --within-sector --broker equity  # screen a universe

python outcomes.py -s XLP,XLB -a index --broker etf       # what happened to the trades?
python thresholds.py -s XLP,XLB -a index --broker etf     # where can it be entered at all?
python risk.py --book XLP~XLB:index,ALL~TRV:equity        # how many bets is this really?
python sizing.py -s XLP,XLB -a index --broker etf --net   # how much should be held?
python signal_report.py -s XLP,XLB -a index --broker etf  # all three, on one page

python verify_pair_report.py                              # 72 checks
python verify_backtest.py                                 # 97 checks
python verify_relationship.py                             # 89 checks
python verify_signal.py                                   # 188 checks
```

Every script takes `--help`, `--dry-run` and `--json`. Parameters are typed by hand
deliberately: one run is one trial, each is logged, and the validation in step 4 needs an
honest count of them.

## State

| Step | What | State |
|---|---|---|
| 0 | Structure study | ✅ done |
| 1 | Cost model and backtest engine | ✅ built, 97 checks green |
| 2 | Relationship engine and health monitor | ✅ built, 89 checks green |
| 3 | Signal, risk, sizing | ✅ built, 188 checks green |
| 4 | Validation | ✅ built, 100 checks green |
| 5–6 | Paper, live | ⬜ |
| 7 | Other asset classes | ✅ done early — crypto, commodities and indices searched |

**The machinery is finished and verified. There is no candidate.** Around 850 pair studies
across forex, crypto, commodities, equity indices and individual equities at daily,
four-hour, hourly and one-minute bars; none survives every gate. `XLP~XLB` and `ALL~TRV` came closest and
were both rejected on 2026-09-14, when the decades of history neither had been fitted on
were added. Each was cointegrated only on the window that selected it, each had a hedge
ratio wandering by a factor of several across eras, and `ALL~TRV` loses 4,870 bps gross
over thirty years — before any cost is charged.

Step 3 — signal, risk and sizing — is built and verified: `outcomes.py`, `thresholds.py`,
`risk.py`, `sizing.py` and `verify_signal.py`, described in [plan/STEP3.md](plan/STEP3.md).
It was built against simulated processes whose answers are known in advance rather than
waiting for a candidate. The measurement that set its order: the expected move the pipeline
has used since Step 0 over-predicts realised gross per trade by 10× to 68×, and has the
sign wrong on half the pairs tested. Writing the layer turned up why — raising the entry
threshold raises the predicted payoff and lowers the realised one, because a large
deviation is evidence the relationship has broken rather than evidence of opportunity.

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
