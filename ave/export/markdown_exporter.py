from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ave.context import PipelineContext
from ave.engines.llm_client import LLMRouter
from ave.models.finding import Finding
from ave.utils.hashing import hash_file
from ave.utils.logging import get_logger

logger = get_logger("markdown_exporter")

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _escape_md(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("|", "\\|")
    text = text.replace("\n", " ").replace("\r", " ")
    return text


def _severity_sort_key(value: str) -> int:
    return _SEVERITY_ORDER.get(value, 99)


class MarkdownExporter:
    def build_executive_summary(self, report: dict, ctx: PipelineContext) -> str:
        summary = self._template_summary(report)
        if not ctx.config.llm.enabled:
            return summary

        router = LLMRouter(ctx.config.llm.provider, ctx.config.llm)
        client = router.get_client()
        if client is None:
            return summary

        prompt = (
            "Provide a 2-3 sentence executive summary for this audit report. "
            "Use professional tone and focus on key risks.\n\n"
            f"Report summary: {json.dumps(self._summary_payload(report), ensure_ascii=False)}"
        )
        try:
            response = client.complete(prompt)
            cleaned = response.strip()
            return cleaned if cleaned else summary
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("LLM executive summary failed: %s", exc)
            return summary

    def build_recommendations(self, findings: List[Finding], ctx: PipelineContext) -> List[str]:
        template = self._template_recommendations(findings)
        if not ctx.config.llm.enabled:
            return template

        router = LLMRouter(ctx.config.llm.provider, ctx.config.llm)
        client = router.get_client()
        if client is None:
            return template

        prompt = (
            "You are an audit assistant. Provide 3-5 actionable recommendations "
            "based on the findings summary. Respond with JSON: "
            "{\"recommendations\": [\"...\"]}.\n\n"
            f"Findings summary: {json.dumps(self._recommendation_payload(findings), ensure_ascii=False)}"
        )
        try:
            response = client.complete_json(prompt, max_retries=ctx.config.llm.max_retries)
            recs = response.get("recommendations") if isinstance(response, dict) else None
            if isinstance(recs, list):
                cleaned = [str(item).strip() for item in recs if str(item).strip()]
                return cleaned or template
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("LLM recommendations failed: %s", exc)

        return template

    def generate(
        self,
        report: dict,
        ctx: PipelineContext,
        executive_summary: Optional[str] = None,
        recommendations: Optional[List[str]] = None,
        trail_hash: Optional[str] = None,
    ) -> str:
        findings = self._findings_from_report(report)
        anomalies = [f for f in findings if f.get("finding_type") == "anomaly"]

        summary_text = executive_summary or self.build_executive_summary(report, ctx)
        recs = recommendations or self._template_recommendations_from_dict(anomalies)

        integrity_checks = (ctx.integrity_report or {}).get("checks", {})
        integrity_rows = []
        for idx in range(1, 11):
            check_id = f"IC-{idx:03d}"
            check = integrity_checks.get(check_id, {})
            count = int(check.get("findings", 0) or 0)
            status = "PASS" if count == 0 else "FAIL"
            integrity_rows.append((check_id, status, count))

        anomaly_rows = self._build_anomaly_rows(anomalies)
        high_findings = [f for f in anomalies if f.get("severity") == "high"]

        meta = report.get("report_meta", {})
        status = (report.get("integrity_summary", {}) or {}).get("overall_rating", "UNKNOWN")

        trail_path = report.get("audit_trail_ref") or ""
        if trail_hash is None and trail_path:
            try:
                trail_hash = hash_file(Path(trail_path))
            except OSError:
                trail_hash = None

        lines: List[str] = []
        lines.append("# AVE Audit Report")
        lines.append(f"**Session:** {meta.get('session_id', '')}")
        lines.append(f"**File:** {meta.get('file_processed', '')}")
        lines.append(f"**Date:** {meta.get('generated_at', datetime.now(timezone.utc).isoformat())}")
        lines.append(f"**Status:** {status}")
        lines.append("")

        lines.append("## Executive Summary")
        lines.append(summary_text)
        lines.append("")

        lines.append("## Integrity Check Results")
        lines.append("| Check | Status | Findings |")
        lines.append("| --- | --- | --- |")
        for check_id, status_value, count in integrity_rows:
            lines.append(f"| {check_id} | {status_value} | {count} |")
        lines.append("")

        lines.append("## Anomaly Findings")
        if not anomaly_rows:
            lines.append("No anomalies detected.")
        else:
            lines.append("| Row Index | Rule ID | Description | Severity | Value |")
            lines.append("| --- | --- | --- | --- | --- |")
            for row in anomaly_rows:
                lines.append("| " + " | ".join(row) + " |")
            if len(anomalies) > 100:
                remaining = len(anomalies) - len(anomaly_rows)
                lines.append("")
                lines.append(f"and {remaining} more findings in JSON report")
        lines.append("")

        lines.append("## High-Severity Findings Detail")
        if not high_findings:
            lines.append("No high-severity findings.")
        else:
            for idx, finding in enumerate(high_findings, start=1):
                lines.append(f"### High Finding {idx}")
                lines.append(f"- Rule: {finding.get('rule_id') or 'LLM'}")
                lines.append(f"- Row Index: {finding.get('row_index')}")
                lines.append(f"- Reasoning: {finding.get('reasoning')}")
                row_data = finding.get("row_data") or {}
                lines.append("- Row Data:")
                lines.append("```json")
                lines.append(json.dumps(row_data, ensure_ascii=False, indent=2))
                lines.append("```")
                lines.append("")

        lines.append("## Recommendations")
        for rec in recs:
            lines.append(f"- {rec}")
        lines.append("")

        lines.append("## Audit Trail Reference")
        lines.append(f"Path: {trail_path}")
        lines.append(f"Hash: {trail_hash or ''}")

        return "\n".join(lines).strip() + "\n"

    def _summary_payload(self, report: dict) -> dict:
        integrity = report.get("integrity_summary", {}) or {}
        anomalies = report.get("anomaly_summary", {}) or {}
        source = report.get("source_summary", {}) or {}
        schema = source.get("schema", {}) if isinstance(source, dict) else {}

        return {
            "overall_rating": integrity.get("overall_rating"),
            "integrity_score": integrity.get("total_score"),
            "anomaly_count": anomalies.get("total_flagged"),
            "row_count": schema.get("row_count_after_cleaning"),
        }

    def _recommendation_payload(self, findings: List[Finding]) -> dict:
        severity_counts = {"high": 0, "medium": 0, "low": 0}
        rule_counts: Dict[str, int] = {}
        for finding in findings:
            if finding.severity in severity_counts:
                severity_counts[finding.severity] += 1
            rule_counts[finding.rule_id or "unknown"] = rule_counts.get(
                finding.rule_id or "unknown", 0
            ) + 1

        return {
            "severity": severity_counts,
            "rules": rule_counts,
        }

    def _template_summary(self, report: dict) -> str:
        integrity = report.get("integrity_summary", {}) or {}
        anomalies = report.get("anomaly_summary", {}) or {}
        rating = integrity.get("overall_rating", "UNKNOWN")
        total = anomalies.get("total_flagged", 0)
        return (
            f"Overall rating is {rating}. "
            f"The anomaly layer identified {total} flagged records. "
            "Review high-severity findings first and validate supporting evidence."
        )

    def _template_recommendations(self, findings: List[Finding]) -> List[str]:
        if not findings:
            return ["No anomalies detected; no additional action required."]

        recs: List[str] = []
        high_count = sum(1 for f in findings if f.severity == "high")
        if high_count > 3:
            recs.append("Escalate high-risk transactions to a senior auditor.")

        rule_ids = {f.rule_id for f in findings if f.rule_id}
        if "IC-002" in rule_ids:
            recs.append("Investigate the source system for duplicate entries.")
        if "IC-006" in rule_ids:
            recs.append("Review negative amount policies and validate exceptions.")
        if "IC-008" in rule_ids:
            recs.append("Validate reference datasets (vendors, accounts) for completeness.")
        if any(f.detection_method == "llm" for f in findings):
            recs.append("Validate LLM-flagged items with source documentation.")

        if not recs:
            recs.append("Investigate flagged items and document remediation actions.")

        return recs

    def _template_recommendations_from_dict(self, findings: List[Dict[str, Any]]) -> List[str]:
        objects = [Finding.from_dict(finding) for finding in findings]
        return self._template_recommendations(objects)

    def _findings_from_report(self, report: dict) -> List[Dict[str, Any]]:
        return list(report.get("findings", []) or [])

    def _build_anomaly_rows(self, anomalies: List[Dict[str, Any]]) -> List[List[str]]:
        if not anomalies:
            return []

        sorted_items = sorted(
            anomalies,
            key=lambda item: (
                _severity_sort_key(str(item.get("severity", ""))),
                int(item.get("row_index") or 0),
            ),
        )

        display_items = sorted_items
        if len(sorted_items) > 100:
            display_items = sorted_items[:50]

        rows: List[List[str]] = []
        for item in display_items:
            row_index = _escape_md(item.get("row_index"))
            rule_id = _escape_md(item.get("rule_id") or "LLM")
            description = _escape_md(item.get("rule_name") or item.get("reasoning"))
            severity = _escape_md(item.get("severity"))
            actual_value = _escape_md(item.get("actual_value"))
            rows.append([row_index, rule_id, description, severity, actual_value])

        return rows
