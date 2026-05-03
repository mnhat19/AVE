from __future__ import annotations

import csv
import keyword
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import chardet
import pandas as pd

try:
    import polars as pl
except Exception:  # pragma: no cover - optional import for runtime
    pl = None

from ave.config import AveConfig, IngestionConfig
from ave.context import PipelineContext
from ave.exceptions import IngestionError, PipelineError
from ave.models.manifest import ColumnMeta, SchemaMeta, SourceFileMeta, build_source_manifest
from ave.models.trail import TrailEntry
from ave.utils.hashing import hash_dataframe, hash_dict, hash_file
from ave.utils.logging import get_logger
from ave.utils.normalization import (
    detect_locale,
    normalize_currency,
    normalize_date,
    normalize_number,
    normalize_text,
    to_snake_case,
)

logger = get_logger("layer1_ingestion")


def _detect_format(file_path: Path) -> str:
    with file_path.open("rb") as handle:
        magic_bytes = handle.read(4)
    if magic_bytes == b"PK\x03\x04":
        return "xlsx"

    suffix = file_path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return "xlsx"
    if suffix == ".csv":
        return "csv"

    try:
        with file_path.open("rb") as handle:
            raw_sample = handle.read(4096)
        sample = raw_sample.decode("utf-8", errors="ignore")
        csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        return "csv"
    except csv.Error as exc:
        raise IngestionError(f"Unsupported file format: {file_path.suffix}") from exc


def _detect_encoding(file_path: Path) -> Tuple[str, float]:
    with file_path.open("rb") as handle:
        sample = handle.read(100 * 1024)
    detection = chardet.detect(sample)
    encoding = detection.get("encoding") or "utf-8"
    confidence = float(detection.get("confidence") or 0.0)
    return encoding, confidence


def _detect_separator(file_path: Path, encoding: str) -> str:
    with file_path.open("r", encoding=encoding, errors="replace") as handle:
        lines = [handle.readline() for _ in range(5)]
    sample = "".join(lines)

    if not sample.strip():
        return ","

    sniffer = csv.Sniffer()
    try:
        dialect = sniffer.sniff(sample, delimiters=[",", ";", "\t", "|"])
        return dialect.delimiter
    except csv.Error:
        pass

    best_sep = ","
    best_score = -1
    for sep in [",", ";", "\t", "|"]:
        counts = []
        for line in lines:
            if not line.strip():
                continue
            reader = csv.reader([line], delimiter=sep)
            counts.append(len(next(reader)))
        if not counts:
            continue
        if len(set(counts)) == 1 and counts[0] > 1:
            score = counts[0]
            if score > best_score:
                best_sep = sep
                best_score = score
    return best_sep


def _parse_file(file_path: Path, config: IngestionConfig) -> Tuple[pd.DataFrame, dict]:
    file_format = _detect_format(file_path)
    parse_warnings: List[str] = []

    if file_path.stat().st_size == 0:
        raise IngestionError("File is empty.")

    encoding = config.encoding
    encoding_confidence = 1.0
    if encoding == "auto":
        encoding, encoding_confidence = _detect_encoding(file_path)
    elif encoding == "utf-8-bom":
        encoding = "utf-8-sig"

    encoding_errors = "strict"
    if encoding_confidence < 0.7:
        parse_warnings.append(
            "Low encoding confidence. Falling back to UTF-8 with replacement characters."
        )
        encoding = "utf-8"
        encoding_errors = "replace"

    separator = None
    sheet_used = None

    try:
        if file_format == "csv":
            if config.separator != "auto":
                separator = "|" if config.separator == "pipe" else config.separator
            else:
                separator = _detect_separator(file_path, encoding)

            raw_df = pd.read_csv(
                file_path,
                encoding=encoding,
                sep=separator,
                header=config.header_row,
                skiprows=config.skip_rows or None,
                on_bad_lines="warn",
                encoding_errors=encoding_errors,
            )
        elif file_format == "xlsx":
            sheet_used = config.sheet_name if config.sheet_name is not None else 0
            raw_df = pd.read_excel(
                file_path,
                engine="openpyxl",
                sheet_name=sheet_used,
                header=config.header_row,
                skiprows=config.skip_rows or None,
            )
        else:
            raise IngestionError("Unsupported file format.")
    except Exception as exc:
        raise IngestionError(f"Unable to parse file: {exc}") from exc

    parse_meta = {
        "format": file_format,
        "encoding_used": encoding,
        "separator_used": separator,
        "sheet_used": sheet_used,
        "rows_raw": len(raw_df),
        "parse_warnings": parse_warnings,
    }
    return raw_df, parse_meta


def _prune_empty(df: pd.DataFrame) -> Tuple[pd.DataFrame, int, int]:
    before_rows = len(df)
    pruned = df.dropna(how="all")
    rows_dropped = before_rows - len(pruned)

    before_cols = len(pruned.columns)
    pruned = pruned.dropna(axis=1, how="all")
    cols_dropped = before_cols - len(pruned.columns)
    return pruned, rows_dropped, cols_dropped


def _normalize_headers(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    mapping: Dict[str, str] = {}
    normalized = []
    seen: Dict[str, int] = {}

    for column in df.columns:
        original = str(column).strip()
        base = to_snake_case(original) or "column"
        if keyword.iskeyword(base):
            base = f"{base}_"
        index = seen.get(base, 0)
        name = base if index == 0 else f"{base}_{index}"
        seen[base] = index + 1
        normalized.append(name)
        mapping[original] = name

    renamed = df.copy()
    renamed.columns = normalized
    return renamed, mapping


def _infer_schema(
    df: pd.DataFrame, original_names: List[str], config: AveConfig
) -> List[ColumnMeta]:
    columns_meta: List[ColumnMeta] = []

    for idx, column in enumerate(df.columns):
        original_name = original_names[idx] if idx < len(original_names) else str(column)
        series = df[column]
        null_count = int(series.isna().sum())
        unique_count = int(series.dropna().nunique())
        sample_values = [str(val) for val in series.dropna().unique()[:3]]

        hint = config.columns.get(column)
        if hint and hint.dtype:
            inferred = hint.dtype
        else:
            samples = series.dropna().head(100).tolist()
            sample_count = len(samples)
            if sample_count == 0:
                inferred = "text"
            else:
                counts = {"date": 0, "numeric": 0, "currency": 0, "boolean": 0}
                for value in samples:
                    text = str(value).strip()
                    if not text:
                        continue
                    if normalize_date(value) is not None:
                        counts["date"] += 1
                    amount, currency = normalize_currency(value)
                    if amount is not None:
                        counts["numeric"] += 1
                    if currency is not None:
                        counts["currency"] += 1
                    if text.lower() in {"true", "false", "yes", "no", "1", "0"}:
                        counts["boolean"] += 1

                max_type = max(counts, key=counts.get)
                max_ratio = counts[max_type] / sample_count if sample_count else 0.0
                if max_ratio >= 0.8:
                    inferred = max_type
                elif max_ratio == 0:
                    inferred = "text"
                else:
                    inferred = "mixed"

        columns_meta.append(
            ColumnMeta(
                original_name=original_name,
                normalized_name=str(column),
                inferred_dtype=inferred,
                null_count=null_count,
                null_ratio=null_count / max(len(df), 1),
                unique_count=unique_count,
                sample_values=sample_values,
            )
        )

    return columns_meta


def _normalize_values(
    df: pd.DataFrame, schema: List[ColumnMeta], locale: str
) -> Tuple[pd.DataFrame, List[str]]:
    normalized = df.copy()
    warnings: List[str] = []

    for col_meta in schema:
        column = col_meta.normalized_name
        if column not in normalized.columns:
            continue
        series = normalized[column]

        if col_meta.inferred_dtype == "date":
            normalized[column] = series.apply(normalize_date)
        elif col_meta.inferred_dtype == "numeric":
            col_locale = detect_locale(series) if locale == "auto" else locale
            normalized[column] = series.apply(lambda v: normalize_number(v, col_locale))
        elif col_meta.inferred_dtype == "currency":
            currencies = set()
            values = []
            for value in series:
                amount, currency = normalize_currency(value)
                if currency:
                    currencies.add(currency)
                values.append(amount)
            normalized[column] = values
            if len(currencies) > 1:
                warnings.append(
                    f"Column '{column}' contains multiple currencies: {sorted(currencies)}"
                )
        elif col_meta.inferred_dtype == "boolean":
            normalized[column] = series.apply(
                lambda v: None if pd.isna(v) else str(v).strip().lower() in {"true", "yes", "1"}
            )
        else:
            normalized[column] = series.apply(normalize_text)

    return normalized, warnings


def _create_manifest(
    file_path: Path,
    parse_meta: dict,
    schema: List[ColumnMeta],
    df_raw: pd.DataFrame,
    df_normalized: pd.DataFrame,
    session_id: str,
    rows_dropped: int,
    cols_dropped: int,
    warnings: List[str],
) -> dict:
    source_file = SourceFileMeta(
        path=str(file_path.resolve()),
        filename=file_path.name,
        format=parse_meta.get("format", ""),
        size_bytes=file_path.stat().st_size,
        sha256_hash=hash_file(file_path),
        encoding=parse_meta.get("encoding_used", ""),
        sheet_name=parse_meta.get("sheet_used"),
    )

    schema_meta = SchemaMeta(
        row_count_raw=len(df_raw),
        row_count_after_cleaning=len(df_normalized),
        column_count=len(df_normalized.columns),
        dropped_empty_rows=rows_dropped,
        dropped_empty_cols=cols_dropped,
        columns=schema,
        parse_warnings=list(parse_meta.get("parse_warnings", [])) + warnings,
    )

    manifest = build_source_manifest(
        session_id=session_id,
        source_file=source_file,
        schema=schema_meta,
    )
    return manifest.to_dict()


def _switch_to_polars_if_large(df: pd.DataFrame, threshold: int) -> Any:
    if pl is None:
        return df
    if len(df) >= threshold:
        return pl.from_pandas(df)
    return df


def run(ctx: PipelineContext) -> PipelineContext:
    if ctx.input_file_path is None:
        raise PipelineError("input_file_path is required for ingestion", layer=1)

    file_path = Path(ctx.input_file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    start = time.perf_counter()
    if ctx.trail_writer:
        file_hash = hash_file(file_path)
        ctx.trail_writer.write(
            TrailEntry(
                session_id=ctx.session_id,
                agent_id="ingestion",
                action_type="FILE_RECEIVED",
                input_hash=file_hash,
                output_hash=file_hash,
                reasoning_summary="Input file received for ingestion.",
                duration_ms=0,
            )
        )

    raw_df, parse_meta = _parse_file(file_path, ctx.config.ingestion)
    if raw_df.empty:
        raise IngestionError("File contains no data rows.")
    ctx.raw_df = raw_df

    pruned_df, rows_dropped, cols_dropped = _prune_empty(raw_df)
    if pruned_df.empty:
        raise IngestionError("File contains no data rows after cleaning.")
    original_columns = [str(col).strip() for col in pruned_df.columns]
    normalized_df, _ = _normalize_headers(pruned_df)

    schema = _infer_schema(normalized_df, original_columns, ctx.config)
    normalized_values, norm_warnings = _normalize_values(normalized_df, schema, "auto")

    if ctx.trail_writer:
        ctx.trail_writer.write(
            TrailEntry(
                session_id=ctx.session_id,
                agent_id="ingestion",
                action_type="SCHEMA_NORMALIZED",
                input_hash=hash_dataframe(pruned_df),
                output_hash=hash_dataframe(normalized_values),
                reasoning_summary="Normalized headers and values.",
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
        )

    manifest = _create_manifest(
        file_path=file_path,
        parse_meta=parse_meta,
        schema=schema,
        df_raw=raw_df,
        df_normalized=normalized_values,
        session_id=ctx.session_id,
        rows_dropped=rows_dropped,
        cols_dropped=cols_dropped,
        warnings=norm_warnings,
    )

    ctx.source_manifest = manifest
    ctx.ingestion_report = {
        "row_count_raw": len(raw_df),
        "row_count_after_cleaning": len(normalized_values),
        "column_count": len(normalized_values.columns),
        "dropped_rows": rows_dropped,
        "dropped_cols": cols_dropped,
        "encoding_used": parse_meta.get("encoding_used"),
        "separator_used": parse_meta.get("separator_used"),
        "sheet_used": parse_meta.get("sheet_used"),
        "parse_warnings": parse_meta.get("parse_warnings", []),
        "normalization_warnings": norm_warnings,
    }

    if ctx.trail_writer:
        ctx.trail_writer.write(
            TrailEntry(
                session_id=ctx.session_id,
                agent_id="ingestion",
                action_type="MANIFEST_CREATED",
                input_hash=hash_dataframe(normalized_values),
                output_hash=hash_dict(manifest),
                reasoning_summary="Source manifest created.",
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
        )

    ctx.normalized_df = _switch_to_polars_if_large(
        normalized_values, ctx.config.pipeline.use_polars_threshold
    )
    ctx.current_layer = 1

    return ctx
