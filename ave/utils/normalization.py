from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime
from typing import Any, Iterable, List, Optional, Tuple

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional import for runtime
    pd = None

try:
    import polars as pl
except Exception:  # pragma: no cover - optional import for runtime
    pl = None

_DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%Y%m%d"]


def _iter_values(series: Any) -> List[Any]:
    if series is None:
        return []
    if hasattr(series, "to_list"):
        return list(series.to_list())
    if isinstance(series, (list, tuple, set)):
        return list(series)
    return [series]


def _score_locale(value: str) -> Optional[str]:
    text = value.strip()
    if not text:
        return None
    text = re.sub(r"[^0-9,\.\-]", "", text)
    if not text or text in {"-", ",", "."}:
        return None

    if "," in text and "." in text:
        return "vi" if text.rfind(",") > text.rfind(".") else "en"

    if "," in text:
        parts = text.split(",")
        last = parts[-1]
        if len(last) == 2:
            return "vi"
        if len(last) == 3 and all(len(p) == 3 for p in parts[1:]):
            return "en"
        return None

    if "." in text:
        parts = text.split(".")
        last = parts[-1]
        if len(last) == 2:
            return "en"
        if len(last) == 3 and all(len(p) == 3 for p in parts[1:]):
            return "vi"
    return None


def detect_locale(series: Any) -> str:
    values = _iter_values(series)
    cleaned = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, float) and math.isnan(value):
            continue
        text = str(value).strip()
        if text:
            cleaned.append(text)

    if len(cleaned) < 5:
        return "en"

    scores = {"vi": 0, "en": 0}
    for text in cleaned[:20]:
        scored = _score_locale(text)
        if scored:
            scores[scored] += 1

    return "vi" if scores["vi"] > scores["en"] else "en"


def normalize_number(value: Any, locale: str = "auto") -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]

    text = re.sub(r"[^0-9,\.\-]", "", text)
    if not text:
        return None

    if locale == "auto":
        locale = _score_locale(text) or detect_locale([text])

    if locale == "vi":
        text = text.replace(".", "")
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")

    try:
        number = float(text)
    except ValueError:
        return None

    return -number if negative else number


def normalize_date(value: Any) -> Optional[str]:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if pd is not None and isinstance(value, pd.Timestamp):
        return value.to_pydatetime().date().isoformat()

    text = str(value).strip()
    if not text:
        return None

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def normalize_currency(value: Any) -> Tuple[Optional[float], Optional[str]]:
    if value is None:
        return None, None

    text = str(value).strip()
    if not text:
        return None, None

    currency = None
    upper_text = text.upper()
    if "VND" in upper_text:
        currency = "VND"
        text = re.sub(r"(?i)VND", "", text)
    if "USD" in upper_text:
        currency = "USD"
        text = re.sub(r"(?i)USD", "", text)

    if "\u20ab" in text:
        currency = currency or "VND"
        text = text.replace("\u20ab", "")
    if "$" in text:
        currency = currency or "USD"
        text = text.replace("$", "")

    amount = normalize_number(text, locale="auto")
    return amount, currency


def strip_pii_if_needed(df: Any, columns_to_strip: List[str]):
    if df is None or not columns_to_strip:
        return df

    if pl is not None and isinstance(df, pl.DataFrame):
        replacements = [
            pl.lit("[REDACTED]").alias(col)
            for col in columns_to_strip
            if col in df.columns
        ]
        if not replacements:
            return df
        return df.with_columns(replacements)

    if pd is not None and isinstance(df, pd.DataFrame):
        redacted = df.copy()
        for col in columns_to_strip:
            if col in redacted.columns:
                redacted[col] = "[REDACTED]"
        return redacted

    return df


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return unicodedata.normalize("NFC", text)


def to_snake_case(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    text = text.strip("_")
    return text
