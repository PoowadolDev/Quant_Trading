---
name: marketdata
description: >
  Load, store, inspect and validate OHLCV market data for forex and crypto
  using the project's `marketdata` CLI and its local Parquet store. Use
  whenever the user asks to download or fetch price data, get bars/candles for
  a symbol, backfill or update history, check what data is already available,
  build a data table or HTML report, or verify data quality — including
  phrases like "get EURUSD data", "download BTC hourly", "load market data",
  "update the data", "what data do I have", "show me the data", "is this data
  clean", or before any analysis, correlation study or backtest that needs
  price history. Never write ad-hoc yfinance or exchange-API download code
  while this skill applies; the CLI already handles symbol mapping, paging,
  retries, incremental merge and the known data defects of each source.
---

# Market Data

The project stores all price history in one Parquet store, managed by the `marketdata`
CLI. This skill covers fetching it, checking it, and handing it to analysis.

Scope is **data only** — load, save, inspect, validate. Strategy and analysis code is not
part of this skill.

## Step 0 — working directory

Store and report paths default to relative locations, so commands run from the package
directory:

```bash
cd development/marketdata
```

To work from elsewhere, pass absolute paths or set the environment:

```bash
export MARKETDATA_STORE=D:/Repository/Quant_Trading/development/marketdata/store
export MARKETDATA_REPORTS=D:/Repository/Quant_Trading/development/marketdata/reports
```

If `marketdata` is not on PATH, use `python -m marketdata` — identical behaviour. To
install it: `pip install -e .` from `development/marketdata`.

## Workflow

Follow in order. Step 1 is the one most often skipped and most often wrong to skip.

### 1. Look before fetching

```bash
marketdata list
```

The store frequently already holds what is being asked for. Re-downloading wastes time and
tells you nothing new. Check coverage — `rows`, `start`, `end` — before deciding anything.

### 2. Fetch only what is missing

```bash
marketdata download -u fx-all --resume            # top up to now
marketdata download -s EURUSD,GBPUSD -a forex --start 2019-01-01
marketdata download -s BTC-USDT -a crypto -t 1h --start 2y
```

`--resume` starts from the last stored bar per instrument, so it fetches the gap rather
than the whole history. Writes merge and de-duplicate, so an overlapping range is safe.

Preview first when the request is large — more than about five symbols, or more than a year
of intraday:

```bash
marketdata download -u fx-all --start 2010-01-01 --dry-run
```

Dry run makes no network calls and writes nothing.

### 3. Validate before trusting

```bash
marketdata validate -a forex
marketdata validate -a crypto --max-gap-pct 1 --strict
```

Exit code 0 means pass, 1 means at least one series failed. Read the findings — do not
assume a pass.

### 4. Report only when the user wants to look

```bash
marketdata report -u fx-all -o reports/forex.html --validate
```

Writes one self-contained HTML file containing every selected instrument: a contents
table, an optional validation section, an aligned cross-instrument panel, and one OHLCV
table per instrument. Prints the absolute path. Add `--open` to launch a browser.

Do not generate a report as a side effect of an analysis task; it is for human eyes.

### 5. Hand off to analysis

For computation, read the store directly. Do not parse CLI text output.

```python
from marketdata import Instrument, ParquetStore, aligned_panel, log_returns

store = ParquetStore("store")
fx = [Instrument(s, "forex") for s in ("EURUSD", "GBPUSD", "USDJPY")]
panel = aligned_panel({i.symbol: store.read(i) for i in fx}, field="close")
returns = log_returns(panel)
```

When a command's output does need parsing, use `--json`:

```bash
marketdata list --json
marketdata validate -a crypto --json
```

## Commands

| Command | Purpose |
|---|---|
| `list` | what the store contains, with coverage and gap share |
| `download` | fetch history and merge it into the store |
| `validate` | data quality checks; non-zero exit on failure |
| `report` | render many instruments into one HTML table file |
| `universes` | list the built-in symbol sets |

### Selection — same flags everywhere

| Flag | Meaning |
|---|---|
| `-s, --symbols` | one symbol, a comma-separated list, or the flag repeated |
| `-u, --universe` | `fx-majors`, `fx-crosses`, `fx-all`, `fx-commodity`, `crypto-majors`, `metals`, `energy`, `commodities` |
| `-a, --asset-class` | `forex`, `crypto` or `commodity`; required with explicit symbols |
| `--source` | `yahoo` or `binance`; defaults to yahoo for forex, binance for crypto |
| `-t, --timeframe` | `1m 5m 15m 1h 4h 1d 1w`, default `1d` |

Prefer a universe over a hand-typed list when one fits.

### Dates

`--start` and `--end` accept `2019-01-01`, `20190101`, `now`, `today`, or an offset back
from now: `30d`, `12h`, `4w`, `6mo`, `2y`. Everything is UTC.

### Common options

`--dry-run` preview · `--resume` incremental · `--replace` overwrite · `--json`
machine-readable · `-q` quiet · `-v` debug and full tracebacks · `--store` / `--reports`
paths. Global options work before or after the subcommand.

Full reference, including every flag and every validation check:
**`development/marketdata/MANUAL.md`**. Consult it rather than guessing; do not copy its
contents into other documents.

## Reading the output

`list` — one row per stored series:

```
asset_class  symbol    timeframe  source   rows   start       end         gap_pct  size_kb
forex        EURUSD    1d         yahoo    2002   2019-01-01  2026-09-09  28.8     68.2
crypto       BTC-USDT  1h         binance  14809  2025-01-01  2026-09-10  0.0      649.5

13 series · 50,257 bars · 1.9 MB
```

`validate` — status is `OK`, `WARN` or `FAIL`:

```
series                   rows   status  findings
EURUSD · 1d · yahoo      2002   FAIL    28 bars where open or close exceeds the high (worst 30.6 pips)
BTC-USDT · 1h · binance  14809  OK      —
```

`download` — one line per instrument, plus a summary table:

```
INFO  EURUSD@yahoo:1d   fetched      1  stored     2002
```

`report` — the absolute path to the written file.

Exit codes: `0` success · `1` validation failed or an instrument failed to download ·
`2` usage error (bad date, missing `--asset-class`, unknown universe) · `130` interrupted.

## Store layout

```
store/{asset_class}/{symbol}/{timeframe}/{source}.parquet
```

The path carries the metadata; the catalogue is rebuilt by scanning the tree. One file per
source, so two feeds for the same instrument coexist and stay comparable.

Symbols are canonical and source-agnostic — write `EURUSD`, not `EURUSD=X`; write
`BTC-USDT`, not `BTCUSDT`; write `GOLD`, not `GC=F`. The mapper translates per feed.

Commodities are named in plain words: `GOLD`, `SILVER`, `COPPER`, `WTI`, `BRENT`,
`NATGAS`. They are the external anchors for FX pair studies — the thing a commodity
currency is supposed to track.

## Data quality — known defects

These are established facts about the sources, not hypotheticals. State them when they
affect what the user is trying to do.

### Yahoo forex has broken OHLC bars

Roughly 1–3% of daily Yahoo FX bars have an open or close outside the bar's own high/low
range, which is impossible for a well-formed bar.

```
EURUSD 2019-03-04   open 1.137527  high 1.137527  close 1.137592
                    close sits 0.65 pips ABOVE the bar's high
28 of 2002 bars · median overshoot 1.0 pip · worst 30.6 pips
```

Every Yahoo FX series therefore fails `validate`. The failure is real, not a false alarm.

- **Close-only work may proceed** — correlation, cointegration, factor decomposition and
  anything else reading only closes is unaffected. Note the defect once, then continue.
- **High/low work may not** — stop-loss and take-profit simulation, range breakouts, and
  swing-point detection all read intrabar extremes, and on these bars the extremes are
  wrong. Say so and stop rather than producing a backtest with impossible fills. This
  includes the Wyckoff logic in `development/wyckoff/`.

To proceed knowingly on a close-only task, record the decision:
`marketdata validate -a forex --ohlc-tolerance-bps 5`

Binance crypto and Yahoo `BTC-USD` pass cleanly. The defect is specific to Yahoo forex.

### Yahoo forex volume is always zero

No central FX exchange, so there is nothing to report. Volume-based signals need a broker
feed or a futures proxy.

### Yahoo intraday history is capped

1-minute bars reach back 7 days, most sub-daily intervals 60 days, hourly 730 days. Asking
for more returns a **short frame, not an error**. For deep intraday FX use Dukascopy or
HistData.

### `gap_pct` is not a defect on daily forex

Daily FX sits near 28% because weekends are 2/7 of the week. Crypto should be near 0%.
`--max-gap-pct` is off by default for this reason; set it per asset class when used:

```bash
marketdata validate -a forex  --max-gap-pct 35
marketdata validate -a crypto --max-gap-pct 1
```

### Commodities are front-month futures, and they roll

Yahoo has no spot commodity feed, so `GOLD` is `GC=F` and `WTI` is `CL=F` — the
front-month contract. The series is continuous but **not roll-adjusted**: at each roll
the level steps by the spread between contracts. Acceptable for a study of daily closes;
wrong for anything that accumulates the jump as if it were a return.

### WTI went negative in April 2020

```
WTI 2020-04-20   open 17.73   high 17.85   low -40.32   close -37.63
WTI 2020-04-21   open -14.00  high 13.86   low -16.74   close  10.01
```

This is real history, not a bad print, and `validate` reports it as `4 prices at or
below zero`. Any log-price work — correlation, cointegration, spread construction — is
impossible across those dates. Use `BRENT`, which never went negative, or start the
window after 2020-05-01. Say which was chosen and why.

### USDT is not USD

`BTC-USDT` (Binance) and `BTC-USD` (Yahoo) are different assets. Never splice them into a
single series.

## Rules

- Run `list` before any download.
- Never pass `--replace` without asking the user first — it discards stored history.
- Never delete files from the store.
- Never present an analysis result from a series that failed `validate` without stating
  the failure and why it does or does not matter for that task.
- Never write a new downloader. If the CLI cannot do something, extend the package under
  `development/marketdata/marketdata/` — see the Extending section of `MANUAL.md`.
- Reports are for the user to read. Do not produce one unprompted.
