"""Command line interface for the market data pipeline.

    python -m marketdata download --universe fx-all --start 2019-01-01
    python -m marketdata report   --universe fx-all -o reports/forex.html
    python -m marketdata validate --asset-class forex --strict

Exit codes
    0   success
    1   validation failed (or a download produced nothing)
    2   bad usage / user error
    130 interrupted
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path

import pandas as pd

from . import __version__
from .feeds import FeedError, get_feed
from .instruments import ASSET_CLASSES, SOURCES, UNIVERSES, resolve_instruments
from .report import DEFAULT_REPORTS, build_report
from .store import DEFAULT_STORE, ParquetStore, select, series_label
from .util import LOG, UserError, human_size, parse_date, setup_logging, split_csv

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_INTERRUPT = 130


# ----------------------------------------------------------------- parsers

def _global_parser(subcommand: bool = False) -> argparse.ArgumentParser:
    """Options accepted both before and after the subcommand.

    The subcommand copies default to SUPPRESS, so an option the user did not repeat there
    leaves the value parsed at the top level untouched. That makes
    ``marketdata --store X list`` and ``marketdata list --store X`` both work, with the
    later, more specific occurrence winning when given twice.
    """
    def default(value):
        return argparse.SUPPRESS if subcommand else value

    parser = argparse.ArgumentParser(add_help=False)
    group = parser.add_argument_group("global options")
    group.add_argument(
        "--store", metavar="PATH",
        default=default(os.environ.get("MARKETDATA_STORE", str(DEFAULT_STORE))),
        help="parquet store root (env: MARKETDATA_STORE) [default: %(default)s]",
    )
    group.add_argument(
        "--reports", metavar="PATH",
        default=default(os.environ.get("MARKETDATA_REPORTS", str(DEFAULT_REPORTS))),
        help="directory for generated HTML (env: MARKETDATA_REPORTS) [default: %(default)s]",
    )
    group.add_argument("-v", "--verbose", action="count", default=default(0),
                       help="show debug logging; repeat for more detail")
    group.add_argument("-q", "--quiet", action="store_true", default=default(False),
                       help="only warnings and errors")
    group.add_argument("--json", action="store_true", dest="as_json", default=default(False),
                       help="print machine-readable JSON instead of a table")
    return parser


def _selection_parser(require_selection: bool = True) -> argparse.ArgumentParser:
    """Options that pick which instruments a command acts on."""
    parser = argparse.ArgumentParser(add_help=False)
    group = parser.add_argument_group("instrument selection")
    group.add_argument(
        "-s", "--symbols", action="append", metavar="SYM[,SYM...]",
        help="one symbol, a comma-separated list, or the flag repeated "
             "(e.g. -s EURUSD -s GBPUSD,USDJPY)",
    )
    group.add_argument(
        "-u", "--universe", choices=sorted(UNIVERSES),
        help="named symbol set; combine with --symbols to extend it",
    )
    group.add_argument("-a", "--asset-class", choices=ASSET_CLASSES,
                       help="required when symbols are given without a universe")
    group.add_argument("--source", choices=SOURCES,
                       help="data source [default: binance for crypto, yahoo for forex]")
    group.add_argument("-t", "--timeframe", default="1d", metavar="TF",
                       help="bar size: 1m, 5m, 15m, 1h, 4h, 1d, 1w [default: %(default)s]")
    parser._require_selection = require_selection  # consulted by the command handlers
    return parser


def build_parser() -> argparse.ArgumentParser:
    globals_ = _global_parser(subcommand=True)

    parser = argparse.ArgumentParser(
        prog="marketdata",
        parents=[_global_parser()],
        description="Download, inspect and validate OHLCV market data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  marketdata download -u fx-all --start 2019-01-01 --end now\n"
            "  marketdata download -s BTC-USDT -a crypto -t 1h --start 90d --resume\n"
            "  marketdata report -u fx-all -o reports/forex.html --validate --open\n"
            "  marketdata validate -a forex --max-gap-pct 35 --strict\n"
            "  marketdata list --json\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"marketdata {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ---- download
    download = subparsers.add_parser(
        "download", parents=[globals_, _selection_parser()],
        help="fetch history and merge it into the store",
        description="Fetch OHLCV history from a source and write it to the parquet store.",
    )
    download.add_argument("--start", default="2y", metavar="DATE",
                          help="start date: YYYY-MM-DD, YYYYMMDD, or an offset such as "
                               "30d / 6mo / 2y [default: %(default)s]")
    download.add_argument("--end", default="now", metavar="DATE",
                          help="end date, same formats [default: %(default)s]")
    download.add_argument("--resume", action="store_true",
                          help="start from the last stored bar when the series already exists")
    download.add_argument("--replace", action="store_true",
                          help="overwrite the stored series instead of merging into it")
    download.add_argument("-n", "--dry-run", action="store_true",
                          help="show what would be fetched and written; no network, no writes")
    download.add_argument("--retries", type=int, default=3, metavar="N",
                          help="attempts per request [default: %(default)s]")
    download.add_argument("--retry-delay", type=float, default=1.0, metavar="SEC",
                          help="initial backoff, doubled per retry [default: %(default)s]")
    download.add_argument("--fail-fast", action="store_true",
                          help="stop at the first failing instrument instead of continuing")
    download.set_defaults(func=cmd_download)

    # ---- report
    report = subparsers.add_parser(
        "report", parents=[globals_, _selection_parser(require_selection=False)],
        help="render stored series into one HTML table file",
        description="Render many instruments into a single self-contained HTML report.",
    )
    report.add_argument("-o", "--output", metavar="FILE",
                        help="output path [default: <reports>/market-data.html]")
    report.add_argument("--title", default="Market Data Report", help="page title")
    report.add_argument("--max-rows", type=int, default=200, metavar="N",
                        help="bars shown per instrument [default: %(default)s]")
    report.add_argument("--panel", dest="panel", action="store_true", default=True,
                        help="include the aligned panel across instruments [default]")
    report.add_argument("--no-panel", dest="panel", action="store_false",
                        help="omit the aligned panel")
    report.add_argument("--panel-field", default="close",
                        choices=["open", "high", "low", "close", "volume"],
                        help="field used for the aligned panel [default: %(default)s]")
    report.add_argument("--panel-rows", type=int, default=200, metavar="N",
                        help="rows shown in the aligned panel [default: %(default)s]")
    report.add_argument("--validate", action="store_true",
                        help="run the data quality checks and include them in the report")
    report.add_argument("--open", dest="open_browser", action="store_true",
                        help="open the finished report in the default browser")
    report.add_argument("-n", "--dry-run", action="store_true",
                        help="list what would be rendered; write nothing")
    report.set_defaults(func=cmd_report)

    # ---- validate
    validate = subparsers.add_parser(
        "validate", parents=[globals_, _selection_parser(require_selection=False)],
        help="run data quality checks against stored series",
        description="Check stored series for structural, consistency and coverage problems.",
    )
    validate.add_argument("--min-rows", type=int, default=100, metavar="N",
                          help="warn below this row count [default: %(default)s]")
    validate.add_argument("--max-gap-pct", type=float, default=None, metavar="PCT",
                          help="warn above this share of missing bars; omitted by default "
                               "because ~28%% of daily forex bars are weekends")
    validate.add_argument("--max-stale-run", type=int, default=20, metavar="N",
                          help="warn when the close is unchanged for N consecutive bars "
                               "[default: %(default)s]")
    validate.add_argument("--ohlc-tolerance-bps", type=float, default=0.0, metavar="BPS",
                          help="how far open/close may sit outside the high/low range before "
                               "it is a violation, in basis points of price so one value "
                               "suits every asset [default: %(default)s]")
    validate.add_argument("--strict", action="store_true",
                          help="treat warnings as failures")
    validate.set_defaults(func=cmd_validate)

    # ---- list
    listing = subparsers.add_parser(
        "list", parents=[globals_, _selection_parser(require_selection=False)],
        help="show what the store contains",
        description="Print the store catalogue: rows, coverage, gap share and file size.",
    )
    listing.set_defaults(func=cmd_list)

    # ---- universes
    universes = subparsers.add_parser(
        "universes", parents=[globals_],
        help="list the built-in symbol sets",
    )
    universes.set_defaults(func=cmd_universes)

    return parser


# ----------------------------------------------------------------- helpers

def _selected_symbols(args) -> list[str]:
    """Flatten --symbols, which may be repeated and/or comma-separated."""
    out: list[str] = []
    for chunk in args.symbols or []:
        out.extend(split_csv(chunk))
    return out


def _catalogue_selection(store: ParquetStore, args) -> pd.DataFrame:
    """Filter the store catalogue by whatever selection flags were given."""
    catalogue = store.catalogue()
    if catalogue.empty:
        return catalogue

    symbols = _selected_symbols(args)
    if args.universe:
        symbols = list(UNIVERSES[args.universe]["symbols"]) + symbols
        args.asset_class = args.asset_class or UNIVERSES[args.universe]["asset_class"]

    # An unset --timeframe keeps its default of "1d"; only filter on it when the user
    # actually narrowed the selection, otherwise `list` would hide every intraday series.
    timeframe = args.timeframe if "-t" in sys.argv or "--timeframe" in sys.argv else None

    return select(
        catalogue,
        asset_class=args.asset_class,
        symbols=symbols or None,
        timeframe=timeframe,
        source=args.source,
    )


def _print_table(df: pd.DataFrame, as_json: bool, empty_message: str) -> None:
    if df.empty:
        print(empty_message)
        return
    if as_json:
        print(df.to_json(orient="records", date_format="iso", indent=2))
    else:
        print(df.to_string(index=False))


# ----------------------------------------------------------------- commands

def cmd_download(args) -> int:
    store = ParquetStore(args.store)
    start = parse_date(args.start)
    end = parse_date(args.end)
    if start is None or end is None:
        raise UserError("--start and --end are both required")
    if start >= end:
        raise UserError(f"--start ({start:%Y-%m-%d}) must be before --end ({end:%Y-%m-%d})")

    instruments = resolve_instruments(
        symbols=_selected_symbols(args),
        universe=args.universe,
        asset_class=args.asset_class,
        source=args.source,
        timeframe=args.timeframe,
    )

    mode = "replace" if args.replace else "merge"
    LOG.info("%s %d instrument(s) from %s to %s into %s",
             "would download" if args.dry_run else "downloading",
             len(instruments), start.date(), end.date(), store.root)

    results = []
    for inst in instruments:
        path = store.path(inst)
        existing = store.read(inst) if path.exists() else None
        window_start = start

        if args.resume and existing is not None and not existing.empty:
            window_start = max(start, existing.index.max())
            LOG.debug("%s resuming from %s", inst, window_start)

        if args.dry_run:
            results.append({
                "instrument": str(inst),
                "action": mode if path.exists() else "create",
                "stored_rows": 0 if existing is None else len(existing),
                "from": str(window_start.date()),
                "to": str(end.date()),
                "path": str(path),
            })
            continue

        try:
            df = get_feed(inst.source).history(inst, window_start, end, retries=args.retries)
            written = store.write(inst, df, mode=mode)
            total = len(store.read(inst))
            results.append({
                "instrument": str(inst), "fetched": len(df), "stored_rows": total,
                "status": "ok" if len(df) else "empty", "path": str(written),
            })
            LOG.info("%-24s fetched %6d  stored %7d", str(inst), len(df), total)
        except (FeedError, UserError) as exc:
            results.append({"instrument": str(inst), "fetched": 0, "stored_rows": 0,
                            "status": f"{type(exc).__name__}: {exc}"[:160], "path": ""})
            LOG.error("%-24s %s", str(inst), exc)
            if args.fail_fast:
                break

    frame = pd.DataFrame(results)
    _print_table(frame, args.as_json, "nothing to download")

    if args.dry_run:
        LOG.info("dry run — no files written")
        return EXIT_OK

    failed = [r for r in results if str(r.get("status", "")).startswith(("FeedError", "UserError"))]
    if failed:
        LOG.error("%d of %d instruments failed", len(failed), len(results))
        return EXIT_FAILED
    return EXIT_OK


def cmd_report(args) -> int:
    store = ParquetStore(args.store)
    selection = _catalogue_selection(store, args)
    if selection.empty:
        LOG.error("no stored series matched the selection — run 'download' first")
        return EXIT_FAILED

    output = Path(args.output) if args.output else Path(args.reports) / "market-data.html"

    if args.dry_run:
        LOG.info("would render %d series to %s", len(selection), output)
        _print_table(selection.drop(columns=["path"]), args.as_json, "nothing selected")
        return EXIT_OK

    validation = None
    if args.validate:
        from .validate import validate_selection
        validation = validate_selection(
            store, selection,
            min_rows=100, max_gap_pct=None, max_stale_run=20,
        )

    path = build_report(
        selection, output,
        store_root=store.root,
        max_rows=args.max_rows,
        include_panel=args.panel,
        panel_field=args.panel_field,
        panel_rows=args.panel_rows,
        title=args.title,
        validation=validation,
    )

    size = human_size(path.stat().st_size)
    LOG.info("wrote %s (%s, %d series)", path, size, len(selection))
    if args.as_json:
        print(json.dumps({"output": str(path.resolve()), "series": len(selection),
                          "bytes": path.stat().st_size}, indent=2))
    else:
        print(path.resolve())

    if args.open_browser:
        webbrowser.open(path.resolve().as_uri())
    return EXIT_OK


def cmd_validate(args) -> int:
    from .validate import validate_selection

    store = ParquetStore(args.store)
    selection = _catalogue_selection(store, args)
    if selection.empty:
        LOG.error("no stored series matched the selection")
        return EXIT_FAILED

    reports = validate_selection(
        store, selection,
        min_rows=args.min_rows,
        max_gap_pct=args.max_gap_pct,
        max_stale_run=args.max_stale_run,
        ohlc_tolerance_bps=args.ohlc_tolerance_bps,
    )

    if args.as_json:
        print(json.dumps([r.to_dict() for r in reports], indent=2))
    else:
        rows = [{"series": r.label, "rows": r.rows, "status": r.status,
                 "findings": "; ".join(i.message for i in r.issues) or "—"}
                for r in reports]
        print(pd.DataFrame(rows).to_string(index=False))

    failures = [r for r in reports if r.errors]
    warned = [r for r in reports if r.warnings and not r.errors]

    if failures:
        LOG.error("%d of %d series failed validation", len(failures), len(reports))
        return EXIT_FAILED
    if warned and args.strict:
        LOG.error("%d series raised warnings and --strict is set", len(warned))
        return EXIT_FAILED
    LOG.info("%d series validated, %d with warnings", len(reports), len(warned))
    return EXIT_OK


def cmd_list(args) -> int:
    store = ParquetStore(args.store)
    selection = _catalogue_selection(store, args)
    if selection.empty:
        print(f"store {store.root}/ is empty or nothing matched the selection")
        return EXIT_OK

    display = selection.drop(columns=["path"])
    _print_table(display, args.as_json, "nothing stored")

    if not args.as_json:
        total_rows = int(selection["rows"].sum())
        total_kb = float(selection["size_kb"].sum())
        print(f"\n{len(selection)} series · {total_rows:,} bars · {human_size(total_kb * 1024)}")
    return EXIT_OK


def cmd_universes(args) -> int:
    rows = [{"universe": name, "asset_class": spec["asset_class"],
             "symbols": len(spec["symbols"]), "description": spec["description"],
             "members": ", ".join(spec["symbols"])}
            for name, spec in sorted(UNIVERSES.items())]
    frame = pd.DataFrame(rows)
    if args.as_json:
        print(frame.to_json(orient="records", indent=2))
    else:
        print(frame.drop(columns=["members"]).to_string(index=False))
        print()
        for row in rows:
            print(f"  {row['universe']:<14} {row['members']}")
    return EXIT_OK


# ----------------------------------------------------------------- entry point

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_USAGE

    setup_logging(args.verbose, args.quiet)

    try:
        return args.func(args)
    except UserError as exc:
        LOG.error("%s", exc)
        return EXIT_USAGE
    except KeyboardInterrupt:
        LOG.warning("interrupted")
        return EXIT_INTERRUPT
    except Exception as exc:  # noqa: BLE001 - last resort, keep the traceback behind -v
        LOG.error("%s: %s", type(exc).__name__, exc)
        if args.verbose:
            raise
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
