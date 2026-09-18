"""Step 0 pair study — fit one relationship and write a self-contained HTML report.

This is the research gate described in PLAN.md, Step 0: take two instruments,
build a spread, and answer one question — is the gap actually closing, often
enough and far enough to pay for the cost of trading it?

Every parameter is entered by hand. That is deliberate. The gate is only honest
if each set of values counts as one trial, so the script appends a row to a
trial log on every run and the report prints the parameters it used.

Usage:

    python pair_report.py -s AUDUSD,NZDUSD
    python pair_report.py -s EURUSD,GBPUSD --split 0.6 --entry-z 1.8 --cost-bps 3
    python pair_report.py -s AUDUSD,NZDUSD --start 2021-01-01 --dry-run

Exit codes: 0 accepted, 3 rejected, 1 runtime error, 2 usage error.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import sys
import webbrowser
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import relationship as rel

import paths

paths.ensure_marketdata_importable()

from marketdata import (  # noqa: E402
    ASSET_CLASSES, DEFAULT_SOURCE, Instrument, ParquetStore, aligned_panel, parse_date,
)

DEFAULT_STORE = paths.STORE
DEFAULT_REPORTS = paths.PAIR_STUDIES
DEFAULT_TRIALS = paths.TRIALS


class UserError(Exception):
    """Bad input from the command line. Reported without a traceback."""


# ---------------------------------------------------------------- statistics
@dataclass
class PairFit:
    """Everything the report needs, and nothing that is not a measured number."""

    symbol_a: str
    symbol_b: str
    n_bars: int
    n_in_sample: int
    beta: float
    alpha: float
    theta: float
    mu: float
    sigma: float
    sigma_eq: float
    half_life: float
    half_life_oos: float
    regime: str                   # in-sample: reverting, explosive or oscillating
    regime_oos: str
    correlation: float
    expected_move_bps: float
    edge_mult: float


def fit_pair(prices: pd.DataFrame, *, split: int, use_log: bool,
             entry_z: float, exit_z: float, cost_bps: float) -> PairFit:
    """Hedge ratio, spread, and an OU fit, all estimated in-sample only.

    The out-of-sample half-life is fitted separately on the held-out half. It is
    the single most informative number here: a relationship that mean-reverts
    in-sample and diverges afterwards was curve fitting, not structure.
    """
    a, b = prices.columns
    px = np.log(prices) if use_log else prices
    in_sample = px.iloc[:split]

    beta, alpha = rel.ols_beta(in_sample[a].to_numpy(float), in_sample[b].to_numpy(float))
    spread = px[a] - beta * px[b] - alpha

    theta, mu, sigma, regime = _fit_ou(spread.iloc[:split].to_numpy(float))
    sigma_eq = sigma / math.sqrt(2 * theta) if theta > 0 else float("nan")
    half_life = math.log(2) / theta if theta > 0 else float("nan")

    theta_oos, _, _, regime_oos = _fit_ou(spread.iloc[split:].to_numpy(float))
    half_life_oos = math.log(2) / theta_oos if theta_oos > 0 else float("nan")

    # Round trip from the entry threshold back to the exit threshold, in basis
    # points, against the round-trip cost of putting both legs on and taking
    # them off again.
    expected_move_bps = (entry_z - exit_z) * sigma_eq * 1e4
    edge_mult = expected_move_bps / cost_bps if cost_bps > 0 else float("inf")

    returns = np.log(prices).diff().dropna()
    correlation = float(returns.corr().iloc[0, 1])

    return PairFit(
        symbol_a=a, symbol_b=b, n_bars=len(px), n_in_sample=split,
        beta=beta, alpha=alpha, theta=theta, mu=mu, sigma=sigma,
        sigma_eq=sigma_eq, half_life=half_life, half_life_oos=half_life_oos,
        regime=regime, regime_oos=regime_oos,
        correlation=correlation, expected_move_bps=expected_move_bps,
        edge_mult=edge_mult,
    )


REVERTING, EXPLOSIVE, OSCILLATING = "reverting", "explosive", "oscillating"

REGIME_NOTE = {
    EXPLOSIVE: "AR(1) coefficient outside (-1, 1): the spread diverges",
    OSCILLATING: "AR(1) coefficient is negative: reversion is faster than one bar, "
                 "which is noise or bid-ask bounce at this timeframe, not an OU process",
}


def _fit_ou(series: np.ndarray) -> tuple[float, float, float, str]:
    """Discrete OU fit by AR(1) regression: s[t+1] = a*s[t] + b + noise.

    Returns theta, mu, sigma and the regime the fitted `a` implies:

    * `0 < a < 1` is the OU case, and theta, mu and sigma are meaningful.
    * `|a| >= 1` is explosive — the spread walks away instead of returning.
    * `-1 < a <= 0` reverts, but it overshoots every bar, so the reversion is
      faster than the sampling interval. The continuous-time half-life `ln2/θ`
      does not exist there, and calling it explosive would be the opposite of
      the truth, so it gets its own label.

    In both non-OU cases theta is returned as 0 so the caller cannot build a
    half-life or an equilibrium standard deviation out of it by accident.
    """
    if not np.isfinite(series).all():
        raise UserError("the spread contains infinite or missing values, so no OU fit is "
                        "possible; check the price data for bad bars")
    s0, s1 = series[:-1], series[1:]
    a, b = (float(v) for v in np.polyfit(s0, s1, 1))
    if not (-1.0 < a < 1.0):
        return 0.0, float(np.mean(series)), float(np.std(series, ddof=1)), EXPLOSIVE
    if a <= 0.0:
        return 0.0, float(np.mean(series)), float(np.std(series, ddof=1)), OSCILLATING
    theta = -math.log(a)
    mu = b / (1 - a)
    resid_sd = float(np.std(s1 - (a * s0 + b), ddof=2))
    sigma = resid_sd * math.sqrt(-2 * math.log(a) / (1 - a ** 2))
    return theta, mu, sigma, REVERTING


def sanity_checks(fit: PairFit, spread: pd.Series, z: pd.Series, split: int) -> None:
    """Invariants that must hold whatever the data says. A breach is a bug here.

    These are cheap and they catch the failure mode that matters most in
    research code: a silent arithmetic mistake that produces a plausible number.
    """
    assert np.isfinite(fit.beta), "hedge ratio is not finite"
    assert -1.0 <= fit.correlation <= 1.0, "correlation outside [-1, 1]"
    # OLS residuals are mean zero in-sample by construction.
    assert abs(float(spread.iloc[:split].mean())) < 1e-8, "in-sample spread is not centred"
    if math.isfinite(fit.sigma_eq) and fit.sigma_eq > 0:
        z_is = z.iloc[:split]
        assert 0.2 < float(z_is.std()) < 5.0, "in-sample z-score has an implausible scale"


# ---------------------------------------------------------------- gates
@dataclass
class Verdict:
    half_life_ok: bool
    half_life_oos_ok: bool
    stationary: bool
    edge_ok: bool | None          # None means the gate was never reached
    accepted: bool
    reason: str


def judge(fit: PairFit, *, min_hl: float, max_hl: float, min_edge: float) -> Verdict:
    """Apply the gates in order. Order is the whole point.

    A spread that is not stationary has no equilibrium standard deviation, so
    sigma_eq is meaningless and any edge computed from it is an artefact of the
    drift. Evaluating the edge gate anyway produces a large, convincing and
    entirely spurious number, so it is skipped rather than reported.
    """
    ou_is = fit.regime == REVERTING and math.isfinite(fit.half_life)
    ou_oos = fit.regime_oos == REVERTING and math.isfinite(fit.half_life_oos)
    hl_ok = ou_is and min_hl <= fit.half_life <= max_hl
    oos_ok = ou_oos and min_hl <= fit.half_life_oos <= max_hl
    stationary = hl_ok and oos_ok
    edge_ok = (fit.edge_mult >= min_edge) if stationary else None

    reasons = []
    if fit.regime == EXPLOSIVE:
        reasons.append("in-sample spread is explosive, not mean-reverting")
    elif fit.regime == OSCILLATING:
        reasons.append("in-sample spread reverts faster than one bar, so it is noise "
                       "at this timeframe rather than a tradable spread")
    elif not hl_ok:
        reasons.append(f"in-sample half-life {fit.half_life:.1f} outside {min_hl:g}-{max_hl:g}")
    if fit.regime_oos == EXPLOSIVE:
        reasons.append("out-of-sample spread diverges, relationship did not hold")
    elif fit.regime_oos == OSCILLATING:
        reasons.append("out-of-sample spread reverts faster than one bar")
    elif not oos_ok:
        reasons.append(f"out-of-sample half-life {fit.half_life_oos:.1f} outside bounds")
    if edge_ok is False:
        reasons.append(f"edge {fit.edge_mult:.2f}x below required {min_edge:g}x")

    accepted = stationary and bool(edge_ok)
    return Verdict(hl_ok, oos_ok, stationary, edge_ok, accepted,
                   "; ".join(reasons) if reasons else "all gates passed")


# ---------------------------------------------------------------- svg charts
# ---------------------------------------------------------------- shared report style
#
# The charts, the CSS and the table row used to live here, which made a module named for one
# strategy family the hard dependency of every report in the project. They now live in
# `report_style.py` and are re-exported so the twenty-one existing importers keep working
# unchanged while the reports are consolidated into one.
from report_style import (                                          # noqa: E402,F401
    W, H, PAD_L, PAD_T, PAD_B, PAD_R, PAD_R_LABELS,
    _grid_and_ticks, line_chart, histogram, bar_chart, waterfall_chart,
    state_timeline, CSS, EXTRA_CSS, _row,
)


def price_series(prices: pd.DataFrame):
    """Raw close per leg, or index-100 when the price levels cannot share an axis.

    A shared axis flattens the smaller leg into a straight line once the levels
    differ by more than about four times — EURUSD at 1.16 against USDJPY at 153 —
    so beyond that the chart switches to index-100 and the legend keeps the real
    first and last prices.
    """
    arrays = {c: prices[c].to_numpy(float) for c in prices.columns}
    lo = min(float(np.nanmin(v)) for v in arrays.values())
    hi = max(float(np.nanmax(v)) for v in arrays.values())
    notes = {k: f"{v[np.isfinite(v)][0]:g} → {v[np.isfinite(v)][-1]:g}"
             for k, v in arrays.items()}
    if lo > 0 and hi / lo <= 4.0:
        return arrays, (4 if hi < 20 else 2), "price axis shared by all legs", notes
    scaled = {k: v / v[np.isfinite(v)][0] * 100.0 for k, v in arrays.items()}
    return (scaled, 1,
            "price levels differ too much to share an axis, so indexed to 100 at the first bar",
            notes)


# ---------------------------------------------------------------- html


def build_html(prices, fit: PairFit, verdict: Verdict, args, spread, z, split, trial) -> str:
    a, b = prices.columns
    use_log = args.price == "log"
    px = np.log(prices) if use_log else prices
    rebased = px - px.iloc[0]

    plot_px, px_decimals, px_mode, px_notes = price_series(prices)
    have_z = bool(np.isfinite(z.to_numpy(float)).any())
    z_caption = ("Red = entry, green = exit. Count the crossings: too few means no trades, "
                 "too many means noise.") if have_z else (
        "Not available: the z-score divides by σ_eq, and the in-sample spread is not an "
        "OU process, so σ_eq does not exist. Only the threshold lines are drawn.")
    hist_caption = ("Should look unimodal and roughly symmetric. Bimodal or skewed means the "
                    "level moved — a regime change, not a spread.") if have_z else (
        "Not available for the same reason as the chart above.")

    charts = [
        ("Price, one line per leg",
         line_chart(prices.index, plot_px, split=split, decimals=px_decimals,
                    end_labels=True, legend_notes=px_notes),
         f"Raw close of every leg in the relationship — {px_mode}. This is what the "
         "account actually holds; everything below is derived from it."),
        (f"Legs, rebased {'log ' if use_log else ''}price",
         line_chart(px.index, {a: rebased[a].to_numpy(), b: rebased[b].to_numpy()},
                    split=split, decimals=3, sign=True),
         "Do they track? Visual only — tracking is not cointegration."),
        (f"Spread  =  {'log ' if use_log else ''}{a} − β·"
         f"{'log ' if use_log else ''}{b}",
         line_chart(spread.index, {"spread": spread.to_numpy()},
                    bands=(fit.mu - args.entry_z * fit.sigma_eq,
                           fit.mu + args.entry_z * fit.sigma_eq)
                    if fit.regime == REVERTING and math.isfinite(fit.sigma_eq) else None,
                    hlines=[(fit.mu, "mean")], split=split, decimals=4, sign=True),
         f"Shaded band = ±{args.entry_z:g}σ_eq entry zone. β fitted in-sample "
         "only; the out-of-sample half is what matters."),
        ("Z-score with signal thresholds",
         line_chart(z.index, {"z": z.to_numpy()},
                    hlines=[(args.entry_z, "entry"), (-args.entry_z, "entry"),
                            (args.exit_z, "exit"), (-args.exit_z, "exit"), (0.0, "mean")],
                    split=split, decimals=1, sign=True),
         z_caption),
        ("Spread distribution",
         histogram(z.to_numpy(), marks=[(-args.entry_z, "entry"), (args.entry_z, "entry"),
                                        (0.0, "mean")], bins=args.bins),
         hist_caption),
    ]

    legs = getattr(args, "resolved_legs", None) or [a, b]
    sources = {leg.rsplit("/", 1)[-1].rstrip(")") for leg in legs} if legs != [a, b] else set()
    params = [
        ("pair", f"{a} ~ {b}"),
        ("legs", "  ·  ".join(legs)),
        ("timeframe", args.timeframe + ("  ·  matched on UTC date"
                                        if getattr(args, "date_aligned", False) else "")),
        ("window", f"{px.index[0]:%Y-%m-%d} → {px.index[-1]:%Y-%m-%d}"),
        ("price", args.price),
        ("hedge", f"{args.hedge}, static, {a} on {b}"),
        ("in/out split", f"{args.split:.0%}  ({split} / {len(px)-split} bars)"),
        ("entry / exit z", f"{args.entry_z:g} / {args.exit_z:g}"),
        ("half-life bounds", f"{args.min_half_life:g}–{args.max_half_life:g} bars"),
        ("round-trip cost", f"{args.cost_bps:g} bps"),
        ("min edge multiple", f"{args.min_edge:g}×"),
    ]

    have_ou = fit.regime == REVERTING and math.isfinite(fit.sigma_eq)
    results = [
        _row("hedge ratio β", f"{fit.beta:.4f}", None,
             f"static {args.hedge.upper()}, fitted in-sample only"),
        _row("return correlation", f"{fit.correlation:.3f}", None,
             "context only — not a tradability test"),
        _row("half-life (IS)",
             f"{fit.half_life:.1f} bars" if fit.regime == REVERTING else fit.regime,
             verdict.half_life_ok,
             REGIME_NOTE.get(fit.regime, f"bounds {args.min_half_life:g}-{args.max_half_life:g}")),
        _row("half-life (OOS)",
             f"{fit.half_life_oos:.1f} bars" if fit.regime_oos == REVERTING else fit.regime_oos,
             verdict.half_life_oos_ok,
             "relationship broke out of sample" if fit.regime_oos != REVERTING
             else "stability check"),
        _row("θ (mean reversion)", f"{fit.theta:.4f}" if have_ou else "not estimated", None,
             "OU, AR(1) estimate"),
        _row("σ_eq", f"{fit.sigma_eq*1e4:.1f} bps" if have_ou else "not estimated", None,
             "equilibrium spread sd" if have_ou
             else "undefined: the in-sample spread is not an OU process"),
        _row("expected move",
             f"{fit.expected_move_bps:.1f} bps" if have_ou else "not estimated", None,
             f"z {args.entry_z:g} → {args.exit_z:g}"),
        _row("edge vs cost",
             "not evaluated" if verdict.edge_ok is None else f"{fit.edge_mult:.2f}x",
             verdict.edge_ok,
             "gated: spread is not stationary, so σ_eq is meaningless"
             if verdict.edge_ok is None else f"needs >= {args.min_edge:g}x"),
    ]

    sections = ["<h2>Parameters used</h2><div class='cols'><div><table><tbody>"
                + "".join(f"<tr><td class='k'>{html.escape(k)}</td>"
                          f"<td class='v'>{html.escape(str(v))}</td></tr>"
                          for k, v in params[:5])
                + "</tbody></table></div><div><table><tbody>"
                + "".join(f"<tr><td class='k'>{html.escape(k)}</td>"
                          f"<td class='v'>{html.escape(str(v))}</td></tr>"
                          for k, v in params[5:])
                + "</tbody></table></div></div>",
                "<h2>Results</h2><table><tbody>" + "".join(results) + "</tbody></table>"]
    for title, svg, caption in charts:
        sections.append(f"<h2>{html.escape(title)}</h2>{svg}"
                        f"<div class='cap'>{html.escape(caption)}</div>")

    trial_note = f" · trial #{trial}" if trial else ""
    # Yahoo forex bars carry open and close values outside their own high/low on
    # roughly 1-3% of days. This study reads closes only, so the defect does not
    # touch these numbers, but the report should say so rather than leave the
    # reader to wonder.
    data_note = ("Close prices only, so the known Yahoo forex high/low defect does not "
                 "affect these numbers."
                 if "yahoo" in sources and any("forex" in leg for leg in legs) else
                 "Close prices only.")
    if getattr(args, "date_aligned", False):
        data_note += (" The legs trade on different venues and their daily bars close at "
                      "different times, matched here by UTC date, so the correlation is "
                      "measured across non-simultaneous closes.")
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{a} ~ {b} — pair study</title><style>{CSS}</style></head><body>"
        f"<h1>{a} ~ {b} · pair study</h1>"
        f"<div class='meta'>{args.timeframe} · {px.index[0]:%Y-%m-%d} → "
        f"{px.index[-1]:%Y-%m-%d} · {len(px):,} bars{trial_note} · generated "
        f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC</div>"
        f"<div class='verdict {'pass' if verdict.accepted else ''}'>"
        f"<b>{'ACCEPT' if verdict.accepted else 'REJECT'}</b> — "
        f"{html.escape(verdict.reason)}"
        f"<p>Descriptive statistics only. {data_note} Not a backtest and not a "
        "recommendation — an accepted pair is a candidate for Step 1, nothing more.</p>"
        "</div>" + "".join(sections) + "</body></html>"
    )


# ---------------------------------------------------------------- trial log
def next_trial(path: Path) -> int:
    """Number the run about to happen, from the rows already logged."""
    if not path.exists():
        return 1
    # Counted through the CSV reader rather than by lines, because a quoted
    # field may contain a newline and would otherwise inflate the count.
    with path.open(newline="", encoding="utf-8") as fh:
        return max(sum(1 for _ in csv.reader(fh)) - 1, 0) + 1


def append_trial(path: Path, trial: int, args, fit: PairFit, verdict: Verdict, out: Path) -> int:
    """Append one row and return the trial number.

    Every run is a trial whether or not it is kept, and the Deflated Sharpe
    Ratio in Step 4 needs an honest count of them. Logging happens here so the
    count cannot quietly drift from what was actually run.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "trial": trial,
        "run_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "symbols": "/".join(getattr(args, "resolved_legs", None)
                            or [fit.symbol_a, fit.symbol_b]).replace(" ", ""),
        "timeframe": args.timeframe,
        "start": args.start or "",
        "end": args.end or "",
        "price": args.price,
        "hedge": args.hedge,
        "split": args.split,
        "entry_z": args.entry_z,
        "exit_z": args.exit_z,
        "min_half_life": args.min_half_life,
        "max_half_life": args.max_half_life,
        "cost_bps": args.cost_bps,
        "min_edge": args.min_edge,
        "bars": fit.n_bars,
        "beta": round(fit.beta, 6),
        "correlation": round(fit.correlation, 4),
        "half_life": round(fit.half_life, 2) if math.isfinite(fit.half_life) else fit.regime,
        "half_life_oos": (round(fit.half_life_oos, 2)
                          if math.isfinite(fit.half_life_oos) else fit.regime_oos),
        "regime": fit.regime,
        "regime_oos": fit.regime_oos,
        "sigma_eq_bps": round(fit.sigma_eq * 1e4, 2) if math.isfinite(fit.sigma_eq) else "",
        "edge_mult": round(fit.edge_mult, 3) if verdict.edge_ok is not None else "",
        "verdict": "ACCEPT" if verdict.accepted else "REJECT",
        "reason": verdict.reason,
        "report": out.name,
    }
    fieldnames = list(row)
    write_header = not path.exists()
    if not write_header:
        # Appending rows with a different shape under an old header silently
        # shifts every value into the wrong column, and the corruption is only
        # visible much later. Refuse instead.
        with path.open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh), [])
        if header and header != fieldnames:
            missing = [c for c in fieldnames if c not in header]
            extra = [c for c in header if c not in fieldnames]
            raise UserError(
                f"the trial log at {path} was written by an older version of this script "
                f"(columns differ: added {missing or 'none'}, dropped {extra or 'none'}). "
                "Rename it to keep the history, then run again to start a fresh log.")
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    return trial


# ---------------------------------------------------------------- cli
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pair_report",
        description="Step 0 pair study: fit one relationship and write an HTML report.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sel = p.add_argument_group("selection")
    sel.add_argument("-s", "--symbols", required=True,
                     help="exactly two canonical symbols, comma separated, e.g. AUDUSD,NZDUSD")
    sel.add_argument("-a", "--asset-class", default="forex", metavar="CLASS[,CLASS]",
                     help="one class for both legs, or one per leg in the order given: "
                          f"{', '.join(ASSET_CLASSES)}")
    sel.add_argument("-t", "--timeframe", default="1d",
                 help="bar size as stored: 1m 5m 15m 1h 4h 1d 1w")
    sel.add_argument("--source", default=None, metavar="SRC[,SRC]",
                     help="yahoo or binance, one for both legs or one per leg; "
                          "defaults per asset class")
    sel.add_argument("--start", default=None, help="2019-01-01, 20190101, 2y, 6mo, ...")
    sel.add_argument("--end", default=None, help="same formats as --start; UTC throughout")

    struct = p.add_argument_group("structure - choose once, not per run")
    struct.add_argument("--price", default="log", choices=("log", "raw"),
                    help="log prices make the hedge ratio a ratio of returns")
    struct.add_argument("--hedge", default="ols", choices=("ols",),
                    help="hedge ratio estimator; static OLS of A on B")

    search = p.add_argument_group("searched - every value is a trial")
    search.add_argument("--split", type=float, default=0.70,
                        help="in-sample fraction, 0 < split < 1")
    search.add_argument("--entry-z", type=float, default=2.0,
                    help="z-score at which a trade would open")
    search.add_argument("--exit-z", type=float, default=0.5,
                    help="z-score at which it would close; must be below --entry-z")
    search.add_argument("--min-half-life", type=float, default=2.0, metavar="BARS",
                    help="below this the spread is noise at this timeframe")
    search.add_argument("--max-half-life", type=float, default=30.0, metavar="BARS",
                    help="above this the capital is tied up longer than intended")
    search.add_argument("--min-edge", type=float, default=2.0, metavar="MULT",
                        help="required expected move as a multiple of round-trip cost")

    given = p.add_argument_group("given by reality - from the broker, not a knob")
    given.add_argument("--cost-bps", type=float, default=2.0,
                       help="round-trip cost of both legs, in basis points")

    out = p.add_argument_group("output")
    out.add_argument("-o", "--out", default=None,
                 help="report path; default studies/pairs/pair-A-B-trialNNN.html")
    out.add_argument("--store", default=str(DEFAULT_STORE),
                 help="marketdata parquet store to read")
    out.add_argument("--trials", default=str(DEFAULT_TRIALS), help="trial log CSV")
    out.add_argument("--no-trial-log", action="store_true", help="do not append to the trial log")
    out.add_argument("--bins", type=int, default=45, help="histogram bins")
    out.add_argument("--dry-run", action="store_true",
                     help="fit and print, write no files")
    out.add_argument("--json", action="store_true", help="print the fit as JSON")
    out.add_argument("--open", action="store_true", help="open the report in a browser")
    out.add_argument("-q", "--quiet", action="store_true",
                 help="suppress the progress lines; --json still prints")
    out.add_argument("-v", "--verbose", action="store_true", help="full tracebacks")
    return p


def _per_leg(value: str, symbols: list[str], flag: str) -> list[str]:
    """Expand a flag that may name one value for both legs or one for each."""
    parts = [v.strip().lower() for v in str(value).split(",") if v.strip()]
    if len(parts) == 1:
        return parts * len(symbols)
    if len(parts) == len(symbols):
        return parts
    raise UserError(f"{flag} takes one value or one per symbol, got {len(parts)} "
                    f"for {len(symbols)} symbols")


def load_prices(args) -> pd.DataFrame:
    store = ParquetStore(Path(args.store))
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if len(symbols) != 2:
        raise UserError(f"need exactly two symbols, got {len(symbols)}: {args.symbols}")
    if symbols[0] == symbols[1]:
        raise UserError("the two symbols must differ")

    # A relationship worth studying often crosses asset classes — gold against a
    # commodity currency, say — so each leg carries its own class and source.
    classes = _per_leg(args.asset_class, symbols, "--asset-class")
    for name in classes:
        if name not in ASSET_CLASSES:
            raise UserError(f"unknown asset class {name!r}; expected one of "
                            f"{', '.join(ASSET_CLASSES)}")
    sources = (_per_leg(args.source, symbols, "--source") if args.source
               else [DEFAULT_SOURCE[c] for c in classes])

    frames = {}
    for symbol, asset_class, source in zip(symbols, classes, sources):
        inst = Instrument(symbol, asset_class=asset_class, source=source,
                          timeframe=args.timeframe)
        hint = (f"{symbol} {args.timeframe} is not in the store at {args.store}. "
                f"Download it first: marketdata download -s {symbol} "
                f"-a {asset_class} -t {args.timeframe}")
        try:
            frame = store.read(inst)
        except FileNotFoundError as exc:
            raise UserError(hint) from exc
        # A missing series reads back empty rather than raising, and an empty
        # frame would otherwise vanish silently in the join below.
        if frame is None or frame.empty:
            raise UserError(hint)
        frames[symbol] = frame

    # Recorded for the report and the trial log, which must show what was read.
    args.resolved_legs = [f"{sym} ({cls}/{src})"
                          for sym, cls, src in zip(symbols, classes, sources)]

    # Daily bars from different venues carry different stamps — Yahoo puts forex
    # at 23:00 UTC and futures at 04:00 — so an exact-timestamp join finds no
    # overlap at all. Daily and weekly bars are therefore matched on the UTC
    # date. The two closes are then not simultaneous, which is a real caveat: it
    # biases measured correlation downward and can manufacture apparent lead-lag.
    args.date_aligned = args.timeframe.endswith(("d", "w")) and len(set(classes)) > 1
    if args.date_aligned:
        frames = {k: v.set_axis(v.index.normalize(), axis=0) for k, v in frames.items()}
        frames = {k: v[~v.index.duplicated(keep="last")] for k, v in frames.items()}

    panel = aligned_panel(frames, field="close").dropna()
    if args.start:
        panel = panel[panel.index >= parse_date(args.start)]
    if args.end:
        panel = panel[panel.index <= parse_date(args.end)]
    if args.start and args.end and parse_date(args.start) > parse_date(args.end):
        raise UserError(f"--start {args.start} is after --end {args.end}")
    if len(panel) < 100:
        raise UserError(f"only {len(panel)} overlapping bars after filtering; need at least 100")
    panel = panel[symbols]
    # Log prices are taken throughout, and a non-positive close would silently
    # become NaN or minus infinity somewhere downstream.
    usable = np.isfinite(panel.to_numpy(float)) & (panel.to_numpy(float) > 0)
    if not usable.all():
        bad = [c for i, c in enumerate(panel.columns) if not usable[:, i].all()]
        raise UserError(f"non-positive or non-finite close prices in {', '.join(bad)}; "
                        "the data is unusable")
    return panel


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))

    if not 0.1 <= args.split <= 0.95:
        raise UserError("--split must be between 0.1 and 0.95")
    if args.exit_z >= args.entry_z:
        raise UserError("--exit-z must be below --entry-z")
    if args.exit_z < 0:
        raise UserError("--exit-z must not be negative")
    if args.min_half_life >= args.max_half_life:
        raise UserError("--min-half-life must be below --max-half-life")
    if args.min_half_life <= 0:
        raise UserError("--min-half-life must be positive")
    if args.cost_bps < 0:
        raise UserError("--cost-bps must not be negative")
    if args.min_edge < 0:
        raise UserError("--min-edge must not be negative")
    if not 5 <= args.bins <= 200:
        raise UserError("--bins must be between 5 and 200")

    prices = load_prices(args)
    split = int(len(prices) * args.split)
    if min(split, len(prices) - split) < 50:
        raise UserError(f"--split {args.split} leaves too few bars on one side "
                        f"({split} / {len(prices)-split}); need 50 each")

    fit = fit_pair(prices, split=split, use_log=args.price == "log",
                   entry_z=args.entry_z, exit_z=args.exit_z, cost_bps=args.cost_bps)
    verdict = judge(fit, min_hl=args.min_half_life, max_hl=args.max_half_life,
                    min_edge=args.min_edge)

    px = np.log(prices) if args.price == "log" else prices
    a, b = prices.columns
    spread = px[a] - fit.beta * px[b] - fit.alpha
    # Without an OU fit there is no equilibrium standard deviation to divide by,
    # so the z-score genuinely does not exist and is left as NaN rather than
    # substituted with the sample standard deviation, which would look the same
    # on the chart while meaning something else entirely.
    z = ((spread - fit.mu) / fit.sigma_eq
         if fit.regime == REVERTING and math.isfinite(fit.sigma_eq) and fit.sigma_eq > 0
         else spread * np.nan)
    sanity_checks(fit, spread, z, split)

    log(f"{a} ~ {b}  {args.timeframe}  {prices.index[0]:%Y-%m-%d} -> "
        f"{prices.index[-1]:%Y-%m-%d}  {len(prices):,} bars")
    def show_hl(value, regime):
        return f"{value:.1f}" if regime == REVERTING and math.isfinite(value) else regime

    log(f"  beta {fit.beta:.4f}   corr {fit.correlation:.3f}   "
        f"half-life IS {show_hl(fit.half_life, fit.regime)}   "
        f"OOS {show_hl(fit.half_life_oos, fit.regime_oos)}")
    log(f"  {'ACCEPT' if verdict.accepted else 'REJECT'} - {verdict.reason}")

    if args.json:
        print(json.dumps({"fit": asdict(fit), "verdict": asdict(verdict)},
                         indent=2, default=str))

    if args.dry_run:
        log("  dry run: nothing written")
        return 0 if verdict.accepted else 3

    # The report filename carries the trial number so the row in the trial log
    # always points at the report that row describes. Re-running the same pair
    # with different parameters otherwise silently overwrites the evidence for
    # the earlier trial, which defeats the point of keeping a log.
    trial = 0 if args.no_trial_log else next_trial(Path(args.trials))
    if args.out:
        out = Path(args.out)
    elif trial:
        out = DEFAULT_REPORTS / f"pair-{a}-{b}-trial{trial:03d}.html"
    else:
        out = DEFAULT_REPORTS / f"pair-{a}-{b}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    if trial:
        append_trial(Path(args.trials), trial, args, fit, verdict, out)
    out.write_text(build_html(prices, fit, verdict, args, spread, z, split, trial),
                   encoding="utf-8")
    log(f"  wrote {out.resolve()}  ({out.stat().st_size/1024:.1f} KB)")
    if trial:
        log(f"  trial #{trial} logged to {Path(args.trials).resolve()}")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0 if verdict.accepted else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001
        if "-v" in sys.argv or "--verbose" in sys.argv:
            raise
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
