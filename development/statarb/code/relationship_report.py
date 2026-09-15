"""Step 2 report — all three gates on one page.

`cointegration.py`, `hedge.py` and `health.py` each answer their question on the
command line and leave a row in a log. This runs all three against one pair and
writes the evidence out as a single self-contained HTML file, so a verdict can be
looked at rather than taken on trust.

    python relationship_report.py -s USDNOK,USDZAR
    python relationship_report.py -s BTC-USDT,ETH-USDT -a crypto --open

Exit codes: 0 every gate passed, 3 at least one failed, 2 usage error.
"""
from __future__ import annotations

import argparse
import html
import math
import sys
import warnings
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import paths

paths.ensure_code_importable()
paths.ensure_marketdata_importable()

import cointegration as ci                                        # noqa: E402
import health as hm                                               # noqa: E402
import hedge as hg                                                # noqa: E402
import pair_report as pr                                          # noqa: E402

UserError = pr.UserError
DEFAULT_REPORTS = paths.STUDIES / "relationships"

EXTRA_CSS = """
rect.state-healthy{fill:var(--ok);opacity:.75}
rect.state-degraded{fill:var(--b);opacity:.8}
rect.state-broken{fill:var(--no);opacity:.7}
text.barlab{fill:var(--muted);font-size:10px;font-family:ui-monospace,Menlo,monospace}
.big{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px}
.big div{flex:1 1 150px;border:1px solid var(--line);border-radius:6px;padding:8px 12px;
background:var(--zebra)}
.big b{display:block;font-size:19px;font-family:ui-monospace,Menlo,monospace}
.big span{color:var(--muted);font-size:11px}
.big .pass b{color:var(--ok)}.big .fail b{color:var(--no)}
"""


def state_timeline(index, checks) -> str:
    """One coloured block per monitoring cycle, in time order."""
    width, height, pad_l = 900, 74, 54
    if not checks:
        return ""
    first, last = checks[0].bar, checks[-1].bar
    span = max(last - first, 1)
    body = ["<text class='tick' x='14' y='14'>HEALTH STATE, ONE BLOCK PER CYCLE</text>"]
    for i, c in enumerate(checks):
        x = pad_l + (c.bar - first) / span * (width - pad_l - 14)
        w = max((width - pad_l - 14) / len(checks), 1.2)
        body.append(f"<rect class='state-{c.state}' x='{x:.1f}' y='22' "
                    f"width='{w:.1f}' height='26'/>")
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        i = int(frac * (len(checks) - 1))
        x = pad_l + (checks[i].bar - first) / span * (width - pad_l - 14)
        body.append(f"<text class='tick' x='{x:.1f}' y='62' text-anchor='middle'>"
                    f"{checks[i].when[:7]}</text>")
    return (f"<div class='chart'><svg viewBox='0 0 {width} {height}' "
            f"preserveAspectRatio='none'>{''.join(body)}</svg>"
            "<div class='legend'>green healthy · amber degraded · red broken</div></div>")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="relationship_report",
                                description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sel = p.add_argument_group("selection")
    sel.add_argument("-s", "--symbols", required=True)
    sel.add_argument("-a", "--asset-class", default="forex")
    sel.add_argument("-t", "--timeframe", default="1d")
    sel.add_argument("--source", default=None)
    sel.add_argument("--start", default=None)
    sel.add_argument("--end", default=None)

    struct = p.add_argument_group("structure")
    struct.add_argument("--price", default="log", choices=("log", "raw"))
    struct.add_argument("--lags", default="aic")
    struct.add_argument("--adf-trend", default="c", choices=("n", "c", "ct"))
    struct.add_argument("--eg-trend", default="c", choices=("n", "c", "ct"))
    struct.add_argument("--test", default="all")
    struct.add_argument("--det-order", type=int, default=0)
    struct.add_argument("--johansen-lags", type=int, default=1)

    search = p.add_argument_group("searched - every value is a trial")
    search.add_argument("--split", type=float, default=0.70)
    search.add_argument("--level", type=float, default=0.05)
    search.add_argument("--both-directions", action="store_true", default=True)
    search.add_argument("--require-oos", action=argparse.BooleanOptionalAction,
                        default=True)
    search.add_argument("--window", type=int, default=250)
    search.add_argument("--kalman-delta", type=float, default=1e-4)
    search.add_argument("--kalman-obs-var", type=float, default=None)
    search.add_argument("--min-abs-beta", type=float, default=0.10)
    search.add_argument("--max-negative-share", type=float, default=0.10)
    search.add_argument("--max-net-exposure", type=float, default=0.35)
    search.add_argument("--lookback", type=int, default=500)
    search.add_argument("--recheck-every", type=int, default=10)
    search.add_argument("--max-pvalue", type=float, default=0.05)
    search.add_argument("--degraded-pvalue", type=float, default=0.20)
    search.add_argument("--min-half-life", type=float, default=2.0)
    search.add_argument("--max-half-life", type=float, default=60.0)
    search.add_argument("--break-z", type=float, default=4.0)
    search.add_argument("--max-beta-drift", type=float, default=3.0)
    search.add_argument("--min-healthy-share", type=float, default=0.10,
                        help="share of cycles the monitor must call healthy. Lowered from "
                             "0.40, which rejected every pair that survived the other "
                             "gates and so ranked nothing. 0.10 separates the four "
                             "candidates measured so far — the two that made money sit at "
                             "17%% and 18%%, the two that lost at 2%% and 3%% — but four "
                             "points calibrate nothing, so treat this as provisional")

    out = p.add_argument_group("output")
    out.add_argument("-o", "--out", default=None)
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--open", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    out.add_argument("--hedge", default="ols", help=argparse.SUPPRESS)
    out.add_argument("--entry-z", type=float, default=2.0, help=argparse.SUPPRESS)
    out.add_argument("--exit-z", type=float, default=0.5, help=argparse.SUPPRESS)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))
    warnings.filterwarnings("ignore")

    px = pr.load_prices(args)
    a, b = px.columns
    split = int(len(px) * args.split)
    lp = np.log(px) if args.price == "log" else px
    y, x = lp[a].to_numpy(float), lp[b].to_numpy(float)

    # ---- gate 1, cointegration
    results, beta = ci.run_tests(px, args)
    cointegrated, reason = ci.verdict_line(results, args.level)
    oos, oos_ok = None, None
    if split < len(px) - 60:
        oos, _ = ci.run_tests(px.iloc[split:], args)
        oos_ok, oos_reason = ci.verdict_line(oos, args.level)
    gate_coint = cointegrated and (oos_ok is not False or not args.require_oos)

    # ---- gate 2, hedge quality
    estimates = [
        hg.evaluate("static", hg.static_beta(y, x, split), y, x, split),
        hg.evaluate("rolling", hg.rolling_beta(y, x, args.window), y, x, split),
        hg.evaluate("kalman", hg.kalman_beta(y, x, delta=args.kalman_delta,
                                             obs_var=args.kalman_obs_var,
                                             fit_through=split), y, x, split),
    ]
    gate_hedge = any(e.usable(args.min_abs_beta, args.max_negative_share,
                              args.max_net_exposure)
                     for e in estimates)

    # ---- gate 3, health
    thresholds = dict(max_pvalue=args.max_pvalue, degraded_pvalue=args.degraded_pvalue,
                      min_half_life=args.min_half_life, max_half_life=args.max_half_life,
                      break_z=args.break_z, max_beta_drift=args.max_beta_drift)
    checks = hm.replay(px, lookback=args.lookback, every=args.recheck_every, **thresholds)
    hstats = hm.summarise(checks)
    gate_health = hstats.get("healthy", 0.0) >= args.min_healthy_share

    passed = gate_coint and gate_hedge and gate_health
    fails = []
    if not gate_coint:
        fails.append("not cointegrated" if not cointegrated
                     else "cointegrated in sample only")
    if not gate_hedge:
        fails.append("no estimator produces a usable hedge")
    if not gate_health:
        fails.append(f"healthy on only {hstats.get('healthy', 0):.0%} of cycles, "
                     f"below {args.min_healthy_share:.0%}")

    log(f"{a} ~ {b}   {args.timeframe}   {len(px):,} bars")
    log(f"  cointegration {'PASS' if gate_coint else 'FAIL'}   "
        f"hedge {'PASS' if gate_hedge else 'FAIL'}   "
        f"health {'PASS' if gate_health else 'FAIL'}")

    # ---- charts
    spread = y - beta * x - float(np.mean(y[:split] - beta * x[:split]))
    sd = float(np.std(spread[:split], ddof=1)) or 1e-12
    pvals = np.full(len(px), np.nan)
    hls = np.full(len(px), np.nan)
    for c in checks:
        pvals[c.bar] = c.pvalue
        hls[c.bar] = c.half_life if math.isfinite(c.half_life) else np.nan
    pseries = pd.Series(pvals, index=px.index).ffill().to_numpy()
    beta_paths = {e.method: np.where(np.isfinite(e.beta_path), e.beta_path, np.nan)
                  for e in estimates}

    charts = [
        ("Legs, rebased", pr.line_chart(px.index, {a: (lp[a] - lp[a].iloc[0]).to_numpy(),
                                                   b: (lp[b] - lp[b].iloc[0]).to_numpy()},
                                        split=split, decimals=3, sign=True),
         "Tracking is not cointegration; this is context, not evidence."),
        ("Spread and its equilibrium band",
         pr.line_chart(px.index, {"spread": spread}, bands=(-2 * sd, 2 * sd),
                       hlines=[(0.0, "mean")], split=split, decimals=4, sign=True),
         "Built with the full-sample hedge ratio, centred on the in-sample mean."),
        ("Hedge ratio by estimator",
         pr.line_chart(px.index, beta_paths, split=split, decimals=3, sign=True),
         f"A ratio at or below zero is not a hedge. The gate allows "
         f"{args.max_negative_share:.0%} of the sample below zero."),
        ("Cointegration p-value through time",
         pr.line_chart(px.index, {"p-value": pseries},
                       hlines=[(args.max_pvalue, "exit"),
                               (args.degraded_pvalue, "entry")],
                       split=split, decimals=3),
         f"Green {args.max_pvalue:g} is the healthy line, red {args.degraded_pvalue:g} "
         "the broken line. Held flat between monitoring cycles."),
        ("Health state", state_timeline(px.index, checks),
         "What the monitor would have said at each cycle, judged only on bars available "
         "then."),
    ]

    tiles = "".join(
        f"<div class='{c}'><b>{v}</b><span>{k}</span></div>" for k, v, c in [
            ("cointegration", "PASS" if gate_coint else "FAIL",
             "pass" if gate_coint else "fail"),
            ("hedge quality", "PASS" if gate_hedge else "FAIL",
             "pass" if gate_hedge else "fail"),
            ("health", "PASS" if gate_health else "FAIL",
             "pass" if gate_health else "fail"),
            ("Engle-Granger p", f"{next((r.pvalue for r in results if r.name == 'Engle-Granger'), float('nan')):.3f}", ""),
            ("healthy cycles", f"{hstats.get('healthy', 0):.0%}", ""),
            ("hedge ratio", f"{beta:+.3f}", ""),
        ])

    def test_rows(rs):
        out = []
        for r in rs:
            pv = "—" if r.pvalue is None else f"{r.pvalue:.4f}"
            crit = r.critical.get("5%", r.critical.get("5.0%"))
            out.append(pr._row(r.name, f"{r.statistic:.3f}   p {pv}", r.reject,
                               (f"5% critical {crit:.3f}. " if crit else "") + r.note))
        return "".join(out)

    hedge_rows = "".join(
        pr._row(e.method,
                f"{e.beta_final:+.3f}   range {e.beta_min:+.3f} to {e.beta_max:+.3f}",
                e.usable(args.min_abs_beta, args.max_negative_share,
                         args.max_net_exposure),
                f"at or below zero {e.negative_share:.0%} of the time, "
                f"half-life "
                + (f"{e.half_life_is:.1f}" if math.isfinite(e.half_life_is) else "none")
                + " in sample, "
                + (f"{e.half_life_oos:.1f}" if math.isfinite(e.half_life_oos) else "none")
                + " out")
        for e in estimates)

    health_rows = "".join(pr._row(k, v, ok, note) for k, v, ok, note in [
        ("healthy", f"{hstats.get('healthy', 0):.0%} of {hstats.get('checks', 0)} cycles",
         gate_health, f"gate needs {args.min_healthy_share:.0%}"),
        ("degraded", f"{hstats.get('degraded', 0):.0%}", None, "no new entries"),
        ("broken", f"{hstats.get('broken', 0):.0%}", None, "forced flat"),
        ("state changes", str(hstats.get("transitions", 0)), None,
         "a monitor that never changes state is not monitoring"),
        ("what fired", ", ".join(f"{k} x{v}" for k, v in
                                 sorted(hstats.get("triggers", {}).items(),
                                        key=lambda kv: -kv[1])) or "nothing", None,
         "one check firing every time means the others are idle"),
        ("state now", hstats.get("final", "unknown"), None, ""),
    ])

    sections = [f"<div class='big'>{tiles}</div>",
                "<h2>Gate 1 — cointegration, full sample</h2><table><tbody>"
                + test_rows(results) + "</tbody></table>"]
    if oos:
        sections.append("<h2>Gate 1 — cointegration, held-out tail</h2><table><tbody>"
                        + test_rows(oos) + "</tbody></table>"
                        + "<div class='cap'>"
                        + html.escape("The tail is shorter, so the test has less power "
                                      "here: a failure may be weakness rather than "
                                      "absence. It still decides, because a relationship "
                                      "that holds only where it was fitted is the failure "
                                      "this project has already paid for.")
                        + "</div>")
    sections.append("<h2>Gate 2 — hedge quality</h2><table><tbody>" + hedge_rows
                    + "</tbody></table>")
    sections.append("<h2>Gate 3 — health through time</h2><table><tbody>" + health_rows
                    + "</tbody></table>")
    for title, svg, cap in charts:
        if svg:
            sections.append(f"<h2>{html.escape(title)}</h2>{svg}"
                            f"<div class='cap'>{html.escape(cap)}</div>")

    summary = html.escape("; ".join(fails)) if fails else (
        "cointegrated in and out of sample, a usable hedge, and healthy often enough "
        "to trade")
    doc = ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
           "<meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>{a} ~ {b} — relationship</title>"
           f"<style>{pr.CSS}{EXTRA_CSS}</style></head><body>"
           f"<h1>{a} ~ {b} · relationship</h1>"
           f"<div class='meta'>{args.timeframe} · {px.index[0]:%Y-%m-%d} to "
           f"{px.index[-1]:%Y-%m-%d} · {len(px):,} bars · generated "
           f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC</div>"
           f"<div class='verdict {'pass' if passed else ''}'>"
           f"<b>{'ALL GATES PASSED' if passed else 'REJECTED'}</b> — "
           f"{summary}"
           "<p>Descriptive statistics on close prices. Passing here makes a pair a "
           "candidate for a backtest, not a strategy.</p></div>"
           + "".join(sections) + "</body></html>")

    out = Path(args.out) if args.out else DEFAULT_REPORTS / f"relationship-{a}-{b}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    log(f"  wrote {out.resolve()}  ({out.stat().st_size/1024:.1f} KB)")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0 if passed else 3


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
