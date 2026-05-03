from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from ave.config import AveConfig, ColumnConfig
from ave.context import PipelineContext
from ave.exceptions import PipelineError
from ave.models.finding import Finding
from ave.models.trail import TrailEntry
from ave.utils.hashing import hash_dataframe, hash_dict
from ave.utils.logging import get_logger

logger = get_logger("layer2_integrity")

_SEVERITY_SCORE = {"high": 3, "medium": 2, "low": 1}


def _ensure_pandas(df: Any) -> pd.DataFrame:
    if isinstance(df, pd.DataFrame):
        return df.reset_index(drop=True)

    try:
        import polars as pl
    except Exception:  # pragma: no cover - optional import for runtime
        pl = None

    if pl is not None and isinstance(df, pl.DataFrame):
        return df.to_pandas().reset_index(drop=True)

    raise TypeError("Integrity checks expect a pandas or polars DataFrame")


def _make_finding(
    ctx: PipelineContext,
    rule_id: str,
    rule_name: str,
    row_index: int,
    row_data: dict,
    severity: str,
    reasoning: str,
    column_name: Optional[str] = None,
    actual_value: Optional[Any] = None,
    expected_value: Optional[Any] = None,
) -> Finding:
    return Finding(
        session_id=ctx.session_id,
        layer=2,
        finding_type="integrity",
        rule_id=rule_id,
        rule_name=rule_name,
        row_index=row_index,
        row_data=row_data,
        column_name=column_name,
        actual_value=actual_value,
        expected_value=expected_value,
        severity=severity,
        confidence=1.0,
        reasoning=reasoning,
        detection_method="rule",
    )


def _column_config(config: AveConfig, column: str) -> Optional[ColumnConfig]:
    return config.columns.get(column)


def _check_nulls(df: pd.DataFrame, ctx: PipelineContext) -> List[Finding]:
    findings: List[Finding] = []
    for column in df.columns:
        series = df[column]
        null_mask = series.isna()
        null_ratio = float(null_mask.mean()) if len(series) else 0.0

        col_config = _column_config(ctx.config, column)
        threshold = ctx.config.integrity.null_threshold_default
        if col_config and col_config.null_threshold is not None:
            threshold = col_config.null_threshold

        if null_ratio > threshold:
            severity = "high" if (col_config and col_config.required) else "low"
            for idx in df[null_mask].index:
                row = df.loc[idx].to_dict()
                findings.append(
                    _make_finding(
                        ctx,
                        "IC-001",
                        "Null completeness",
                        int(idx),
                        row,
                        severity,
                        f"Null value in column '{column}'",
                        column_name=column,
                        actual_value=None,
                        expected_value="not null",
                    )
                )
    return findings


def _check_duplicate_rows(df: pd.DataFrame, ctx: PipelineContext) -> List[Finding]:
    findings: List[Finding] = []
    dup_mask = df.duplicated(keep=False)
    for idx in df[dup_mask].index:
        row = df.loc[idx].to_dict()
        findings.append(
            _make_finding(
                ctx,
                "IC-002",
                "Duplicate row detection",
                int(idx),
                row,
                "high",
                "Exact duplicate row detected",
            )
        )
    return findings


def _check_duplicate_keys(df: pd.DataFrame, ctx: PipelineContext) -> List[Finding]:
    findings: List[Finding] = []
    keys = ctx.config.primary_key_columns
    if not keys:
        return findings
    missing = [key for key in keys if key not in df.columns]
    if missing:
        logger.warning("Primary key columns missing: %s", missing)
        return findings

    dup_mask = df.duplicated(subset=keys, keep=False)
    for idx in df[dup_mask].index:
        row = df.loc[idx].to_dict()
        findings.append(
            _make_finding(
                ctx,
                "IC-003",
                "Duplicate key detection",
                int(idx),
                row,
                "high",
                f"Duplicate key detected for columns {keys}",
            )
        )
    return findings


def _date_bounds(col_config: Optional[ColumnConfig]) -> tuple[datetime, datetime]:
    min_date = datetime(1900, 1, 1)
    max_date = datetime.now() + timedelta(days=1)
    if col_config and col_config.min_date:
        min_date = datetime.fromisoformat(col_config.min_date)
    if col_config and col_config.max_date:
        max_date = datetime.fromisoformat(col_config.max_date)
    return min_date, max_date


def _check_date_ranges(df: pd.DataFrame, ctx: PipelineContext) -> List[Finding]:
    findings: List[Finding] = []
    date_columns = set()
    for column in df.columns:
        col_config = _column_config(ctx.config, column)
        if col_config and col_config.dtype == "date":
            date_columns.add(column)
        elif "date" in column:
            date_columns.add(column)

    for column in sorted(date_columns):
        series = pd.to_datetime(df[column], errors="coerce")
        col_config = _column_config(ctx.config, column)
        min_date, max_date = _date_bounds(col_config)
        mask = (series.notna()) & ((series < min_date) | (series > max_date))
        for idx in df[mask].index:
            row = df.loc[idx].to_dict()
            actual = row.get(column)
            findings.append(
                _make_finding(
                    ctx,
                    "IC-004",
                    "Date range validity",
                    int(idx),
                    row,
                    "medium",
                    f"Date out of range for '{column}'",
                    column_name=column,
                    actual_value=actual,
                    expected_value=f"{min_date.date()}..{max_date.date()}",
                )
            )
    return findings


def _check_numeric_ranges(df: pd.DataFrame, ctx: PipelineContext) -> List[Finding]:
    findings: List[Finding] = []
    for column in df.columns:
        col_config = _column_config(ctx.config, column)
        if not col_config or (col_config.min_value is None and col_config.max_value is None):
            continue
        series = pd.to_numeric(df[column], errors="coerce")
        mask = pd.Series(False, index=df.index)
        if col_config.min_value is not None:
            mask |= series < col_config.min_value
        if col_config.max_value is not None:
            mask |= series > col_config.max_value
        mask &= series.notna()
        for idx in df[mask].index:
            row = df.loc[idx].to_dict()
            actual = row.get(column)
            findings.append(
                _make_finding(
                    ctx,
                    "IC-005",
                    "Numeric range validity",
                    int(idx),
                    row,
                    "medium",
                    f"Numeric value out of range for '{column}'",
                    column_name=column,
                    actual_value=actual,
                    expected_value=f"{col_config.min_value}..{col_config.max_value}",
                )
            )
    return findings


def _check_negative_amounts(df: pd.DataFrame, ctx: PipelineContext) -> List[Finding]:
    findings: List[Finding] = []
    for column in df.columns:
        col_config = _column_config(ctx.config, column)
        if col_config and col_config.allowed_negative:
            continue

        if col_config and col_config.dtype not in {None, "numeric", "currency"}:
            continue

        if "amount" not in column and col_config is None:
            continue

        if col_config and col_config.min_value is not None and col_config.min_value < 0:
            continue

        series = pd.to_numeric(df[column], errors="coerce")
        mask = series.notna() & (series < 0)
        for idx in df[mask].index:
            row = df.loc[idx].to_dict()
            actual = row.get(column)
            findings.append(
                _make_finding(
                    ctx,
                    "IC-006",
                    "Negative amount detection",
                    int(idx),
                    row,
                    "medium",
                    f"Negative amount detected in '{column}'",
                    column_name=column,
                    actual_value=actual,
                    expected_value=">= 0",
                )
            )
    return findings


def _check_format_consistency(df: pd.DataFrame, ctx: PipelineContext) -> List[Finding]:
    findings: List[Finding] = []
    for column in df.columns:
        col_config = _column_config(ctx.config, column)
        if not col_config or not col_config.pattern:
            continue
        series = df[column]
        text_values = series.fillna("").astype(str)
        mask = series.notna() & (~text_values.str.contains(col_config.pattern, regex=True))
        for idx in df[mask].index:
            row = df.loc[idx].to_dict()
            actual = row.get(column)
            findings.append(
                _make_finding(
                    ctx,
                    "IC-007",
                    "Format consistency",
                    int(idx),
                    row,
                    "low",
                    f"Value does not match pattern for '{column}'",
                    column_name=column,
                    actual_value=actual,
                    expected_value=col_config.pattern,
                )
            )
    return findings


def _check_referential_integrity(df: pd.DataFrame, ctx: PipelineContext) -> List[Finding]:
    findings: List[Finding] = []
    for column in df.columns:
        col_config = _column_config(ctx.config, column)
        if not col_config or not col_config.reference_values:
            continue
        reference_set = set(col_config.reference_values)
        series = df[column]
        mask = series.notna() & (~series.isin(reference_set))
        for idx in df[mask].index:
            row = df.loc[idx].to_dict()
            actual = row.get(column)
            findings.append(
                _make_finding(
                    ctx,
                    "IC-008",
                    "Referential integrity",
                    int(idx),
                    row,
                    "high",
                    f"Value not in reference set for '{column}'",
                    column_name=column,
                    actual_value=actual,
                    expected_value="reference set",
                )
            )
    return findings


def _compare_series(left: pd.Series, right: pd.Series, op: str) -> pd.Series:
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == "!=":
        return left != right
    return left == right


def _compute_right_expression(df: pd.DataFrame, rule: Dict[str, Any]) -> Optional[pd.Series]:
    right = rule.get("right")
    if right:
        return df[right] if right in df.columns else None

    right_fields = rule.get("right_fields") or []
    if not right_fields:
        return None
    missing = [field for field in right_fields if field not in df.columns]
    if missing:
        logger.warning("Cross-check missing fields: %s", missing)
        return None

    op = (rule.get("right_op") or "mul").lower()
    series = pd.to_numeric(df[right_fields[0]], errors="coerce")
    for field in right_fields[1:]:
        values = pd.to_numeric(df[field], errors="coerce")
        if op == "sum":
            series = series + values
        else:
            series = series * values
    return series


def _check_cross_column_consistency(df: pd.DataFrame, ctx: PipelineContext) -> List[Finding]:
    findings: List[Finding] = []
    rules = ctx.config.integrity.cross_checks
    if not rules:
        return findings

    for rule in rules:
        left = rule.get("left")
        op = rule.get("op", "==")
        if not left or left not in df.columns:
            logger.warning("Cross-check missing left column: %s", left)
            continue

        left_series = df[left]
        right_series = _compute_right_expression(df, rule)
        if right_series is None:
            continue

        left_numeric = pd.to_numeric(left_series, errors="coerce")
        right_numeric = pd.to_numeric(right_series, errors="coerce")

        if left_numeric.notna().any() and right_numeric.notna().any():
            left_cmp = left_numeric
            right_cmp = right_numeric
        else:
            left_cmp = pd.to_datetime(left_series, errors="coerce")
            right_cmp = pd.to_datetime(right_series, errors="coerce")

        mask = left_cmp.notna() & right_cmp.notna() & (~_compare_series(left_cmp, right_cmp, op))
        for idx in df[mask].index:
            row = df.loc[idx].to_dict()
            findings.append(
                _make_finding(
                    ctx,
                    "IC-009",
                    "Cross-column logical consistency",
                    int(idx),
                    row,
                    "medium",
                    f"Cross-column rule failed: {left} {op} {rule.get('right') or rule.get('right_fields')}",
                    column_name=left,
                    actual_value=row.get(left),
                    expected_value=rule.get("right") or rule.get("right_fields"),
                )
            )
    return findings


def _check_outliers(df: pd.DataFrame, ctx: PipelineContext) -> List[Finding]:
    findings: List[Finding] = []
    multiplier = ctx.config.integrity.outlier_std_multiplier

    for column in df.columns:
        series = pd.to_numeric(df[column], errors="coerce")
        if series.notna().sum() < 2:
            continue
        mean = series.mean()
        std = series.std()
        if std == 0 or pd.isna(std):
            continue
        mask = series.notna() & ((series < mean - multiplier * std) | (series > mean + multiplier * std))
        for idx in df[mask].index:
            row = df.loc[idx].to_dict()
            actual = row.get(column)
            findings.append(
                _make_finding(
                    ctx,
                    "IC-010",
                    "Statistical outlier detection",
                    int(idx),
                    row,
                    "low",
                    f"Outlier detected in '{column}'",
                    column_name=column,
                    actual_value=actual,
                    expected_value=f"mean±{multiplier}*std",
                )
            )
    return findings


def validate_prerequisites(ctx: PipelineContext) -> None:
    if ctx.normalized_df is None:
        raise PipelineError("normalized_df is required for integrity checks", layer=2)


def run(ctx: PipelineContext) -> PipelineContext:
    validate_prerequisites(ctx)
    start = time.perf_counter()

    df = _ensure_pandas(ctx.normalized_df)

    findings: List[Finding] = []
    checks: Dict[str, Dict[str, Any]] = {}

    check_definitions = [
        ("IC-001", "Null completeness", _check_nulls),
        ("IC-002", "Duplicate row detection", _check_duplicate_rows),
        ("IC-003", "Duplicate key detection", _check_duplicate_keys),
        ("IC-004", "Date range validity", _check_date_ranges),
        ("IC-005", "Numeric range validity", _check_numeric_ranges),
        ("IC-006", "Negative amount detection", _check_negative_amounts),
        ("IC-007", "Format consistency", _check_format_consistency),
        ("IC-008", "Referential integrity", _check_referential_integrity),
        ("IC-009", "Cross-column logical consistency", _check_cross_column_consistency),
        ("IC-010", "Statistical outlier detection", _check_outliers),
    ]

    for check_id, name, handler in check_definitions:
        check_findings = handler(df, ctx)
        findings.extend(check_findings)
        score = sum(_SEVERITY_SCORE.get(f.severity, 0) for f in check_findings)
        checks[check_id] = {
            "name": name,
            "findings": len(check_findings),
            "severity_score": score,
        }

    total_score = sum(_SEVERITY_SCORE.get(f.severity, 0) for f in findings)
    if total_score == 0:
        overall = "CLEAN"
    elif total_score <= 10:
        overall = "MINOR"
    elif total_score <= 30:
        overall = "MODERATE"
    else:
        overall = "SEVERE"

    ctx.integrity_findings = findings
    ctx.integrity_report = {
        "overall_rating": overall,
        "total_score": total_score,
        "checks_run": len(check_definitions),
        "findings_count": len(findings),
        "checks": checks,
    }

    if ctx.trail_writer:
        ctx.trail_writer.write(
            TrailEntry(
                session_id=ctx.session_id,
                agent_id="integrity",
                action_type="INTEGRITY_CHECK_RUN",
                input_hash=hash_dataframe(df),
                output_hash=hash_dict(ctx.integrity_report),
                reasoning_summary="Integrity checks completed.",
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
        )

    ctx.current_layer = 2
    return ctx
