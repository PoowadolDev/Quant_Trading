"""Step 3 report — all four decisions on one page.

`outcomes.py`, `thresholds.py` and `sizing.py` each answer their question on the
command line and leave a row in a log. This runs them against one pair and
writes the evidence out as a single self-contained HTML file, the way
`pair_report.py` does for Step 0 and `relationship_report.py` for Step 2, so a
verdict can be looked at rather than taken on trust.

Three questions, and a pair has to survive all of them:

    does the prediction hold?   The expected move the pipeline has used since
                                Step 0 over-predicts realised gross per trade by
                                10x to 68x on every pair tested so far, and has
                                the sign wrong on half of them. If it fails here
                                too, no edge computed from it describes this
                                trade.

    does any threshold pay?     The lowest entry threshold whose own trades
                                earned their own cost back, read off replayed
                                trades rather than off the formula.

    is any size justified?      Growth-optimal leverage on a mean discounted by
                                the uncertainty in its own estimate. A mean that
                                the sample does not establish as positive gets
                                no size at all.

    python signal_report.py -s XLP,XLB -a index --broker etf
    python signal_report.py -s ALL,TRV -a equity --broker equity --start 1996-01-01
    python signal_report.py -s SPY,DIA -a index --broker etf --open

Exit codes: 0 every question answered yes, 3 at least one no, 2 usage error.
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

import paths

paths.ensure_code_importable()
paths.ensure_marketdata_importable()

import backtest as bt                                             # noqa: E402
import costs as cost_model                                        # noqa: E402
import outcomes as oc                                             # noqa: E402
import pair_report as pr                                          # noqa: E402
import sizing as sz                                               # noqa: E402
import strategy as sig                                            # noqa: E402
import thresholds as th                                           # noqa: E402

UserError = pr.UserError
DEFAULT_REPORTS = paths.STUDIES / "signals"

EXTRA_CSS = """
.big{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px}
.big div{flex:1 1 150px;border:1px solid var(--line);border-radius:6px;padding:8px 12px;
background:var(--zebra)}
.big b{display:block;font-size:19px;font-family:ui-monospace,Menlo,monospace}
.big span{color:var(--muted);font-size:11px}
.big .pass b{color:var(--ok)}.big .fail b{color:var(--no)}
table.grid{width:100%;border-collapse:collapse;margin:4px 0 2px}
table.grid th{text-align:right;font-weight:600;font-size:11px;color:var(--muted);
padding:4px 8px;border-bottom:1px solid var(--line)}
table.grid th:first-child{text-align:left}
table.grid td{text-align:right;padding:4px 8px;font-family:ui-monospace,Menlo,monospace;
font-size:12px;border-bottom:1px solid var(--line)}
table.grid td:first-child{text-align:left}
table.grid tr:nth-child(even) td{background:var(--zebra)}
td.yes{color:var(--ok);font-weight:600}td.no{color:var(--no);font-weight:600}
"""


def bar_chart(labels, series: dict, *, height: int = 150, decimals: int = 0,
              zero_line: bool = True) -> str:
    """Grouped bars over a handful of categories, drawn as plain SVG.

    The x axis here is a short list of thresholds rather than time, so the
    line chart in `pair_report` would imply a continuity between cells that
    does not exist: nothing happens at z = 1.7 because nothing was run there.
    """
    values = np.concatenate([np.asarray(v, float) for v in series.values()])
    values = values[np.isfinite(values)]
    if not values.size:
        return ""
    low, high = float(values.min()), float(values.max())
    if zero_line:
        low, high = min(low, 0.0), max(high, 0.0)
    if high == low:
        high = low + 1.0
    pad = (high - low) * 0.08
    low, high = low - pad, high + pad

    w, pad_l, pad_r, pad_t, pad_b = pr.W, 62, 18, 12, 30
    plot_w = w - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n_groups = len(labels)
    n_series = len(series)
    group_w = plot_w / max(1, n_groups)
    bar_w = group_w / (n_series + 0.6)

    def y_of(v: float) -> float:
        return pad_t + (high - v) / (high - low) * plot_h

    body = [f"<rect x='{pad_l}' y='{pad_t}' width='{plot_w:.1f}' height='{plot_h:.1f}' "
            "class='plot'/>"]
    if low <= 0 <= high:
        body.append(f"<line x1='{pad_l}' x2='{pad_l + plot_w:.1f}' y1='{y_of(0):.1f}' "
                    f"y2='{y_of(0):.1f}' class='axis'/>")
    for si, (name, vals) in enumerate(series.items()):
        for gi, v in enumerate(np.asarray(vals, float)):
            if not math.isfinite(v):
                continue
            x = pad_l + gi * group_w + 0.3 * bar_w + si * bar_w
            top, bottom = y_of(max(v, 0.0)), y_of(min(v, 0.0))
            body.append(f"<rect x='{x:.1f}' y='{top:.1f}' width='{bar_w * 0.86:.1f}' "
                        f"height='{max(1.0, bottom - top):.1f}' class='s{si}' "
                        f"opacity='0.85'><title>{html.escape(name)} at "
                        f"{labels[gi]}: {v:,.{decimals}f}</title></rect>")
    for gi, label in enumerate(labels):
        x = pad_l + (gi + 0.5) * group_w
        body.append(f"<text x='{x:.1f}' y='{height - 10}' class='tick' "
                    f"text-anchor='middle'>{html.escape(str(label))}</text>")
    for v in (high, (high + low) / 2, low):
        body.append(f"<text x='{pad_l - 6}' y='{y_of(v) + 4:.1f}' class='tick' "
                    f"text-anchor='end'>{v:,.{decimals}f}</text>")
    legend = " ".join(
        f"<span class='lg s{i}'>{html.escape(name)}</span>"
        for i, name in enumerate(series))
    return (f"<div class='chart'><svg viewBox='0 0 {w} {height}' width='100%' "
            f"height='{height}' role='img'>{''.join(body)}</svg>"
            f"<div class='legend'>{legend}</div></div>")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="signal_report",
                                description=__doc__.splitlines()[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sel = p.add_argument_group("selection")
    sel.add_argument("-s", "--symbols", required=True)
    sel.add_argument("-a", "--asset-class", default="forex")
    sel.add_argument("-t", "--timeframe", default="1d")
    sel.add_argument("--source", default=None)
    sel.add_argument("--start", default=None)
    sel.add_argument("--end", default=None)

    struct = p.add_argument_group("structure - choose once")
    struct.add_argument("--price", default="log", choices=("log", "raw"))
    struct.add_argument("--hedge-source", default="rolling",
                        choices=("static", "rolling"))
    struct.add_argument("--fit-window", type=int, default=250)
    struct.add_argument("--rehedge-every", type=int, default=5)

    search = p.add_argument_group("searched - every value is a trial")
    search.add_argument("--entry-grid", default="1.0,1.5,2.0,2.5,3.0")
    search.add_argument("--entry-z", type=float, default=2.0,
                        help="the threshold the outcome breakdown is shown for")
    search.add_argument("--exit-z", type=float, default=0.5)
    search.add_argument("--stop-z", type=float, default=4.0)
    search.add_argument("--max-holding-bars", type=int, default=20)
    search.add_argument("--min-edge", type=float, default=2.0)
    search.add_argument("--min-trades", type=int, default=20)
    search.add_argument("--max-overstatement", type=float, default=3.0)

    size = p.add_argument_group("sizing")
    size.add_argument("--equity", type=float, default=100_000.0)
    size.add_argument("--confidence", type=float, default=1.0)
    size.add_argument("--max-leverage", type=float, default=1.0)

    given = p.add_argument_group("given by reality")
    given.add_argument("--broker", required=True)
    given.add_argument("--costs-dir", default=str(cost_model.DEFAULT_COSTS))
    given.add_argument("--bars-per-night", type=float, default=None,
                       help="nights of financing per bar; defaults to the asset "
                            "class and timeframe")
    given.add_argument("--lag", type=int, default=1)
    given.add_argument("--warmup", type=int, default=260)

    out = p.add_argument_group("output")
    out.add_argument("-o", "--out", default=None)
    out.add_argument("--store", default=str(paths.STORE))
    out.add_argument("--open", dest="open_browser", action="store_true")
    out.add_argument("-q", "--quiet", action="store_true")
    out.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None) -> int:
    warnings.filterwarnings("ignore")
    args = build_parser().parse_args(argv)
    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a))

    profile_path = Path(args.costs_dir) / f"{args.broker}.json"
    profile = cost_model.load_profile(profile_path)
    if not profile:
        raise UserError(f"no cost profile at {profile_path}; run costs.py add first")
    estimated = any(c.estimated for c in profile.values())

    if args.equity <= 0:
        raise UserError(f"--equity {args.equity:g} is not an account.")
    if args.confidence < 0:
        raise UserError(f"--confidence {args.confidence:g} would add the "
                        "uncertainty back on instead of taking it off.")
    if args.max_leverage < 0:
        raise UserError(f"--max-leverage {args.max_leverage:g} is not a cap.")
    if args.min_edge <= 0:
        raise UserError(f"--min-edge {args.min_edge:g} would accept a trade that "
                        "earns less than it costs.")
    if args.min_trades < 1:
        raise UserError(f"--min-trades {args.min_trades} would let a threshold "
                        "with no trades set the floor.")
    if args.max_overstatement <= 0:
        raise UserError(f"--max-overstatement {args.max_overstatement:g} can never "
                        "be met; it is a multiple of the realised mean.")
    grid_levels = oc.parse_levels(args.entry_grid, "--entry-grid")

    px = pr.load_prices(args)
    if args.bars_per_night is None:
        first_class = args.asset_class.split(",")[0].strip().lower()
        args.bars_per_night = cost_model.nights_per_bar(first_class, args.timeframe)
    if args.warmup >= len(px):
        raise UserError(f"--warmup {args.warmup} leaves no bars to trade")
    a, b = px.columns

    try:
        base = sig.SignalParams(
            entry_z=args.entry_z, exit_z=args.exit_z, stop_z=args.stop_z,
            max_holding_bars=args.max_holding_bars,
            hedge_source=args.hedge_source, fit_window=args.fit_window,
            rehedge_every=args.rehedge_every, use_log=args.price == "log")
    except ValueError as exc:
        raise UserError(str(exc)) from exc

    sigma, half_life = oc.traded_sigma(px, base)
    if not (math.isfinite(sigma) and sigma > 0):
        raise UserError(f"{a}~{b} has no usable OU fit on a {args.fit_window}-bar "
                        "window, so there is nothing here to decide about")

    # ---- the strategy as configured, and everything measured from its trades
    result = bt.run_backtest(px, profile, base, warmup=args.warmup,
                             bars_per_night=args.bars_per_night, lag=args.lag)
    focus = oc.compare(px, profile, base, static_sigma=sigma,
                       static_half_life=half_life, warmup=args.warmup,
                       bars_per_night=args.bars_per_night, lag=args.lag)
    m = focus.outcomes

    # ---- the grid, from which the operative floor is read
    beta = 0.0
    for t in range(len(px) - 1, args.fit_window - 1, -1):
        fit = sig.fit_relationship(px.iloc[t - args.fit_window:t],
                                   use_log=base.use_log, at=t)
        if fit is not None:
            beta = fit.beta
            break
    direction = bt.cheaper_direction(profile, a, b, beta)
    carry_night = -bt.carry_per_night_bps(profile, a, b, direction, beta)
    transaction = bt.round_trip_bps(profile, a, b, direction, beta)
    grid = th.measure_grid(px, profile, base, grid_levels,
                           transaction_bps=transaction,
                           carry_per_night_bps=carry_night,
                           bars_per_night=args.bars_per_night,
                           min_edge=args.min_edge, warmup=args.warmup,
                           lag=args.lag, static_sigma=sigma)
    floor = th.measured_floor(grid, args.min_trades)
    modelled = th.break_even_z(args.exit_z, transaction, carry_night,
                               half_life * args.bars_per_night, sigma * 1e4,
                               args.min_edge)

    # ---- size, on net returns, which is the only honest basis
    try:
        size = sz.size_from_trades(f"{a}~{b}", [t.net_bps for t in result.trades],
                                   confidence=args.confidence,
                                   max_leverage=args.max_leverage,
                                   equity=args.equity)
    except UserError:
        size = None

    gate_prediction = (math.isfinite(focus.overstatement)
                       and focus.overstatement <= args.max_overstatement)
    gate_threshold = math.isfinite(floor)
    gate_size = bool(size and size.justified)
    passed = gate_prediction and gate_threshold and gate_size

    fails = []
    if not gate_prediction:
        fails.append("the expected move does not describe these trades"
                     if math.isfinite(focus.overstatement)
                     else "the expected move has the wrong sign")
    if not gate_threshold:
        fails.append("no entry threshold earned its own cost back")
    if not gate_size:
        fails.append(size.reason() if size else "too few trades to size on")

    # ---------------------------------------------------------------- page
    over = ("wrong sign" if not math.isfinite(focus.overstatement)
            else f"{focus.overstatement:.1f}x")
    tiles = "".join(
        f"<div class='{c}'><b>{html.escape(v)}</b><span>{html.escape(k)}</span></div>"
        for k, v, c in [
            ("prediction", "HOLDS" if gate_prediction else "FAILS",
             "pass" if gate_prediction else "fail"),
            ("a threshold pays", "YES" if gate_threshold else "NO",
             "pass" if gate_threshold else "fail"),
            ("size justified", "YES" if gate_size else "NO",
             "pass" if gate_size else "fail"),
            ("reached the exit", f"{m.completion_rate:.0%}", ""),
            ("predicted over realised", over, ""),
            ("leverage", f"{size.capped_leverage:.2f}" if size else "—", ""),
        ])

    cat_rows = "".join(
        pr._row(name, f"{m.by_category.get(key, 0)} trades",
                None,
                f"{m.gross_by_category.get(key, 0.0):+,.1f} bps gross in total, "
                f"{(m.by_category.get(key, 0) / m.trades if m.trades else 0):.0%} "
                "of all trades" + note)
        for name, key, note in [
            ("reached the exit", oc.TARGET,
             ". The only ending the expected-move formula describes"),
            ("hit the stop", oc.STOP,
             ". The relationship was presumed broken while the position was open"),
            ("ran out of holding period", oc.TIME,
             ". Closed on the clock, at whatever the spread was worth"),
            ("ended with the sample", oc.SAMPLE_END,
             ". Closed at the last price so no basis point goes unattributed"),
            ("other", oc.OTHER, ""),
        ] if m.by_category.get(key, 0) or key in (oc.TARGET, oc.STOP, oc.TIME))

    outcome_rows = "".join(pr._row(k, v, ok, note) for k, v, ok, note in [
        ("trades", f"{m.trades}", None, f"at entry z {args.entry_z:g}"),
        ("completion rate", f"{m.completion_rate:.0%}", None,
         "the share the expected-move formula silently assumes is 100%"),
        ("average win", f"{m.avg_win_bps:+,.1f} bps", None,
         f"{m.wins} winners"),
        ("average loss", f"{m.avg_loss_bps:+,.1f} bps", None,
         f"{m.losses} losers"),
        ("win to loss", f"{m.win_loss_ratio:.2f}", None,
         "below one means the losers are larger than the winners"),
        ("spread scale, as the reports fit it", f"{focus.sigma_static_bps:,.0f} bps",
         None, "one OU process over the whole in-sample half"),
        ("spread scale, as the strategy trades it", f"{focus.sigma_traded_bps:,.0f} bps",
         None, f"refit every {args.rehedge_every} bars on {args.fit_window}"),
        ("predicted move", f"{focus.predicted_traded_bps:,.0f} bps", None,
         "from the traded scale, which is the generous version"),
        ("realised, per trade", f"{focus.realised_bps:+,.1f} bps", gate_prediction,
         f"the prediction is {over} the result"),
    ])

    def grid_table(rows):
        head = ("<tr><th>entry z</th><th>trades</th><th>reached exit</th>"
                "<th>bars held</th><th>predicted</th><th>realised</th>"
                "<th>cost</th><th>edge</th><th>pays?</th></tr>")
        body = []
        for r in rows:
            edge = "—" if not math.isfinite(r.edge) else f"{r.edge:,.2f}"
            body.append(
                f"<tr><td>{r.entry_z:g}</td><td>{r.trades}</td>"
                f"<td>{r.completion_rate:.0%}</td><td>{r.bars_held:.1f}</td>"
                f"<td>{r.predicted_bps:,.0f}</td><td>{r.realised_bps:+,.1f}</td>"
                f"<td>{r.cost_bps:,.1f}</td><td>{edge}</td>"
                f"<td class='{'yes' if r.clears else 'no'}'>"
                f"{'yes' if r.clears else 'no'}</td></tr>")
        return f"<table class='grid'><thead>{head}</thead><tbody>" \
               + "".join(body) + "</tbody></table>"

    threshold_rows = "".join(pr._row(k, v, ok, note) for k, v, ok, note in [
        ("direction priced", "long spread" if direction > 0 else "short spread", None,
         "the cheaper of the two to finance"),
        ("round trip", f"{transaction:,.1f} bps", None, "in and out, both legs"),
        ("financing", f"{carry_night:,.3f} bps per night", None,
         f"charged {args.bars_per_night:g} nights per bar"),
        ("half-life, as traded", f"{half_life:,.1f} bars", None,
         f"{focus.half_life_static:,.1f} as the report fits it"
         if math.isfinite(focus.half_life_static) else "no static fit"),
        ("modelled floor", f"z {modelled:.2f}", None,
         "charges financing for the half-life and credits a move the trade only "
         "collects if it completes"),
        ("measured floor", f"z {floor:.2f}" if gate_threshold else "none",
         gate_threshold,
         f"lowest threshold whose own trades earned {args.min_edge:g} times their own "
         f"cost, with at least {args.min_trades} trades"),
    ])

    size_rows = "" if size is None else "".join(
        pr._row(k, v, ok, note) for k, v, ok, note in [
            ("trades", f"{size.trades}", None, "on net returns, after cost and carry"),
            ("mean per trade", f"{size.mu_bps:+,.1f} bps", None, ""),
            ("deviation per trade", f"{size.sigma_bps:,.1f} bps", None, ""),
            ("standard error", f"{size.sigma_bps / math.sqrt(size.trades):,.1f} bps",
             None, "deviation over the square root of the trade count"),
            ("mean, less uncertainty", f"{size.mu_lower_bps:+,.1f} bps", None,
             f"{size.confidence:g} standard errors below the estimate"),
            ("growth-optimal leverage", f"{size.full_leverage:,.2f}", None,
             "on the point estimate, which no sample here supports"),
            ("after the haircut", f"{size.bounded_leverage:,.2f}", None, ""),
            ("after the cap", f"{size.capped_leverage:,.2f}", gate_size,
             f"capped at {size.max_leverage:g}"),
            ("gross exposure", f"{size.notional:,.0f}", None,
             f"on {size.equity:,.0f} of equity"),
        ])

    labels = [f"{r.entry_z:g}" for r in grid]
    charts = [
        ("Predicted against realised, per trade",
         bar_chart(labels, {"predicted": [r.predicted_bps for r in grid],
                            "realised": [r.realised_bps for r in grid]}, decimals=0),
         "The formula says a wider entry earns more, because the distance back to the "
         "exit is longer. What actually rises with the threshold is the chance there is "
         "no reversion left to catch."),
        ("Completion rate by threshold",
         bar_chart(labels, {"reached the exit": [r.completion_rate for r in grid]},
                   decimals=2, zero_line=True),
         "The share of trades that reached the exit. The expected-move formula assumes "
         "this is one."),
        ("What a trade earned against what it cost",
         bar_chart(labels, {"realised": [r.realised_bps for r in grid],
                            "cost": [-r.cost_bps for r in grid]}, decimals=0),
         f"Cost is drawn negative. A threshold pays when the bar above clears "
         f"{args.min_edge:g} times the bar below."),
        ("Per-trade net, distribution",
         pr.histogram(np.array([t.net_bps for t in result.trades], dtype=float),
                      marks=[(0.0, "break even")]) if result.trades else "",
         "Every finished trade at the configured threshold, after cost and financing."),
        ("Equity, gross and net",
         pr.line_chart(px.index, {"gross": result.equity_gross,
                                  "net": result.equity_net},
                       hlines=[(0.0, "")], decimals=0, sign=True),
         "The gap between the two lines is transaction cost and financing."),
    ]

    sections = [f"<div class='big'>{tiles}</div>",
                "<h2>Question 1 — does the prediction describe these trades?</h2>"
                "<table><tbody>" + outcome_rows + "</tbody></table>",
                "<h3>How each trade ended</h3><table><tbody>" + cat_rows
                + "</tbody></table>",
                "<h2>Question 2 — does any threshold pay for itself?</h2>"
                "<table><tbody>" + threshold_rows + "</tbody></table>",
                "<h3>Measured at each threshold</h3>" + grid_table(grid)
                + "<div class='cap'>"
                + html.escape("A sweep, not an optimisation: the floor is the lowest "
                              "row that pays, not the best one. Picking the most "
                              "profitable cell of a grid is what step 4 exists to "
                              "catch, and a boundary moves less than a maximum.")
                + "</div>"]
    if size_rows:
        sections.append("<h2>Question 3 — is any size justified?</h2>"
                        "<table><tbody>" + size_rows + "</tbody></table>")
    for title, svg, cap in charts:
        if svg:
            sections.append(f"<h2>{html.escape(title)}</h2>{svg}"
                            f"<div class='cap'>{html.escape(cap)}</div>")
    if estimated:
        sections.append("<div class='cap'>"
                        + html.escape("The cost profile is an estimate, not a broker "
                                      "sheet. Every figure above that involves cost or "
                                      "financing inherits that.")
                        + "</div>")

    summary = html.escape("; ".join(fails)) if fails else (
        "the prediction holds, a threshold pays for itself, and the sample supports a "
        "position")
    doc = ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
           "<meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>{a} ~ {b} — signal, risk and sizing</title>"
           f"<style>{pr.CSS}{EXTRA_CSS}</style></head><body>"
           f"<h1>{a} ~ {b} · signal, risk and sizing</h1>"
           f"<div class='meta'>{args.timeframe} · {px.index[0]:%Y-%m-%d} to "
           f"{px.index[-1]:%Y-%m-%d} · {len(px):,} bars · broker {args.broker} · "
           f"{args.bars_per_night:g} nights per bar · generated "
           f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC</div>"
           f"<div class='verdict {'pass' if passed else ''}'>"
           f"<b>{'TRADEABLE' if passed else 'NOT TRADEABLE'}</b> — {summary}"
           "<p>These are bounds read off replayed trades, not a strategy. Passing here "
           "makes a pair worth validating in step 4, which is where a result like this "
           "is expected to die.</p></div>"
           + "".join(sections) + "</body></html>")

    out = Path(args.out) if args.out else DEFAULT_REPORTS / f"signal-{a}-{b}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")

    log(f"{a} ~ {b}   {args.timeframe}   {len(px):,} bars   broker {args.broker}")
    log(f"  prediction {'holds' if gate_prediction else 'FAILS'} ({over})   "
        f"threshold {('z ' + format(floor, '.2f')) if gate_threshold else 'NONE pays'}   "
        f"size {size.capped_leverage:.2f}" if size else "  size none")
    if fails:
        for f in fails:
            log(f"    - {f}")
    log(f"  wrote {out}  ({out.stat().st_size / 1024:.1f} KB)")
    if args.open_browser:
        webbrowser.open(out.resolve().as_uri())
    return 0 if passed else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
