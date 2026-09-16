from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import streamlit as st


def _file_version(path: Path) -> tuple[int, int]:
    """Return a cache-busting token that changes only when the file changes."""
    stat = path.stat()
    return int(stat.st_mtime_ns), int(stat.st_size)


@st.cache_data(show_spinner=False)
def _load_data_cached(
    file_path: str,
    file_version: tuple[int, int],
    usecols: tuple[str, ...] | None = None,
    dtype_items: tuple[tuple[str, str], ...] | None = None,
    sheet_name: str | int = 0,
    json_lines: bool = False,
) -> pd.DataFrame:
    """Load CSV, Excel, JSON, or JSONL data once and reuse it across reruns."""
    del file_version  # intentionally part of the Streamlit cache key

    path = Path(file_path)
    suffix = path.suffix.lower()
    dtype = dict(dtype_items or ())

    with st.spinner(f"Loading {path.name}..."):
        if suffix == ".csv":
            return pd.read_csv(
                path,
                usecols=list(usecols) if usecols else None,
                dtype=dtype or None,
                low_memory=False,
                memory_map=True,
            )

        if suffix in {".xlsx", ".xlsm"}:
            return pd.read_excel(
                path,
                sheet_name=sheet_name,
                usecols=list(usecols) if usecols else None,
                dtype=dtype or None,
                engine="openpyxl",
            )

        if suffix == ".xls":
            return pd.read_excel(
                path,
                sheet_name=sheet_name,
                usecols=list(usecols) if usecols else None,
                dtype=dtype or None,
            )

        if suffix in {".json", ".jsonl"}:
            df = pd.read_json(
                path,
                lines=json_lines or suffix == ".jsonl",
            )

            if usecols:
                columns = [name for name in usecols if name in df.columns]
                df = df.loc[:, columns]

            if dtype:
                valid_dtype = {
                    name: value
                    for name, value in dtype.items()
                    if name in df.columns
                }
                if valid_dtype:
                    df = df.astype(valid_dtype, copy=False)

            return df

        raise ValueError(
            f"Unsupported file type: {suffix or '<no extension>'}. "
            "Supported types: CSV, XLSX/XLSM/XLS, JSON, JSONL."
        )


def load_data(
    file_path: str | Path,
    *,
    usecols: Sequence[str] | None = None,
    dtype: Mapping[str, Any] | None = None,
    sheet_name: str | int = 0,
    json_lines: bool = False,
) -> pd.DataFrame:
    """Public cached loader for Streamlit applications."""
    path = Path(file_path).expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    if not path.is_file():
        raise ValueError(f"Expected a file but received: {path}")

    normalized_usecols = tuple(usecols) if usecols else None
    normalized_dtype = (
        tuple(
            sorted(
                (str(column), str(pandas_dtype))
                for column, pandas_dtype in dtype.items()
            )
        )
        if dtype
        else None
    )

    return _load_data_cached(
        str(path),
        _file_version(path),
        normalized_usecols,
        normalized_dtype,
        sheet_name,
        json_lines,
    )
