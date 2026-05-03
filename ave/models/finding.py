from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Optional
from uuid import uuid4


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _stringify(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


@dataclass
class Finding:
    finding_id: str = field(default_factory=lambda: str(uuid4()))
    session_id: str = ""
    layer: int = 0
    finding_type: str = ""
    rule_id: Optional[str] = None
    rule_name: str = ""
    row_index: int = 0
    row_data: Dict[str, Any] = field(default_factory=dict)
    column_name: Optional[str] = None
    actual_value: Optional[Any] = None
    expected_value: Optional[Any] = None
    severity: str = ""
    confidence: float = 1.0
    reasoning: str = ""
    detection_method: str = ""
    cross_verified: bool = False
    cross_verify_status: Optional[str] = None
    human_decision: Optional[str] = None
    human_decision_at: Optional[str] = None
    human_decision_note: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "session_id": self.session_id,
            "layer": self.layer,
            "finding_type": self.finding_type,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "row_index": self.row_index,
            "row_data": _json_safe(self.row_data),
            "column_name": self.column_name,
            "actual_value": _stringify(self.actual_value),
            "expected_value": _stringify(self.expected_value),
            "severity": self.severity,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "detection_method": self.detection_method,
            "cross_verified": self.cross_verified,
            "cross_verify_status": self.cross_verify_status,
            "human_decision": self.human_decision,
            "human_decision_at": self.human_decision_at,
            "human_decision_note": self.human_decision_note,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Finding":
        return cls(**data)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)
