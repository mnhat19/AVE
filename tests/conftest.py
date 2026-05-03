from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture
def sample_csv_path(tmp_path: Path) -> Path:
    csv_path = tmp_path / "sample_data.csv"
    csv_path.write_text(
        textwrap.dedent(
            """
            account,amount,date
            Sales,100,2024-01-01
            Expense,-50,2024-01-02
            Sales,100,2024-01-01
            """
        ),
        encoding="utf-8",
    )
    return csv_path


@pytest.fixture
def minimal_config_path(tmp_path: Path) -> Path:
    config_path = tmp_path / "ave_config.yaml"
    config_path.write_text(
        textwrap.dedent(
            """
            pipeline:
              checkpoint_enabled: false
            ingestion:
              encoding: utf-8
              separator: ","
              header_row: 0
            integrity:
              null_threshold_default: 0.0
              outlier_std_multiplier: 3.0
              cross_checks: []
            llm:
              enabled: false
              provider: ollama
              model: mistral:7b
            output:
              directory: ./ave_output
              formats:
                - json
                - markdown
              pdf_enabled: false
            """
        ),
        encoding="utf-8",
    )
    return config_path


@pytest.fixture
def cli_runner() -> Generator[object, None, None]:
    from typer.testing import CliRunner

    yield CliRunner()
