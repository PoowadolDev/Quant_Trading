---
name: pipeline
description: >
  Run the residual statistical arbitrage research pipeline from stage 00 to
  stage 21 in one pass and write a single self-contained HTML page with one
  section per stage, each carrying its own verdict. Covers the stage map, what
  is implemented against what is only declared, the gate applied at each step,
  and the deliberate refusal to reduce the result to one number. Use whenever
  the user asks for an overview of where the research stands, to run the whole
  process end to end, for a report covering every step, which stages are missing
  or unbuilt, or what the pipeline currently concludes — including phrases like
  "run the whole pipeline", "all the steps", "where are we", "full report",
  "stage map", "what is missing", "end to end", or before presenting research
  status to anyone. Never assemble a status summary by hand from the separate
  report directories while this skill applies; `pipeline.py` reads the logs and
  re-runs the measurements, so the page cannot quietly go stale.
---

# Pipeline — stages 00 to 21 as a sequence of gates, on one page

| File | Role |
|---|---|
| `pipeline.py` | run every stage, collect a verdict each, write one HTML page |
| `residual.py`, `ic.py`, `portfolio.py` | the stages it re-runs rather than reads |
| `logs/screens.csv`, `logs/backtests.csv` | the trial counts it charges |

## Working directory

```bash
cd development/statarb/code

python pipeline.py                  # full precision, several minutes
python pipeline.py --fast           # fewer null draws and horizons, a quick look
python pipeline.py --open --json
```

Exit codes: `0` every implemented stage passed, `3` at least one failed — which is the
usual and informative outcome — `2` usage error.

## Why it exists

Every other script here answers one question and prints it to a terminal. That is the right
shape for doing the work and the wrong shape for seeing where the work stands: the answer
to "is there anything here" was spread across five report directories, three logs and two
plan documents, and nobody could hold all of it at once.

## The two refusals

> **No overall score.** `STEP4.md` refuses to aggregate the validation gates into one
> number, on the evidence of a study where the composite had no forward relationship, and
> `verify_validation.py` asserts that no function returns one.

The same reasoning applies to the pipeline as a whole. Four stages failing for four
different reasons is four pieces of information; one number is none. Every stage reports
its own verdict and the page reports no total.

> **A stage with nothing behind it says so.**

Point-in-time data is not implemented, and the page prints that in the same place and the
same size as a passing gate, along with the direction of the bias it leaves behind. A
report that silently omitted its unimplemented stages would be a way of forgetting them.

## The five states

| State | Means |
|---|---|
| `PASS` | the gate was applied and the evidence cleared it |
| `FAIL` | the gate was applied and the evidence did not clear it |
| `PARTIAL` | some of the stage is built; what is missing is named |
| `NOT IMPLEMENTED` | nothing is built, and the bias that leaves is stated |
| `NOT RUN` | built but not executed, usually because an earlier stage blocks it |

Only `PASS` and `FAIL` are judgements about the strategy. The other three are statements
about the pipeline, and mixing them would let an unbuilt stage read as a passing one.

## What the stages currently say

```
  00  PARTIAL          Research specification
  01  PASS             Data acquisition
  02  PASS             Data cleaning and quality
  03  PASS             Universe definition
  04  NOT IMPLEMENTED  Point-in-time data
  05  PASS             Exploratory analysis
  06  PASS             Candidate generation
  07  PASS             Relationship test — factor model
  08  PASS             Residual construction
  09  PASS             Mean-reversion analysis
  10  PASS             Signal construction
  11  PASS             Information coefficient, ICIR and decay
  12  FAIL             Portfolio construction
  13  PARTIAL          Risk model
  14  PASS             Transaction cost model
  15  PASS             Backtest engine
  16  NOT RUN          In-sample backtest
  17  NOT RUN          Out-of-sample backtest
  18  PARTIAL          Walk-forward validation
  19  PARTIAL          Robustness and stress tests
  20  PASS             Multiple testing and bias check
  21  NOT RUN          Final model selection
```

**Stage 16 is the honest stopping point.** Stage 11 says the signal predicts and stage 12
says it can be sized, but nothing above has been charged a spread. `RESIDUAL.md` section
1.3 records that financing, not signal, killed every previous candidate, so stage 16 is the
one most likely to end the work.

**Stage 04 is the standing bias.** The universe is every name with enough history as of
today, which is a filter on having survived. A null result under it is conservative; a
passing one is an upper bound. The shuffled null used throughout does not correct for it.

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
| `--ou-window` | `60` | bars after it the residual is accumulated over |
| `--step` | `21` | bars between formation dates |
| `--factors` | `15` | principal components removed |
| `--primary-horizon` | `5` | declared from the stage 09 half-life, not read off the IC table |

### Output

| Flag | Default | Meaning |
|---|---|---|
| `--fast` | off | fewer null draws and horizons; a quick look, not a result |
| `-o, --out` | `studies/pipeline/pipeline-{class}-{date}.html` | |
| `--open` | off | open the written page in a browser |
| `--json` · `-q` · `-v` · `--store` | | |

## Reading the page

Self-contained HTML: inline SVG, no scripts, no external requests, and a dark-mode block
that re-declares the colour variables under `prefers-color-scheme`. It opens from a file
path with no server.

The page opens with five tiles — stages passed, failed, partial or absent, names, bars —
then a contents table of every stage and its badge, then one section per stage with the
rows that justify its verdict. Sections carry a caption where the verdict needs
qualifying.

**Read the contents table first and the `NOT RUN` rows second.** The passing stages are the
ones that have been asked a question; the rest are the ones that have not.

## Rules

- Never compute or report an overall score across stages.
- Never omit an unimplemented stage from the page; state it and name its bias.
- Never present a `--fast` run as a result. It is a look.
- Never read a `PASS` at stage 11 as an edge; nothing before stage 16 has been charged a cost.
- Never hand-assemble a status summary from the separate report directories. Run this.
- Never let the page stand as current without re-running it; it re-reads the logs each time.

Related: **factor-residual**, **ic** and **portfolio** are the stages this orchestrates;
**validation** owns the Step 4 gates it reports; **backtest** is what stage 16 needs. Plans:
`development/statarb/plan/PLAN.md` and `RESIDUAL.md`.

A page where every implemented stage passes is not permission to trade. It means the
evidence is not yet against the strategy, and stages 16 to 21 have not been reached.
