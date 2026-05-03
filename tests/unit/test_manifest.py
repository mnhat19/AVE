import pytest

from ave.models.manifest import ColumnMeta, SchemaMeta, SourceFileMeta, SourceManifest


def test_column_meta_sample_values_limit() -> None:
    meta = ColumnMeta(
        original_name="A",
        normalized_name="a",
        inferred_dtype="text",
        null_count=0,
        null_ratio=0.0,
        unique_count=3,
        sample_values=["1", "2", "3", "4"],
    )
    assert meta.sample_values == ["1", "2", "3"]


def test_column_meta_null_ratio_validation() -> None:
    with pytest.raises(ValueError):
        ColumnMeta(
            original_name="A",
            normalized_name="a",
            inferred_dtype="text",
            null_count=0,
            null_ratio=1.5,
            unique_count=0,
            sample_values=[],
        )


def test_source_manifest_round_trip() -> None:
    source = SourceFileMeta(
        path="/tmp/file.csv",
        filename="file.csv",
        format="csv",
        size_bytes=10,
        sha256_hash="x" * 64,
        encoding="utf-8",
        sheet_name=None,
    )
    schema = SchemaMeta(
        row_count_raw=10,
        row_count_after_cleaning=10,
        column_count=2,
        dropped_empty_rows=0,
        dropped_empty_cols=0,
        columns=[
            ColumnMeta(
                original_name="A",
                normalized_name="a",
                inferred_dtype="text",
                null_count=0,
                null_ratio=0.0,
                unique_count=1,
                sample_values=["x"],
            )
        ],
        parse_warnings=[],
    )
    manifest = SourceManifest(
        manifest_version="1.0",
        created_at="2025-05-01T00:00:00",
        session_id="s1",
        source_file=source,
        schema=schema,
    )
    payload = manifest.to_dict()
    clone = SourceManifest.from_dict(payload)
    assert clone.session_id == manifest.session_id
    assert clone.source_file.filename == "file.csv"
