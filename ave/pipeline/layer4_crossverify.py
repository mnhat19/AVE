from __future__ import annotations

import time
from typing import List
from uuid import uuid4

from ave.context import PipelineContext
from ave.models.finding import Finding
from ave.models.trail import TrailEntry
from ave.utils.hashing import hash_dict
from ave.utils.logging import get_logger

logger = get_logger("layer4_crossverify")

# TODO: Full cross-verification implementation in Alpha (Section 2.4.2)


def validate_prerequisites(ctx: PipelineContext) -> None:
    if ctx.integrity_findings is None or ctx.anomaly_findings is None:
        logger.warning("Cross-verification received incomplete findings lists.")


def run(ctx: PipelineContext) -> PipelineContext:
    validate_prerequisites(ctx)
    start = time.perf_counter()

    combined: List[Finding] = []
    combined.extend(ctx.integrity_findings or [])
    combined.extend(ctx.anomaly_findings or [])

    verified: List[Finding] = []
    for finding in combined:
        payload = finding.to_dict()
        copied = Finding.from_dict(payload)
        if not copied.finding_id:
            copied.finding_id = str(uuid4())
        copied.cross_verified = False
        copied.cross_verify_status = "pending"
        verified.append(copied)

    ctx.verified_findings = verified

    if ctx.trail_writer:
        ctx.trail_writer.write(
            TrailEntry(
                session_id=ctx.session_id,
                agent_id="cross_verify",
                action_type="CROSS_VERIFY_RUN",
                input_hash=hash_dict({"incoming": len(combined)}),
                output_hash=hash_dict({"verified": len(verified)}),
                reasoning_summary=(
                    "Cross-verification skipped in MVP - findings passed through unchanged"
                ),
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
        )

    logger.info(
        "Layer 4 (Cross-Verification): stub mode - %d findings passed through",
        len(verified),
    )

    ctx.current_layer = 4
    return ctx
