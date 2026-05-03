from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ave import __version__
from ave.context import PipelineContext
from ave.export.markdown_exporter import MarkdownExporter
from ave.export.pdf_exporter import PdfExporter
from ave.models.finding import Finding
from ave.models.trail import TrailEntry
from ave.utils.hashing import hash_dict, hash_file
from ave.utils.logging import get_logger

logger = get_logger("layer5_synthesis")


def _collect_findings(ctx: PipelineContext) -> List[Finding]:
    if ctx.verified_findings:
        return list(ctx.verified_findings)
    return ctx.get_all_findings()


def _summarize_anomalies(findings: List[Finding]) -> Dict[str, Any]:
    by_rule: Dict[str, int] = {}
    by_severity = {"high": 0, "medium": 0, "low": 0}
    llm_count = 0

    for finding in findings:
        if finding.finding_type != "anomaly":
            continue
        by_rule[finding.rule_id or "unknown"] = by_rule.get(finding.rule_id or "unknown", 0) + 1
        if finding.severity in by_severity:
            by_severity[finding.severity] += 1
        if finding.detection_method == "llm":
            llm_count += 1

    return {
        "total_flagged": sum(by_severity.values()),
        "by_severity": by_severity,
        "by_rule": by_rule,
        "llm_assisted_count": llm_count,
    }


def _compute_config_hash(ctx: PipelineContext) -> tuple[str, Optional[str]]:
    config_path = getattr(ctx, "config_file_path", None)
    if config_path:
        path = Path(config_path)
        if path.exists():
            return hash_file(path), str(path)

    return hash_dict(ctx.config.model_dump()), None


def _aggregate_findings(ctx: PipelineContext) -> dict:
    findings = _collect_findings(ctx)
    config_hash, config_path = _compute_config_hash(ctx)

    integrity_report = ctx.integrity_report or {}
    integrity_summary = {
        "overall_rating": integrity_report.get("overall_rating", "UNKNOWN"),
        "total_score": integrity_report.get("total_score", 0),
        "checks_run": integrity_report.get("checks_run", 0),
        "findings_count": integrity_report.get("findings_count", 0),
    }

    report_meta = {
        "session_id": ctx.session_id,
        "generated_at": datetime.utcnow().isoformat(),
        "ave_version": __version__,
        "file_processed": str(ctx.input_file_path) if ctx.input_file_path else "",
        "config_file": config_path or "",
        "config_hash": config_hash,
    }

    report = {
        "report_meta": report_meta,
        "source_summary": ctx.source_manifest or {},
        "integrity_summary": integrity_summary,
        "anomaly_summary": _summarize_anomalies(findings),
        "findings": [finding.to_dict() for finding in findings],
        "audit_trail_ref": str(ctx.trail_writer.trail_path)
        if ctx.trail_writer is not None
        else "",
        "recommendations": [],
    }
    return report


def _export_json(report: dict, output_dir: Path, session_id: str) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / f"{session_id}_report.json"

    with target_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    return target_path


def _export_markdown(markdown_text: str, output_dir: Path, session_id: str) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / f"{session_id}_report.md"
    target_path.write_text(markdown_text, encoding="utf-8")
    return target_path


def _load_rule_snapshot(ctx: PipelineContext) -> List[dict]:
    rules_path = None
    if ctx.detection_stats:
        rules_path = ctx.detection_stats.get("resolved_rules_path")
    if not rules_path:
        rules_path = ctx.config.rules_file

    path = Path(rules_path)
    if not path.exists():
        return []

    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Unable to load rules snapshot: %s", exc)
        return []

    if isinstance(payload, list):
        return [rule for rule in payload if isinstance(rule, dict)]
    if isinstance(payload, dict):
        rules = payload.get("rules") or []
        return [rule for rule in rules if isinstance(rule, dict)]
    return []


def _save_findings_to_db(ctx: PipelineContext, findings: List[Finding]) -> None:
    db = getattr(ctx, "database", None)
    if db is None:
        return

    for finding in findings:
        try:
            db.save_finding(finding)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to save finding %s: %s", finding.finding_id, exc)


def _update_session_in_db(
    ctx: PipelineContext,
    report: dict,
    trail_path: Optional[str] = None,
) -> None:
    db = getattr(ctx, "database", None)
    if db is None:
        return

    integrity = report.get("integrity_summary", {}) or {}
    updates = {
        "completed_at": datetime.utcnow().isoformat(),
        "status": "completed",
        "overall_rating": integrity.get("overall_rating"),
        "total_findings": len(_collect_findings(ctx)),
    }
    if trail_path:
        updates["trail_file_path"] = trail_path
    try:
        db.update_session(ctx.session_id, updates)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to update session: %s", exc)


def _save_rule_snapshot(ctx: PipelineContext) -> None:
    db = getattr(ctx, "database", None)
    if db is None:
        return

    rules = _load_rule_snapshot(ctx)
    if not rules:
        return
    try:
        db.save_rule_snapshot(ctx.session_id, rules)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to save rule snapshot: %s", exc)


def run(ctx: PipelineContext) -> PipelineContext:
    report = _aggregate_findings(ctx)
    findings = _collect_findings(ctx)

    exporter = MarkdownExporter()
    recommendations = exporter.build_recommendations(findings, ctx)
    report["recommendations"] = recommendations
    executive_summary = exporter.build_executive_summary(report, ctx)

    report_path = _export_json(report, ctx.output_dir, ctx.session_id)
    ctx.report_paths["json"] = str(report_path)

    formats = set(ctx.config.output.formats or [])
    if ctx.config.output.pdf_enabled:
        formats.add("pdf")

    planned_paths: Dict[str, str] = {"json": str(report_path)}
    if "markdown" in formats:
        planned_paths["markdown"] = str(Path(ctx.output_dir) / f"{ctx.session_id}_report.md")
    if "pdf" in formats:
        planned_paths["pdf"] = str(Path(ctx.output_dir) / f"{ctx.session_id}_report.pdf")

    if ctx.trail_writer:
        ctx.trail_writer.write(
            TrailEntry(
                session_id=ctx.session_id,
                agent_id="synthesis",
                action_type="EXPORT_COMPLETED",
                input_hash=hash_dict({"formats": list(planned_paths.keys())}),
                output_hash=hash_dict(planned_paths),
                reasoning_summary="Report exports completed.",
                duration_ms=0,
            )
        )

    trail_path = None
    if ctx.trail_writer:
        try:
            trail_path = ctx.trail_writer.finalize()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Trail finalization failed: %s", exc)

    trail_hash = None
    if trail_path and Path(trail_path).exists():
        try:
            trail_hash = hash_file(Path(trail_path))
        except OSError:
            trail_hash = None

    markdown_content = None
    if "markdown" in formats:
        markdown_content = exporter.generate(
            report,
            ctx,
            executive_summary=executive_summary,
            recommendations=recommendations,
            trail_hash=trail_hash,
        )
        md_path = _export_markdown(markdown_content, ctx.output_dir, ctx.session_id)
        ctx.report_paths["markdown"] = str(md_path)

    if "pdf" in formats:
        if markdown_content is None:
            markdown_content = exporter.generate(
                report,
                ctx,
                executive_summary=executive_summary,
                recommendations=recommendations,
                trail_hash=trail_hash,
            )
        pdf_exporter = PdfExporter()
        pdf_path = pdf_exporter.generate(
            markdown_content,
            Path(ctx.output_dir) / f"{ctx.session_id}_report.pdf",
            ctx.session_id,
        )
        if pdf_path is not None:
            ctx.report_paths["pdf"] = str(pdf_path)

    ctx.final_report = report
    ctx.current_layer = 5

    _save_findings_to_db(ctx, findings)
    _save_rule_snapshot(ctx)
    _update_session_in_db(ctx, report, trail_path)

    logger.info("JSON report generated: %s", report_path)
    return ctx
