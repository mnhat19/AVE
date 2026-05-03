from __future__ import annotations

import json
from pathlib import Path

import typer

from ave.cli import export_report, run, sessions
from ave.storage.database import AveDatabase


def test_cli_run_and_export_flow(tmp_path: Path, sample_csv_path: Path, minimal_config_path: Path) -> None:
    output_dir = tmp_path / "output"
    try:
        run(
            sample_csv_path,
            minimal_config_path,
            output_dir,
            llm="ollama",
            llm_model=None,
            sheet=None,
            verbose=False,
            dry_run=False,
            no_llm=True,
            report_format="all",
        )
    except typer.Exit as exc:
        assert exc.exit_code == 0

    assert output_dir.exists()

    db = AveDatabase(output_dir / "ave.db")
    session_rows = db.list_sessions()
    assert len(session_rows) == 1

    session = session_rows[0]
    session_id = session["session_id"]
    assert session["status"] == "completed"
    assert session["total_findings"] >= 0

    assert (output_dir / f"{session_id}_report.json").exists()
    assert (output_dir / f"{session_id}_report.md").exists()

    try:
        export_report(session_id, "json", output_dir)
    except typer.Exit as exc:
        assert exc.exit_code == 0

    exported_report = output_dir / f"{session_id}_report.json"
    assert exported_report.exists()
    payload = json.loads(exported_report.read_text(encoding="utf-8"))
    assert payload["report_meta"]["session_id"] == session_id

    try:
        sessions(last=5, output_dir=output_dir)
    except typer.Exit as exc:
        assert exc.exit_code == 0

    assert session_id in db.get_session(session_id)["session_id"]
