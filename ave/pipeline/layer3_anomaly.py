from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict

from ave.context import PipelineContext
from ave.engines.rule_engine import RuleEngine, materialize_rules_file
from ave.exceptions import PipelineError
from ave.models.trail import TrailEntry
from ave.utils.hashing import hash_dataframe, hash_dict
from ave.utils.logging import get_logger

logger = get_logger("layer3_anomaly")


def validate_prerequisites(ctx: PipelineContext) -> None:
    if ctx.normalized_df is None:
        raise PipelineError("normalized_df is required for anomaly detection", layer=3)


def _summarize_findings(findings) -> Dict[str, Any]:
    by_rule: Dict[str, int] = {}
    by_severity = {"high": 0, "medium": 0, "low": 0}

    for finding in findings:
        by_rule[finding.rule_id or "unknown"] = by_rule.get(finding.rule_id or "unknown", 0) + 1
        if finding.severity in by_severity:
            by_severity[finding.severity] += 1

    return {
        "total_flagged": len(findings),
        "by_severity": by_severity,
        "by_rule": by_rule,
        "llm_assisted_count": 0,
    }


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

    engine = RuleEngine(config=ctx.config)
    engine.load_from_yaml(materialized_path)
    findings = engine.evaluate(ctx.normalized_df, session_id=ctx.session_id)

    ctx.anomaly_findings = findings
    ctx.detection_stats = _summarize_findings(findings)
    ctx.detection_stats["resolved_rules_path"] = str(materialized_path)

    if ctx.config.llm.enabled:
        ctx.add_warning("LLM anomaly detection is not implemented yet; skipped.")

    if ctx.trail_writer:
        ctx.trail_writer.write(
            TrailEntry(
                session_id=ctx.session_id,
                agent_id="anomaly",
                action_type="ANOMALY_RULE_EVALUATED",
                input_hash=hash_dataframe(ctx.normalized_df),
                output_hash=hash_dict(ctx.detection_stats),
                reasoning_summary="Rule-based anomaly evaluation completed.",
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
        )

    ctx.current_layer = 3
    return ctx
