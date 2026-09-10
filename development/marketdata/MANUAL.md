# marketdata — User Manual

Complete reference for the market data pipeline: fetching OHLCV history for forex and
crypto, storing it as Parquet, inspecting it as HTML, and validating it before anything is
built on top.

For a two-minute overview see [README.md](README.md). This document is the full reference.

---

## Contents

1. [Installation](#1-installation)
2. [Concepts](#2-concepts)
3. [Command reference](#3-command-reference)
4. [Date formats](#4-date-formats)
5. [Exit codes](#5-exit-codes)
6. [Recipes](#6-recipes)
7. [Data quality](#7-data-quality)
8. [Library use](#8-library-use)
9. [Troubleshooting](#9-troubleshooting)
10. [Extending](#10-extending)
11. [Limits](#11-limits)

---

## 1. Installation

### Editable install (recommended)

```bash
cd development/marketdata
pip install -e .
marketdata --version
```

This puts a `marketdata` executable on PATH and links it to the source, so edits take
effect without reinstalling.

### Without installing

```bash
cd development/marketdata
python -m marketdata --help
```

Both forms are identical in behaviour. Every example below uses `marketdata`; substitute
`python -m marketdata` if you skipped the install.

### Requirements

Python 3.10 or newer, plus `pandas`, `numpy`, `pyarrow`, `requests`, `yfinance`. All are
declared in `pyproject.toml` and installed automatically by `pip install -e .`.

### Working directory

The default store and report paths are **relative** (`store`, `reports`), so commands
expect to run from `development/marketdata`. To run from anywhere, pass absolute paths or
set the environment variables:

```bash
export MARKETDATA_STORE=D:/Repository/Quant_Trading/development/marketdata/store
export MARKETDATA_REPORTS=D:/Repository/Quant_Trading/development/marketdata/reports
```

---

## 2. Concepts

### Instrument

An instrument is the unit of everything: what you download, what gets stored, what appears
in a report. Four fields identify it.

| Field | Example | Notes |
|---|---|---|
| `symbol` | `EURUSD`, `BTC-USDT` | canonical and source-agnostic; upper-cased automatically |
| `asset_class` | `forex`, `crypto` | decides the default source and the symbol mapping |
| `source` | `yahoo`, `binance` | defaults to `yahoo` for forex, `binance` for crypto |
| `timeframe` | `1d`, `1h`, `15m` | Binance-style tokens |

Printed as `EURUSD@yahoo:1d`.

### Canonical symbols

You always write the canonical form. The mapper translates it for each feed, so the same
name works everywhere and the store stays consistent.

| Asset class | Canonical | Yahoo | Binance |
|---|---|---|---|
| forex | `EURUSD` | `EURUSD=X` | unsupported — raises a clear error |
| crypto | `BTC-USD` | `BTC-USD` | `BTCUSD` |
| crypto | `BTC-USDT` | not quoted by Yahoo | `BTCUSDT` |

`BTC-USDT` and `BTC-USD` are **different assets**. USDT is a stablecoin, not dollars. Never
splice them into one series.

### Store layout

```
store/{asset_class}/{symbol}/{timeframe}/{source}.parquet
```

Example: `store/forex/EURUSD/1d/yahoo.parquet`

The path carries the metadata, so the catalogue is rebuilt by scanning the directory tree.
There is no index file that can drift out of sync with the data.

One file **per source** means Yahoo and a future broker feed for the same instrument sit
side by side and stay comparable — which is how you check a free feed against a real one.

### Schema

Every feed returns the same frame regardless of source:

- index: `DatetimeIndex`, UTC, named `timestamp`, sorted ascending, no duplicates
- columns: `open`, `high`, `low`, `close`, `volume`, all `float64`

### Merge semantics

Writes merge by default. The existing file is read, concatenated with the new rows,
de-duplicated on the index keeping the **newest** copy, sorted, and rewritten.

Consequences:

- Re-running a download over an overlapping range is safe and idempotent.
- A revised bar from the source replaces the stale one.
- Downloads can be built up in pieces over time.

`--replace` discards the stored series instead. Use it when the source has restated history
or you changed how a series is constructed.

### Timeframes

`1m`, `2m`, `5m`, `15m`, `30m`, `90m`, `1h`, `4h`, `1d`, `3d`, `1w`.

Yahoo has no native `4h`, `3d` or `1w` bar; those are fetched one level down and resampled
(`4h` from `1h`, `3d` and `1w` from `1d`) with the standard OHLCV aggregation —
first/max/min/last/sum. Binance serves all of them natively.

---

## 3. Command reference

```
marketdata [--version] COMMAND [options]

COMMAND:
  download    fetch history and merge it into the store
  report      render stored series into one HTML table file
  validate    run data quality checks against stored series
  list        show what the store contains
  universes   list the built-in symbol sets
```

### 3.1 Global options

Available on every subcommand.

| Option | Default | Meaning |
|---|---|---|
| `--store PATH` | `store` | parquet root. Env: `MARKETDATA_STORE` |
| `--reports PATH` | `reports` | HTML output directory. Env: `MARKETDATA_REPORTS` |
| `-v, --verbose` | off | debug logging; also re-raises tracebacks instead of swallowing them |
| `-q, --quiet` | off | warnings and errors only |
| `--json` | off | machine-readable output instead of a text table |
| `-h, --help` | — | per-command help |

`--version` is on the top-level command only.

**Position does not matter.** Global options are accepted before or after the subcommand,
and if given in both places the later, more specific one wins:

```bash
marketdata --store /data/market list       # before
marketdata list --store /data/market       # after — identical
marketdata --store /a list --store /b      # uses /b
```

Logging goes to **stderr**, results go to **stdout**. So `marketdata list --json > out.json`
gives clean JSON with progress messages still visible in the terminal.

### 3.2 Instrument selection

Shared by `download`, `report`, `validate` and `list`.

| Option | Meaning |
|---|---|
| `-s, --symbols SYM[,SYM...]` | one symbol, a comma-separated list, or the flag repeated |
| `-u, --universe NAME` | a named symbol set; combine with `--symbols` to extend it |
| `-a, --asset-class {forex,crypto}` | required when symbols are given without a universe |
| `--source {yahoo,binance}` | defaults per asset class |
| `-t, --timeframe TF` | default `1d` |

All three of these are equivalent ways to select many instruments:

```bash
marketdata download -s EURUSD,GBPUSD,USDJPY -a forex --start 1y
marketdata download -s EURUSD -s GBPUSD -s USDJPY -a forex --start 1y
marketdata download -u fx-majors --start 1y            # and seven more besides
```

A universe carries its own asset class, so `-a` becomes optional:

```bash
marketdata download -u fx-crosses --start 1y           # asset class inferred
marketdata download -u fx-majors -s EURNOK -a forex    # universe plus an extra symbol
```

**Timeframe filtering quirk.** `--timeframe` defaults to `1d`, but for the read-side
commands (`list`, `report`, `validate`) that default is *not* applied as a filter — only an
explicitly typed `-t`/`--timeframe` narrows the selection. Without this, `marketdata list`
would silently hide every intraday series. `download` always uses the value, default
included, because it has to pick a bar size.

### 3.3 `download`

Fetches history from a source and writes it to the store.

| Option | Default | Meaning |
|---|---|---|
| `--start DATE` | `2y` | first bar; see [date formats](#4-date-formats) |
| `--end DATE` | `now` | last bar |
| `--resume` | off | start from the last stored bar instead of `--start` |
| `--replace` | off | overwrite the stored series rather than merging |
| `-n, --dry-run` | off | print the plan; no network, no writes |
| `--retries N` | 3 | attempts per request |
| `--retry-delay SEC` | 1.0 | initial backoff, doubled each retry |
| `--fail-fast` | off | stop at the first failing instrument |

Behaviour notes:

- **One bad symbol does not abort the batch.** Failures are recorded in the result table
  with their reason, and the command exits 1 if any instrument failed. `--fail-fast`
  overrides this when you would rather stop immediately.
- **`--resume` is per instrument.** For each one it takes `max(--start, last stored bar)`,
  so a mixed store where some series are current and some are not gets topped up correctly
  in a single call.
- **Retries cover transient network failures only.** A rejected symbol (Binance
  `Invalid symbol.`) fails immediately — retrying would not help.

Dry-run output shows, per instrument, whether the action would be `create` or `merge`, how
many rows are already stored, the effective date window, and the target file:

```
     instrument action  stored_rows       from         to                                path
EURUSD@yahoo:1d  merge         2002 2019-01-01 2026-09-10 store\forex\EURUSD\1d\yahoo.parquet
GBPJPY@yahoo:1d create            0 2025-09-10 2026-09-10 store\forex\GBPJPY\1d\yahoo.parquet
```

### 3.4 `report`

Renders many instruments into **one self-contained HTML file**. Tables only, no charts.

| Option | Default | Meaning |
|---|---|---|
| `-o, --output FILE` | `<reports>/market-data.html` | output path |
| `--title TEXT` | `Market Data Report` | page title |
| `--max-rows N` | 200 | bars shown per instrument |
| `--panel` / `--no-panel` | on | include the aligned cross-instrument panel |
| `--panel-field FIELD` | `close` | field used for the panel |
| `--panel-rows N` | 200 | rows shown in the panel |
| `--validate` | off | run the checks and include a status section |
| `--open` | off | open the finished file in a browser |
| `-n, --dry-run` | off | list what would be rendered; write nothing |

The page contains, in order:

1. **Contents** — every included series with rows, coverage, gap share and file size.
2. **Validation** — status per series, coloured, only with `--validate`.
3. **Aligned panel** — one column per instrument on shared timestamps. This is the same
   frame a correlation or cointegration study consumes, so reading it here is a direct check
   on that input. Skipped automatically when the selection shares no timestamps, which is
   what happens if you mix timeframes.
4. **One OHLCV table per instrument**, most recent `--max-rows` bars.

The output has no external dependencies — styles and the row-filter script are inlined — so
it renders offline and can be sent to someone as a single file. It follows the reader's
light or dark system setting.

Prices are formatted by magnitude: 2 decimals above 1000, 3 above 100 (JPY pairs), 5 above
0.01 (FX majors), 8 below that (sub-cent crypto). Volume gets thousands separators.

### 3.5 `validate`

Runs data quality checks and **exits non-zero on failure**, so it works as a gate in a
script or CI job.

| Option | Default | Meaning |
|---|---|---|
| `--min-rows N` | 100 | warn below this row count |
| `--max-gap-pct PCT` | off | warn above this share of missing bars |
| `--max-stale-run N` | 20 | warn when the close is unchanged for N consecutive bars |
| `--ohlc-tolerance-bps BPS` | 0 | how far open/close may sit outside the high/low range before it counts, in basis points of price |
| `--strict` | off | treat warnings as failures |

#### Checks

**Errors** — the series is not fit to trade on:

| Code | Meaning | Usual cause |
|---|---|---|
| `empty` | no rows | download never ran, or returned nothing |
| `index-type` | index is not a `DatetimeIndex` | file written outside this tool |
| `index-tz` | index is timezone-naive | as above; everything here is UTC |
| `index-order` | index not sorted ascending | as above |
| `index-duplicates` | repeated timestamps | as above; the store de-duplicates on write |
| `columns` | a required column is missing | source changed its response shape |
| `nan` | NaN in `open/high/low/close` | source gap, often a trailing partial bar |
| `non-positive` | a price at or below zero | corrupt source data |
| `ohlc-high` | open or close **above** the bar's high | broken source data — see §7 |
| `ohlc-low` | open or close **below** the bar's low | broken source data — see §7 |
| `ohlc-inverted` | high below low | corrupt source data |
| `volume-negative` | negative volume | corrupt source data |
| `future` | bars timestamped more than a day ahead | clock or timezone bug |

**Warnings** — worth knowing, not automatically disqualifying:

| Code | Meaning | Notes |
|---|---|---|
| `short` | fewer rows than `--min-rows` | expected for a newly added symbol |
| `gaps` | missing-bar share above `--max-gap-pct` | off by default; see below |
| `stale` | close unchanged for N consecutive bars | possible frozen feed, or a genuinely dead market |

The `ohlc-high` and `ohlc-low` messages report the **worst discrepancy**, in pips for
forex-shaped quotes, so you can tell a rounding artefact from a broken bar:

```
28 bars where open or close exceeds the high (worst 30.6 pips)
```

#### Why `--max-gap-pct` is off by default

`gap_pct` is the share of expected bars that are absent, inferred from the median spacing
between timestamps. Daily forex sits near **28%** because markets close at weekends
(2/7 = 28.6%). Turning the check on with a naive threshold would fail every FX series for a
non-problem. Set it deliberately:

```bash
marketdata validate -a forex --max-gap-pct 35     # catches real holes, ignores weekends
marketdata validate -a crypto --max-gap-pct 1     # crypto trades 24/7; anything is a hole
```

#### Tolerance is relative

`--ohlc-tolerance-bps` is in basis points of the price level, not raw price units, so one
value means the same thing on EURUSD (~1.16), USDJPY (~153) and BTCUSDT (~60000). A raw
price tolerance would be 5 pips on one and 0.05 pips on another.

### 3.6 `list`

Prints the store catalogue: asset class, symbol, timeframe, source, row count, coverage
start and end, gap share, file size. Accepts the selection options as filters.

```bash
marketdata list                      # everything
marketdata list -a forex             # one asset class
marketdata list -s EURUSD,GBPUSD -a forex
marketdata list --json > catalogue.json
```

The text form ends with a total line: series count, bars, and size on disk.

### 3.7 `universes`

Lists the built-in symbol sets and their members.

| Universe | Class | Members |
|---|---|---|
| `fx-majors` | forex | EURUSD GBPUSD USDJPY USDCHF AUDUSD USDCAD NZDUSD |
| `fx-crosses` | forex | EURGBP EURJPY AUDNZD GBPJPY EURCHF |
| `fx-all` | forex | majors + crosses — the currency-factor study universe |
| `fx-commodity` | forex | AUDUSD USDCAD NZDUSD AUDNZD |
| `crypto-majors` | crypto | BTC-USDT ETH-USDT |

---

## 4. Date formats

`--start` and `--end` accept:

| Form | Example | Meaning |
|---|---|---|
| ISO date | `2019-01-01` | midnight UTC on that day |
| Compact date | `20190101` | same |
| Date and time | `"2019-01-01 12:30"` | quote it so the shell keeps it as one argument |
| `now` | `now` | this instant |
| `today` | `today` | midnight UTC today |
| Relative | `30d` `12h` `4w` `6mo` `2y` | that far before now |

Relative offsets may be written with a leading minus (`-30d`); it is ignored, since the
offset is always backwards from now. Everything is interpreted and stored as **UTC**.

An unparseable value is a usage error (exit 2) with a message naming the accepted forms.

---

## 5. Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | validation failed, or one or more instruments in a download failed |
| 2 | usage error — unparseable date, reversed date range, missing `--asset-class`, unknown universe |
| 130 | interrupted with Ctrl-C |

The split between 1 and 2 is deliberate: **2 means the command was wrong**, so nothing was
attempted; **1 means the command was right but the data was not**. Asking Binance for a
forex symbol lands in the second group — the batch runs, that instrument is reported as
failed with its reason, and the exit code is 1.

Use in a shell script:

```bash
if ! marketdata validate -a crypto --max-gap-pct 1 -q; then
    echo "crypto data is not fit to backtest on" >&2
    exit 1
fi
```

---

## 6. Recipes

### First-time setup

```bash
cd development/marketdata
pip install -e .

marketdata download -u fx-all --start 2019-01-01
marketdata download -u crypto-majors -t 1h --start 2y
marketdata list
```

### Nightly top-up

`--resume` fetches only what is missing, so this is cheap to run often.

```bash
marketdata download -u fx-all --resume -q
marketdata download -u crypto-majors -t 1h --resume -q
```

### Quality gate before a backtest

```bash
marketdata validate -a crypto --max-gap-pct 1 --strict -q || exit 1
```

### Look at the data

```bash
marketdata report -u fx-all -o reports/forex.html --validate --open
```

### Add one symbol to an existing store

```bash
marketdata download -s EURNOK -a forex --start 2019-01-01
```

### Backfill deeper history

Merge semantics mean an earlier start simply extends the file backwards; nothing is lost.

```bash
marketdata download -u fx-majors --start 2010-01-01
```

### Rebuild a series from scratch

```bash
marketdata download -s EURUSD -a forex --start 2019-01-01 --replace
```

### Compare two sources for the same instrument

They are stored separately, so both survive and the report shows them side by side.

```bash
marketdata download -s BTC-USD -a crypto --source yahoo   -t 1d --start 2y
marketdata download -s BTC-USDT -a crypto --source binance -t 1d --start 2y
marketdata report -a crypto -t 1d -o reports/btc-sources.html
```

### Use a store somewhere else

```bash
marketdata --store /mnt/data/market list
MARKETDATA_STORE=/mnt/data/market marketdata list
```

### Preview before committing to a long download

```bash
marketdata download -u fx-all --start 2005-01-01 --dry-run
```

---

## 7. Data quality

### Yahoo forex has broken OHLC bars

`validate` fails every Yahoo FX series, and the failure is real:

```
EURUSD 2019-03-04   open 1.137527  high 1.137527  close 1.137592
                    close sits 0.65 pips ABOVE the bar's high

28 of 2002 bars affected · median overshoot 1.0 pip · worst 30.6 pips
```

Roughly 1–3% of daily bars have an open or close outside the bar's own high/low range,
which is impossible for a correctly formed bar.

What it means in practice:

- **Close-only work is unaffected.** Correlation, cointegration, factor decomposition and
  anything else reading only closes is fine.
- **Anything reading intrabar extremes is not.** Stop-loss and take-profit simulation, range
  breakouts, and swing-point detection all use highs and lows, and on these bars they are
  wrong. A backtest will report fills that could not have happened.

Binance crypto passes cleanly, as does Yahoo's `BTC-USD`. The defect is specific to Yahoo
forex. Get a broker or Dukascopy feed before running any high/low-dependent backtest.

To proceed anyway with eyes open, set a tolerance and record why:

```bash
marketdata validate -a forex --ohlc-tolerance-bps 5
```

### Yahoo forex reports zero volume

There is no central FX exchange, so Yahoo has no volume to report and returns 0. Any
volume-based signal needs a broker feed or a futures proxy. The report notes this
automatically when a series is entirely zero-volume.

### Yahoo intraday history is capped

| Interval | Maximum lookback |
|---|---|
| `1m` | 7 days |
| `2m`–`90m` | 60 days |
| `1h` | 730 days |
| `1d` and coarser | full history |

Asking for more returns a **short frame, not an error**. The feed logs a warning when the
request exceeds the cap. For deep intraday FX use Dukascopy or HistData.

### Reading `gap_pct`

| Series | Expected | A problem when |
|---|---|---|
| daily forex | ~28% (weekends) | materially above ~30% |
| hourly crypto | ~0% | anything above ~1% |
| daily crypto | ~0% | anything above ~1% |

---

## 8. Library use

Everything the CLI does is available as a normal Python API.

```python
from marketdata import (
    Instrument, ParquetStore, aligned_panel, log_returns,
    validate_frame, build_report, get_feed, parse_date,
)

store = ParquetStore("store")

# read what is already stored
eurusd = store.read(Instrument("EURUSD", "forex", "yahoo", "1d"))

# a panel across instruments, on shared timestamps
fx = [Instrument(s, "forex") for s in ("EURUSD", "GBPUSD", "USDJPY")]
panel = aligned_panel({i.symbol: store.read(i) for i in fx}, field="close")
returns = log_returns(panel)

# fetch without the CLI
feed = get_feed("binance")
btc = feed.history(
    Instrument("BTC-USDT", "crypto", "binance", "1h"),
    parse_date("30d"), parse_date("now"),
)
store.write(Instrument("BTC-USDT", "crypto", "binance", "1h"), btc)

# validate in code
report = validate_frame(eurusd, label="EURUSD", min_rows=500)
print(report.status, [str(i) for i in report.issues])
```

Key objects:

| Name | Purpose |
|---|---|
| `Instrument` | frozen dataclass identifying a series; validates its own fields |
| `ParquetStore` | `.read()`, `.write()`, `.delete()`, `.path()`, `.catalogue()` |
| `select(catalogue, ...)` | filter a catalogue by class, symbol, timeframe, source |
| `aligned_panel(frames, field)` | wide frame on shared timestamps |
| `log_returns(panel)` | log differences, NaNs dropped |
| `gap_pct(index)` | missing-bar share from median spacing |
| `validate_frame(df, ...)` | returns a `SeriesReport` with `.status`, `.errors`, `.warnings` |
| `build_report(selection, output, ...)` | write the HTML file |
| `get_feed(name)` | `YahooFeed` or `BinanceFeed` |
| `parse_date(value)` | CLI date strings to UTC `Timestamp` |

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `--asset-class is required when symbols are given explicitly` | `-s` without `-a` | add `-a forex` or `-a crypto`, or use `-u` |
| `Binance serves crypto only; EURUSD is forex` | `--source binance` on an FX symbol | drop `--source`; forex defaults to Yahoo |
| `binance rejected NOTREAL 1d: Invalid symbol.` | symbol does not exist on Binance | check the canonical form, e.g. `BTC-USDT` not `BTCUSDT` or `BTC/USDT` |
| `cannot parse date 'yesterday'` | unsupported date form | use `1d`, `2024-01-01`, `now`, `today` |
| `--start must be before --end` | reversed range | swap them |
| Download reports `empty`, no error | source has no data for that window | widen the range; check the Yahoo intraday caps |
| `no stored series matched the selection` | nothing downloaded yet, or filters too narrow | run `marketdata list` to see what exists |
| Report shows "No timestamps shared by every selected series" | selection mixes timeframes | add `-t 1d`, or pass `--no-panel` |
| Every FX series fails validation | genuine Yahoo data defect | see §7; use `--ohlc-tolerance-bps` or a better feed |
| Intraday request returns far fewer bars than asked | Yahoo lookback cap | see the table in §7 |
| `list` shows nothing after a download | wrong `--store`, or wrong working directory | check `MARKETDATA_STORE`; paths default to relative |

For an unexpected error, re-run with `-v`. Verbose mode re-raises the traceback instead of
printing a one-line summary.

---

## 10. Extending

### Add a data source

1. Subclass `DataFeed` in `marketdata/feeds.py`, implement
   `history(inst, start, end, retries) -> pd.DataFrame`, and return `normalise(df)`.
2. Register it in the `_FEEDS` dict at the bottom of the module.
3. Add its name to `SOURCES` in `marketdata/instruments.py`, and teach `to_source_symbol()`
   how to translate a canonical symbol for it.

Wrap network calls in `with_retries(...)` so the source inherits the retry and backoff
behaviour.

### Add a universe

Add an entry to `UNIVERSES` in `marketdata/instruments.py`:

```python
"fx-scandi": {
    "symbols": ["USDNOK", "USDSEK", "EURNOK", "EURSEK"],
    "asset_class": "forex",
    "description": "Scandinavian currencies",
},
```

It becomes available to `-u` and appears in `marketdata universes` immediately.

### Add a validation check

In `validate_frame()` in `marketdata/validate.py`, append an `Issue(severity, code,
message)` to `report.issues`. Use `ERROR` when the series should not be traded on and
`WARNING` when it merely deserves attention. Expose any threshold as a keyword argument and
add a matching CLI flag in `cli.py`.

### Add an asset class

Extend `ASSET_CLASSES` and `DEFAULT_SOURCE` in `marketdata/instruments.py`, then handle the
new class in `to_source_symbol()`. Equities need only this: Yahoo already serves them and
the symbol passes through unchanged.

---

## 11. Limits

- **History only.** Live streaming is not part of this package; the prototype lives in
  `development/volume/dev-tradingsystem.ipynb`.
- **No bid/ask, no spread.** Every source here provides mid or last prices only. Cost
  modelling — spread, commission, overnight swap quoted separately for long and short —
  is the next component and does not exist yet.
- **No corporate actions.** Yahoo is queried with `auto_adjust=False`, so equity prices
  would be unadjusted. Irrelevant for forex and crypto.
- **Single-threaded downloads.** Instruments are fetched in sequence to stay inside source
  rate limits. A full `fx-all` daily download takes a few seconds; hourly crypto over
  several years takes a few seconds per symbol.
- **Reports truncate.** Per-instrument tables show the most recent `--max-rows` bars. The
  full series is always in the Parquet file; the HTML is for eyeballing, not archiving.
