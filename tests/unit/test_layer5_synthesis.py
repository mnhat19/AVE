import json
from pathlib import Path

from ave.config import AveConfig
from ave.context import PipelineContext
from ave.models.finding import Finding
from ave.pipeline import layer5_synthesis


def test_layer5_synthesis_exports_json(tmp_path: Path) -> None:
    config = AveConfig()
    config.output.formats = ["json"]
    config.output.pdf_enabled = False

    ctx = PipelineContext(session_id="s1", config=config, output_dir=tmp_path)
    ctx.input_file_path = tmp_path / "input.csv"
    ctx.integrity_report = {
        "overall_rating": "CLEAN",
        "total_score": 0,
        "checks_run": 10,
        "findings_count": 0,
    }

    finding = Finding(
        session_id="s1",
        layer=3,
        finding_type="anomaly",
        rule_id="R001",
        rule_name="Test Rule",
        row_index=0,
        row_data={"amount": 100},
        severity="high",
        confidence=1.0,
        reasoning="Test reasoning",
        detection_method="rule",
    )
    ctx.verified_findings = [finding]

    result = layer5_synthesis.run(ctx)

    assert result.current_layer == 5
    assert "json" in result.report_paths

    report_path = Path(result.report_paths["json"])
    assert report_path.exists()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["report_meta"]["session_id"] == "s1"
    assert payload["recommendations"]
