"""Stock catalogue loaded from the ``stock-income`` folder.

The folder holds supplier price lists as ``.csv``/``.xlsx`` files. Every file
is read on startup and merged into a single in-memory catalogue.
"""

import logging
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

EXPECTED_COLUMNS = ["sku", "name", "description", "quantity", "available_date", "price"]

STOCK_INCOME_DIR = Path(__file__).resolve().parents[1] / "stock-income"


class StockService:
    """Read-only access to the merged product catalogue."""

    def __init__(self, folder: Path | str = STOCK_INCOME_DIR) -> None:
        """Load every ``.csv``/``.xlsx`` file in ``folder`` into one DataFrame."""
        self.folder = Path(folder)
        self.df = self._load()

    def _load(self) -> pd.DataFrame:
        """Return the merged catalogue, or an empty frame if nothing loaded."""
        frames = self._read_files()
        if not frames:
            return self._empty_frame()

        merged = pd.concat(frames, ignore_index=True)
        return self._normalize(merged)

    def _read_files(self) -> list[pd.DataFrame]:
        """Read each stock file, skipping any that are missing or unreadable."""
        if not self.folder.is_dir():
            logger.warning("Stock folder %s does not exist", self.folder)
            return []

        frames = []
        for path in sorted(self.folder.iterdir()):
            if path.suffix.lower() not in {".csv", ".xlsx"}:
                continue
            frame = self._read_file(path)
            if frame is not None:
                frames.append(frame)
        return frames

    def _read_file(self, path: Path) -> pd.DataFrame | None:
        """Read one file as strings, or return None when it cannot be parsed."""
        try:
            if path.suffix.lower() == ".csv":
                frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
            else:
                frame = pd.read_excel(path, dtype=str)
        except Exception:
            logger.exception("Skipping unreadable stock file %s", path)
            return None

        if frame.empty:
            logger.warning("Stock file %s has no rows", path)
            return None

        frame.columns = [str(column).strip().lower() for column in frame.columns]
        if "sku" not in frame.columns:
            logger.warning("Skipping %s: no 'sku' column found", path.name)
            return None

        logger.info("Loaded %d rows from %s", len(frame), path.name)
        return frame

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Align columns to the expected schema and coerce value types."""
        df = df.copy()
        df.columns = [str(column).strip().lower() for column in df.columns]
        df = df.reindex(columns=EXPECTED_COLUMNS)
        df = df.dropna(how="all")

        for column in ("sku", "name", "description"):
            df[column] = df[column].astype("string").str.strip()

        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").astype("Int64")
        df["price"] = pd.to_numeric(df["price"], errors="coerce").astype("float64")
        df["available_date"] = pd.to_datetime(df["available_date"], errors="coerce")

        return df

    def _empty_frame(self) -> pd.DataFrame:
        """Return an empty catalogue with the expected schema."""
        return self._normalize(pd.DataFrame(columns=EXPECTED_COLUMNS))

    def _records(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Convert a DataFrame slice to JSON-safe dicts."""
        records = []
        for row in df.to_dict("records"):
            records.append(
                {column: self._clean_value(row.get(column)) for column in EXPECTED_COLUMNS}
            )
        return records

    def _clean_value(self, value: Any) -> Any:
        """Map pandas/numpy scalars to plain Python values, nulls to None."""
        if value is None or value is pd.NaT:
            return None
        if isinstance(value, float) and math.isnan(value):
            return None
        if isinstance(value, np.generic):
            value = value.item()
            if isinstance(value, float) and math.isnan(value):
                return None
        if isinstance(value, (pd.Timestamp, datetime, date)):
            return value.date().isoformat()
        return value

    def get_all_products(self) -> list[dict[str, Any]]:
        """Return every product in the catalogue."""
        return self._records(self.df)

    def search_products(self, query: str) -> list[dict[str, Any]]:
        """Return products whose name or description contains ``query``.

        Matching is case-insensitive and treats ``query`` as literal text, not
        a regular expression. An empty query returns the whole catalogue.
        """
        if not query or not query.strip():
            return self.get_all_products()

        mask = self.df["name"].str.contains(
            query, case=False, na=False, regex=False
        ) | self.df["description"].str.contains(query, case=False, na=False, regex=False)

        return self._records(self.df[mask])

    def get_product_by_sku(self, sku: str) -> dict[str, Any] | None:
        """Return the product with the given SKU, or None if it is unknown."""
        if not sku or not sku.strip():
            return None

        matches = self.df[self.df["sku"].str.casefold() == sku.strip().casefold()]
        if matches.empty:
            return None

        return self._records(matches.head(1))[0]