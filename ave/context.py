from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ave.config import AveConfig
from ave.models.finding import Finding
from ave.utils.logging import get_logger

logger = get_logger("context")


@dataclass
class PipelineContext:
    session_id: str
    config: AveConfig
    output_dir: Path
    input_file_path: Optional[Path] = None

    raw_df: Optional[Any] = None
    normalized_df: Optional[Any] = None
    source_manifest: Optional[dict] = None
    ingestion_report: Optional[dict] = None

    integrity_report: Optional[dict] = None
    integrity_findings: List[Finding] = field(default_factory=list)

    anomaly_findings: List[Finding] = field(default_factory=list)
    detection_stats: Optional[dict] = None

    verified_findings: List[Finding] = field(default_factory=list)

    final_report: Optional[dict] = None
    report_paths: Dict[str, str] = field(default_factory=dict)

    current_layer: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    trail_writer: Optional[Any] = None
    llm_client: Optional[Any] = None

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        logger.error(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)
        logger.warning(message)

    def get_all_findings(self) -> List[Finding]:
        combined: List[Finding] = []
        for findings in [self.integrity_findings, self.anomaly_findings, self.verified_findings]:
            if findings:
                combined.extend(findings)

        deduped: Dict[str, Finding] = {}
        for finding in combined:
            if finding.finding_id not in deduped:
                deduped[finding.finding_id] = finding

        return list(deduped.values())

    def has_fatal_error(self) -> bool:
        return bool(self.errors)

    def to_checkpoint_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "config": self.config.model_dump(),
            "output_dir": str(self.output_dir),
            "input_file_path": str(self.input_file_path) if self.input_file_path else None,
            "source_manifest": self.source_manifest,
            "ingestion_report": self.ingestion_report,
            "integrity_report": self.integrity_report,
            "integrity_findings": [finding.to_dict() for finding in self.integrity_findings],
            "anomaly_findings": [finding.to_dict() for finding in self.anomaly_findings],
            "detection_stats": self.detection_stats,
            "verified_findings": [finding.to_dict() for finding in self.verified_findings],
            "final_report": self.final_report,
            "report_paths": dict(self.report_paths),
            "current_layer": self.current_layer,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }
