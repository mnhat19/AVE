from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Optional

from rich.prompt import Confirm

from ave.config import AveConfig
from ave.context import PipelineContext
from ave.exceptions import PipelineError, StorageError
from ave.models.finding import Finding
from ave.pipeline import (
    layer1_ingestion,
    layer2_integrity,
    layer3_anomaly,
    layer4_crossverify,
    layer5_synthesis,
)
from ave.storage.checkpoint import CheckpointManager
from ave.utils.logging import get_logger

logger = get_logger("orchestrator")


def _build_context_from_checkpoint(checkpoint: dict) -> PipelineContext:
    config_data = checkpoint.get("config") or {}
    config = AveConfig.model_validate(config_data)

    output_dir = Path(checkpoint.get("output_dir") or ".")
    ctx = PipelineContext(
        session_id=checkpoint.get("session_id") or "",
        config=config,
        output_dir=output_dir,
    )
    input_file_path = checkpoint.get("input_file_path")
    if input_file_path:
        ctx.input_file_path = Path(input_file_path)

    config_file_path = checkpoint.get("config_file_path")
    if config_file_path:
        ctx.config_file_path = Path(config_file_path)

    ctx.source_manifest = checkpoint.get("source_manifest")
    ctx.ingestion_report = checkpoint.get("ingestion_report")
    ctx.integrity_report = checkpoint.get("integrity_report")
    ctx.detection_stats = checkpoint.get("detection_stats")
    ctx.final_report = checkpoint.get("final_report")
    ctx.report_paths = dict(checkpoint.get("report_paths") or {})
    ctx.current_layer = int(checkpoint.get("current_layer") or 0)
    ctx.errors = list(checkpoint.get("errors") or [])
    ctx.warnings = list(checkpoint.get("warnings") or [])

    ctx.integrity_findings = [
        Finding.from_dict(item) for item in checkpoint.get("integrity_findings") or []
    ]
    ctx.anomaly_findings = [
        Finding.from_dict(item) for item in checkpoint.get("anomaly_findings") or []
    ]
    ctx.verified_findings = [
        Finding.from_dict(item) for item in checkpoint.get("verified_findings") or []
    ]
    return ctx


def _attach_runtime_objects(
    ctx: PipelineContext,
    trail_writer: Optional[object],
    database: Optional[object],
    llm_client: Optional[object],
    config_path: Optional[Path],
) -> None:
    ctx.trail_writer = trail_writer
    ctx.database = database
    ctx.llm_client = llm_client
    if config_path is not None:
        ctx.config_file_path = Path(config_path)


def _run_layer(
    ctx: PipelineContext,
    handler: Callable[[PipelineContext], PipelineContext],
    layer: int,
    checkpoint: Optional[CheckpointManager],
) -> PipelineContext:
    try:
        ctx = handler(ctx)
        if checkpoint and ctx.config.pipeline.checkpoint_enabled:
            checkpoint.save_checkpoint(layer, ctx)
    except PipelineError as exc:
        ctx.add_error(str(exc))
    except StorageError as exc:
        ctx.add_error(str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        ctx.add_error(f"Layer {layer} failed: {exc}")
    return ctx


def build_pipeline(checkpoint: Optional[CheckpointManager] = None):
    """Build the LangGraph pipeline for a full run.

    Returns:
        A compiled LangGraph pipeline.
    """
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise PipelineError(
            "LangGraph is required for orchestration. Install langgraph>=0.2."
        ) from exc

    graph = StateGraph(PipelineContext)

    graph.add_node(
        "ingest",
        lambda ctx: _run_layer(ctx, layer1_ingestion.run, 1, checkpoint),
    )
    graph.add_node(
        "integrity",
        lambda ctx: _run_layer(ctx, layer2_integrity.run, 2, checkpoint),
    )
    graph.add_node(
        "anomaly",
        lambda ctx: _run_layer(ctx, layer3_anomaly.run, 3, checkpoint),
    )
    graph.add_node(
        "crossverify",
        lambda ctx: _run_layer(ctx, layer4_crossverify.run, 4, checkpoint),
    )
    graph.add_node(
        "synthesize",
        lambda ctx: _run_layer(ctx, layer5_synthesis.run, 5, checkpoint),
    )

    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "integrity")
    graph.add_edge("integrity", "anomaly")
    graph.add_edge("anomaly", "crossverify")
    graph.add_edge("crossverify", "synthesize")
    graph.add_edge("synthesize", END)

    def _after_ingest(ctx: PipelineContext):
        return "integrity" if not ctx.has_fatal_error() else END

    graph.add_conditional_edges("ingest", _after_ingest)

    return graph.compile()


def _run_sequential(
    ctx: PipelineContext,
    start_layer: int,
    checkpoint: Optional[CheckpointManager],
) -> PipelineContext:
    layers = [
        (1, layer1_ingestion.run),
        (2, layer2_integrity.run),
        (3, layer3_anomaly.run),
        (4, layer4_crossverify.run),
        (5, layer5_synthesis.run),
    ]

    for layer_number, handler in layers:
        if layer_number < start_layer:
            continue
        ctx = _run_layer(ctx, handler, layer_number, checkpoint)
        if layer_number == 1 and ctx.has_fatal_error():
            break
    return ctx


def _ask_resume(session_id: str) -> bool:
    if not sys.stdin.isatty():
        return True
    return Confirm.ask(
        f"Resume incomplete session {session_id}?",
        default=True,
    )


def run_pipeline(
    config: AveConfig,
    file_path: Path,
    output_dir: Path,
    session_id: str,
    trail_writer: Optional[object],
    database: Optional[object],
    llm_client: Optional[object] = None,
    config_path: Optional[Path] = None,
    force_rerun: bool = False,
) -> PipelineContext:
    """Execute the AVE pipeline with orchestration and checkpoint handling."""
    checkpoint = CheckpointManager(session_id, output_dir)
    ctx: PipelineContext

    if checkpoint.has_checkpoint(session_id, output_dir) and not force_rerun:
        if _ask_resume(session_id):
            payload = checkpoint.load_checkpoint(session_id, output_dir) or {}
            ctx = _build_context_from_checkpoint(payload)
            if ctx.current_layer >= 1:
                logger.warning(
                    "Checkpoint resume requires normalized data; restarting from Layer 1."
                )
                ctx.current_layer = 0
        else:
            checkpoint.clear_checkpoint(session_id, output_dir)
            ctx = PipelineContext(
                session_id=session_id,
                config=config,
                output_dir=Path(output_dir),
                input_file_path=Path(file_path),
            )
    else:
        ctx = PipelineContext(
            session_id=session_id,
            config=config,
            output_dir=Path(output_dir),
            input_file_path=Path(file_path),
        )

    _attach_runtime_objects(ctx, trail_writer, database, llm_client, config_path)

    if ctx.current_layer == 0:
        pipeline = build_pipeline(checkpoint)
        ctx = pipeline.invoke(ctx)
    else:
        ctx = _run_sequential(ctx, ctx.current_layer + 1, checkpoint)

    return ctx
