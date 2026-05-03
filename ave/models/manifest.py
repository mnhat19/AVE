from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class ColumnMeta:
    original_name: str
    normalized_name: str
    inferred_dtype: str
    null_count: int
    null_ratio: float
    unique_count: int
    sample_values: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.sample_values = [str(value) for value in self.sample_values[:3]]
        if not (0.0 <= self.null_ratio <= 1.0):
            raise ValueError("null_ratio must be between 0.0 and 1.0")

    def to_dict(self) -> dict:
        return {
            "original_name": self.original_name,
            "normalized_name": self.normalized_name,
            "inferred_dtype": self.inferred_dtype,
            "null_count": self.null_count,
            "null_ratio": self.null_ratio,
            "unique_count": self.unique_count,
            "sample_values": list(self.sample_values),
        }


@dataclass
class SourceFileMeta:
    path: str
    filename: str
    format: str
    size_bytes: int
    sha256_hash: str
    encoding: str
    sheet_name: Optional[str]

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "filename": self.filename,
            "format": self.format,
            "size_bytes": self.size_bytes,
            "sha256_hash": self.sha256_hash,
            "encoding": self.encoding,
            "sheet_name": self.sheet_name,
        }


@dataclass
class SchemaMeta:
    row_count_raw: int
    row_count_after_cleaning: int
    column_count: int
    dropped_empty_rows: int
    dropped_empty_cols: int
    columns: List[ColumnMeta]
    parse_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "row_count_raw": self.row_count_raw,
            "row_count_after_cleaning": self.row_count_after_cleaning,
            "column_count": self.column_count,
            "dropped_empty_rows": self.dropped_empty_rows,
            "dropped_empty_cols": self.dropped_empty_cols,
            "columns": [col.to_dict() for col in self.columns],
            "parse_warnings": list(self.parse_warnings),
        }


@dataclass
class SourceManifest:
    manifest_version: str
    created_at: str
    session_id: str
    source_file: SourceFileMeta
    schema: SchemaMeta

    def to_dict(self) -> dict:
        return {
            "manifest_version": self.manifest_version,
            "created_at": self.created_at,
            "session_id": self.session_id,
            "source_file": self.source_file.to_dict(),
            "schema": self.schema.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SourceManifest":
        source_file = SourceFileMeta(**data["source_file"])
        schema_data = data["schema"]
        columns = [ColumnMeta(**col) for col in schema_data.get("columns", [])]
        schema = SchemaMeta(
            row_count_raw=schema_data.get("row_count_raw", 0),
            row_count_after_cleaning=schema_data.get("row_count_after_cleaning", 0),
            column_count=schema_data.get("column_count", 0),
            dropped_empty_rows=schema_data.get("dropped_empty_rows", 0),
            dropped_empty_cols=schema_data.get("dropped_empty_cols", 0),
            columns=columns,
            parse_warnings=list(schema_data.get("parse_warnings", [])),
        )
        return cls(
            manifest_version=data["manifest_version"],
            created_at=data["created_at"],
            session_id=data["session_id"],
            source_file=source_file,
            schema=schema,
        )


def build_source_manifest(
    session_id: str,
    source_file: SourceFileMeta,
    schema: SchemaMeta,
    manifest_version: str = "1.0",
) -> SourceManifest:
    return SourceManifest(
        manifest_version=manifest_version,
        created_at=datetime.now(timezone.utc).isoformat(),
        session_id=session_id,
        source_file=source_file,
        schema=schema,
    )
