import sys
import types
from pathlib import Path

import pytest

from ave.export.pdf_exporter import PdfExporter


def test_pdf_exporter_generate_with_dummy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyHTML:
        def __init__(self, string: str) -> None:
            self.string = string

        def write_pdf(self, path: str) -> None:
            Path(path).write_bytes(b"pdf")

    dummy_weasyprint = types.SimpleNamespace(HTML=DummyHTML)
    dummy_markdown = types.SimpleNamespace(
        markdown=lambda text, extensions=None: f"<p>{text}</p>"
    )

    monkeypatch.setitem(sys.modules, "weasyprint", dummy_weasyprint)
    monkeypatch.setitem(sys.modules, "markdown", dummy_markdown)

    exporter = PdfExporter()
    assert exporter.available

    output_path = exporter.generate("hello", tmp_path / "report.pdf", "s1")
    assert output_path is not None
    assert output_path.exists()


def test_pdf_exporter_unavailable(tmp_path: Path) -> None:
    exporter = PdfExporter()
    if exporter.available:
        pytest.skip("WeasyPrint available in this environment")

    output_path = exporter.generate("hello", tmp_path / "report.pdf", "s1")
    assert output_path is None
