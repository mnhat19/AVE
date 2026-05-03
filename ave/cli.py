from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from ave import __version__
from ave.config import AveConfig, get_default_config, load_config
from ave.context import PipelineContext
from ave.engines.llm_client import GroqClient, LLMRouter, MistralClient, OllamaClient
from ave.engines.trail_writer import TrailWriter
from ave.exceptions import (
    AveError,
    ConfigError,
    LLMUnavailableError,
    PipelineError,
    StorageError,
)
from ave.models.trail import TrailEntry
from ave.orchestrator import run_pipeline
from ave.pipeline import layer5_synthesis
from ave.storage.database import AveDatabase
from ave.utils.hashing import hash_dict, hash_file
from ave.utils.logging import setup_logging

app = typer.Typer(name="ave", help="Autonomous Verification Engine for Auditors")
console = Console()

_DEFAULT_OUTPUT_DIR = Path("./ave_output")


def _parse_sheet(value: Optional[str]) -> Optional[str | int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    return text


def _apply_report_format(config: AveConfig, report_format: str) -> None:
    report_format = report_format.lower().strip()
    if report_format == "all":
        return

    if report_format == "json":
        config.output.formats = ["json"]
        config.output.pdf_enabled = False
    elif report_format == "markdown":
        config.output.formats = ["markdown"]
        config.output.pdf_enabled = False
    elif report_format == "pdf":
        config.output.formats = ["pdf"]
        config.output.pdf_enabled = True


def _print_summary(ctx: PipelineContext) -> None:
    findings = ctx.get_all_findings()
    severity_counts = {"high": 0, "medium": 0, "low": 0}
    for finding in findings:
        if finding.severity in severity_counts:
            severity_counts[finding.severity] += 1

    rating = (ctx.integrity_report or {}).get("overall_rating", "UNKNOWN")

    table = Table(title="Findings Summary", show_header=True, header_style="bold")
    table.add_column("Severity")
    table.add_column("Count", justify="right")
    for severity in ["high", "medium", "low"]:
        table.add_row(severity, str(severity_counts[severity]))

    panel = Panel.fit(
        f"Session: {ctx.session_id}\n"
        f"File: {ctx.input_file_path}\n"
        f"Rating: {rating}\n"
        f"Reports: {json.dumps(ctx.report_paths, ensure_ascii=False)}",
        title="AVE Run Summary",
    )

    console.print(panel)
    console.print(table)


def _create_session_record(
    session_id: str,
    file_path: Path,
    config_path: Optional[Path],
    config: AveConfig,
) -> dict:
    config_hash = hash_dict(config.model_dump())
    if config_path and config_path.exists():
        config_hash = hash_file(config_path)

    return {
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "input_file_path": str(file_path),
        "input_file_hash": hash_file(file_path),
        "config_file_path": str(config_path) if config_path else None,
        "config_hash": config_hash,
        "ave_version": __version__,
    }


@app.command()
def run(
    file: Path = typer.Argument(..., help="Input data file (CSV or Excel)"),
    config: Path = typer.Option(
        "./audit_rules.yaml", "--config", help="Rules and config file"
    ),
    output_dir: Path = typer.Option(
        _DEFAULT_OUTPUT_DIR, "--output-dir", help="Directory for reports and trail"
    ),
    llm: str = typer.Option(
        "ollama", "--llm", help="LLM provider: ollama, groq, mistral, none"
    ),
    llm_model: Optional[str] = typer.Option(
        None, "--llm-model", help="Override LLM model"
    ),
    sheet: Optional[str] = typer.Option(
        None, "--sheet", help="Excel sheet name or index"
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Verbose output"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run without writing outputs"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Disable LLM"),
    report_format: str = typer.Option(
        "all", "--report-format", help="all, json, markdown, pdf"
    ),
) -> None:
    setup_logging(verbose=verbose)

    try:
        file_path = Path(file).expanduser().resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        config_path = Path(config).expanduser().resolve()
        config_obj = load_config(config_path)

        llm = llm.lower().strip()
        if no_llm or llm == "none":
            config_obj.llm.enabled = False
        else:
            config_obj.llm.enabled = True
            config_obj.llm.provider = llm

        if llm_model:
            config_obj.llm.model = llm_model

        if sheet is not None:
            config_obj.ingestion.sheet_name = _parse_sheet(sheet)

        _apply_report_format(config_obj, report_format)

        output_dir = Path(output_dir).expanduser().resolve()
        config_obj.output.directory = str(output_dir)

        session_id = str(uuid4())
        trail_writer = None
        database = None
        temp_dir = None

        if dry_run:
            temp_dir = tempfile.TemporaryDirectory()
            output_dir = Path(temp_dir.name)
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            trail_writer = TrailWriter(session_id, output_dir)
            database = AveDatabase(output_dir / "ave.db")
            database.create_session(
                _create_session_record(session_id, file_path, config_path, config_obj)
            )

        llm_client = None
        if config_obj.llm.enabled:
            router = LLMRouter(config_obj.llm.provider, config_obj.llm)
            llm_client = router.get_client()
            if llm_client is None:
                console.print("LLM unavailable - continuing without LLM.")
                config_obj.llm.enabled = False

        ctx = run_pipeline(
            config_obj,
            file_path,
            output_dir,
            session_id,
            trail_writer,
            database,
            llm_client=llm_client,
            config_path=config_path,
        )

        console.print(f"DEBUG: Output dir: {output_dir}")
        console.print(f"DEBUG: Report paths: {ctx.report_paths}")
        console.print(f"DEBUG: Current layer: {ctx.current_layer}")
        console.print(f"DEBUG: Output dir exists: {output_dir.exists()}")

        if temp_dir is not None:
            temp_dir.cleanup()

        _print_summary(ctx)
        raise typer.Exit(code=0)

    except (ConfigError, FileNotFoundError) as exc:
        console.print(f"Input error: {exc}")
        raise typer.Exit(code=1)
    except LLMUnavailableError as exc:
        console.print(f"LLM unavailable: {exc}")
        raise typer.Exit(code=3)
    except PipelineError as exc:
        console.print(f"Pipeline error: {exc}")
        raise typer.Exit(code=2)
    except StorageError as exc:
        console.print(f"Output error: {exc}")
        raise typer.Exit(code=4)
    except KeyboardInterrupt:
        console.print("Run interrupted by user.")
        raise typer.Exit(code=2)
    except AveError as exc:
        console.print(f"Error: {exc}")
        raise typer.Exit(code=1)


@app.command()
def review(
    session: str = typer.Option(..., "--session", help="Session ID"),
    output_dir: Path = typer.Option(
        _DEFAULT_OUTPUT_DIR, "--output-dir", help="Output directory"
    ),
) -> None:
    if not sys.stdin.isatty():
        console.print("Review requires interactive terminal.")
        raise typer.Exit(code=1)

    db = AveDatabase(Path(output_dir) / "ave.db")
    session_row = db.get_session(session)
    if not session_row:
        console.print(f"Session not found: {session}")
        raise typer.Exit(code=1)

    findings = db.get_findings(session)
    if not findings:
        console.print(f"No findings to review for session {session}")
        raise typer.Exit(code=0)

    trail_path = session_row.get("trail_file_path")
    trail_output = Path(trail_path).parent if trail_path else Path(output_dir)
    trail_writer = TrailWriter(session, trail_output)

    accepted = 0
    rejected = 0
    skipped = 0
    wrote_trail = False

    for finding in findings:
        severity_color = {"high": "red", "medium": "yellow", "low": "blue"}.get(
            finding.severity, "white"
        )
        title = Text(f"Finding {finding.finding_id}", style=severity_color)

        table = Table(show_header=True, header_style="bold")
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("Rule", finding.rule_id or "LLM")
        table.add_row("Severity", finding.severity)
        table.add_row("Reasoning", finding.reasoning)
        table.add_row("Row Index", str(finding.row_index))

        row_data = finding.row_data or {}
        for key, value in row_data.items():
            table.add_row(str(key), str(value))

        console.print(Panel(table, title=title))

        decision = Prompt.ask(
            "Decision [A]ccept/[R]eject/[S]kip/[Q]uit",
            choices=["A", "R", "S", "Q"],
            default="S",
        )
        decision = decision.upper()

        if decision == "Q":
            break

        if decision == "S":
            skipped += 1
            continue

        note = Prompt.ask("Note (optional)", default="")
        decision_value = "accepted" if decision == "A" else "rejected"
        timestamp = datetime.now(timezone.utc).isoformat()

        db.update_finding_decision(finding.finding_id, decision_value, timestamp, note)
        trail_writer.write(
            TrailEntry(
                session_id=session,
                agent_id="review",
                action_type="HUMAN_REVIEW_RECEIVED",
                input_hash=hash_dict(finding.to_dict()),
                output_hash=hash_dict({"decision": decision_value}),
                reasoning_summary=f"Human review: {decision_value}",
                human_decision=decision_value,
                human_decision_timestamp=timestamp,
                human_decision_note=note or None,
                duration_ms=0,
            )
        )
        wrote_trail = True

        if decision == "A":
            accepted += 1
        else:
            rejected += 1

    if wrote_trail:
        trail_writer.finalize()

    console.print(
        f"Review summary: accepted={accepted}, rejected={rejected}, skipped={skipped}"
    )


@app.command("export")
def export_report(
    session: str = typer.Option(..., "--session", help="Session ID"),
    format: str = typer.Option("json", "--format", help="pdf, json, markdown"),
    output_dir: Path = typer.Option(
        _DEFAULT_OUTPUT_DIR, "--output-dir", help="Output directory"
    ),
) -> None:
    format = format.lower().strip()
    if format not in {"json", "markdown", "pdf"}:
        console.print(f"Unknown format: {format}")
        raise typer.Exit(code=1)

    db = AveDatabase(Path(output_dir) / "ave.db")
    session_row = db.get_session(session)
    if not session_row:
        console.print(f"Session not found: {session}")
        raise typer.Exit(code=1)

    config_path = session_row.get("config_file_path")
    if config_path and Path(config_path).exists():
        config_obj = load_config(Path(config_path))
    else:
        config_obj = get_default_config()

    config_obj.output.directory = str(output_dir)
    config_obj.output.formats = [format]
    config_obj.output.pdf_enabled = format == "pdf"

    trail_path = session_row.get("trail_file_path")
    if trail_path:
        output_dir = Path(trail_path).parent

    ctx = PipelineContext(
        session_id=session,
        config=config_obj,
        output_dir=Path(output_dir),
    )
    input_file = session_row.get("input_file_path")
    if input_file:
        ctx.input_file_path = Path(input_file)
    if config_path:
        ctx.config_file_path = Path(config_path)

    ctx.verified_findings = db.get_findings(session)
    ctx.trail_writer = None
    ctx.database = None

    ctx = layer5_synthesis.run(ctx)

    console.print(f"Exported reports: {json.dumps(ctx.report_paths, ensure_ascii=False)}")


@app.command()
def sessions(
    last: int = typer.Option(10, "--last", help="Number of sessions to show"),
    output_dir: Path = typer.Option(
        _DEFAULT_OUTPUT_DIR, "--output-dir", help="Output directory"
    ),
) -> None:
    db = AveDatabase(Path(output_dir) / "ave.db")
    items = db.list_sessions(limit=last)
    if not items:
        console.print("No sessions found")
        raise typer.Exit(code=0)

    table = Table(show_header=True, header_style="bold")
    table.add_column("Session ID")
    table.add_column("Created")
    table.add_column("File")
    table.add_column("Status")
    table.add_column("Rating")
    table.add_column("Findings", justify="right")

    for row in items:
        table.add_row(
            str(row.get("session_id")),
            str(row.get("created_at")),
            str(row.get("input_file_path")),
            str(row.get("status")),
            str(row.get("overall_rating")),
            str(row.get("total_findings")),
        )

    console.print(table)


@app.command("validate-config")
def validate_config_cmd(
    config: Path = typer.Option(..., "--config", help="Config file path"),
) -> None:
    from ave.engines.rule_engine import load_rules_from_yaml, validate_rules

    try:
        config_obj = load_config(Path(config))
        rules = load_rules_from_yaml(Path(config_obj.rules_file))
        errors = validate_rules(rules)
        if errors:
            table = Table(show_header=True, header_style="bold")
            table.add_column("Error")
            for err in errors:
                table.add_row(err)
            console.print(table)
            raise typer.Exit(code=1)
        console.print(f"Config valid: {len(rules)} rules loaded")
    except ConfigError as exc:
        console.print(f"Config error: {exc}")
        raise typer.Exit(code=1)
    except AveError as exc:
        console.print(f"Validation error: {exc}")
        raise typer.Exit(code=1)


@app.command("check-llm")
def check_llm_cmd(
    provider: str = typer.Option("ollama", "--provider", help="ollama, groq, mistral"),
) -> None:
    provider = provider.lower().strip()
    config_obj = get_default_config()
    config_obj.llm.provider = provider

    try:
        if provider == "ollama":
            client = OllamaClient(config_obj.llm.model, config=config_obj.llm)
        elif provider == "groq":
            client = GroqClient(config_obj.llm.model, config=config_obj.llm)
        elif provider == "mistral":
            client = MistralClient(config_obj.llm.model, config=config_obj.llm)
        else:
            console.print(f"Unknown provider: {provider}")
            raise typer.Exit(code=1)

        available = client.health_check()
        if available:
            console.print(f"LLM provider {provider} is available")
            if provider == "ollama":
                base_url = os.environ.get("AVE_OLLAMA_URL", "http://localhost:11434")
                try:
                    response = httpx.get(f"{base_url}/api/tags", timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        models = [item.get("name") for item in data.get("models", [])]
                        if models:
                            console.print("Available models:")
                            for model in models:
                                console.print(f"- {model}")
                except httpx.HTTPError:
                    console.print("Unable to list Ollama models.")
        else:
            console.print(f"LLM provider {provider} is not available")

    except LLMUnavailableError as exc:
        console.print(f"LLM provider {provider} is not available: {exc}")
        raise typer.Exit(code=1)
def verify(
    trail_file: Path = typer.Argument(..., help="Trail file to verify"),
) -> None:
    """Verify the integrity of an AVE audit trail."""
    from ave.engines.trail_writer import TrailWriter

    trail_path = Path(trail_file)
    if not trail_path.exists():
        console.print(f"Trail file not found: {trail_path}")
        raise typer.Exit(code=1)

    try:
        # Read and verify the trail
        with trail_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            console.print("Trail file is empty")
            raise typer.Exit(code=1)

        # Check final hash
        last_line = lines[-1].strip()
        if not last_line:
            console.print("Trail file ends with empty line")
            raise typer.Exit(code=1)

        try:
            final_entry = json.loads(last_line)
        except json.JSONDecodeError:
            console.print("Invalid JSON in final trail entry")
            raise typer.Exit(code=1)

        if final_entry.get("action_type") != "trail_finalized":
            console.print("Trail is not finalized")
            raise typer.Exit(code=1)

        expected_hash = final_entry.get("chain_hash")
        if not expected_hash:
            console.print("No chain hash found in final entry")
            raise typer.Exit(code=1)

        # Compute actual hash of all lines except the last
        content = "".join(lines[:-1]).encode("utf-8")
        actual_hash = hashlib.sha256(content).hexdigest()

        if actual_hash == expected_hash:
            console.print("Trail integrity verified successfully")
            console.print(f"Session ID: {final_entry.get('session_id')}")
            console.print(f"Total entries: {len(lines) - 1}")
        else:
            console.print("Trail integrity check failed")
            console.print(f"Expected hash: {expected_hash}")
            console.print(f"Actual hash: {actual_hash}")
            raise typer.Exit(code=1)

    except Exception as exc:
        console.print(f"Error verifying trail: {exc}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
