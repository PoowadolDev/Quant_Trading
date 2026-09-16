# Quant Trading

Research and engineering for **non-directional trading systems** — strategies that trade the
*relationship* between instruments rather than the direction of any one of them.

This is a working research repository, not a product. The organising principle is that a
strategy is guilty until proven innocent: every claim here is gated on evidence, every run is
logged as a trial, and negative results are kept rather than deleted. The headline result so
far is a negative one, and it is stated plainly below.

---

## What is in here

| Area | Path | What it is |
|---|---|---|
| **Statistical arbitrage** | [`development/statarb/`](development/statarb/) | The main project. A verified pair-trading pipeline: hedge ratios, cointegration, cost and financing model, backtest engine, signal/risk/sizing layer, and a validation layer that judges the search itself. |
| **Market data** | [`development/marketdata/`](development/marketdata/) | Installable Python package + CLI for fetching, storing, inspecting and validating OHLCV history (forex, crypto, commodities, indices, equities) in a local Parquet store. |
| **Paper library** | [`research/paper/`](research/paper/) | ~30 arXiv papers across seven topics, each read and triaged before being kept. Rejections are documented with the reason. |
| **Digests & math notes** | [`research/wiki/`](research/wiki/), [`research/math/`](research/math/) | Structured summaries of each paper, plus plain-language explanations of the formulas that matter. |
| **Wyckoff POC** | [`development/wyckoff/`](development/wyckoff/) | Reproduction of a published LSTM/Wyckoff pattern paper against real BTCUSDT bars — the paper tested only on its own synthetic generator. |
| **Volume anomaly** | [`development/volume/`](development/volume/) | Eight robust volume-anomaly detection concepts (median/MAD baselines and friends) with worked examples. |
| **Grid trading** | [`development/grid/`](development/grid/) | Earlier work on geometric grid systems, from the dynamic-grid papers in the library. |

Roughly **15,500 lines of Python** plus the research write-ups.

---

## The main project: `development/statarb`

A market-neutral pair-trading bot, built in gated steps. Forex first, paper only.

```
statarb/
├── plan/        what to build and why       PLAN.md, STEP1–4.md
├── code/        the scripts                 run these
├── costs/       broker cost profiles        one JSON per broker
├── logs/        one row per run             trials.csv, backtests.csv
├── worklog/     what was done, for a human
└── studies/     what the scripts produced   HTML reports, one per run
```

### Build state

| Step | What | State |
|---|---|---|
| 0 | Structure study — is there anything to trade? | ✅ done |
| 1 | Cost model + backtest engine | ✅ 97 checks green |
| 2 | Relationship engine + health monitor | ✅ 89 checks green |
| 3 | Signal, risk, sizing | ✅ 188 checks green |
| 4 | Validation — deflated Sharpe, multiple testing, purged CV | ✅ 100 checks green |
| 5–6 | Paper execution, then live at small size | ⬜ not started |
| 7 | Other asset classes | ✅ done early |

**547 checks pass across five verification suites.** The newest suite has been
mutation-tested: twenty deliberate defects introduced one at a time, twenty caught.

### The honest result

> **The machinery is finished and verified. There is no tradable candidate.**

Around **850 pair studies** and **390 backtest configurations** across forex, crypto,
commodities, equity indices and individual equities, at daily, four-hour, hourly and
one-minute bars. None survives every gate.

| Universe | Pairs tested | Survived every gate |
|---|---|---|
| Forex (daily, 4h, 1m) | 246 | 0 |
| Crypto (daily, hourly) | 45 | 0 |
| Commodity vs forex | 12 | 0 |
| Equity index vs forex | 357 | 0 |
| Index vs index | 84 | 0 — the four that "passed" were an index against its own tracker |
| Sector / industry funds | 105 | 0 |
| Equities, within sector | 205 | 1 — and it failed re-testing |

The two closest candidates, `XLP~XLB` and `ALL~TRV`, were both rejected once the decades of
history they had *not* been fitted on were downloaded. Each was cointegrated only on the
window that selected it; each had a hedge ratio wandering by a factor of several across eras;
`ALL~TRV` loses 4,870 bps gross over thirty years, before any cost is charged.

`SPY~DIA` clears cointegration and hedge quality and still loses 581 bps — a 49-bar half-life
pays 71 nights of retail margin financing to capture a 529 bps move. Financing, not signal
quality, is what kills most of these.

A further measurement from the signal layer: the expected-move estimate used since Step 0
**over-predicts realised gross per trade by 10× to 68×**, with the wrong sign on half the
pairs tested. Raising the entry threshold raises the predicted payoff and *lowers* the
realised one — a large deviation turns out to be evidence that the relationship has broken,
not evidence of opportunity.

---

## Quick start

Requires Python 3.10+.

```bash
# 1. Data layer
cd development/marketdata
pip install -e .

marketdata download -u fx-all --start 2019-01-01   # majors + crosses
marketdata list                                     # what is on disk
marketdata validate -a forex                        # data quality gate

# 2. Pair research
cd ../statarb/code

python pair_report.py -s USDNOK,USDZAR              # is there a relationship?
python costs.py show --broker demo --holding-bars 7 # what does trading it cost?
python feasibility.py -s USDNOK,USDZAR --broker demo # does the edge survive costs?
python backtest.py -s USDNOK,USDZAR --broker demo   # what would it have earned?

python relationship_report.py -s SPY,DIA -a index   # is it real, and still alive?
python screen.py -u equities --within-sector --broker equity
python signal_report.py -s XLP,XLB -a index --broker etf

# 3. Verification
python verify_pair_report.py    # 72 checks
python verify_backtest.py       # 97 checks
python verify_relationship.py   # 89 checks
python verify_signal.py         # 188 checks
python verify_validation.py     # 100 checks
```

Every script takes `--help`, `--dry-run` and `--json`, resolves its own paths, and writes a
self-contained HTML report plus one row in `logs/`.

---

## How the work is organised

A few conventions that explain most of what you will see:

- **Parameters are typed by hand, deliberately.** One run is one trial, each trial is logged,
  and the validation layer needs an honest count of them. Automated sweeps would make the
  deflated-Sharpe and multiple-testing corrections meaningless.
- **Three kinds of parameter.** *Structure* is chosen once and makes runs comparable.
  *Searched* values each cost a trial. *Given by reality* comes off a broker sheet and is not
  a knob to turn until something passes.
- **Exit codes carry the verdict.** `0` accepted or profitable, `3` rejected or a net loss,
  `2` a usage error — so sweeping a universe and keeping the zeros is a valid way to work.
- **`worklog/` is written for a human; `studies/` is written by a script.** A worklog entry
  explains a stretch of work; a study is one run with one set of parameters.
- **Canonical symbols.** `EURUSD`, not `EURUSD=X`. `GOLD`, not `GC=F`. The `marketdata`
  package handles translation per source.
- **Known data defects are documented, not hidden.** `validate` fails every Yahoo forex
  series, and the failure is real: 1–3% of daily bars have an open or close outside the bar's
  own high/low. Close-only work is unaffected; anything reading intrabar extremes is not.

---

## Research method

Papers are sourced from arXiv and triaged before being kept, with the test *"can this be
implemented and trusted on live capital"* rather than *"is this interesting"*. Rejections are
recorded in each topic's `_triage.md`, because several are more instructive than the keeps —
they catalogue the specific ways a backtest manufactures an edge that is not there:

- Mid-price fills where the spread is a large fraction of the edge.
- Notional-denominated returns that produce a 0.0% drawdown across 2008.
- Overlapping-window t-statistics overstating effective sample size tenfold.
- An abstract that contradicts its own tables (0.47 Sharpe claimed to beat a 0.78 baseline).
- Strategies validated only inside a simulator the author designed.
- Composite validation scores with no forward relationship on unseen data (ρ = 0.013, p = 0.40).

These are the checks applied to this repository's own backtests. See
[`research/paper/README.md`](research/paper/README.md) for the full library and the
suggested reading order.

---

## Repository layout

```
Quant_Trading/
├── development/
│   ├── statarb/        pair-trading pipeline — the main project
│   ├── marketdata/     data package and CLI
│   ├── wyckoff/        Wyckoff pattern POC
│   ├── volume/         volume anomaly concepts
│   └── grid/           grid trading research
├── research/
│   ├── paper/          PDF library, organised by topic, with triage notes
│   ├── wiki/           per-paper digests
│   └── math/           plain-language formula explanations (EN + TH)
└── .claude/skills/     reproducible workflows for the tooling above
```

`store/`, `logs/`, `studies/` and `worklog/` contents are partly gitignored — the data and
some generated output do not live in version control. The reports checked in under
`development/statarb/studies/` and `development/marketdata/reports/` are self-contained HTML
and can be opened directly in a browser.

## Status

Active research, September 2026. Nothing here has traded live money.
