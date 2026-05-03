from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from ave.utils.logging import get_logger

logger = get_logger("pdf_exporter")


class PdfExporter:
    def __init__(self) -> None:
        self.available = False
        self._error: Optional[str] = None

        try:
            import weasyprint  # noqa: F401
            import markdown  # noqa: F401

            self.available = True
        except Exception as exc:  # pragma: no cover - optional dependency
            self._error = str(exc)

    def generate(
        self, markdown_content: str, output_path: Path, session_id: str
    ) -> Optional[Path]:
        if not self.available:
            logger.warning("PDF export skipped: WeasyPrint not installed")
            return None

        try:
            from weasyprint import HTML
            import markdown
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.warning("PDF export skipped: %s", exc)
            return None

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report_hash = hashlib.sha256(markdown_content.encode("utf-8")).hexdigest()
        body_html = markdown.markdown(markdown_content, extensions=["tables", "fenced_code"])

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    @page {{
      size: A4;
      margin: 1.5cm;
    }}
    body {{
      font-family: Arial, sans-serif;
      font-size: 12px;
      color: #1f2933;
    }}
    h1, h2, h3 {{
      color: #0f172a;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 16px;
    }}
    th, td {{
      border: 1px solid #d9e2ec;
      padding: 6px 8px;
      text-align: left;
    }}
    th {{
      background-color: #f5f7fa;
    }}
    code, pre {{
      font-family: "Courier New", monospace;
      background: #f5f5f5;
    }}
    footer {{
      position: running(footer);
      font-size: 10px;
      color: #52606d;
    }}
    @page {{
      @bottom-center {{
        content: "AVE Audit Report | Session: {session_id} | Hash: {report_hash}";
      }}
    }}
  </style>
</head>
<body>
  {body_html}
</body>
</html>
"""

        try:
            HTML(string=html_content).write_pdf(str(output_path))
        except Exception as exc:  # pragma: no cover - platform-specific
            logger.warning("PDF export failed: %s", exc)
            return None

        return output_path
