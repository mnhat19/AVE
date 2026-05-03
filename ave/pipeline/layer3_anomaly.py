from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Mapping, Optional, Tuple

from ave.context import PipelineContext
from ave.engines.llm_client import LLMRouter
from ave.engines.rule_engine import RuleEngine, materialize_rules_file
from ave.exceptions import PipelineError
from ave.models.finding import Finding
from ave.models.trail import TrailEntry
from ave.utils.hashing import hash_dataframe, hash_dict
from ave.utils.logging import get_logger
from ave.utils.normalization import strip_pii_if_needed

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional import for runtime
    pd = None

if TYPE_CHECKING:
    from pandas import DataFrame

logger = get_logger("layer3_anomaly")


def validate_prerequisites(ctx: PipelineContext) -> None:
    if ctx.normalized_df is None:
        raise PipelineError("normalized_df is required for anomaly detection", layer=3)


def _ensure_pandas(df: Any) -> "DataFrame":
    if pd is None:
        raise TypeError("pandas is required for anomaly detection")
    if isinstance(df, pd.DataFrame):
        return df.reset_index(drop=True)

    try:
        import polars as pl
    except Exception:  # pragma: no cover - optional import for runtime
        pl = None

    if pl is not None and isinstance(df, pl.DataFrame):
        return df.to_pandas().reset_index(drop=True)

    raise TypeError("Anomaly checks expect a pandas or polars DataFrame")


def _find_column(columns: List[str], keyword: str) -> Optional[str]:
    needle = keyword.lower()
    for column in columns:
        if needle in column.lower():
            return column
    return None


def _find_amount_column(columns: List[str], ctx: PipelineContext) -> Optional[str]:
    for name, col_config in ctx.config.columns.items():
        if name in columns and "amount" in name:
            if col_config.dtype in {None, "numeric", "currency"}:
                return name
    return _find_column(columns, "amount")


def _json_safe_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if pd is not None and isinstance(value, pd.Timestamp):
        return value.to_pydatetime().isoformat()
    return value


def _row_to_dict(row: Mapping[Any, Any]) -> Dict[str, Any]:
    return {str(key): _json_safe_value(value) for key, value in row.items()}


def _build_column_definitions(ctx: PipelineContext, df: Any) -> List[Dict[str, str]]:
    if ctx.source_manifest and isinstance(ctx.source_manifest, dict):
        schema = ctx.source_manifest.get("schema", {})
        columns = schema.get("columns", [])
        if isinstance(columns, list) and columns:
            return [
                {
                    "name": col.get("normalized_name") or col.get("original_name") or "",
                    "dtype": col.get("inferred_dtype") or "text",
                }
                for col in columns
            ]

    data = _ensure_pandas(df)
    return [{"name": str(col), "dtype": "text"} for col in data.columns]


def _prepare_llm_batches(
    df: Any,
    already_flagged_indices: Iterable[int],
    batch_size: int,
    pii_columns: List[str],
) -> List[List[Dict[str, Any]]]:
    data = _ensure_pandas(df)
    flagged = {int(idx) for idx in already_flagged_indices}

    sanitized = strip_pii_if_needed(data, pii_columns)
    sanitized = _ensure_pandas(sanitized)
    if pii_columns and any(col in data.columns for col in pii_columns):
        logger.info("Stripped PII columns for LLM: %s", pii_columns)

    rows: List[Dict[str, Any]] = []
    for idx in range(len(sanitized)):
        if idx in flagged:
            continue
        row = sanitized.iloc[idx].to_dict()
        payload = _row_to_dict(row)
        payload["row_index"] = int(idx)
        rows.append(payload)

    batches: List[List[Dict[str, Any]]] = []
    for offset in range(0, len(rows), batch_size):
        batches.append(rows[offset : offset + batch_size])
    return batches


def _build_anomaly_prompt(
    batch: List[Dict[str, Any]],
    column_defs: List[Dict[str, str]],
    audit_context: str,
    flagged: Iterable[int],
) -> str:
    transactions_json = json.dumps(batch, ensure_ascii=False)
    column_definitions = json.dumps(column_defs, ensure_ascii=False)
    flagged_list = sorted({int(idx) for idx in flagged})

    return (
        "You are an expert auditor reviewing financial transaction data.\n"
        f"Audit context: {audit_context}\n"
        f"Column definitions: {column_definitions}\n\n"
        f"Review the following {len(batch)} transactions and identify any that appear anomalous,\n"
        "suspicious, or warrant further investigation based on audit best practices.\n\n"
        "Transactions (JSON):\n"
        f"{transactions_json}\n\n"
        f"Previously flagged rows (do not re-flag): {flagged_list}\n\n"
        "Respond ONLY with a JSON object in this exact format:\n"
        "{\n"
        "  \"flagged\": [\n"
        "    {\n"
        "      \"row_index\": <integer>,\n"
        "      \"reasoning\": \"<string: specific reason, referencing column values>\",\n"
        "      \"confidence\": <float 0.0-1.0>,\n"
        "      \"severity\": \"high|medium|low\"\n"
        "    }\n"
        "  ],\n"
        "  \"summary\": \"<string: overall observations>\"\n"
        "}\n\n"
        "If no anomalies found, return {\"flagged\": [], \"summary\": "
        "\"No additional anomalies detected.\"}"
    )


def _reasoning_mentions_value(reasoning: str, row_data: Dict[str, Any]) -> bool:
    text = reasoning.lower()
    for value in row_data.values():
        if value is None:
            continue
        value_text = str(value).strip().lower()
        if len(value_text) < 3:
            continue
        if value_text in text:
            return True
    return False


def _parse_llm_findings(
    response: dict,
    df: Any,
    session_id: str,
) -> List[Finding]:
    data = _ensure_pandas(df)
    flagged = response.get("flagged", [])
    if not isinstance(flagged, list):
        return []

    findings: List[Finding] = []
    for item in flagged:
        if not isinstance(item, dict):
            continue
        row_index = item.get("row_index")
        if row_index is None:
            continue
        try:
            row_index = int(row_index)
        except (TypeError, ValueError):
            continue
        if row_index < 0 or row_index >= len(data):
            continue

        confidence = item.get("confidence")
        if confidence is None:
            continue
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            continue
        if not (0.0 <= confidence_value <= 1.0):
            continue

        severity = str(item.get("severity") or "").lower()
        if severity not in {"high", "medium", "low"}:
            continue

        reasoning = str(item.get("reasoning") or "").strip()
        if not reasoning:
            continue

        row = data.iloc[row_index].to_dict()
        row_payload = _row_to_dict(row)
        if not _reasoning_mentions_value(reasoning, row_payload):
            continue

        findings.append(
            Finding(
                session_id=session_id,
                layer=3,
                finding_type="anomaly",
                rule_id=None,
                rule_name="LLM",
                row_index=int(row_index),
                row_data=row_payload,
                column_name=None,
                actual_value=None,
                expected_value=None,
                severity=severity,
                confidence=confidence_value,
                reasoning=reasoning,
                detection_method="llm",
            )
        )

    return findings


def _run_llm_detection(
    ctx: PipelineContext,
    already_flagged_indices: Iterable[int],
) -> List[Finding]:
    router = LLMRouter(ctx.config.llm.provider, ctx.config.llm)
    client = router.get_client()
    if client is None:
        logger.warning("LLM is not available; skipping LLM anomaly detection.")
        return []

    data = _ensure_pandas(ctx.normalized_df)
    column_defs = _build_column_definitions(ctx, data)
    audit_context = f"Audit standard: {ctx.config.audit_standard}"

    batches = _prepare_llm_batches(
        data,
        already_flagged_indices=already_flagged_indices,
        batch_size=ctx.config.llm.batch_size,
        pii_columns=ctx.config.llm.strip_pii_columns,
    )

    findings: List[Finding] = []
    for batch in batches:
        prompt = _build_anomaly_prompt(batch, column_defs, audit_context, already_flagged_indices)
        if ctx.trail_writer:
            ctx.trail_writer.write(
                TrailEntry(
                    session_id=ctx.session_id,
                    agent_id="anomaly",
                    action_type="LLM_QUERY_SENT",
                    input_hash=hash_dict({"rows": len(batch)}),
                    output_hash="",
                    reasoning_summary="LLM query submitted.",
                    duration_ms=0,
                )
            )

        try:
            response = client.complete_json(
                prompt,
                system_prompt=None,
                max_retries=ctx.config.llm.max_retries,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("LLM batch failed: %s", exc)
            continue

        if ctx.trail_writer:
            ctx.trail_writer.write(
                TrailEntry(
                    session_id=ctx.session_id,
                    agent_id="anomaly",
                    action_type="LLM_RESPONSE_RECEIVED",
                    input_hash="",
                    output_hash=hash_dict(response),
                    reasoning_summary="LLM response received.",
                    duration_ms=0,
                )
            )

        findings.extend(_parse_llm_findings(response, data, ctx.session_id))

    return findings


def _check_r018_frequent_small_transactions(
    df: Any,
    ctx: PipelineContext,
) -> List[Finding]:
    if pd is None:
        raise TypeError("pandas is required for R018 detection")
    data = _ensure_pandas(df)
    columns = list(data.columns)

    vendor_col = _find_column(columns, "vendor")
    date_col = _find_column(columns, "date")
    amount_col = _find_amount_column(columns, ctx)

    if not vendor_col or not date_col or not amount_col:
        logger.warning(
            "R018 skipped: missing required columns (vendor/date/amount)."
        )
        return []

    threshold = ctx.config.approval_thresholds.level_1
    amount_series = pd.to_numeric(data[amount_col], errors="coerce")
    date_key = pd.to_datetime(data[date_col], errors="coerce").dt.date

    base = pd.DataFrame(
        {
            "vendor": data[vendor_col],
            "date_key": date_key,
            "amount": amount_series,
        }
    ).dropna(subset=["vendor", "date_key", "amount"])

    if base.empty:
        return []

    group_counts = base.groupby(["vendor", "date_key"]).size()
    group_max = base.groupby(["vendor", "date_key"])["amount"].max()

    flagged: List[Tuple[Any, Any, int]] = []
    for key, count in group_counts.items():
        if not isinstance(key, tuple) or len(key) < 2:
            continue
        max_amount = group_max.get(key)
        if max_amount is not None and count > 5 and max_amount < threshold:
            flagged.append((key[0], key[1], int(count)))

    if not flagged:
        return []

    findings: List[Finding] = []
    for vendor, date_value, count in flagged:
        mask = (
            (data[vendor_col] == vendor)
            & (date_key == date_value)
            & amount_series.notna()
            & (amount_series < threshold)
        )
        for idx in data[mask].index:
            row = data.loc[idx].to_dict()
            findings.append(
                Finding(
                    session_id=ctx.session_id,
                    layer=3,
                    finding_type="anomaly",
                    rule_id="R018",
                    rule_name="Frequent small transactions",
                    row_index=int(idx) if isinstance(idx, (int, float)) else idx,
                    row_data=row,
                    column_name=amount_col,
                    actual_value=row.get(amount_col),
                    expected_value=f"< {threshold} with <= 5 per vendor/day",
                    severity="high",
                    confidence=1.0,
                    reasoning=(
                        f"Vendor {vendor} has {count} transactions on {date_value} "
                        f"below threshold {threshold}"
                    ),
                    detection_method="rule",
                )
            )

    return findings


def _summarize_findings(findings) -> Dict[str, Any]:
    by_rule: Dict[str, int] = {}
    by_severity = {"high": 0, "medium": 0, "low": 0}
    llm_count = 0

    for finding in findings:
        by_rule[finding.rule_id or "unknown"] = by_rule.get(finding.rule_id or "unknown", 0) + 1
        if finding.severity in by_severity:
            by_severity[finding.severity] += 1
        if finding.detection_method == "llm":
            llm_count += 1

    return {
        "total_flagged": len(findings),
        "by_severity": by_severity,
        "by_rule": by_rule,
        "llm_assisted_count": llm_count,
    }


def _run_rule_engine(ctx: PipelineContext, rules_path: Path) -> Tuple[List[Finding], Dict[str, int]]:
    engine = RuleEngine(config=ctx.config)
    engine.load_from_yaml(rules_path)

    findings: List[Finding] = []
    per_rule: Dict[str, int] = {}

    for rule in engine.rules:
        if rule.id == "R018":
            logger.debug("Skipping R018 in rule engine; handled separately.")
            continue
        rule_findings = engine.evaluate_rule(rule, ctx.normalized_df, session_id=ctx.session_id)
        if rule_findings:
            per_rule[rule.id] = len(rule_findings)
            findings.extend(rule_findings)
            logger.debug("Rule %s produced %d findings", rule.id, len(rule_findings))

    return findings, per_rule


def run(ctx: PipelineContext) -> PipelineContext:
    validate_prerequisites(ctx)
    start = time.perf_counter()

    rules_path = Path(ctx.config.rules_file)
    if not rules_path.exists():
        raise PipelineError(f"Rules file not found: {rules_path}", layer=3)

    materialized_path = materialize_rules_file(
        rules_path,
        ctx.config,
        ctx.output_dir,
        ctx.session_id,
    )

    rule_findings, per_rule_counts = _run_rule_engine(ctx, materialized_path)
    r018_findings = _check_r018_frequent_small_transactions(ctx.normalized_df, ctx)

    findings = rule_findings + r018_findings

    if ctx.config.llm.enabled:
        flagged_indices = set()
        for finding in findings:
            try:
                flagged_indices.add(int(finding.row_index))
            except (TypeError, ValueError):
                continue
        llm_findings = _run_llm_detection(ctx, flagged_indices)
        findings.extend(llm_findings)

    ctx.anomaly_findings = findings
    ctx.detection_stats = _summarize_findings(findings)
    ctx.detection_stats["resolved_rules_path"] = str(materialized_path)

    if ctx.trail_writer:
        input_hash = hash_dataframe(ctx.normalized_df)
        for rule_id, count in per_rule_counts.items():
            ctx.trail_writer.write(
                TrailEntry(
                    session_id=ctx.session_id,
                    agent_id="anomaly",
                    action_type="ANOMALY_RULE_EVALUATED",
                    input_hash=input_hash,
                    output_hash=hash_dict({"rule_id": rule_id, "count": count}),
                    reasoning_summary=f"Rule {rule_id} produced {count} findings.",
                    duration_ms=int((time.perf_counter() - start) * 1000),
                )
            )

        if r018_findings:
            ctx.trail_writer.write(
                TrailEntry(
                    session_id=ctx.session_id,
                    agent_id="anomaly",
                    action_type="ANOMALY_RULE_EVALUATED",
                    input_hash=input_hash,
                    output_hash=hash_dict({"rule_id": "R018", "count": len(r018_findings)}),
                    reasoning_summary=(
                        f"Rule R018 produced {len(r018_findings)} findings."
                    ),
                    duration_ms=int((time.perf_counter() - start) * 1000),
                )
            )

        ctx.trail_writer.write(
            TrailEntry(
                session_id=ctx.session_id,
                agent_id="anomaly",
                action_type="ANOMALY_RULE_EVALUATED",
                input_hash=input_hash,
                output_hash=hash_dict(ctx.detection_stats),
                reasoning_summary=(
                    f"Rule-based anomaly evaluation completed. Total findings: {len(findings)}."
                ),
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
        )

    ctx.current_layer = 3
    return ctx
