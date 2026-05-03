from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional import for runtime
    pd = None

try:
    import polars as pl
except Exception:  # pragma: no cover - optional import for runtime
    pl = None


def hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def hash_string(value: str) -> str:
    hasher = hashlib.sha256()
    hasher.update(value.encode("utf-8"))
    return hasher.hexdigest()


def hash_dict(data: dict) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hash_string(payload)


def _to_pandas(df: Any):
    if pl is not None and isinstance(df, pl.DataFrame):
        return df.to_pandas()
    return df


def hash_dataframe(df: Any) -> str:
    if pd is None:
        raise TypeError("pandas is required for hash_dataframe")
    pandas_df = _to_pandas(df)
    if not isinstance(pandas_df, pd.DataFrame):
        raise TypeError("hash_dataframe expects a pandas or polars DataFrame")
    # Convert to strings to guarantee a stable, sortable representation.
    sortable = pandas_df.astype(str)
    sortable = sortable.reindex(sorted(sortable.columns), axis=1)
    if len(sortable.columns) > 0 and len(sortable) > 0:
        sortable = sortable.sort_values(by=list(sortable.columns), kind="mergesort")
    sortable = sortable.reset_index(drop=True)
    csv_data = sortable.to_csv(index=False)
    return hash_string(csv_data)


def verify_hash(data: Any, expected_hash: str) -> bool:
    if isinstance(data, Path):
        actual = hash_file(data)
    elif isinstance(data, str):
        actual = hash_string(data)
    elif isinstance(data, dict):
        actual = hash_dict(data)
    else:
        raise TypeError("verify_hash expects Path, str, or dict")
    return actual == expected_hash
