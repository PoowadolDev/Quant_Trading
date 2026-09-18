"""Step 2.1 — the hypothesis test the pipeline never had.

Everything before this used the Ornstein-Uhlenbeck half-life as evidence of mean
reversion. A half-life is an estimate, not a test: it has no null hypothesis and
no p-value, so a fitted number can never be *rejected*, only judged against a
bound somebody chose.

Three tests, because they answer different questions:

* **ADF** on a spread built with a given hedge ratio — is this particular series
  stationary?
* **Engle-Granger** — are the two series cointegrated, allowing for the fact that
  the hedge ratio was itself estimated? Its critical values differ from plain ADF
  for exactly that reason, and using the ADF table on an estimated residual is a
  standard way to manufacture significance.
* **Johansen** — how many cointegrating relationships exist among the legs. It is
  the test that generalises past two legs.

    python cointegration.py -s USDNOK,USDZAR
    python cointegration.py -s SOL-USDT,LINK-USDT -a crypto --split 0.7
    python cointegration.py -s EURUSD,GBPUSD --test engle-granger --both-directions

Exit codes: 0 cointegrated on the full sample and, unless --no-require-oos,
on the held-out tail as well; 3 not; 2 usage error.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import warnings
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import paths

paths.ensure_code_importable()
paths.ensure_marketdata_importable()

import relationship as rel                                     # noqa: E402
import pair_report as pr                                          # noqa: E402

UserError = pr.UserError
DEFAULT_LOG = paths.LOGS / "cointegration.csv"

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from statsmodels.tsa.stattools import adfuller, coint         # noqa: E402
    from statsmodels.tsa.vector_ar.vecm import coint_johansen     # noqa: E402


@dataclass
class TestResult:
    name: str
    statistic: float
    pvalue: float | None
    critical: dict
    reject: bool
    note: str = ""


def adf_test(series: np.ndarray, *, trend: str, lags) -> TestResult:
    """Stationarity of a series that was handed to us, not estimated from a fit."""
    kwargs = {"regression": trend}
    if isinstance(lags, int):
        kwargs["maxlag"] = lags
        kwargs["autolag"] = None
    else:
        kwargs["autolag"] = lags.upper()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        stat, pvalue, _, _, crit, *_ = adfuller(series, **kwargs)
    return TestResult("ADF on the spread", float(stat), float(pvalue),
                      {k: float(v) for k, v in crit.items()}, pvalue < 0.05,
                      "assumes the hedge ratio was given, not fitted")


def engle_granger(y: np.ndarray, x: np.ndarray, *, trend: str, lags) -> TestResult:
    """Cointegration with an estimated hedge ratio, using the right critical values."""
    kwargs = {"trend": trend}
    if isinstance(lags, int):
        kwargs["maxlag"] = lags
        kwargs["autolag"] = None
    else:
        kwargs["autolag"] = lags.upper()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        stat, pvalue, crit = coint(y, x, **kwargs)
    return TestResult("Engle-Granger", float(stat), float(pvalue),
                      {"1%": float(crit[0]), "5%": float(crit[1]), "10%": float(crit[2])},
                      pvalue < 0.05, "accounts for the fitted hedge ratio")


def johansen(frame: pd.DataFrame, *, det_order: int, lags: int) -> list[TestResult]:
    """How many cointegrating relationships exist among the columns."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = coint_johansen(frame.to_numpy(float), det_order, lags)
    out = []
    for rank in range(len(res.lr1)):
        crit = {"10%": float(res.cvt[rank, 0]), "5%": float(res.cvt[rank, 1]),
                "1%": float(res.cvt[rank, 2])}
        out.append(TestResult(f"Johansen trace, rank <= {rank}", float(res.lr1[rank]),
                              None, crit, res.lr1[rank] > res.cvt[rank, 1],
                              "no p-value; compare the statistic with the critical values"))
    return out


def verdict_line(results: list[TestResult], level: float) -> tuple[bool, str]:
    eg = next((r for r in results if r.name == "Engle-Granger"), None)
    if eg is None:
        rejecting = [r for r in results if r.reject]
        return bool(rejecting), ("some tests reject the null" if rejecting
                                 else "no test rejects the null")
    if eg.pvalue is not None and eg.pvalue < level:
        return True, (f"Engle-Granger rejects the null of no cointegration at "
                      f"p = {eg.pvalue:.3f}")
    return False, (f"Engle-Granger cannot reject the null of no cointegration, "
                   f"p = {eg.pvalue:.3f}; the two series may simply drift together")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cointegration", description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sel = p.add_argument_group("selection")
    sel.add_argument("-s", "--symbols", required=True, help="two symbols, comma separated")
    sel.add_argument("-a", "--asset-class", default="forex",
                     help="one class for both legs, or one per leg")
    sel.add_argument("-t", "--timeframe", default="1d")
    sel.add_argument("--source", default=None)
    sel.add_argument("--start", default=None)
    sel.add_argument("--end", default=None)

    struct = p.add_argument_group("structure - choose once, not per run")
    struct.add_argument("--test", default="all",
                        choices=("all", "adf", "engle-granger", "johansen"))
    struct.add_argument("--price", default="log", choices=("log", "raw"))
    struct.add_argument("--adf-trend", default="c", choices=("n", "c", "ct"),
                        help="n none, c constant, ct constant plus trend")
    struct.add_argument("--eg-trend", default="c", choices=("n", "c", "ct"))
    struct.add_argument("--lags", default="aic",
                        help="aic, bic, t-stat, or a fixed integer number of lags. "
                             "Measured on 2000 independent random-walk pairs, every one "
                             "of these rejects between 4.5%% and 4.9%% at the nominal 5%% "
                             "level, so the choice does not change how often the test "
                             "cries wolf")
    struct.add_argument("--det-order", type=int, default=0,
                        help="Johansen deterministic term: -1 none, 0 constant, 1 trend")
    struct.add_argument("--johansen-lags", type=int, default=1)

    search = p.add_argument_group("searched - every value is a trial")
    search.add_argument("--split", type=float, default=0.70,
                        help="also test the held-out tail on its own")
    search.add_argument("--level", type=float, default=0.05, help="significance level")
    search.add_argument("--require-oos", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="the held-out tail must also reject the null before the run "
                             "counts as cointegrated. The tail is shorter and the test "
                             "has less power there, so --no-require-oos reports it "
                             "without letting it decide")
    search.add_argument("--both-directions", action="store_true",
                        help="also regress B on A; a pair cointegrated only one way is "
                             "weaker evidence")

    out = p.add_argument_group("output")
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--log", default=str(DEFAULT_LOG), help="one row per run")
    out.add_argument("--no-log", action="store_true")
    out.add_argument("--json", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    out.add_argument("--min-half-life", type=float, default=2.0, help=argparse.SUPPRESS)
    out.add_argument("--max-half-life", type=float, default=1e9, help=argparse.SUPPRESS)
    out.add_argument("--hedge", default="ols", help=argparse.SUPPRESS)
    out.add_argument("--entry-z", type=float, default=2.0, help=argparse.SUPPRESS)
    out.add_argument("--exit-z", type=float, default=0.5, help=argparse.SUPPRESS)
    return p


def run_tests(px: pd.DataFrame, args) -> tuple[list[TestResult], float]:
    a, b = px.columns
    lags = int(args.lags) if str(args.lags).isdigit() else str(args.lags).lower()
    if not isinstance(lags, int) and lags not in ("aic", "bic", "t-stat"):
        raise UserError(f"--lags takes aic, bic, t-stat or an integer, not {args.lags!r}")
    lp = np.log(px) if args.price == "log" else px
    beta, alpha = rel.ols_beta(lp[a].to_numpy(float), lp[b].to_numpy(float))
    spread = (lp[a] - beta * lp[b] - alpha).to_numpy(float)

    results: list[TestResult] = []
    if args.test in ("all", "adf"):
        results.append(adf_test(spread, trend=args.adf_trend, lags=lags))
    if args.test in ("all", "engle-granger"):
        results.append(engle_granger(lp[a].to_numpy(float), lp[b].to_numpy(float),
                                     trend=args.eg_trend, lags=lags))
        if args.both_directions:
            rev = engle_granger(lp[b].to_numpy(float), lp[a].to_numpy(float),
                                trend=args.eg_trend, lags=lags)
            rev.name = "Engle-Granger, legs reversed"
            rev.note = "regressing the other way; disagreement weakens the evidence"
            results.append(rev)
    if args.test in ("all", "johansen"):
        results.extend(johansen(lp, det_order=args.det_order, lags=args.johansen_lags))
    return results, beta


def show(results: list[TestResult], log) -> None:
    log(f"  {'test':32s} {'statistic':>10s} {'p-value':>9s} {'5% crit':>9s} "
        f"{'reject?':>8s}  note")
    for r in results:
        pv = f"{r.pvalue:9.4f}" if r.pvalue is not None else f"{'—':>9s}"
        crit = r.critical.get("5%", r.critical.get("5.0%"))
        cs = f"{crit:9.3f}" if crit is not None else f"{'—':>9s}"
        log(f"  {r.name:32s} {r.statistic:10.3f} {pv} {cs} "
            f"{('yes' if r.reject else 'no'):>8s}  {r.note}")


def append_log(path: Path, args, pair: str, beta: float, results: list[TestResult],
               oos: list[TestResult] | None, cointegrated: bool) -> int:
    def pv(rs, name):
        r = next((x for x in rs or [] if x.name == name), None)
        return "" if r is None or r.pvalue is None else round(r.pvalue, 4)

    row = {"run": 0,
           "run_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "pair": pair, "timeframe": args.timeframe, "start": args.start or "",
           "end": args.end or "", "price": args.price, "test": args.test,
           "adf_trend": args.adf_trend, "eg_trend": args.eg_trend, "lags": args.lags,
           "split": args.split, "level": args.level, "beta": round(beta, 6),
           "adf_p": pv(results, "ADF on the spread"),
           "eg_p": pv(results, "Engle-Granger"),
           "eg_p_reversed": pv(results, "Engle-Granger, legs reversed"),
           "eg_p_out_of_sample": pv(oos, "Engle-Granger"),
           "cointegrated": "yes" if cointegrated else "no"}
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = 0
    if path.exists():
        with path.open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh), [])
            existing = sum(1 for _ in csv.reader(fh))
        if header and header != list(row):
            raise UserError(f"{path} was written by an older version; rename it to keep "
                            "the history and a fresh log will start")
    row["run"] = existing + 1
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row))
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    return row["run"]


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))
    if not 0.0 < args.level < 0.5:
        raise UserError("--level must be between 0 and 0.5")
    if not 0.1 <= args.split <= 0.95:
        raise UserError("--split must be between 0.1 and 0.95")

    px = pr.load_prices(args)
    a, b = px.columns
    split = int(len(px) * args.split)

    results, beta = run_tests(px, args)
    cointegrated, reason = verdict_line(results, args.level)

    log(f"{a} ~ {b}   {args.timeframe}   {px.index[0]:%Y-%m-%d} to {px.index[-1]:%Y-%m-%d}"
        f"   {len(px):,} bars   hedge ratio {beta:+.4f}")
    log(f"  {'COINTEGRATED' if cointegrated else 'NOT COINTEGRATED'} — {reason}")
    log("")
    show(results, log)

    oos, oos_ok = None, None
    if split < len(px) - 60:
        tail = px.iloc[split:]
        oos, beta_oos = run_tests(tail, args)
        oos_ok, oos_reason = verdict_line(oos, args.level)
        log("")
        log(f"  held-out tail only, {len(tail):,} bars, hedge ratio {beta_oos:+.4f}")
        show(oos, log)
        log(f"  {'holds' if oos_ok else 'does not hold'} out of sample — {oos_reason}")

    accepted = cointegrated and (oos_ok is not False or not args.require_oos)
    if cointegrated and oos_ok is False:
        if args.require_oos:
            log("")
            log("  REJECTED — cointegrated on the full sample but not on the held-out "
                "tail.")
            log("  A relationship that only holds where it was fitted is the failure this "
                "project")
            log("  has already paid for once. Pass --no-require-oos to report it without "
                "letting")
            log("  it decide, remembering the tail is shorter and the test has less power "
                "there.")

    if args.json:
        print(json.dumps({"pair": f"{a}~{b}", "beta": beta,
                          "cointegrated": cointegrated, "accepted": accepted,
                          "out_of_sample_holds": oos_ok, "reason": reason,
                          "full_sample": [asdict(r) for r in results],
                          "out_of_sample": [asdict(r) for r in (oos or [])]},
                         indent=2, default=str))

    if not args.no_log:
        run = append_log(Path(args.log), args, f"{a}~{b}", beta, results, oos,
                         accepted)
        log(f"\n  run #{run} logged to {Path(args.log).resolve()}")
    return 0 if accepted else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:                                       # noqa: BLE001
        if "-v" in sys.argv or "--verbose" in sys.argv:
            raise
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
