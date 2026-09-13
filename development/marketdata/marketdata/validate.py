"""Data quality checks. Every check answers: would I trade on this series?"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .store import ParquetStore, gap_pct

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.code}: {self.message}"


@dataclass
class SeriesReport:
    label: str
    rows: int
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == WARNING]

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def status(self) -> str:
        if self.errors:
            return "FAIL"
        if self.warnings:
            return "WARN"
        return "OK"

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "rows": self.rows,
            "status": self.status,
            "errors": [i.message for i in self.errors],
            "warnings": [i.message for i in self.warnings],
        }


def validate_frame(
    df: pd.DataFrame,
    *,
    label: str = "",
    asset_class: str = "forex",
    min_rows: int = 100,
    max_gap_pct: float | None = None,
    max_stale_run: int = 20,
    ohlc_tolerance_bps: float = 0.0,
    future_tolerance: pd.Timedelta = pd.Timedelta("1D"),
) -> SeriesReport:
    """Run every check against one OHLCV frame.

    `max_gap_pct` of None disables the gap check, which is the sensible default for daily
    forex where ~28% "missing" bars are simply weekends.

    `ohlc_tolerance_bps` is how far open/close may sit outside the bar's high/low range
    before it counts as a violation, expressed in basis points of the price level so that
    one setting means the same thing on EURUSD, USDJPY and BTCUSDT alike. It defaults to
    zero: a close above the high is broken data, and Yahoo forex contains such bars. Raise
    it deliberately if you have decided to live with a known-imperfect feed.
    """
    report = SeriesReport(label=label, rows=len(df))
    add = report.issues.append

    if df.empty:
        add(Issue(ERROR, "empty", "series contains no rows"))
        return report

    # --- structure -------------------------------------------------------
    if not isinstance(df.index, pd.DatetimeIndex):
        add(Issue(ERROR, "index-type", "index is not a DatetimeIndex"))
        return report
    if df.index.tz is None:
        add(Issue(ERROR, "index-tz", "index is timezone-naive; expected UTC"))
    if not df.index.is_monotonic_increasing:
        add(Issue(ERROR, "index-order", "index is not sorted ascending"))
    duplicates = int(df.index.duplicated().sum())
    if duplicates:
        add(Issue(ERROR, "index-duplicates", f"{duplicates} duplicate timestamps"))

    missing_columns = [c for c in ("open", "high", "low", "close") if c not in df.columns]
    if missing_columns:
        add(Issue(ERROR, "columns", f"missing columns: {', '.join(missing_columns)}"))
        return report

    # --- values ----------------------------------------------------------
    nan_counts = df[["open", "high", "low", "close"]].isna().sum()
    for column, count in nan_counts[nan_counts > 0].items():
        add(Issue(ERROR, "nan", f"{count} NaN values in {column}"))

    non_positive = int((df[["open", "high", "low", "close"]] <= 0).sum().sum())
    if non_positive:
        add(Issue(ERROR, "non-positive", f"{non_positive} prices at or below zero"))

    # --- OHLC consistency ------------------------------------------------
    price_level = float(pd.to_numeric(df["close"], errors="coerce").abs().median())
    tolerance = max(float(ohlc_tolerance_bps), 0.0) / 10_000 * price_level
    body_high = df[["open", "close"]].max(axis=1)
    body_low = df[["open", "close"]].min(axis=1)

    high_overshoot = (body_high - df["high"]).where(lambda s: s > tolerance).dropna()
    low_undershoot = (df["low"] - body_low).where(lambda s: s > tolerance).dropna()
    inverted = int((df["high"] < df["low"] - tolerance).sum())

    if len(high_overshoot):
        add(Issue(ERROR, "ohlc-high",
                  f"{len(high_overshoot)} bars where open or close exceeds the high "
                  f"(worst {_price_gap(high_overshoot.max(), df, asset_class)})"))
    if len(low_undershoot):
        add(Issue(ERROR, "ohlc-low",
                  f"{len(low_undershoot)} bars where open or close is below the low "
                  f"(worst {_price_gap(low_undershoot.max(), df, asset_class)})"))
    if inverted:
        add(Issue(ERROR, "ohlc-inverted", f"{inverted} bars where high is below low"))

    if "volume" in df.columns:
        negative_volume = int((df["volume"] < 0).sum())
        if negative_volume:
            add(Issue(ERROR, "volume-negative", f"{negative_volume} bars with negative volume"))

    # --- coverage --------------------------------------------------------
    if len(df) < min_rows:
        add(Issue(WARNING, "short",
                  f"{len(df)} rows is below the --min-rows threshold of {min_rows}"))

    if max_gap_pct is not None:
        gaps = gap_pct(df.index)
        if pd.notna(gaps) and gaps > max_gap_pct:
            add(Issue(WARNING, "gaps",
                      f"{gaps:.1f}% of expected bars are missing, above the "
                      f"{max_gap_pct:.1f}% threshold"))

    latest_allowed = pd.Timestamp.now(tz="UTC") + future_tolerance
    future_bars = int((df.index > latest_allowed).sum())
    if future_bars:
        add(Issue(ERROR, "future", f"{future_bars} bars are timestamped in the future"))

    # --- staleness -------------------------------------------------------
    run = _longest_constant_run(df["close"])
    if run >= max_stale_run:
        add(Issue(WARNING, "stale",
                  f"close price is unchanged for {run} consecutive bars "
                  f"(threshold {max_stale_run}) — possible frozen feed"))

    return report


def _price_gap(magnitude: float, df: pd.DataFrame, asset_class: str = "forex") -> str:
    """Describe a price discrepancy in the units a trader reads.

    Forex quotes are reported in pips so "0.000103" becomes "1.0 pip", which is the
    difference between a rounding artefact and a broken bar. Only forex is converted:
    crude at 102 dollars a barrel is forex-shaped by magnitude alone, and calling a
    fifty-cent move "50 pips" would be nonsense.
    """
    if asset_class != "forex":
        return f"{magnitude:.6g}"
    level = float(pd.to_numeric(df["close"], errors="coerce").abs().median())
    if 0 < level < 500:                       # forex-shaped quote
        pips = magnitude * (100 if level > 50 else 10_000)   # JPY pairs quote to 0.01
        return f"{pips:.1f} pip" + ("s" if abs(pips) >= 2 else "")
    return f"{magnitude:.6g}"


def _longest_constant_run(series: pd.Series) -> int:
    """Length of the longest stretch of identical consecutive values."""
    if series.empty:
        return 0
    changed = series.ne(series.shift())
    group_sizes = changed.cumsum().value_counts()
    return int(group_sizes.max()) if len(group_sizes) else 0


def validate_selection(store: ParquetStore, selection: pd.DataFrame, **kwargs) -> list[SeriesReport]:
    """Validate every series in a catalogue slice."""
    from .store import series_label

    reports = []
    for _, row in selection.iterrows():
        df = ParquetStore.read_path(row["path"])
        # The asset class decides how a price discrepancy is phrased, so it
        # travels with the frame rather than being guessed from the magnitude.
        reports.append(validate_frame(df, label=series_label(row),
                                      asset_class=row["asset_class"], **kwargs))
    return reports
