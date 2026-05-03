from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from ave.exceptions import RuleValidationError
from ave.models.finding import Finding
from ave.utils.logging import get_logger

logger = get_logger("rule_engine")

_ID_PATTERN = re.compile(r"^[A-Z][0-9]{3}$")
_SEVERITIES = {"high", "medium", "low"}

_CONDITION_TYPES = {
    "gt",
    "gte",
    "lt",
    "lte",
    "eq",
    "neq",
    "in",
    "not_in",
    "is_null",
    "not_null",
    "matches",
    "not_matches",
    "weekend_transaction",
    "end_of_period",
    "cross_field_gt",
    "cross_field_eq",
    "compound",
}

_THRESHOLD_CONDITIONS = {"gt", "gte", "lt", "lte"}
_VALUE_CONDITIONS = {"eq", "neq"}
_VALUES_CONDITIONS = {"in", "not_in"}
_PATTERN_CONDITIONS = {"matches", "not_matches"}
_CROSS_FIELD_CONDITIONS = {"cross_field_gt", "cross_field_eq"}

_PLACEHOLDER_APPROVED_VENDORS = "__CONFIG_APPROVED_VENDORS__"
_PLACEHOLDER_PUBLIC_HOLIDAYS = "__CONFIG_PUBLIC_HOLIDAYS__"

_ALLOWED_KEYS = {
    "id",
    "name",
    "description",
    "field",
    "fields",
    "condition",
    "threshold",
    "value",
    "values",
    "pattern",
    "reference_field",
    "severity",
    "requires_cross_check",
    "active",
    "tags",
    "audit_standard",
    "logic",
    "sub_conditions",
}


@dataclass
class Rule:
    id: str
    name: str
    description: Optional[str] = None
    field: Optional[str] = None
    fields: Optional[List[str]] = None
    condition: str = ""
    threshold: Optional[float] = None
    value: Optional[Any] = None
    values: Optional[List[Any]] = None
    pattern: Optional[str] = None
    reference_field: Optional[str] = None
    severity: str = ""
    requires_cross_check: bool = False
    active: bool = True
    tags: List[str] = dc_field(default_factory=list)
    audit_standard: Optional[str] = None
    logic: Optional[str] = None
    sub_conditions: Optional[List[dict]] = None


def _build_rule(rule_data: Dict[str, Any], index: int) -> Rule:
    if not isinstance(rule_data, dict):
        raise RuleValidationError(f"Rule entry at index {index} must be a mapping")

    rule_id = rule_data.get("id")
    if not rule_id:
        raise RuleValidationError(f"Rule missing id at index {index}")

    unknown_keys = set(rule_data.keys()) - _ALLOWED_KEYS
    if unknown_keys:
        logger.warning(
            "Rule %s contains unknown keys: %s",
            rule_id,
            sorted(unknown_keys),
        )

    payload = {key: rule_data.get(key) for key in _ALLOWED_KEYS}
    if payload.get("tags") is None:
        payload["tags"] = []
    return Rule(**payload)


def _validate_rule(rule: Rule) -> List[str]:
    errors: List[str] = []

    if not rule.id:
        errors.append("Rule id is required")
    elif not _ID_PATTERN.match(rule.id):
        errors.append(f"Rule {rule.id}: id must match pattern ^[A-Z][0-9]{{3}}$")

    if not rule.name:
        errors.append(f"Rule {rule.id}: name is required")

    if rule.condition not in _CONDITION_TYPES:
        errors.append(f"Rule {rule.id}: unsupported condition '{rule.condition}'")

    if rule.severity not in _SEVERITIES:
        errors.append(f"Rule {rule.id}: invalid severity '{rule.severity}'")

    if rule.fields is not None:
        if not isinstance(rule.fields, list) or len(rule.fields) == 0:
            errors.append(f"Rule {rule.id}: fields must be a non-empty list")

    if rule.tags and not isinstance(rule.tags, list):
        errors.append(f"Rule {rule.id}: tags must be a list")

    if rule.condition != "compound":
        if not rule.field and not rule.fields:
            errors.append(f"Rule {rule.id}: field is required for condition '{rule.condition}'")

    if rule.condition in _THRESHOLD_CONDITIONS and rule.threshold is None:
        errors.append(f"Rule {rule.id}: threshold is required for condition '{rule.condition}'")

    if rule.condition in _VALUE_CONDITIONS and rule.value is None:
        errors.append(f"Rule {rule.id}: value is required for condition '{rule.condition}'")

    if rule.condition in _VALUES_CONDITIONS:
        if not isinstance(rule.values, list) or len(rule.values) == 0:
            errors.append(f"Rule {rule.id}: values list is required for condition '{rule.condition}'")

    if rule.condition in _PATTERN_CONDITIONS:
        if not rule.pattern:
            errors.append(f"Rule {rule.id}: pattern is required for condition '{rule.condition}'")
        else:
            try:
                re.compile(rule.pattern)
            except re.error as exc:
                errors.append(f"Rule {rule.id}: invalid regex pattern ({exc})")

    if rule.condition in _CROSS_FIELD_CONDITIONS and not rule.reference_field:
        errors.append(
            f"Rule {rule.id}: reference_field is required for condition '{rule.condition}'"
        )

    if rule.condition == "compound":
        if rule.logic not in {"AND", "OR"}:
            errors.append(f"Rule {rule.id}: logic must be AND or OR for compound rules")
        if not isinstance(rule.sub_conditions, list) or len(rule.sub_conditions) == 0:
            errors.append(f"Rule {rule.id}: sub_conditions list is required for compound rules")
        else:
            for idx, sub in enumerate(rule.sub_conditions):
                if not isinstance(sub, dict):
                    errors.append(f"Rule {rule.id}: sub_conditions[{idx}] must be a mapping")
                    continue
                if "condition" not in sub:
                    errors.append(
                        f"Rule {rule.id}: sub_conditions[{idx}] missing condition field"
                    )
                if "field" not in sub and "fields" not in sub:
                    errors.append(
                        f"Rule {rule.id}: sub_conditions[{idx}] missing field/fields"
                    )

    return errors


def validate_rules(rules: List[Rule]) -> List[str]:
    errors: List[str] = []
    seen_ids = set()

    for rule in rules:
        if rule.id in seen_ids:
            errors.append(f"Duplicate rule ID: {rule.id}")
        else:
            seen_ids.add(rule.id)
        errors.extend(_validate_rule(rule))

    return errors


def load_rules_from_yaml(path: Path) -> List[Rule]:
    rules_path = Path(path)
    if not rules_path.exists():
        raise RuleValidationError(f"Rules file not found: {rules_path}")

    try:
        raw_text = rules_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise RuleValidationError(f"Invalid YAML in rules file: {exc}") from exc
    except OSError as exc:
        raise RuleValidationError(f"Unable to read rules file: {rules_path}") from exc

    if data is None:
        return []

    if isinstance(data, list):
        rules_data = data
    elif isinstance(data, dict):
        rules_data = data.get("rules") or []
    else:
        raise RuleValidationError("Rules YAML must be a mapping with a 'rules' list")

    if not rules_data:
        return []

    rules: List[Rule] = []
    seen_ids = set()
    for index, rule_item in enumerate(rules_data):
        rule = _build_rule(rule_item, index)
        if rule.id in seen_ids:
            raise RuleValidationError(f"Duplicate rule ID: {rule.id}", rule_id=rule.id)
        seen_ids.add(rule.id)

        rule_errors = _validate_rule(rule)
        if rule_errors:
            raise RuleValidationError(rule_errors[0], rule_id=rule.id)

        rules.append(rule)

    return rules


def _load_reference_values(path: Optional[str]) -> List[str]:
    if not path:
        return []

    file_path = Path(path)
    if not file_path.exists():
        logger.warning("Reference file not found: %s", file_path)
        return []

    values: List[str] = []
    try:
        with file_path.open("r", encoding="utf-8", errors="replace") as handle:
            reader = csv.reader(handle)
            for idx, row in enumerate(reader):
                if not row:
                    continue
                value = str(row[0]).strip()
                if idx == 0 and value.lower() in {"vendor_id", "vendor", "id", "code", "name"}:
                    continue
                if value:
                    values.append(value)
    except OSError as exc:
        logger.warning("Unable to read reference file %s: %s", file_path, exc)
        return []

    return values


def _replace_placeholders(values: List[Any], config: Any) -> tuple[List[Any], bool]:
    missing = False
    output: List[Any] = []

    for value in values:
        if value == _PLACEHOLDER_APPROVED_VENDORS:
            approved = _load_reference_values(getattr(config, "approved_vendor_file", None))
            if not approved:
                missing = True
            output.extend(approved)
        elif value == _PLACEHOLDER_PUBLIC_HOLIDAYS:
            holidays = list(getattr(config, "public_holidays", []) or [])
            if not holidays:
                missing = True
            output.extend(holidays)
        else:
            output.append(value)

    return output, missing


def materialize_rules_file(
    rules_path: Path,
    config: Any,
    output_dir: Path,
    session_id: str,
) -> Path:
    raw_text = Path(rules_path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw_text) or {}

    if isinstance(data, list):
        rules_data = data
    else:
        rules_data = data.get("rules") or []

    materialized: List[Dict[str, Any]] = []
    for rule in rules_data:
        if not isinstance(rule, dict):
            continue
        values = rule.get("values")
        if isinstance(values, list):
            replaced, missing = _replace_placeholders(values, config)
            if missing and any(
                val in values for val in [_PLACEHOLDER_APPROVED_VENDORS, _PLACEHOLDER_PUBLIC_HOLIDAYS]
            ):
                logger.warning("Rule %s skipped due to missing config values", rule.get("id"))
                continue
            rule = {**rule, "values": replaced}
        materialized.append(rule)

    target_dir = Path(output_dir) / "rules"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{session_id}_rules.yaml"

    payload = {"rules": materialized}
    target_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    return target_path


def _ensure_pandas(df: Any) -> pd.DataFrame:
    if isinstance(df, pd.DataFrame):
        return df.reset_index(drop=True)

    try:
        import polars as pl
    except Exception:  # pragma: no cover - optional import for runtime
        pl = None

    if pl is not None and isinstance(df, pl.DataFrame):
        return df.to_pandas().reset_index(drop=True)

    raise TypeError("Rule evaluation expects a pandas or polars DataFrame")


def _get_series(df: pd.DataFrame, field: str) -> Optional[pd.Series]:
    if not field:
        logger.warning("Rule field is missing")
        return None
    if field not in df.columns:
        logger.warning("Rule field '%s' not found in DataFrame", field)
        return None
    return df[field]


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _mask_gt(df: pd.DataFrame, field: str, threshold: float) -> Optional[pd.Series]:
    series = _get_series(df, field)
    if series is None:
        return None
    return _to_numeric(series) > threshold


def _mask_gte(df: pd.DataFrame, field: str, threshold: float) -> Optional[pd.Series]:
    series = _get_series(df, field)
    if series is None:
        return None
    return _to_numeric(series) >= threshold


def _mask_lt(df: pd.DataFrame, field: str, threshold: float) -> Optional[pd.Series]:
    series = _get_series(df, field)
    if series is None:
        return None
    return _to_numeric(series) < threshold


def _mask_lte(df: pd.DataFrame, field: str, threshold: float) -> Optional[pd.Series]:
    series = _get_series(df, field)
    if series is None:
        return None
    return _to_numeric(series) <= threshold


def _mask_eq(df: pd.DataFrame, field: str, value: Any) -> Optional[pd.Series]:
    series = _get_series(df, field)
    if series is None:
        return None
    if value is None:
        return series.isna()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = _to_numeric(series)
        return numeric == float(value)
    target = str(value)
    return series.fillna("").astype(str).str.strip() == target


def _mask_neq(df: pd.DataFrame, field: str, value: Any) -> Optional[pd.Series]:
    series = _get_series(df, field)
    if series is None:
        return None
    if value is None:
        return series.notna()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = _to_numeric(series)
        return numeric.notna() & (numeric != float(value))
    target = str(value)
    return series.notna() & (series.astype(str).str.strip() != target)


def _mask_in(df: pd.DataFrame, field: str, values: List[Any]) -> Optional[pd.Series]:
    series = _get_series(df, field)
    if series is None:
        return None
    return series.isin(values)


def _mask_not_in(df: pd.DataFrame, field: str, values: List[Any]) -> Optional[pd.Series]:
    series = _get_series(df, field)
    if series is None:
        return None
    return series.notna() & (~series.isin(values))


def _mask_is_null(df: pd.DataFrame, field: str) -> Optional[pd.Series]:
    series = _get_series(df, field)
    if series is None:
        return None
    return series.isna()


def _mask_not_null(df: pd.DataFrame, field: str) -> Optional[pd.Series]:
    series = _get_series(df, field)
    if series is None:
        return None
    return series.notna()


def _mask_matches(df: pd.DataFrame, field: str, pattern: str) -> Optional[pd.Series]:
    series = _get_series(df, field)
    if series is None:
        return None
    return series.fillna("").astype(str).str.contains(pattern, regex=True, na=False)


def _mask_not_matches(df: pd.DataFrame, field: str, pattern: str) -> Optional[pd.Series]:
    mask = _mask_matches(df, field, pattern)
    if mask is None:
        return None
    return ~mask


def _mask_weekend_transaction(df: pd.DataFrame, field: str) -> Optional[pd.Series]:
    series = _get_series(df, field)
    if series is None:
        return None
    dates = pd.to_datetime(series, errors="coerce")
    return dates.dt.weekday >= 5


def _mask_end_of_period(
    df: pd.DataFrame,
    field: str,
    period: str = "month",
    config: Optional[Any] = None,
) -> Optional[pd.Series]:
    series = _get_series(df, field)
    if series is None:
        return None
    dates = pd.to_datetime(series, errors="coerce")
    if period == "quarter":
        return dates.dt.is_quarter_end
    if period == "year":
        end_month = 12
        end_day = 31
        if config is not None:
            end_month = getattr(config, "fiscal_year_end_month", end_month)
            end_day = getattr(config, "fiscal_year_end_day", end_day)
        return (dates.dt.month == end_month) & (dates.dt.day == end_day)
    return dates.dt.is_month_end


def _mask_cross_field_gt(
    df: pd.DataFrame, field: str, reference_field: str
) -> Optional[pd.Series]:
    left = _get_series(df, field)
    right = _get_series(df, reference_field)
    if left is None or right is None:
        return None
    left_num = _to_numeric(left)
    right_num = _to_numeric(right)
    return left_num.notna() & right_num.notna() & (left_num > right_num)


def _mask_cross_field_eq(
    df: pd.DataFrame, field: str, reference_field: str
) -> Optional[pd.Series]:
    left = _get_series(df, field)
    right = _get_series(df, reference_field)
    if left is None or right is None:
        return None
    left_num = _to_numeric(left)
    right_num = _to_numeric(right)
    return left_num.notna() & right_num.notna() & (left_num == right_num)


def _mask_from_condition(
    condition: Dict[str, Any],
    df: pd.DataFrame,
    config: Optional[Any] = None,
) -> Optional[pd.Series]:
    cond_type = condition.get("condition")
    field = condition.get("field")
    fields = condition.get("fields")
    if not field and isinstance(fields, list) and len(fields) == 1:
        field = fields[0]

    match cond_type:
        case "gt":
            threshold = condition.get("threshold")
            return _mask_gt(df, field, threshold) if threshold is not None else None
        case "gte":
            threshold = condition.get("threshold")
            return _mask_gte(df, field, threshold) if threshold is not None else None
        case "lt":
            threshold = condition.get("threshold")
            return _mask_lt(df, field, threshold) if threshold is not None else None
        case "lte":
            threshold = condition.get("threshold")
            return _mask_lte(df, field, threshold) if threshold is not None else None
        case "eq":
            return _mask_eq(df, field, condition.get("value"))
        case "neq":
            return _mask_neq(df, field, condition.get("value"))
        case "in":
            return _mask_in(df, field, condition.get("values") or [])
        case "not_in":
            return _mask_not_in(df, field, condition.get("values") or [])
        case "is_null":
            return _mask_is_null(df, field)
        case "not_null":
            return _mask_not_null(df, field)
        case "matches":
            pattern = condition.get("pattern")
            return _mask_matches(df, field, pattern) if pattern else None
        case "not_matches":
            pattern = condition.get("pattern")
            return _mask_not_matches(df, field, pattern) if pattern else None
        case "weekend_transaction":
            return _mask_weekend_transaction(df, field)
        case "end_of_period":
            period = condition.get("value") or "month"
            return _mask_end_of_period(df, field, period=period, config=config)
        case "cross_field_gt":
            reference = condition.get("reference_field")
            return _mask_cross_field_gt(df, field, reference) if reference else None
        case "cross_field_eq":
            reference = condition.get("reference_field")
            return _mask_cross_field_eq(df, field, reference) if reference else None
        case "compound":
            return _mask_compound(condition, df, config=config)
        case _:
            return None


def _mask_compound(
    rule_data: Dict[str, Any],
    df: pd.DataFrame,
    config: Optional[Any] = None,
) -> Optional[pd.Series]:
    logic = rule_data.get("logic")
    sub_conditions = rule_data.get("sub_conditions") or []
    if logic not in {"AND", "OR"}:
        return None

    masks = []
    for sub in sub_conditions:
        mask = _mask_from_condition(sub, df, config=config)
        if mask is None:
            return None
        masks.append(mask)

    if not masks:
        return None

    combined = masks[0]
    for mask in masks[1:]:
        combined = combined & mask if logic == "AND" else combined | mask
    return combined


def _build_reasoning(
    rule: Rule,
    column: Optional[str],
    actual_value: Any,
    expected_value: Any,
) -> str:
    if column:
        return f"{rule.name}: {column}={actual_value} expected {expected_value}"
    return f"{rule.name}: condition matched"


def _build_findings(
    rule: Rule,
    df: pd.DataFrame,
    mask: Optional[pd.Series],
    column_name: Optional[str],
    expected_value: Any,
    session_id: Optional[str] = None,
) -> List[Finding]:
    if mask is None:
        return []
    matches = df[mask]
    findings: List[Finding] = []
    for idx, row in matches.iterrows():
        row_data = row.to_dict()
        actual_value = row_data.get(column_name) if column_name else None
        reasoning = _build_reasoning(rule, column_name, actual_value, expected_value)
        findings.append(
            Finding(
                session_id=session_id or "",
                layer=3,
                finding_type="anomaly",
                rule_id=rule.id,
                rule_name=rule.name,
                row_index=int(idx) if isinstance(idx, (int, float)) else idx,
                row_data=row_data,
                column_name=column_name,
                actual_value=actual_value,
                expected_value=expected_value,
                severity=rule.severity,
                confidence=1.0,
                reasoning=reasoning,
                detection_method="rule",
            )
        )
    return findings


def evaluate_rule(
    rule: Rule,
    df: Any,
    config: Optional[Any] = None,
    session_id: Optional[str] = None,
) -> List[Finding]:
    data = _ensure_pandas(df)

    field = rule.field
    if not field and rule.fields and len(rule.fields) == 1:
        field = rule.fields[0]
    if not field and rule.condition != "compound":
        logger.warning("Rule %s missing target field", rule.id)
        return []

    match rule.condition:
        case "gt":
            mask = _mask_gt(data, field, rule.threshold)
            return _build_findings(rule, data, mask, field, rule.threshold, session_id)
        case "gte":
            mask = _mask_gte(data, field, rule.threshold)
            return _build_findings(rule, data, mask, field, rule.threshold, session_id)
        case "lt":
            mask = _mask_lt(data, field, rule.threshold)
            return _build_findings(rule, data, mask, field, rule.threshold, session_id)
        case "lte":
            mask = _mask_lte(data, field, rule.threshold)
            return _build_findings(rule, data, mask, field, rule.threshold, session_id)
        case "eq":
            mask = _mask_eq(data, field, rule.value)
            return _build_findings(rule, data, mask, field, rule.value, session_id)
        case "neq":
            mask = _mask_neq(data, field, rule.value)
            return _build_findings(rule, data, mask, field, rule.value, session_id)
        case "in":
            mask = _mask_in(data, field, rule.values or [])
            return _build_findings(rule, data, mask, field, rule.values, session_id)
        case "not_in":
            mask = _mask_not_in(data, field, rule.values or [])
            return _build_findings(rule, data, mask, field, rule.values, session_id)
        case "is_null":
            mask = _mask_is_null(data, field)
            return _build_findings(rule, data, mask, field, "not null", session_id)
        case "not_null":
            mask = _mask_not_null(data, field)
            return _build_findings(rule, data, mask, field, "null", session_id)
        case "matches":
            mask = _mask_matches(data, field, rule.pattern or "")
            return _build_findings(rule, data, mask, field, rule.pattern, session_id)
        case "not_matches":
            mask = _mask_not_matches(data, field, rule.pattern or "")
            return _build_findings(rule, data, mask, field, rule.pattern, session_id)
        case "weekend_transaction":
            mask = _mask_weekend_transaction(data, field)
            return _build_findings(rule, data, mask, field, "weekend", session_id)
        case "end_of_period":
            period = rule.value or "month"
            mask = _mask_end_of_period(data, field, period=period, config=config)
            return _build_findings(rule, data, mask, field, period, session_id)
        case "cross_field_gt":
            ref = rule.reference_field
            if not ref:
                logger.warning("Rule %s missing reference_field", rule.id)
                return []
            mask = _mask_cross_field_gt(data, field, ref)
            return _build_findings(rule, data, mask, field, ref, session_id)
        case "cross_field_eq":
            ref = rule.reference_field
            if not ref:
                logger.warning("Rule %s missing reference_field", rule.id)
                return []
            mask = _mask_cross_field_eq(data, field, ref)
            return _build_findings(rule, data, mask, field, ref, session_id)
        case "compound":
            mask = _mask_compound(
                {
                    "logic": rule.logic,
                    "sub_conditions": rule.sub_conditions,
                },
                data,
                config=config,
            )
            return _build_findings(rule, data, mask, None, rule.logic, session_id)
        case _:
            return []


def evaluate(
    rules: List[Rule],
    df: Any,
    config: Optional[Any] = None,
    session_id: Optional[str] = None,
) -> List[Finding]:
    data = _ensure_pandas(df)
    findings: List[Finding] = []
    for rule in rules:
        if not rule.active:
            continue
        findings.extend(evaluate_rule(rule, data, config=config, session_id=session_id))

    deduped: Dict[tuple, Finding] = {}
    for finding in findings:
        key = (finding.rule_id, finding.row_index)
        if key not in deduped:
            deduped[key] = finding

    return list(deduped.values())


class RuleEngine:
    def __init__(self, rules: Optional[List[Rule]] = None, config: Optional[Any] = None) -> None:
        self.rules = rules or []
        self.config = config

    def load_from_yaml(self, path: Path) -> None:
        self.rules = load_rules_from_yaml(path)

    def validate_rules(self) -> List[str]:
        return validate_rules(self.rules)

    def evaluate(self, df: Any, session_id: Optional[str] = None) -> List[Finding]:
        return evaluate(self.rules, df, config=self.config, session_id=session_id)

    def evaluate_rule(self, rule: Rule, df: Any, session_id: Optional[str] = None) -> List[Finding]:
        return evaluate_rule(rule, df, config=self.config, session_id=session_id)
