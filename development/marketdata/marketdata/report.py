"""Render stored series into one self-contained HTML table report."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .store import ParquetStore, aligned_panel, series_label, short_label
from .util import LOG, UserError

DEFAULT_REPORTS = Path("reports")

CSS = """
:root {
  --bg: #ffffff; --fg: #1b1f24; --muted: #6b7280; --line: #e3e6ea;
  --head: #f4f6f8; --zebra: #fafbfc; --accent: #2f6feb;
  --ok: #1a7f37; --warn: #9a6700; --fail: #cf222e;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1419; --fg: #dfe3e8; --muted: #8b949e; --line: #262c34;
    --head: #171d24; --zebra: #131920; --accent: #6ba0ff;
    --ok: #3fb950; --warn: #d29922; --fail: #f85149;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 28px 32px 64px; background: var(--bg); color: var(--fg);
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
h1 { font-size: 20px; margin: 0 0 4px; }
h2 { font-size: 15px; margin: 34px 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--line); }
.meta { color: var(--muted); font-size: 12px; margin-bottom: 22px; }
.note { color: var(--muted); font-size: 12px; margin: 6px 0 10px; }
.wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 6px; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td {
  padding: 5px 10px; text-align: right; white-space: nowrap;
  border-bottom: 1px solid var(--line); font-size: 12.5px;
}
thead th { position: sticky; top: 0; background: var(--head); font-weight: 600; z-index: 1; }
tbody tr:nth-child(even) { background: var(--zebra); }
td.idx, th.idx { text-align: left; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
tbody tr:hover { background: color-mix(in srgb, var(--accent) 9%, transparent); }
.status-OK { color: var(--ok); font-weight: 600; }
.status-WARN { color: var(--warn); font-weight: 600; }
.status-FAIL { color: var(--fail); font-weight: 600; }
#filter {
  width: 260px; padding: 6px 10px; margin-bottom: 18px; font: inherit; font-size: 13px;
  color: var(--fg); background: var(--bg); border: 1px solid var(--line); border-radius: 6px;
}
nav { margin-bottom: 8px; font-size: 12px; }
nav a { color: var(--accent); text-decoration: none; margin-right: 14px; }
nav a:hover { text-decoration: underline; }
"""

SCRIPT = """
const box = document.getElementById('filter');
if (box) {
  box.addEventListener('input', () => {
    const q = box.value.trim().toLowerCase();
    document.querySelectorAll('tbody tr').forEach(tr => {
      tr.style.display = !q || tr.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
  });
}
"""


# ------------------------------------------------------------------ formatting

def decimals_for(series: pd.Series) -> int:
    """Choose decimal places from the magnitude of the data."""
    magnitude = pd.to_numeric(series, errors="coerce").abs().median()
    if not np.isfinite(magnitude) or magnitude == 0:
        return 4
    if magnitude >= 1000:
        return 2          # BTCUSDT
    if magnitude >= 100:
        return 3          # USDJPY, EURJPY
    if magnitude >= 0.01:
        return 5          # FX majors and crosses, either side of 1.0
    return 8              # sub-cent crypto


def format_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return a string frame ready for HTML: aligned decimals, thousands separators."""
    out = pd.DataFrame(index=df.index)
    for name, col in df.items():
        numeric = pd.to_numeric(col, errors="coerce")
        if numeric.isna().all():
            out[name] = col.astype(str)
        elif str(name).lower() == "volume":
            out[name] = numeric.map(lambda v: "" if pd.isna(v) else f"{v:,.0f}")
        else:
            nd = decimals_for(numeric)
            out[name] = numeric.map(lambda v, nd=nd: "" if pd.isna(v) else f"{v:,.{nd}f}")

    out.index = [t.strftime("%Y-%m-%d %H:%M") if isinstance(t, pd.Timestamp) else str(t)
                 for t in df.index]
    return out


def table_html(df: pd.DataFrame, index_label: str = "", raw_columns: set[str] | None = None) -> str:
    """Semantic HTML table from an already-formatted frame.

    Columns named in `raw_columns` are emitted without escaping, so they may carry markup
    (used for the coloured status column in the validation report).
    """
    raw_columns = raw_columns or set()
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    header = f"<thead><tr><th class='idx'>{html.escape(index_label)}</th>{head}</tr></thead>"

    body = []
    for idx, row in df.iterrows():
        cells = "".join(
            f"<td>{value if column in raw_columns else html.escape(str(value))}</td>"
            for column, value in row.items()
        )
        body.append(f"<tr><td class='idx'>{html.escape(str(idx))}</td>{cells}</tr>")

    return f"<table>{header}<tbody>{''.join(body)}</tbody></table>"


def html_document(title: str, sections: list[str], subtitle: str = "",
                  nav: list[tuple[str, str]] | None = None) -> str:
    """Assemble the final page. `nav` is a list of (anchor, label) pairs."""
    nav_links = "".join(
        f'<a href="#{html.escape(anchor)}">{html.escape(label)}</a>'
        for anchor, label in (nav or [])
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body>"
        f"<h1>{html.escape(title)}</h1>"
        f"<div class='meta'>{html.escape(subtitle)}</div>"
        f"<nav>{nav_links}</nav>"
        "<input id='filter' type='search' placeholder='Filter rows…' autocomplete='off'>"
        f"{''.join(sections)}"
        f"<script>{SCRIPT}</script></body></html>"
    )


# ------------------------------------------------------------------ report

def build_report(
    selection: pd.DataFrame,
    output: Path,
    *,
    store_root: Path | str = "store",
    max_rows: int = 200,
    include_panel: bool = True,
    panel_field: str = "close",
    panel_rows: int = 200,
    title: str = "Market Data Report",
    validation: list | None = None,
) -> Path:
    """Render a catalogue slice into one self-contained HTML file. Returns the path."""
    if selection.empty:
        raise UserError("selection is empty — nothing to report")

    frames = {series_label(row): ParquetStore.read_path(row["path"])
              for _, row in selection.iterrows()}

    sections: list[str] = []
    nav: list[tuple[str, str]] = []

    # 1. contents
    overview = selection.drop(columns=["path"], errors="ignore").copy()
    for column in ("start", "end"):
        if column in overview:
            overview[column] = pd.to_datetime(
                overview[column], utc=True, errors="coerce"
            ).dt.strftime("%Y-%m-%d %H:%M")
    nav.append(("contents", "Contents"))
    sections.append("<h2 id='contents'>Contents</h2>")
    sections.append(f"<div class='note'>{len(selection)} series from {store_root}/</div>")
    sections.append("<div class='wrap'>" + table_html(overview.astype(str), "#") + "</div>")

    # 2. validation summary, when the caller ran the checks
    if validation:
        nav.append(("validation", "Validation"))
        sections.append("<h2 id='validation'>Validation</h2>")
        rows = []
        for report in validation:
            rows.append({
                "series": report.label,
                "rows": f"{report.rows:,}",
                "status": f"<span class='status-{report.status}'>{report.status}</span>",
                "findings": "; ".join(i.message for i in report.issues) or "—",
            })
        table = pd.DataFrame(rows).set_index("series")
        sections.append("<div class='wrap'>"
                        + table_html(table, "series", raw_columns={"status"})
                        + "</div>")

    # 3. aligned panel across every selected instrument
    if include_panel and len(frames) > 1:
        uniform = (selection["timeframe"].nunique() == 1
                   and selection["source"].nunique() == 1)
        labelled = {(short_label(label) if uniform else label): df
                    for label, df in frames.items()}
        panel = aligned_panel(labelled, field=panel_field)

        nav.append(("panel", f"Aligned {panel_field}"))
        sections.append(f"<h2 id='panel'>Aligned {html.escape(panel_field)} panel</h2>")
        if panel.empty:
            sections.append("<div class='note'>No timestamps shared by every selected series "
                            "— check that they use the same timeframe.</div>")
        else:
            sections.append(
                f"<div class='note'>{len(panel):,} shared timestamps across {panel.shape[1]} "
                f"instruments; showing the last {min(panel_rows, len(panel)):,}.</div>"
            )
            sections.append("<div class='wrap'>"
                            + table_html(format_frame(panel.tail(panel_rows)), "timestamp")
                            + "</div>")

    # 4. one table per instrument
    for label, df in frames.items():
        anchor = label.replace(" · ", "-").replace(" ", "")
        nav.append((anchor, short_label(label)))
        sections.append(f"<h2 id='{html.escape(anchor)}'>{html.escape(label)}</h2>")

        note = f"{len(df):,} bars stored"
        if len(df) > max_rows:
            note += f"; showing the last {max_rows:,}"
        if len(df) and "volume" in df.columns and (df["volume"] == 0).all():
            note += ". Volume is all zero — expected for Yahoo forex"
        sections.append(f"<div class='note'>{html.escape(note)}.</div>")
        sections.append("<div class='wrap'>"
                        + table_html(format_frame(df.tail(max_rows)), "timestamp")
                        + "</div>")

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subtitle = f"Generated {generated} · {len(selection)} series · source: {store_root}/"

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_document(title, sections, subtitle, nav), encoding="utf-8")
    LOG.debug("report written to %s", output)
    return output
