from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from ave.exceptions import ConfigError


class PipelineConfig(BaseModel):
    max_rows: int = 50000
    use_polars_threshold: int = 10000
    checkpoint_enabled: bool = True

    @field_validator("max_rows")
    @classmethod
    def validate_max_rows(cls, value: int) -> int:
        if not (1 <= value <= 50000):
            raise ValueError("max_rows must be between 1 and 50000")
        return value


class IngestionConfig(BaseModel):
    encoding: str = "auto"
    header_row: int = 0
    skip_rows: List[int] = Field(default_factory=list)
    sheet_name: Optional[str | int] = None
    separator: str = "auto"


class ColumnConfig(BaseModel):
    dtype: Optional[str] = None
    currency: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    required: Optional[bool] = None
    null_threshold: Optional[float] = None
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    pattern: Optional[str] = None
    reference_values: Optional[List[str]] = None
    allowed_negative: Optional[bool] = None


class IntegrityConfig(BaseModel):
    null_threshold_default: float = 0.0
    outlier_std_multiplier: float = 3.0
    cross_checks: List[Dict[str, Any]] = Field(default_factory=list)


class LLMConfig(BaseModel):
    enabled: bool = False
    provider: str = "ollama"
    model: str = "mistral:7b"
    timeout_seconds: int = 30
    max_retries: int = 2
    batch_size: int = 50
    temperature: float = 0.1
    strip_pii_columns: List[str] = Field(default_factory=list)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        allowed = {"ollama", "groq", "mistral"}
        if value not in allowed:
            raise ValueError("llm.provider must be one of: ollama, groq, mistral")
        return value

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, value: float) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError("llm.temperature must be between 0.0 and 1.0")
        return value

    @field_validator("batch_size")
    @classmethod
    def validate_batch_size(cls, value: int) -> int:
        if not (1 <= value <= 500):
            raise ValueError("llm.batch_size must be between 1 and 500")
        return value


class OutputConfig(BaseModel):
    directory: str = "./ave_output"
    formats: List[str] = Field(default_factory=lambda: ["json", "markdown"])
    pdf_enabled: bool = False

    @field_validator("formats")
    @classmethod
    def validate_formats(cls, value: List[str]) -> List[str]:
        allowed = {"json", "markdown", "pdf"}
        invalid = [fmt for fmt in value if fmt not in allowed]
        if invalid:
            raise ValueError("output.formats must be subset of: json, markdown, pdf")
        return value


class ApprovalThresholds(BaseModel):
    level_1: int = 100000000
    level_2: int = 500000000


class AveConfig(BaseModel):
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    columns: Dict[str, ColumnConfig] = Field(default_factory=dict)
    primary_key_columns: List[str] = Field(default_factory=list)
    integrity: IntegrityConfig = Field(default_factory=IntegrityConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    audit_standard: str = "VAS"
    fiscal_year_end_month: int = 12
    fiscal_year_end_day: int = 31
    public_holidays: List[str] = Field(default_factory=list)
    approved_vendor_file: Optional[str] = None
    approval_thresholds: ApprovalThresholds = Field(default_factory=ApprovalThresholds)
    rules_file: str = "audit_rules.yaml"
    output: OutputConfig = Field(default_factory=OutputConfig)


def load_config(path: Path) -> AveConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        raw_text = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        line_info = ""
        if hasattr(exc, "problem_mark") and exc.problem_mark is not None:
            line_info = f" (line {exc.problem_mark.line + 1})"
        raise ConfigError(f"Invalid YAML in config file{line_info}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Unable to read config file: {config_path}") from exc

    if data is None:
        data = {}

    rules_file = data.get("rules_file")
    if rules_file:
        rules_path = Path(rules_file)
        if not rules_path.is_absolute():
            data["rules_file"] = str((config_path.parent / rules_path).resolve())

    try:
        return AveConfig.model_validate(data)
    except ValidationError as exc:
        messages = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", []))
            messages.append(f"{loc}: {err.get('msg')}")
        detail = "\n".join(messages)
        raise ConfigError(f"Config validation error:\n{detail}") from exc


def get_default_config() -> AveConfig:
    return AveConfig()
