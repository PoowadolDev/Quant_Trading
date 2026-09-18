"""Every chart, colour and table row the reports share, in one module.

Extracted from `pair_report.py`, which had become three things at once: the Step 0 pair
study, the HTML style library imported by twenty-one modules, and the home of `UserError`.
A module named for one strategy family should not be the hard dependency of the entire
reporting layer, and the cost of that arrangement was visible: `EXTRA_CSS` was forked three
ways with cosmetic drift, `.big` was redefined in three files with different gaps, and
`text.barlab` had two different fills.

Inline SVG only — no JavaScript, no canvas, no external libraries, no web fonts. A report
has to open from a file path on a machine with no network and render the same way in five
years. Dark mode is a plain `prefers-color-scheme` re-declaration of the same custom
properties rather than a toggle, for the same reason.

`pair_report` re-exports these names so existing importers keep working while the reports
are consolidated.
"""
from __future__ import annotations

import html
import math

import numpy as np
import pandas as pd

W, H, PAD_L, PAD_T, PAD_B = 900, 210, 54, 12, 22
PAD_R = 12
PAD_R_LABELS = 64


def _grid_and_ticks(index, sx, sy, ylo, yhi, pad_r, decimals, sign):
    out = []
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        value = ylo + (yhi - ylo) * frac
        y = sy(value)
        text = f"{value:+.{decimals}f}" if sign else f"{value:.{decimals}f}"
        out.append(f"<line class='grid' x1='{PAD_L}' y1='{y:.1f}' x2='{W-pad_r}' y2='{y:.1f}'/>")
        out.append(f"<text class='tick' x='{PAD_L-6}' y='{y+3:.1f}' text-anchor='end'>{text}</text>")
    n = len(index)
    fmt = _date_format(index)
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        i = int(frac * (n - 1))
        out.append(f"<text class='tick' x='{sx(i):.1f}' y='{H-6}' text-anchor='middle'>"
                   f"{index[i].strftime(fmt)}</text>")
    return "".join(out)


def _date_format(index) -> str:
    """Tick format that changes with the span, so intraday ticks stay distinct."""
    days = (index[-1] - index[0]).total_seconds() / 86400
    if days > 400:
        return "%Y-%m"
    if days > 5:
        return "%Y-%m-%d"
    return "%m-%d %H:%M"


def _scales(n, values, pad_r):
    ylo, yhi = float(np.nanmin(values)), float(np.nanmax(values))
    if yhi == ylo:
        yhi = ylo + 1e-9
    pad = (yhi - ylo) * 0.08
    ylo, yhi = ylo - pad, yhi + pad
    sx = lambda i: PAD_L + i / max(n - 1, 1) * (W - PAD_L - pad_r)          # noqa: E731
    sy = lambda v: PAD_T + (yhi - v) / (yhi - ylo) * (H - PAD_T - PAD_B)    # noqa: E731
    return sx, sy, ylo, yhi


def _path(values, sx, sy):
    parts, pen = [], False
    for i, v in enumerate(values):
        if not np.isfinite(v):
            pen = False
            continue
        parts.append(("L" if pen else "M") + f"{sx(i):.1f},{sy(v):.1f}")
        pen = True
    return "".join(parts)


def _split_marker(sx, split):
    x = sx(split)
    return (f"<line class='split' x1='{x:.1f}' y1='{PAD_T}' x2='{x:.1f}' y2='{H-PAD_B}'/>"
            f"<text class='tick' x='{x+5:.1f}' y='{PAD_T+11}'>out-of-sample →</text>")


def line_chart(index, series: dict[str, np.ndarray], *, bands=None, hlines=(),
               split=None, decimals=4, sign=False, end_labels=False,
               legend_notes=None) -> str:
    """One panel, one line per entry in `series`, up to six lines."""
    pad_r = PAD_R_LABELS if end_labels else PAD_R
    stacked = [np.asarray(v, float) for v in series.values()]
    span = np.concatenate(stacked)
    if bands:
        span = np.concatenate([span, np.asarray(bands, float)])
    if hlines:
        span = np.concatenate([span, np.asarray([h for h, _ in hlines], float)])
    sx, sy, ylo, yhi = _scales(len(index), span, pad_r)

    body = [_grid_and_ticks(index, sx, sy, ylo, yhi, pad_r, decimals, sign)]
    if bands:
        lo, hi = min(bands), max(bands)
        body.append(f"<rect class='band' x='{PAD_L}' y='{sy(hi):.1f}' "
                    f"width='{W-PAD_L-pad_r}' height='{max(sy(lo)-sy(hi), 0):.1f}'/>")
    for value, cls in hlines:
        body.append(f"<line class='{cls}' x1='{PAD_L}' y1='{sy(value):.1f}' "
                    f"x2='{W-pad_r}' y2='{sy(value):.1f}'/>")
    if split is not None:
        body.append(_split_marker(sx, split))
    for i, values in enumerate(stacked):
        body.append(f"<path class='s{i}' d='{_path(values, sx, sy)}'/>")
        if end_labels:
            last = values[np.isfinite(values)][-1]
            body.append(f"<text class='end s{i}' x='{W-pad_r+5}' y='{sy(last)+3:.1f}'>"
                        f"{last:.{decimals}f}</text>")

    keys = []
    for i, name in enumerate(series):
        note = ""
        if legend_notes and name in legend_notes:
            note = f"<span class='px'>{html.escape(legend_notes[name])}</span>"
        keys.append(f"<span class='key'><i class='s{i}'></i>{html.escape(name)}{note}</span>")
    legend = " ".join(keys) if len(series) > 1 or legend_notes else ""

    return (f"<div class='chart'><svg viewBox='0 0 {W} {H}' preserveAspectRatio='none'>"
            f"{''.join(body)}</svg>"
            + (f"<div class='legend'>{legend}</div>" if legend else "") + "</div>")


def histogram(values: np.ndarray, marks=(), bins: int = 45) -> str:
    values = values[np.isfinite(values)]
    counts, edges = np.histogram(values, bins=bins)
    height = 150
    tallest = counts.max() or 1
    bar_w = (W - PAD_L - PAD_R) / bins
    body = []
    for i, count in enumerate(counts):
        bar_h = count / tallest * (height - 24)
        body.append(f"<rect class='bar' x='{PAD_L + i*bar_w:.1f}' y='{height-12-bar_h:.1f}' "
                    f"width='{bar_w*0.86:.1f}' height='{bar_h:.1f}'/>")
    lo, hi = float(edges[0]), float(edges[-1])
    for value, cls in marks:
        x = PAD_L + (value - lo) / (hi - lo) * (W - PAD_L - PAD_R)
        body.append(f"<line class='{cls}' x1='{x:.1f}' y1='6' x2='{x:.1f}' y2='{height-12}'/>")
    for frac in (0, 0.5, 1.0):
        x = PAD_L + frac * (W - PAD_L - PAD_R)
        body.append(f"<text class='tick' x='{x:.1f}' y='{height-1}' text-anchor='middle'>"
                    f"{lo + (hi-lo)*frac:.1f}</text>")
    return (f"<div class='chart'><svg viewBox='0 0 {W} {height}' preserveAspectRatio='none'>"
            f"{''.join(body)}</svg></div>")



CSS = """
:root{--bg:#fff;--fg:#1b1f24;--muted:#6b7280;--line:#e3e6ea;--zebra:#fafbfc;
--ok:#1a7f37;--no:#cf222e;--a:#2f6feb;--b:#d1913c;--c:#1a7f37;--d:#8250df;--e:#bf3989;--f:#0f7c8a;
--band:#2f6feb;--grid:#eceff2}
@media(prefers-color-scheme:dark){:root{--bg:#0f1419;--fg:#dfe3e8;--muted:#8b949e;--line:#262c34;
--zebra:#131920;--ok:#3fb950;--no:#f85149;--a:#6ba0ff;--b:#e3b341;--c:#3fb950;--d:#bc8cff;
--e:#f778ba;--f:#39c5cf;--band:#6ba0ff;--grid:#1d242c}}
*{box-sizing:border-box}
body{margin:0;padding:26px 30px 60px;background:var(--bg);color:var(--fg);
font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
h1{font-size:19px;margin:0 0 2px}
.meta{color:var(--muted);font-size:12px;margin-bottom:18px}
.verdict{border:1px solid var(--line);border-left:4px solid var(--no);border-radius:6px;
padding:12px 16px;margin-bottom:22px;background:var(--zebra)}
.verdict.pass{border-left-color:var(--ok)}
.verdict b{font-size:16px;color:var(--no)}.verdict.pass b{color:var(--ok)}
.verdict p{margin:4px 0 0;color:var(--muted);font-size:13px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);
margin:26px 0 8px;padding-bottom:5px;border-bottom:1px solid var(--line)}
.cols{display:flex;gap:26px;flex-wrap:wrap}.cols>div{flex:1 1 340px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
td,th{padding:4px 8px;border-bottom:1px solid var(--line);font-size:12.5px;text-align:left}
td.k{color:var(--muted);white-space:nowrap}
td.v{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;white-space:nowrap}
td.n{color:var(--muted);font-size:11.5px}
tbody tr:nth-child(even){background:var(--zebra)}
.b{font-size:10.5px;font-weight:700;padding:1px 6px;border-radius:3px}
.b.ok{color:var(--ok);background:color-mix(in srgb,var(--ok) 14%,transparent)}
.b.no{color:var(--no);background:color-mix(in srgb,var(--no) 14%,transparent)}
.chart{border:1px solid var(--line);border-radius:6px;padding:6px 4px 2px;margin-bottom:6px;
background:var(--bg)}
svg{width:100%;height:auto;display:block}
path{fill:none;stroke-width:1.3;vector-effect:non-scaling-stroke}
path.s0{stroke:var(--a)}path.s1{stroke:var(--b)}path.s2{stroke:var(--c)}
path.s3{stroke:var(--d)}path.s4{stroke:var(--e)}path.s5{stroke:var(--f)}
text.end{font-size:9.5px;font-family:ui-monospace,Menlo,monospace}
text.end.s0{fill:var(--a)}text.end.s1{fill:var(--b)}text.end.s2{fill:var(--c)}
text.end.s3{fill:var(--d)}text.end.s4{fill:var(--e)}text.end.s5{fill:var(--f)}
line.grid{stroke:var(--grid);stroke-width:1;vector-effect:non-scaling-stroke}
line.mean{stroke:var(--muted);stroke-dasharray:4 3;vector-effect:non-scaling-stroke}
line.entry{stroke:var(--no);stroke-dasharray:3 3;vector-effect:non-scaling-stroke}
line.exit{stroke:var(--ok);stroke-dasharray:2 4;vector-effect:non-scaling-stroke}
line.split{stroke:var(--muted);stroke-dasharray:2 3;vector-effect:non-scaling-stroke}
rect.band{fill:var(--band);opacity:.07}rect.bar{fill:var(--a);opacity:.75}
text.tick{fill:var(--muted);font-size:9px;font-family:ui-monospace,Menlo,monospace}
.legend{font-size:11px;color:var(--muted);padding:2px 0 4px 54px}
.key{margin-right:14px}
.key i{display:inline-block;width:10px;height:2px;margin-right:5px;vertical-align:middle}
.key i.s0{background:var(--a)}.key i.s1{background:var(--b)}.key i.s2{background:var(--c)}
.key i.s3{background:var(--d)}.key i.s4{background:var(--e)}.key i.s5{background:var(--f)}
.key .px{margin-left:5px;opacity:.7;font-family:ui-monospace,Menlo,monospace;font-size:10px}
.cap{color:var(--muted);font-size:11.5px;margin:2px 0 14px}
"""


def _row(label, value, status=None, note=""):
    badge = ""
    if status is True:
        badge = "<span class='b ok'>PASS</span>"
    elif status is False:
        badge = "<span class='b no'>FAIL</span>"
    return (f"<tr><td class='k'>{html.escape(label)}</td><td class='v'>{html.escape(value)}</td>"
            f"<td>{badge}</td><td class='n'>{html.escape(note)}</td></tr>")


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


def waterfall_chart(stats: dict) -> str:
    """Gross, then each cost, then net — the four numbers that matter, to scale."""
    width, height, pad_l, pad_b = 900, 190, 54, 26
    steps = [("gross", stats["gross_bps"], "up" if stats["gross_bps"] >= 0 else "down"),
             ("transaction", -stats["transaction_bps"], "down"),
             ("carry", stats["carry_bps"], "up" if stats["carry_bps"] >= 0 else "down"),
             ("net", stats["net_bps"], "net")]
    running, marks = 0.0, []
    for name, value, kind in steps[:-1]:
        marks.append((name, running, running + value, kind))
        running += value
    marks.append(("net", 0.0, stats["net_bps"], "net"))
    lo = min([m[1] for m in marks] + [m[2] for m in marks] + [0.0])
    hi = max([m[1] for m in marks] + [m[2] for m in marks] + [0.0])
    span = (hi - lo) or 1.0
    lo, hi = lo - span * 0.15, hi + span * 0.15
    sy = lambda v: 10 + (hi - v) / (hi - lo) * (height - 10 - pad_b)      # noqa: E731
    slot = (width - pad_l - 20) / len(marks)
    body = [f"<line class='grid' x1='{pad_l}' y1='{sy(0):.1f}' "
            f"x2='{width-20}' y2='{sy(0):.1f}'/>"]
    for i, (name, start, end, kind) in enumerate(marks):
        x = pad_l + i * slot + slot * 0.22
        w = slot * 0.56
        top, bottom = sy(max(start, end)), sy(min(start, end))
        cls = {"up": "bar-up", "down": "bar-down", "net": "bar-net"}[kind]
        body.append(f"<rect class='{cls}' x='{x:.1f}' y='{top:.1f}' width='{w:.1f}' "
                    f"height='{max(bottom-top, 1.5):.1f}'/>")
        body.append(f"<text class='tick' x='{x+w/2:.1f}' y='{height-12}' "
                    f"text-anchor='middle'>{name}</text>")
        body.append(f"<text class='barlab' x='{x+w/2:.1f}' y='{top-5:.1f}' "
                    f"text-anchor='middle'>{end-start:+,.0f}</text>")
    return (f"<div class='chart'><svg viewBox='0 0 {width} {height}' "
            f"preserveAspectRatio='none'>{''.join(body)}</svg></div>")


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


# ---------------------------------------------------------------- merged EXTRA_CSS
#
# One definition of each class. Before this, `.big` lived in `relationship_report`,
# `signal_report` and `backtest` with gaps of 14px, 18px and 18px and margins of 14px, 6px
# and 6px, and `text.barlab` had `fill:var(--muted)` in one and `fill:var(--fg)` in another.
# Nobody chose those differences; they are what happens when a block is pasted three times.
EXTRA_CSS = """
.big{display:flex;gap:18px;flex-wrap:wrap;margin-bottom:14px}
.big>div{flex:0 0 auto}
.big b{display:block;font:600 19px ui-monospace,SFMono-Regular,Menlo,monospace}
.big span{color:var(--muted);font-size:11.5px}
.big .pass b{color:var(--ok)}.big .fail b{color:var(--no)}
text.barlab{fill:var(--muted);font-size:10px;text-anchor:middle}
rect.bar-up{fill:var(--ok)}rect.bar-down{fill:var(--no)}rect.bar-net{fill:var(--a)}
rect.state-healthy{fill:var(--ok)}rect.state-degraded{fill:var(--b)}
rect.state-broken{fill:var(--no)}
"""
