from pathlib import Path

from ave.config import AveConfig
from ave.context import PipelineContext
from ave.export.markdown_exporter import MarkdownExporter
from ave.models.finding import Finding


def _build_context(tmp_path: Path) -> PipelineContext:
    config = AveConfig()
    config.llm.enabled = False
    config.output.formats = ["json"]

    ctx = PipelineContext(session_id="s1", config=config, output_dir=tmp_path)
    ctx.integrity_report = {
        "checks": {f"IC-{idx:03d}": {"findings": 0} for idx in range(1, 11)}
    }
    return ctx


def test_markdown_exporter_generates_sections(tmp_path: Path) -> None:
    ctx = _build_context(tmp_path)
    finding = Finding(
        session_id="s1",
        layer=3,
        finding_type="anomaly",
        rule_id="R001",
        rule_name="Test Rule",
        row_index=0,
        row_data={"amount": 123},
        severity="high",
        confidence=1.0,
        reasoning="Test reasoning",
        detection_method="rule",
    )

    report = {
        "report_meta": {
            "session_id": "s1",
            "generated_at": "2025-01-01T00:00:00",
            "file_processed": "file.csv",
        },
        "integrity_summary": {
            "overall_rating": "MINOR",
            "total_score": 1,
            "checks_run": 10,
            "findings_count": 1,
        },
        "anomaly_summary": {
            "total_flagged": 1,
            "by_severity": {"high": 1, "medium": 0, "low": 0},
            "by_rule": {"R001": 1},
            "llm_assisted_count": 0,
        },
        "findings": [finding.to_dict()],
        "audit_trail_ref": "trail.jsonl",
        "recommendations": [],
    }

    exporter = MarkdownExporter()
    content = exporter.generate(report, ctx, trail_hash="abc")

    assert "# AVE Audit Report" in content
    assert "## Integrity Check Results" in content
    assert "## Anomaly Findings" in content
    assert "## High-Severity Findings Detail" in content
    assert "## Recommendations" in content
    assert "## Audit Trail Reference" in content
    assert "IC-001" in content
    assert "R001" in content
