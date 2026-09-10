# marketdata

Fetch, store, inspect and validate OHLCV history for **forex** and **crypto**.

**[Full manual → MANUAL.md](MANUAL.md)**

```bash
cd development/marketdata
pip install -e .

marketdata download -u fx-all --start 2019-01-01     # majors + crosses
marketdata list                                       # what is on disk
marketdata validate -a forex                          # data quality gate
marketdata report -u fx-all -o reports/forex.html --validate --open
```

## What is here

```
development/marketdata/
├── marketdata/            the package
│   ├── instruments.py     Instrument identity, symbol translation, named universes
│   ├── feeds.py           YahooFeed, BinanceFeed, retry/backoff, one output schema
│   ├── store.py           ParquetStore, catalogue, selection, aligned panel
│   ├── validate.py        data quality checks
│   ├── report.py          self-contained HTML table report
│   ├── cli.py             command line
│   └── util.py            date parsing, logging, formatting
├── store/                 parquet data (gitignored via *.parquet)
├── reports/               generated HTML
├── data-loader.ipynb      prototype — superseded by the package
├── data-viewer.ipynb      prototype — superseded by the package
├── MANUAL.md              full reference
└── pyproject.toml
```

The notebooks were the prototypes and are kept for exploratory work. The package is the
version to depend on.

## Commands

| Command | Purpose |
|---|---|
| `download` | fetch history and merge it into the store |
| `report` | render many instruments into one HTML table file |
| `validate` | data quality checks; exits non-zero on failure |
| `list` | show what the store contains |
| `universes` | list the built-in symbol sets |

Every command takes `--store`, `--reports`, `-v`, `-q`, `--json`, and the instrument
selection flags `-s/--symbols`, `-u/--universe`, `-a/--asset-class`, `--source`,
`-t/--timeframe`. See [MANUAL.md](MANUAL.md#3-command-reference) for the complete reference.

## Storage

```
store/{asset_class}/{symbol}/{timeframe}/{source}.parquet
```

The path is the metadata, so the catalogue is rebuilt by scanning the tree — no index file
to fall out of sync. Writes merge and de-duplicate, so re-running a download over an
overlapping range is safe.

## Before you trust the data

`validate` fails every Yahoo **forex** series, and the failure is real: 1–3% of daily bars
have an open or close outside the bar's own high/low range.

```
EURUSD 2019-03-04   open 1.137527  high 1.137527  close 1.137592
                    close sits 0.65 pips ABOVE the bar's high
```

Close-only work (correlation, cointegration, factor decomposition) is unaffected. Anything
reading intrabar extremes — stop-loss simulation, range breakouts, swing-point detection —
is not. Binance crypto passes cleanly. Details in
[MANUAL.md §7](MANUAL.md#7-data-quality).
