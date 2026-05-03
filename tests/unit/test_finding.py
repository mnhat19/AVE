import json
from datetime import date, datetime

from ave.models.finding import Finding


def test_finding_to_dict_json_safe() -> None:
    finding = Finding(
        session_id="s1",
        layer=2,
        finding_type="integrity",
        rule_id="IC-001",
        rule_name="Null check",
        row_index=0,
        row_data={"created_at": datetime(2025, 5, 1), "date": date(2025, 5, 2)},
        actual_value=123,
        expected_value=["a", "b"],
        severity="high",
        confidence=1.0,
        reasoning="test",
        detection_method="rule",
    )
    payload = finding.to_dict()
    json.dumps(payload)
    assert payload["actual_value"] == "123"
    assert payload["expected_value"] == "['a', 'b']"
    assert payload["row_data"]["created_at"].startswith("2025-05-01")


def test_finding_round_trip() -> None:
    finding = Finding(
        session_id="s2",
        layer=3,
        finding_type="anomaly",
        rule_name="Rule",
        row_index=1,
        severity="medium",
        confidence=0.5,
        reasoning="reason",
        detection_method="rule",
    )
    clone = Finding.from_dict(finding.to_dict())
    assert clone.finding_id == finding.finding_id
    assert clone.session_id == finding.session_id
