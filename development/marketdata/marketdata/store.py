"""Local Parquet store: one file per (asset_class, symbol, timeframe, source)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .feeds import empty_ohlcv, normalise
from .instruments import Instrument
from .util import LOG, UserError

DEFAULT_STORE = Path("store")


class ParquetStore:
    """Read and write OHLCV history under a directory tree.

    Layout: ``{root}/{asset_class}/{symbol}/{timeframe}/{source}.parquet``

    The path carries the metadata, so a catalogue can be rebuilt by scanning the tree —
    there is no separate index file to fall out of sync.
    """

    def __init__(self, root: Path | str = DEFAULT_STORE):
        self.root = Path(root)

    def __repr__(self) -> str:
        return f"ParquetStore({str(self.root)!r})"

    # ---------------------------------------------------------------- paths

    def path(self, inst: Instrument) -> Path:
        return (self.root / inst.asset_class / inst.symbol
                / inst.timeframe / f"{inst.source}.parquet")

    @staticmethod
    def instrument_from_path(path: Path) -> Instrument:
        asset_class, symbol, timeframe = Path(path).parts[-4:-1]
        return Instrument(symbol, asset_class, Path(path).stem, timeframe)

    # ---------------------------------------------------------------- io

    def read(self, inst: Instrument) -> pd.DataFrame:
        path = self.path(inst)
        if not path.exists():
            return empty_ohlcv()
        return self.read_path(path)

    @staticmethod
    def read_path(path: Path | str) -> pd.DataFrame:
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index, utc=True)
        return normalise(df)

    def write(self, inst: Instrument, df: pd.DataFrame, mode: str = "merge") -> Path:
        """Persist `df`.

        mode="merge"   keep existing rows, add new ones, newest copy wins on collision
        mode="replace" discard whatever was stored for this instrument
        """
        if mode not in {"merge", "replace"}:
            raise UserError(f"unknown write mode {mode!r}; expected 'merge' or 'replace'")

        path = self.path(inst)
        if df.empty and mode == "merge":
            return path

        if mode == "merge" and path.exists():
            combined = normalise(pd.concat([self.read(inst), df]))
        else:
            combined = normalise(df)

        path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(path, engine="pyarrow", compression="snappy")
        LOG.debug("wrote %s (%d rows)", path, len(combined))
        return path

    def delete(self, inst: Instrument) -> bool:
        path = self.path(inst)
        if path.exists():
            path.unlink()
            return True
        return False

    # ---------------------------------------------------------------- catalogue

    def catalogue(self) -> pd.DataFrame:
        """One row per stored series, with coverage and gap statistics.

        Only the index of each file is read, so this stays cheap on a large store.
        """
        rows = []
        for path in sorted(self.root.rglob("*.parquet")):
            try:
                asset_class, symbol, timeframe = path.parts[-4:-1]
            except ValueError:
                LOG.warning("skipping %s: not in {asset_class}/{symbol}/{timeframe} layout", path)
                continue

            index = pd.to_datetime(pd.read_parquet(path, columns=[]).index, utc=True)
            rows.append({
                "asset_class": asset_class,
                "symbol": symbol,
                "timeframe": timeframe,
                "source": path.stem,
                "rows": len(index),
                "start": index.min() if len(index) else pd.NaT,
                "end": index.max() if len(index) else pd.NaT,
                "gap_pct": gap_pct(index),
                "size_kb": round(path.stat().st_size / 1024, 1),
                "path": str(path),
            })

        columns = ["asset_class", "symbol", "timeframe", "source", "rows",
                   "start", "end", "gap_pct", "size_kb", "path"]
        return pd.DataFrame(rows, columns=columns)


def gap_pct(index: pd.DatetimeIndex) -> float:
    """Share of expected bars that are absent, inferred from the median bar spacing.

    Daily forex sits near 28% because of weekends; intraday crypto should be near zero.
    """
    if len(index) < 3:
        return float("nan")
    step = pd.Series(index).diff().median()
    if pd.isna(step) or step.total_seconds() <= 0:
        return float("nan")
    expected = (index.max() - index.min()) / step + 1
    return round(float(100 * (1 - len(index) / expected)), 1)


def select(catalogue: pd.DataFrame, asset_class=None, symbols=None,
           timeframe=None, source=None) -> pd.DataFrame:
    """Filter a catalogue. Each argument accepts a string, a list, or None for 'any'."""
    def as_list(value):
        if value is None:
            return None
        return [value] if isinstance(value, str) else [str(v) for v in value]

    out = catalogue
    for column, wanted in (("asset_class", asset_class), ("symbol", symbols),
                           ("timeframe", timeframe), ("source", source)):
        wanted = as_list(wanted)
        if wanted is not None:
            wanted = [w.upper() if column == "symbol" else w.lower() for w in wanted]
            out = out[out[column].isin(wanted)]
    return out.reset_index(drop=True)


def series_label(row) -> str:
    return f'{row["symbol"]} · {row["timeframe"]} · {row["source"]}'


def short_label(label: str) -> str:
    return label.split(" · ", 1)[0]


def aligned_panel(frames: dict[str, pd.DataFrame], field: str = "close",
                  how: str = "inner") -> pd.DataFrame:
    """Wide frame, one column per series, on shared timestamps."""
    usable = {label: df[field] for label, df in frames.items() if not df.empty}
    if not usable:
        return pd.DataFrame()
    return pd.concat(usable, axis=1, join=how).dropna(how="all")


def log_returns(panel: pd.DataFrame) -> pd.DataFrame:
    return np.log(panel.astype(float)).diff().dropna()
