# AVE — AI-Ready Context Document
### Autonomous Verification Engine for Auditors
**Derived from:** AVE PRD v1.0 (01/05/2025)
**Document version:** 1.0
**Classification:** Internal — AI Coding Agent Use

---

> **Purpose of this document:** This document is the single authoritative reference for an AI coding agent implementing the AVE system. It is self-contained — no re-reading of the original PRD is required. Every section has been expanded, disambiguated, and operationalized with explicit assumptions where the PRD was silent.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Functional Specification (Expanded)](#2-functional-specification-expanded)
3. [Non-Functional Requirements](#3-non-functional-requirements)
4. [Data Model & Schema Design](#4-data-model--schema-design)
5. [API Design (CLI & Internal)](#5-api-design-cli--internal)
6. [System Architecture (Detailed)](#6-system-architecture-detailed)
7. [Edge Cases & Error Handling](#7-edge-cases--error-handling)
8. [Development Plan](#8-development-plan)
9. [Testing Strategy](#9-testing-strategy)
10. [AI Coding Instructions](#10-ai-coding-instructions)

---

## 1. System Overview

### 1.1 Purpose

AVE (Autonomous Verification Engine) is a **local-first, CLI-driven AI Agent pipeline** that automates repetitive data verification tasks for auditors. It processes structured financial/accounting data files (CSV, Excel), detects anomalies using configurable rule-based and LLM-assisted reasoning, produces verified findings, and generates immutable audit trails — entirely offline with zero mandatory cloud cost.

### 1.2 Scope

**In scope (MVP):**
- Single-file ingestion: CSV and Excel (.xlsx) up to 50,000 rows
- Five-layer sequential verification pipeline
- Rule-based anomaly detection (≥20 configurable rules via YAML)
- Immutable local audit trail (JSONL + SQLite)
- CLI interface (`ave run`)
- Report export: Markdown, JSON, PDF

**Out of scope (MVP — explicitly deferred):**
- Web UI / Desktop UI
- Multi-file concurrent processing
- Database connectors (SQL, ERP)
- LLM fine-tuning
- Cloud deployment
- Multi-user / authentication
- PDF/email document ingestion
- Multi-agent collaboration bus

### 1.3 Stakeholders

| Role | Description |
|------|-------------|
| **Primary User** | Internal or independent auditor, 2–5 years experience, comfortable with CLI |
| **Decision Maker** | Auditor retains final judgment — AVE is advisory only |
| **System Operator** | Same as user in MVP — single-user local deployment |
| **Future Stakeholder** | Audit firm IT admin (deferred) |

### 1.4 High-Level Architecture

```
User (CLI)
    │
    ▼
┌───────────────────────────────────┐
│         AVE CLI (Typer)           │  ← Entry point: `ave run`
└─────────────────┬─────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│              Pipeline Orchestrator (LangGraph)       │
│                                                     │
│  ┌───────────┐  ┌───────────┐  ┌────────────────┐  │
│  │ Layer 1   │→ │ Layer 2   │→ │   Layer 3      │  │
│  │ Ingestion │  │ Integrity │  │ Anomaly Detect │  │
│  │  Agent    │  │  Agent    │  │    Agent       │  │
│  └───────────┘  └───────────┘  └────────────────┘  │
│                                        │            │
│                  ┌─────────────────────┘            │
│                  ▼                                  │
│  ┌───────────────────┐   ┌──────────────────────┐  │
│  │ Layer 4           │→  │ Layer 5              │  │
│  │ Cross-Verification│   │ Synthesis Agent      │  │
│  │ Agent             │   │ (Report + Trail)     │  │
│  └───────────────────┘   └──────────────────────┘  │
└─────────────────────────────────────────────────────┘
                  │
        ┌─────────┴──────────┐
        ▼                    ▼
┌──────────────┐    ┌────────────────┐
│  SQLite DB   │    │  JSONL Audit   │
│  (metadata,  │    │  Trail (append │
│   findings)  │    │  only)         │
└──────────────┘    └────────────────┘
                  │
        ┌─────────┴──────────┐
        ▼                    ▼
┌──────────────┐    ┌────────────────┐
│  LLM Router  │    │  Rule Engine   │
│  (Ollama /   │    │  (YAML DSL)    │
│  Groq/Mistral│    │                │
└──────────────┘    └────────────────┘
```

### 1.5 Core Product Principle

> AVE is advisory, not actuative. All pipeline operations are **read-only** with respect to source data. Auditors retain final decision authority. Every finding must be traceable to a specific source row and rule.

---

## 2. Functional Specification (Expanded)

### 2.1 Layer 1 — Ingestion Agent

#### 2.1.1 Purpose
Accept raw input files, detect format, parse content, normalize schema, and produce a clean DataFrame plus a Source Manifest.

#### 2.1.2 Inputs
| Parameter | Type | Source | Notes |
|-----------|------|--------|-------|
| `file_path` | `str` | CLI `--file` arg | Absolute or relative path |
| `file_type` | `str` | Auto-detected | Override via `--type csv\|xlsx` |
| `encoding` | `str` | Auto-detected | Default: try UTF-8, then UTF-8-BOM, then latin-1 |
| `sheet_name` | `str\|int` | Config or CLI | For Excel: default = first sheet (index 0) |
| `header_row` | `int` | Config | Default = 0. Override if file has metadata rows above headers |
| `skip_rows` | `list[int]` | Config | Rows to skip (0-indexed), e.g., footer rows |

#### 2.1.3 Processing Steps (in order)

1. **File existence check** — Raise `FileNotFoundError` with guidance if file missing.
2. **Format detection** — Use file extension first; fallback to magic bytes (PK\x03\x04 = xlsx/zip; detect CSV by attempting parse).
3. **Encoding detection** — Use `chardet` library. If confidence < 0.7, warn and fall back to UTF-8 with `errors='replace'`.
4. **Parsing** — 
   - CSV: `pandas.read_csv` with detected encoding and separator. Auto-detect separator from `[',', ';', '\t', '|']` by testing each on first 5 rows.
   - Excel: `pandas.read_excel` with `openpyxl` engine. Read sheet name from config; if not specified, use first sheet.
5. **Row/column pruning** — Drop fully empty rows and fully empty columns. Log count of dropped rows/columns.
6. **Header normalization** — Strip whitespace from all column names. Convert to `snake_case`. Detect and resolve duplicate column names by appending `_1`, `_2`, etc.
7. **Schema inference** — For each column, infer dominant dtype: `date`, `numeric`, `currency`, `text`, `boolean`. Store in Source Manifest.
8. **Value normalization** — 
   - Dates: Attempt parse with formats `['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y', '%Y%m%d']`. Store as ISO 8601 string internally.
   - Numbers: Remove thousands separators (`,` or `.` depending on locale). Handle Vietnamese locale (`.` as thousands, `,` as decimal).
   - Currency: Strip currency symbols (`VND`, `₫`, `$`, `USD`). Store raw numeric value; preserve currency type in metadata.
   - Text: Strip leading/trailing whitespace. Normalize Unicode to NFC.
9. **Source Manifest creation** — See Section 4.2 for schema.
10. **Output** — Normalized DataFrame (Polars for files >10K rows, Pandas otherwise) + Source Manifest dict.

#### 2.1.4 Outputs
- `normalized_df`: Polars/Pandas DataFrame with clean column names and normalized values
- `source_manifest`: Dict (see Section 4.2)
- `ingestion_report`: Dict with stats (row count, column count, dropped rows, encoding used, parse warnings)

#### 2.1.5 State Transitions
```
IDLE → FILE_RECEIVED → FORMAT_DETECTED → PARSED → NORMALIZED → MANIFEST_CREATED → READY
                ↓                ↓           ↓
           FORMAT_ERROR    PARSE_ERROR  NORMALIZE_WARNING (non-fatal, logged)
```

---

### 2.2 Layer 2 — Integrity Agent

#### 2.2.1 Purpose
Apply 10 mandatory integrity checks on the normalized DataFrame. Produce a severity-scored Integrity Report.

#### 2.2.2 Mandatory Integrity Checks (10 rules — always run, not configurable off)

| Check ID | Name | Logic | Severity |
|----------|------|-------|----------|
| IC-001 | Null completeness | For each column: if null ratio > threshold (default 0%), flag. Threshold configurable per column in YAML. | `high` if required field null, `low` otherwise |
| IC-002 | Duplicate row detection | Hash of all columns per row. Flag exact duplicates. | `high` |
| IC-003 | Duplicate key detection | If `primary_key_columns` defined in config, flag duplicate key values. | `high` |
| IC-004 | Date range validity | Dates must fall within `[min_date, max_date]` from config. Default: 1900-01-01 to today+1. | `medium` |
| IC-005 | Numeric range validity | For numeric columns with `min_value`/`max_value` in config, flag out-of-range values. | `medium` |
| IC-006 | Negative amount detection | Flag rows where amount columns contain negative values (configurable: some amount types allow negatives). | `medium` |
| IC-007 | Format consistency | For columns with defined format patterns (e.g., invoice numbers `^INV-\d{6}$`), flag non-conforming values. | `low` |
| IC-008 | Referential integrity | If `foreign_key` mappings provided, flag values not present in reference set. | `high` |
| IC-009 | Cross-column logical consistency | Configurable cross-column rules (e.g., `end_date >= start_date`, `total = quantity * unit_price`). | `medium` |
| IC-010 | Statistical outlier detection | For numeric columns: flag values beyond `mean ± N*std` (default N=3). Z-score method. | `low` |

#### 2.2.3 Severity Score Calculation
- Each finding has severity: `high=3`, `medium=2`, `low=1`
- `total_severity_score = sum(severity_value for finding in findings)`
- `overall_rating`: `CLEAN` (score=0), `MINOR` (1-10), `MODERATE` (11-30), `SEVERE` (>30)

#### 2.2.4 Outputs
- `integrity_report`: Dict with per-check results, per-row findings, total score, overall rating
- `integrity_findings`: List of `IntegrityFinding` objects (see Section 4.3)

---

### 2.3 Layer 3 — Anomaly Detection Agent

#### 2.3.1 Purpose
Apply configurable rule-based detection plus optional LLM-assisted reasoning to flag suspicious transactions/rows.

#### 2.3.2 Two Detection Modes

**Mode A — Rule Engine (always runs first)**
- Load rules from `audit_rules.yaml`
- Evaluate each rule against each row (vectorized where possible)
- Assign flag with rule ID, severity, and confidence=1.0 (deterministic)

**Mode B — LLM Reasoning (optional, activated when `llm_enabled: true` in config)**
- Only runs on rows that passed all rule checks (to find non-rule-covered anomalies)
- Batch rows into groups of 50 (configurable: `llm_batch_size`)
- Send structured prompt to LLM with: column definitions, row values, audit context
- LLM returns flagged row indices with reasoning text
- Confidence score derived from LLM's stated certainty (parsed from response)
- **Assumption:** LLM response is JSON-formatted (enforced via prompt and retry)

#### 2.3.3 Rule YAML DSL Specification

```yaml
# Full rule schema
rules:
  - id: string          # Unique, e.g. "R001" — REQUIRED
    name: string        # Human-readable name — REQUIRED
    description: string # Optional explanation
    field: string       # Column name to apply condition to (single field rules)
    fields: [string]    # Multiple columns (multi-field rules) — alternative to `field`
    condition: string   # See condition types below — REQUIRED
    threshold: number   # Numeric threshold for gt/lt/gte/lte conditions
    value: any          # Exact match value for eq/neq conditions
    values: [any]       # List of values for in/not_in conditions
    pattern: string     # Regex pattern for matches condition
    reference_field: string  # For cross-field comparisons
    severity: high|medium|low  # REQUIRED
    requires_cross_check: bool  # Default: false
    active: bool        # Default: true. Set false to disable without deleting.
    tags: [string]      # Optional grouping tags
    audit_standard: string  # e.g., "VAS-01", "ISA-240" for compliance mapping
```

**Supported condition types:**
| Condition | Meaning |
|-----------|---------|
| `gt` | field > threshold |
| `gte` | field >= threshold |
| `lt` | field < threshold |
| `lte` | field <= threshold |
| `eq` | field == value |
| `neq` | field != value |
| `in` | field in values |
| `not_in` | field not in values |
| `is_null` | field is null |
| `not_null` | field is not null |
| `matches` | field matches regex pattern |
| `not_matches` | field does not match regex pattern |
| `weekend_transaction` | date field falls on Saturday or Sunday |
| `end_of_period` | date field is last day of month/quarter/year (configurable) |
| `cross_field_gt` | field > reference_field |
| `cross_field_eq` | field == reference_field |
| `compound` | AND/OR combination of sub-conditions (see below) |

**Compound condition syntax:**
```yaml
condition: compound
logic: AND  # or OR
sub_conditions:
  - field: approval_special
    condition: is_null
  - field: transaction_date
    condition: weekend_transaction
```

#### 2.3.4 Minimum Rule Set (20 rules — shipped as `default_rules.yaml`)

| ID | Name | Condition | Severity |
|----|------|-----------|----------|
| R001 | Amount exceeds approval threshold | `amount > 500,000,000 VND` | high |
| R002 | Weekend transaction without approval | `weekend_transaction AND missing(approval_special)` | high |
| R003 | Round number transaction | `amount % 1,000,000 == 0 AND amount > 0` | medium |
| R004 | Sequential transaction numbers | `id - prev_id == 1 AND amount == prev_amount` | medium |
| R005 | Late-night transaction | `transaction_time between 22:00-06:00` | medium |
| R006 | Year-end transaction spike | `date in last 3 days of fiscal year` | medium |
| R007 | Transaction to unknown vendor | `vendor_id not in approved_vendor_list` | high |
| R008 | Duplicate invoice reference | `invoice_no appears > 1 time` | high |
| R009 | Amount just below approval threshold | `amount between threshold*0.9 and threshold` | high |
| R010 | Missing required approval | `amount > 100,000,000 AND approver is null` | high |
| R011 | Currency mismatch | `currency != expected_currency for account` | medium |
| R012 | Negative revenue | `revenue < 0` | high |
| R013 | Credit > Debit imbalance | `total_credit != total_debit` (per journal entry) | high |
| R014 | Unmatched intercompany transaction | `interco_flag = true AND matching_id is null` | medium |
| R015 | Transaction on public holiday | `transaction_date in public_holiday_list` | low |
| R016 | Excessive discount | `discount_rate > 30%` | medium |
| R017 | Price deviation from standard | `unit_price deviates > 20% from std_price` | medium |
| R018 | Frequent small transactions | `same vendor, same day, count > 5, each < threshold` | high |
| R019 | Backdated entry | `entry_date > transaction_date by > 30 days` | medium |
| R020 | Missing supporting document reference | `amount > 10,000,000 AND document_ref is null` | medium |

#### 2.3.5 LLM Prompt Template (for Mode B)

```python
ANOMALY_DETECTION_PROMPT = """
You are an expert auditor reviewing financial transaction data.
Audit context: {audit_context}
Column definitions: {column_definitions}

Review the following {row_count} transactions and identify any that appear anomalous, 
suspicious, or warrant further investigation based on audit best practices.

Transactions (JSON):
{transactions_json}

Previously flagged rows (do not re-flag): {already_flagged_indices}

Respond ONLY with a JSON object in this exact format:
{{
  "flagged": [
    {{
      "row_index": <integer>,
      "reasoning": "<string: specific reason, referencing column values>",
      "confidence": <float 0.0-1.0>,
      "severity": "high|medium|low"
    }}
  ],
  "summary": "<string: overall observations>"
}}

If no anomalies found, return {{"flagged": [], "summary": "No additional anomalies detected."}}
"""
```

#### 2.3.6 Outputs
- `anomaly_findings`: List of `AnomalyFinding` objects
- `detection_stats`: Dict with counts per rule, LLM calls made, rows evaluated

---

### 2.4 Layer 4 — Cross-Verification Agent

**Note: Layer 4 is P1 priority (post-MVP). Implement as a stub in MVP that passes Layer 3 findings through unchanged.**

#### 2.4.1 MVP Stub Behavior
- Accept Layer 3 findings
- Return them unchanged with `cross_verified: false` flag on each finding
- Log that cross-verification was skipped

#### 2.4.2 Full Implementation (Alpha)
- Accept an optional `--cross-file` second data source
- For each finding from Layer 3, attempt to locate corresponding record in cross-file
- If cross-file has matching record with contradicting data → `status: CONFIRMED`
- If cross-file has matching record with consistent data → `status: UNCONFIRMED` (may be false positive)
- If cross-file has no matching record → `status: UNVERIFIABLE`
- Output: enriched findings list with `cross_verification_status`

---

### 2.5 Layer 5 — Synthesis Agent

#### 2.5.1 Purpose
Aggregate all findings from Layers 2–4, map to audit standards (if configured), produce human-readable and machine-readable reports, and finalize the audit trail.

#### 2.5.2 Report Structure

**JSON Report (`{session_id}_report.json`)**
```json
{
  "report_meta": {
    "session_id": "string",
    "generated_at": "ISO 8601",
    "ave_version": "string",
    "file_processed": "string",
    "config_file": "string",
    "config_hash": "string"
  },
  "source_summary": { /* from Source Manifest */ },
  "integrity_summary": {
    "overall_rating": "CLEAN|MINOR|MODERATE|SEVERE",
    "total_score": 0,
    "checks_run": 10,
    "findings_count": 0
  },
  "anomaly_summary": {
    "total_flagged": 0,
    "by_severity": { "high": 0, "medium": 0, "low": 0 },
    "by_rule": {},
    "llm_assisted_count": 0
  },
  "findings": [ /* full list of Finding objects */ ],
  "audit_trail_ref": "path/to/session.jsonl",
  "recommendations": [ /* generated by LLM from findings summary */ ]
}
```

**Markdown Report (`{session_id}_report.md`)**
```markdown
# AVE Audit Report
**Session:** {session_id}
**File:** {filename}
**Date:** {date}
**Status:** {overall_status}

## Executive Summary
{llm_generated_summary: ≤200 words}

## Integrity Check Results
{table of IC checks with pass/fail}

## Anomaly Findings ({count})
{table: Row | Rule | Description | Severity | Evidence}

## Audit Trail Reference
Trail file: {path}
Hash: {hash}
```

**PDF Report** — Generated from Markdown using WeasyPrint or ReportLab. Include AVE header, page numbers, and hash footer.

#### 2.5.3 Recommendations Generation
- If `llm_enabled: true`: Send findings summary to LLM with prompt asking for 3-5 actionable recommendations
- If `llm_enabled: false`: Use template-based recommendations based on finding patterns

---

### 2.6 Audit Trail Engine

#### 2.6.1 Trail Entry Schema
Every agent action writes one entry:
```json
{
  "session_id": "string",
  "entry_id": "string (UUID v4)",
  "timestamp": "ISO 8601 with timezone",
  "agent_id": "ingestion|integrity|anomaly|cross_verify|synthesis",
  "action_type": "string (see Action Types below)",
  "input_hash": "SHA-256 of serialized input",
  "output_hash": "SHA-256 of serialized output",
  "reasoning_summary": "string (≤500 chars)",
  "human_decision": null,
  "human_decision_timestamp": null,
  "human_decision_note": null,
  "confidence": 1.0,
  "duration_ms": 0,
  "llm_model_used": null,
  "llm_tokens_used": null
}
```

#### 2.6.2 Action Types
`FILE_RECEIVED`, `FORMAT_DETECTED`, `SCHEMA_NORMALIZED`, `INTEGRITY_CHECK_RUN`, `ANOMALY_RULE_EVALUATED`, `LLM_QUERY_SENT`, `LLM_RESPONSE_RECEIVED`, `FINDING_FLAGGED`, `FINDING_DISMISSED`, `CROSS_VERIFY_RUN`, `REPORT_GENERATED`, `EXPORT_COMPLETED`, `HUMAN_REVIEW_RECEIVED`

#### 2.6.3 Immutability Guarantee
- JSONL file: opened in append-only mode (`open(path, 'a')`)
- Each line is a complete JSON object followed by `\n`
- Session start entry contains hash of config file
- Session end entry contains hash of entire JSONL file up to that point (chain hash)
- **Assumption:** Single-user local system; OS-level file permissions are sufficient for immutability guarantees in MVP. True cryptographic immutability (e.g., Merkle tree) is deferred to Beta.

#### 2.6.4 Human Review Flow
After pipeline completion, auditor can review findings via CLI interactive mode:
```
ave review --session {session_id}
```
For each finding, auditor sees: Row data, Rule triggered, Evidence. Auditor responds: `[A]ccept / [R]eject / [S]kip`. Decision written to trail as `human_decision` update (new trail entry — original entry never modified).

---

### 2.7 CLI Interface

#### 2.7.1 Commands

```bash
# Primary command
ave run --file <path> [--config <path>] [--output-dir <path>] [--llm <ollama|groq|mistral|none>] [--verbose]

# Review findings from a completed session
ave review --session <session_id>

# Export trail to PDF
ave export --session <session_id> --format <pdf|json|markdown>

# List past sessions
ave sessions [--last N]

# Validate a config file
ave validate-config --config <path>

# Test LLM connectivity
ave check-llm [--provider <ollama|groq|mistral>]
```

#### 2.7.2 `ave run` Full Option Specification

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--file` | path | required | Input data file (CSV or Excel) |
| `--config` | path | `./audit_rules.yaml` | Rules and config file |
| `--output-dir` | path | `./ave_output/` | Directory for reports and trail |
| `--llm` | enum | `ollama` | LLM provider: `ollama`, `groq`, `mistral`, `none` |
| `--llm-model` | str | auto | Override LLM model (e.g., `mistral:7b`) |
| `--sheet` | str/int | `0` | Excel sheet name or index |
| `--verbose` | flag | false | Print per-step progress to stdout |
| `--dry-run` | flag | false | Run pipeline but don't write output files |
| `--no-llm` | flag | false | Equivalent to `--llm none` |
| `--report-format` | enum | `all` | `all`, `json`, `markdown`, `pdf` |

#### 2.7.3 Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success — pipeline completed, report generated |
| 1 | Input error (file not found, config invalid) |
| 2 | Pipeline error (fatal error during processing) |
| 3 | LLM unavailable (fallback exhausted) |
| 4 | Output write error |

---

## 3. Non-Functional Requirements

### 3.1 Performance

| Metric | Target | Measurement Method |
|--------|--------|--------------------|
| File 10K rows, no LLM | < 30 seconds | Automated benchmark test |
| File 10K rows, with Ollama LLM | < 60 seconds | Automated benchmark test |
| File 50K rows, no LLM | < 120 seconds | Automated benchmark test |
| File 50K rows, with LLM | < 300 seconds | Acceptable — warn user |
| Memory usage (10K rows) | < 500 MB RSS | Measured with `psutil` |
| Memory usage (50K rows) | < 2 GB RSS | Measured with `psutil` |

**Implementation requirements:**
- Use **Polars** for files >10,000 rows. Use Pandas for ≤10,000 rows.
- Rule evaluation must be vectorized (no Python-level row iteration) using Polars expressions or Pandas `.apply` with vectorized operations where possible.
- Chunked processing: read and process files in chunks of 5,000 rows for integrity checks to avoid full memory load.
- **Assumption:** "Standard machine" = 8GB RAM, modern x86 CPU (no GPU required). Apple Silicon M-series also supported via Ollama native support.

### 3.2 Scalability

- MVP hard limit: 50,000 rows. Reject with clear error message if exceeded.
- Files must be processed sequentially in MVP (no parallelism required).
- Single-user; no concurrency requirements in MVP.

### 3.3 Security

- All processing is local. No data leaves the machine unless Groq/Mistral API is enabled (explicit opt-in).
- When LLM API is used: send only row values and column names. Never send file paths, session IDs, or user metadata to external APIs.
- **Data minimization for LLM calls:** Strip PII columns (identified by column name patterns like `name`, `id_number`, `phone`, `email`) before sending to external LLM. Log that stripping occurred.
- Config files may contain threshold values but must not contain credentials (API keys in environment variables only).
- API keys stored in environment variables: `GROQ_API_KEY`, `MISTRAL_API_KEY`. Never in config files or code.
- Audit trail JSONL files: set file permissions to `600` (owner read/write only) on creation.

### 3.4 Reliability

| Metric | Target |
|--------|--------|
| Pipeline crash rate | < 1% over 100 runs on valid inputs |
| Partial failure recovery | Each layer saves intermediate output; resume from last successful layer |
| Data integrity | Input files never modified — all operations are read-only |
| Trail integrity | Hash chain verifiable at any point |

**Fault tolerance implementation:**
- Each layer writes its output to disk before the next layer starts (checkpoint files in `output_dir/.checkpoints/`)
- If a layer crashes, re-running the same session resumes from the last checkpoint
- `--force-rerun` flag bypasses checkpoint resume

### 3.5 Usability

- New user can execute first pipeline run within 30 minutes of installation
- All error messages include: what went wrong, why it happened, and how to fix it
- Progress indication: real-time progress bar (using `rich` library) showing current layer and estimated completion
- Verbose mode provides per-rule evaluation output

### 3.6 Compliance Considerations

- Audit trail format designed to meet general audit evidence standards (ISA 500 intent — auditor can verify origin and chain of custody of digital evidence)
- **Assumption:** Regulatory compliance (specific Vietnamese audit standards VAS, Circular 48) is enforced at the rule configuration level (auditor's responsibility), not hardcoded into the engine.
- Hash-based integrity verification satisfies basic requirements for non-repudiation of AI-generated findings.

---

## 4. Data Model & Schema Design

### 4.1 SQLite Database Schema

**Database file:** `{output_dir}/ave.db`

```sql
-- Sessions table: tracks each pipeline run
CREATE TABLE sessions (
    session_id      TEXT PRIMARY KEY,           -- UUID v4
    created_at      TEXT NOT NULL,              -- ISO 8601
    completed_at    TEXT,                       -- NULL if not completed
    status          TEXT NOT NULL DEFAULT 'running',  -- running|completed|failed|partial
    input_file_path TEXT NOT NULL,
    input_file_hash TEXT NOT NULL,              -- SHA-256 of input file
    config_file_path TEXT,
    config_hash     TEXT,                       -- SHA-256 of config file
    row_count       INTEGER,
    column_count    INTEGER,
    overall_rating  TEXT,                       -- CLEAN|MINOR|MODERATE|SEVERE
    total_findings  INTEGER DEFAULT 0,
    ave_version     TEXT NOT NULL,
    trail_file_path TEXT                        -- path to .jsonl file
);

-- Findings table: normalized finding records
CREATE TABLE findings (
    finding_id          TEXT PRIMARY KEY,       -- UUID v4
    session_id          TEXT NOT NULL REFERENCES sessions(session_id),
    layer               INTEGER NOT NULL,       -- 2, 3, or 4
    finding_type        TEXT NOT NULL,          -- integrity|anomaly|cross_verify
    rule_id             TEXT,                   -- NULL for LLM-detected findings
    rule_name           TEXT,
    row_index           INTEGER NOT NULL,       -- 0-based index in source file
    column_name         TEXT,                   -- NULL for row-level findings
    actual_value        TEXT,                   -- Serialized as string
    expected_value      TEXT,                   -- NULL if not applicable
    severity            TEXT NOT NULL,          -- high|medium|low
    confidence          REAL NOT NULL DEFAULT 1.0,
    reasoning           TEXT NOT NULL,
    detection_method    TEXT NOT NULL,          -- rule|llm
    cross_verified      INTEGER NOT NULL DEFAULT 0,  -- boolean
    cross_verify_status TEXT,                   -- confirmed|unconfirmed|unverifiable|pending
    human_decision      TEXT,                   -- accepted|rejected|skipped|NULL
    human_decision_at   TEXT,                   -- ISO 8601
    human_decision_note TEXT,
    created_at          TEXT NOT NULL
);

-- Rules table: snapshot of rules used in each session
CREATE TABLE rule_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(session_id),
    rule_id         TEXT NOT NULL,
    rule_name       TEXT NOT NULL,
    rule_yaml       TEXT NOT NULL,              -- full YAML of rule at time of run
    active          INTEGER NOT NULL DEFAULT 1
);

-- LLM calls log
CREATE TABLE llm_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(session_id),
    called_at       TEXT NOT NULL,
    provider        TEXT NOT NULL,              -- ollama|groq|mistral
    model           TEXT NOT NULL,
    layer           INTEGER NOT NULL,
    prompt_tokens   INTEGER,
    completion_tokens INTEGER,
    duration_ms     INTEGER,
    success         INTEGER NOT NULL DEFAULT 1, -- boolean
    error_message   TEXT
);
```

### 4.2 Source Manifest (In-memory Dict / JSON)

```json
{
  "manifest_version": "1.0",
  "created_at": "ISO 8601",
  "session_id": "string",
  "source_file": {
    "path": "string",
    "filename": "string",
    "format": "csv|xlsx",
    "size_bytes": 0,
    "sha256_hash": "string",
    "encoding": "string",
    "sheet_name": "string|null"
  },
  "schema": {
    "row_count_raw": 0,
    "row_count_after_cleaning": 0,
    "column_count": 0,
    "dropped_empty_rows": 0,
    "dropped_empty_cols": 0,
    "columns": [
      {
        "original_name": "string",
        "normalized_name": "string",
        "inferred_dtype": "date|numeric|currency|text|boolean|mixed",
        "null_count": 0,
        "null_ratio": 0.0,
        "unique_count": 0,
        "sample_values": ["val1", "val2", "val3"]
      }
    ]
  },
  "parse_warnings": ["string"]
}
```

### 4.3 Finding Object (Python Dataclass)

```python
@dataclass
class Finding:
    finding_id: str           # UUID v4
    session_id: str
    layer: int                # 2, 3, or 4
    finding_type: str         # "integrity" | "anomaly" | "cross_verify"
    rule_id: Optional[str]    # None for LLM findings
    rule_name: str
    row_index: int            # 0-based
    row_data: dict            # Snapshot of the row at detection time
    column_name: Optional[str]
    actual_value: Optional[Any]
    expected_value: Optional[Any]
    severity: str             # "high" | "medium" | "low"
    confidence: float         # 0.0–1.0
    reasoning: str
    detection_method: str     # "rule" | "llm"
    cross_verified: bool = False
    cross_verify_status: Optional[str] = None
    human_decision: Optional[str] = None
    human_decision_at: Optional[str] = None
    human_decision_note: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
```

### 4.4 Config File Schema (YAML)

```yaml
# ave_config.yaml — full schema with defaults

# Pipeline settings
pipeline:
  max_rows: 50000                    # Hard limit
  use_polars_threshold: 10000        # Use Polars above this row count
  checkpoint_enabled: true
  
# Ingestion settings
ingestion:
  encoding: auto                     # auto|utf-8|latin-1|utf-8-bom
  header_row: 0
  skip_rows: []
  sheet_name: null                   # null = first sheet
  separator: auto                    # auto|,|;|\t|pipe
  
# Column type hints (optional overrides for auto-inference)
columns:
  amount:
    dtype: currency
    currency: VND
    min_value: 0
    required: true
  transaction_date:
    dtype: date
    min_date: "2020-01-01"
    max_date: null                   # null = today
  # etc.

# Primary key columns for IC-003
primary_key_columns: []

# Integrity check settings
integrity:
  null_threshold_default: 0.0       # 0 = any null is flagged
  outlier_std_multiplier: 3.0
  
# LLM settings
llm:
  enabled: false                    # Must be explicitly enabled
  provider: ollama                  # ollama|groq|mistral
  model: mistral:7b                 # Provider-specific model name
  timeout_seconds: 30
  max_retries: 2
  batch_size: 50                    # Rows per LLM call
  temperature: 0.1                  # Low temperature for determinism
  strip_pii_columns: []             # Column names to exclude from LLM calls

# Audit standard tags (for report mapping)
audit_standard: VAS                 # VAS|ISA|IFRS|custom

# Fiscal year end (for R006 — year-end spike detection)
fiscal_year_end_month: 12
fiscal_year_end_day: 31

# Public holidays list (for R015)
public_holidays: []                 # ["2025-01-01", "2025-04-30", ...]

# Approved vendor list (for R007)
approved_vendor_file: null          # Path to CSV with approved vendors

# Approval thresholds (for R001, R009, R010)
approval_thresholds:
  level_1: 100000000               # 100M VND
  level_2: 500000000               # 500M VND

# Rules (loaded separately from audit_rules.yaml or inline here)
rules_file: audit_rules.yaml        # Can be relative or absolute path

# Output settings
output:
  directory: ./ave_output
  formats: [json, markdown]        # pdf requires WeasyPrint installed
  pdf_enabled: false
```

### 4.5 Data Validation Rules

| Entity | Field | Validation |
|--------|-------|-----------|
| Finding | `severity` | Must be one of: `high`, `medium`, `low` |
| Finding | `confidence` | Must be in range `[0.0, 1.0]` |
| Finding | `layer` | Must be in `{2, 3, 4}` |
| Rule | `id` | Must match pattern `^[A-Z][0-9]{3}$` |
| Rule | `severity` | Must be one of: `high`, `medium`, `low` |
| Rule | `condition` | Must be a recognized condition type |
| Session | `status` | Must be one of: `running`, `completed`, `failed`, `partial` |
| Trail entry | `timestamp` | Must be valid ISO 8601 with timezone |
| Trail entry | `input_hash` | Must be 64-character hex string (SHA-256) |

---

## 5. API Design (CLI & Internal)

### 5.1 Internal Python Module API

The pipeline is composed of Python modules with well-defined interfaces. Each layer exposes a `run(context: PipelineContext) -> PipelineContext` function signature.

#### 5.1.1 PipelineContext (Shared State Object)

```python
@dataclass
class PipelineContext:
    session_id: str
    config: AveConfig                         # Parsed config object
    output_dir: Path
    
    # Set by Layer 1
    raw_df: Optional[Any] = None             # Original DataFrame before normalization
    normalized_df: Optional[Any] = None      # Normalized DataFrame
    source_manifest: Optional[dict] = None
    ingestion_report: Optional[dict] = None
    
    # Set by Layer 2
    integrity_report: Optional[dict] = None
    integrity_findings: List[Finding] = field(default_factory=list)
    
    # Set by Layer 3
    anomaly_findings: List[Finding] = field(default_factory=list)
    detection_stats: Optional[dict] = None
    
    # Set by Layer 4
    verified_findings: List[Finding] = field(default_factory=list)
    
    # Set by Layer 5
    final_report: Optional[dict] = None
    report_paths: dict = field(default_factory=dict)  # format -> path
    
    # Runtime state
    current_layer: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    trail_writer: Optional[Any] = None       # TrailWriter instance
    llm_client: Optional[Any] = None         # LLMClient instance
```

#### 5.1.2 Layer Module Interface

```python
# Each layer module must implement:
def run(ctx: PipelineContext) -> PipelineContext:
    """Execute this layer's processing. Mutates ctx in place and returns it."""
    ...

def validate_prerequisites(ctx: PipelineContext) -> None:
    """Raise PipelineError if required context fields are missing."""
    ...
```

### 5.2 LLM Client Interface

```python
class LLMClient:
    def __init__(self, provider: str, model: str, config: LLMConfig): ...
    
    def complete(self, prompt: str, system_prompt: str = None) -> str:
        """Send completion request. Returns raw string response."""
        ...
    
    def complete_json(self, prompt: str, system_prompt: str = None, 
                      max_retries: int = 2) -> dict:
        """Send completion request expecting JSON response. 
        Retries on parse failure. Raises LLMResponseError after max_retries."""
        ...
    
    def health_check(self) -> bool:
        """Returns True if LLM provider is reachable."""
        ...
```

**Provider implementations:**
- `OllamaClient(LLMClient)` — calls `http://localhost:11434/api/generate`
- `GroqClient(LLMClient)` — calls Groq API with `GROQ_API_KEY`
- `MistralClient(LLMClient)` — calls Mistral API with `MISTRAL_API_KEY`

**LLM Router (fallback chain):**
```
Configured provider → (if fails) → next in chain → none (LLM disabled)
Chain order: ollama → groq → mistral → none
```

### 5.3 Rule Engine Interface

```python
class RuleEngine:
    def __init__(self, rules: List[Rule]): ...
    
    def load_from_yaml(self, path: Path) -> None:
        """Load and validate rules from YAML file."""
        ...
    
    def evaluate(self, df: DataFrame) -> List[Finding]:
        """Evaluate all active rules against the DataFrame. 
        Returns list of findings."""
        ...
    
    def evaluate_rule(self, rule: Rule, df: DataFrame) -> List[Finding]:
        """Evaluate a single rule. Returns findings for that rule."""
        ...
    
    def validate_rules(self) -> List[str]:
        """Validate rule definitions. Returns list of validation errors."""
        ...
```

### 5.4 TrailWriter Interface

```python
class TrailWriter:
    def __init__(self, session_id: str, output_dir: Path): ...
    
    def write(self, entry: TrailEntry) -> None:
        """Append entry to JSONL trail file. Thread-safe (though single-threaded in MVP)."""
        ...
    
    def finalize(self) -> str:
        """Write final chain hash entry. Returns trail file path."""
        ...
    
    def verify(self, trail_path: Path) -> bool:
        """Verify hash chain integrity of an existing trail file."""
        ...
```

---

## 6. System Architecture (Detailed)

### 6.1 Project Directory Structure

```
ave/
├── ave/                          # Main Python package
│   ├── __init__.py
│   ├── cli.py                    # Typer CLI entry points
│   ├── config.py                 # Config loading, validation, AveConfig dataclass
│   ├── context.py                # PipelineContext dataclass
│   ├── orchestrator.py           # LangGraph pipeline orchestration
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── layer1_ingestion.py
│   │   ├── layer2_integrity.py
│   │   ├── layer3_anomaly.py
│   │   ├── layer4_crossverify.py
│   │   └── layer5_synthesis.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── finding.py            # Finding dataclass
│   │   ├── trail.py              # TrailEntry dataclass
│   │   └── manifest.py           # SourceManifest
│   ├── engines/
│   │   ├── __init__.py
│   │   ├── rule_engine.py        # Rule evaluation engine
│   │   ├── llm_client.py         # LLMClient + provider implementations
│   │   └── trail_writer.py       # TrailWriter
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py           # SQLite operations
│   │   └── checkpoint.py         # Checkpoint save/load
│   ├── export/
│   │   ├── __init__.py
│   │   ├── json_exporter.py
│   │   ├── markdown_exporter.py
│   │   └── pdf_exporter.py
│   └── utils/
│       ├── __init__.py
│       ├── hashing.py            # SHA-256 helpers
│       ├── normalization.py      # Date/number/currency normalization
│       └── logging.py            # Structured logging setup
├── rules/
│   ├── default_rules.yaml        # 20 built-in rules
│   └── examples/
│       ├── vas_rules.yaml
│       └── isa_rules.yaml
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/
├── pyproject.toml
├── setup.py (or setup.cfg)
└── README.md
```

### 6.2 Suggested Tech Stack

| Component | Technology | Version | Justification |
|-----------|-----------|---------|---------------|
| Language | Python | 3.11+ | f-string support, match statements, performance |
| CLI | Typer | 0.12+ | Type-safe CLI with auto-help generation |
| Orchestration | LangGraph | 0.2+ | State machine pipeline with visual debuggability |
| Data (small) | Pandas | 2.x | Familiarity, rich ecosystem |
| Data (large) | Polars | 0.20+ | 10–100x faster than Pandas for large files |
| Excel parsing | openpyxl | 3.x | Required by Pandas for .xlsx |
| Encoding detection | chardet | 5.x | File encoding auto-detection |
| Database | SQLite (via `sqlite3` stdlib) | - | Zero dependency, local-first |
| Config | PyYAML | 6.x | YAML parsing |
| Config validation | Pydantic | 2.x | Schema validation for config and data models |
| LLM (local) | Ollama | via REST API | Local LLM execution |
| LLM (cloud) | httpx | 0.27+ | Async-capable HTTP client for API calls |
| Progress | rich | 13.x | Progress bars, formatted console output |
| PDF export | WeasyPrint | 62+ | HTML-to-PDF (optional dependency) |
| Hashing | hashlib (stdlib) | - | SHA-256 |
| Testing | pytest + pytest-cov | latest | Standard test framework |
| Linting | ruff | latest | Fast linter/formatter |

**Assumptions:**
- Python 3.11 minimum (not 3.12+) to maximize compatibility with older machines
- All dependencies installable via `pip install ave` (WeasyPrint is optional extra)
- LangGraph is used for orchestration; if too heavy for MVP, replace with a simple sequential function chain and add LangGraph in Alpha

### 6.3 Data Flow Description

```
[User] --ave run --file data.csv--> [CLI (cli.py)]
                                          |
                                   Load config + validate
                                          |
                                   Create session_id (UUID)
                                          |
                                   Initialize TrailWriter
                                   Initialize SQLite session record
                                   Initialize LLMClient (if enabled)
                                          |
                              [Orchestrator (LangGraph)]
                                          |
                              ┌───────────▼────────────┐
                              │   Layer 1: Ingestion   │
                              │   - Detect format      │
                              │   - Parse file         │
                              │   - Normalize schema   │
                              │   - Write manifest     │
                              │   - Write trail entry  │
                              └───────────┬────────────┘
                                          │ normalized_df + manifest
                              ┌───────────▼────────────┐
                              │   Layer 2: Integrity   │
                              │   - Run 10 IC checks   │
                              │   - Score findings     │
                              │   - Write trail entry  │
                              └───────────┬────────────┘
                                          │ integrity_findings
                              ┌───────────▼────────────┐
                              │   Layer 3: Anomaly     │
                              │   - Rule engine eval   │
                              │   - LLM batch eval     │──→ [LLM Router]
                              │   - Merge findings     │       |
                              │   - Write trail entry  │   [Ollama/Groq/Mistral]
                              └───────────┬────────────┘
                                          │ anomaly_findings
                              ┌───────────▼────────────┐
                              │   Layer 4: CrossVerify │
                              │   - Stub (MVP)         │
                              │   - Write trail entry  │
                              └───────────┬────────────┘
                                          │ verified_findings
                              ┌───────────▼────────────┐
                              │   Layer 5: Synthesis   │
                              │   - Aggregate findings │
                              │   - Generate report    │──→ [LLM for summary]
                              │   - Write to SQLite    │
                              │   - Export files       │
                              │   - Finalize trail     │
                              └───────────┬────────────┘
                                          │
                                   [Output files written]
                                   {session_id}_report.json
                                   {session_id}_report.md
                                   {session_id}_trail.jsonl
                                          |
                              [User sees summary in terminal]
```

### 6.4 LangGraph State Machine Nodes

```python
# orchestrator.py — LangGraph graph definition

from langgraph.graph import StateGraph, END

graph = StateGraph(PipelineContext)

graph.add_node("ingest", layer1_ingestion.run)
graph.add_node("integrity", layer2_integrity.run)
graph.add_node("anomaly", layer3_anomaly.run)
graph.add_node("crossverify", layer4_crossverify.run)
graph.add_node("synthesize", layer5_synthesis.run)

graph.set_entry_point("ingest")
graph.add_edge("ingest", "integrity")
graph.add_edge("integrity", "anomaly")
graph.add_edge("anomaly", "crossverify")
graph.add_edge("crossverify", "synthesize")
graph.add_edge("synthesize", END)

# Conditional: if ingestion fails fatally, skip to END with error state
graph.add_conditional_edges(
    "ingest",
    lambda ctx: "integrity" if not ctx.errors else END
)

pipeline = graph.compile()
```

---

## 7. Edge Cases & Error Handling

### 7.1 Input Edge Cases

| Scenario | Detection | Handling |
|----------|-----------|----------|
| File does not exist | `Path.exists()` check | Exit code 1, clear message with path |
| File is empty (0 rows after header) | Row count == 0 after parsing | Exit with error: "File contains no data rows" |
| File has only headers, no data | Same as above | Same handling |
| File with only 1 column | Column count == 1 | Warning: "Single-column file — limited analysis possible" |
| Completely empty cells forming entire rows | Drop in normalization | Log count of dropped rows |
| Mixed date formats in same column | Detected during normalization | Best-effort parse, log ambiguous rows, mark column as `mixed` dtype |
| Excel file with merged cells | openpyxl unmerges on read | Log warning about merged cells |
| Excel file with multiple sheets | Read only specified sheet | Warn user about additional sheets |
| CSV with inconsistent column counts per row | Pandas `on_bad_lines='warn'` | Log bad rows, skip them |
| File exceeds 50,000 row limit | Row count check after parse | Error: "File exceeds MVP limit of 50,000 rows. Use --max-rows to override." |
| File is binary/corrupt | Exception during parse | Error: "Unable to parse file. Verify it is a valid CSV or Excel file." |
| Encoding detection fails | chardet confidence < 0.5 | Try UTF-8 with replacement chars, warn user |

### 7.2 Rule Engine Edge Cases

| Scenario | Handling |
|----------|----------|
| Rule references column that doesn't exist | Log warning, skip rule, continue (do not fail pipeline) |
| Rule YAML has invalid syntax | Fail at startup with line-number-specific error |
| Rule with unsupported condition type | Fail at startup with rule ID and condition name |
| All rows flagged by a single rule (>80% of rows) | Warning: "Rule R{id} flagged {pct}% of rows — possible misconfiguration" |
| No rules defined | Warning: "No rules configured — running integrity checks only" |
| Rule threshold missing when required | Fail at startup with descriptive error |
| Duplicate rule IDs in YAML | Fail at startup: "Duplicate rule ID: {id}" |

### 7.3 LLM Edge Cases

| Scenario | Handling |
|----------|----------|
| Ollama not running | Detect via health check at startup. Warning: "Ollama not available — LLM disabled". Proceed without LLM. |
| Ollama model not pulled | HTTP 404 from Ollama. Error message: "Model {model} not found. Run: ollama pull {model}" |
| LLM returns non-JSON response | Retry up to `max_retries` times with "respond only in JSON" reminder. After retries: log warning, skip batch, continue. |
| LLM response references non-existent row index | Validate all row_index values against actual DataFrame length. Discard invalid references. |
| LLM response confidence out of range | Clamp to [0.0, 1.0] |
| Groq API key missing | Check `GROQ_API_KEY` env var at startup. If Groq selected and key missing: error with setup instructions. |
| LLM timeout | `httpx` timeout after `timeout_seconds`. Retry once. Then disable LLM for remainder of session. |
| LLM hallucination (references values not in data) | Cross-validate all LLM-stated evidence against actual row data before creating finding. Discard if evidence not verifiable. |

### 7.4 Output & Storage Edge Cases

| Scenario | Handling |
|----------|----------|
| Output directory doesn't exist | Auto-create with `mkdir -p` |
| Disk full during write | Catch `OSError`. Log error. Attempt to write minimal JSON report to temp dir. |
| SQLite DB locked | Retry 3 times with 100ms backoff. If still locked: warn, continue without DB write (JSONL still written). |
| PDF export fails (WeasyPrint not installed) | Graceful fallback: skip PDF, warn user, export JSON + Markdown only |
| Report file already exists | Append timestamp suffix to avoid overwrite: `{session_id}_report_2.json` |
| Session interrupted mid-run | Checkpoint saves intermediate state. On restart, prompt: "Incomplete session {id} found. Resume? [Y/n]" |

### 7.5 Failure Scenarios & Recovery

```
Scenario: Layer 3 crashes due to unexpected data format
Recovery:
  1. Exception caught in orchestrator
  2. Partial findings from Layer 3 (before crash) preserved in checkpoint
  3. Context.errors list updated with error details
  4. Trail entry written with action_type=LAYER_ERROR
  5. Pipeline continues to Layer 5 with partial findings
  6. Report generated with warning: "Layer 3 completed partially"
  7. Exit code 2
```

### 7.6 Retry Strategies

| Component | Retry Policy |
|-----------|-------------|
| LLM API call | Exponential backoff: 1s, 2s, 4s — max 3 retries |
| LLM JSON parse failure | Immediate retry with explicit JSON prompt — max 2 retries |
| SQLite write | Linear backoff: 100ms × 3 retries |
| File read | No retry (fail immediately with clear error) |

### 7.7 Logging & Monitoring

**Log levels:**
- `DEBUG`: Per-row rule evaluations, LLM prompts/responses (only with `--verbose --debug`)
- `INFO`: Layer start/end, finding counts, file paths
- `WARNING`: Non-fatal issues (encoding fallback, skipped rules, LLM unavailable)
- `ERROR`: Fatal issues before graceful exit

**Log format:**
```
2025-05-01T14:23:01+07:00 | INFO     | layer2_integrity  | IC-001 PASS: 0 nulls in required columns
2025-05-01T14:23:01+07:00 | WARNING  | layer3_anomaly    | Rule R007 skipped: column 'vendor_id' not found
2025-05-01T14:23:02+07:00 | INFO     | layer3_anomaly    | 12 anomalies flagged (8 rule-based, 4 LLM-assisted)
```

**Log file:** `{output_dir}/ave_{session_id}.log`

---

## 8. Development Plan

### 8.1 Task Decomposition

#### Phase 0 — Foundation (Week 1)

| Task | Description | Dependencies | Estimate |
|------|-------------|--------------|----------|
| T001 | Project scaffolding | None | 0.5d |
| T002 | Config model (Pydantic) + YAML loader | T001 | 1d |
| T003 | PipelineContext dataclass | T002 | 0.5d |
| T004 | Finding dataclass + SQLite schema | T003 | 1d |
| T005 | TrailWriter (JSONL append + hash) | T004 | 1d |
| T006 | SQLite storage module | T004 | 1d |
| T007 | Hashing utilities | None | 0.5d |
| T008 | Logging setup (rich + structlog) | None | 0.5d |

#### Phase 1 — Core Pipeline (Weeks 2–3)

| Task | Description | Dependencies | Estimate |
|------|-------------|--------------|----------|
| T010 | Layer 1: File format detection + parsing (CSV + Excel) | T003, T008 | 1.5d |
| T011 | Layer 1: Normalization (dates, numbers, currency) | T010 | 1.5d |
| T012 | Layer 1: Source Manifest creation | T010, T011 | 0.5d |
| T013 | Layer 2: Integrity checks IC-001 through IC-010 | T012 | 2d |
| T014 | Layer 2: Severity scoring | T013 | 0.5d |
| T015 | Rule Engine: YAML loader + validator | T002 | 1d |
| T016 | Rule Engine: Condition evaluators (all types) | T015 | 2d |
| T017 | Layer 3: Rule engine integration | T016, T012 | 1d |
| T018 | Layer 4: Stub (pass-through) | T017 | 0.5d |
| T019 | Layer 5: Findings aggregation | T018 | 1d |
| T020 | Layer 5: JSON report generation | T019 | 1d |
| T021 | Layer 5: Markdown report generation | T019 | 1d |

#### Phase 2 — LLM Integration (Week 4)

| Task | Description | Dependencies | Estimate |
|------|-------------|--------------|----------|
| T030 | LLM Client interface + Ollama implementation | T008 | 1.5d |
| T031 | Groq + Mistral client implementations | T030 | 1d |
| T032 | LLM Router (fallback chain) | T031 | 0.5d |
| T033 | Layer 3: LLM batch anomaly detection | T032, T017 | 2d |
| T034 | LLM response validation (JSON parse + evidence verify) | T033 | 1d |
| T035 | LLM calls logging (SQLite) | T034 | 0.5d |

#### Phase 3 — CLI & Orchestration (Week 5)

| Task | Description | Dependencies | Estimate |
|------|-------------|--------------|----------|
| T040 | LangGraph orchestrator setup | T019 | 1d |
| T041 | Checkpoint save/load | T006 | 1d |
| T042 | CLI: `ave run` command | T040, T041 | 1.5d |
| T043 | CLI: `ave review` interactive mode | T042 | 1d |
| T044 | CLI: `ave export`, `ave sessions`, `ave validate-config`, `ave check-llm` | T042 | 1d |
| T045 | Progress bar integration (rich) | T042 | 0.5d |

#### Phase 4 — Export & Polish (Week 6)

| Task | Description | Dependencies | Estimate |
|------|-------------|--------------|----------|
| T050 | PDF export (WeasyPrint) | T021 | 1d |
| T051 | Trail verification (`ave verify`) | T005 | 0.5d |
| T052 | Default rules YAML (20 rules) | T015 | 1d |
| T053 | Error messages + user guidance polish | T042 | 1d |
| T054 | Installation docs + README | None | 0.5d |
| T055 | End-to-end integration test with real fixture data | T042 | 1.5d |

### 8.2 Dependency Graph

```
T001 → T002 → T003 → T004 → T005
                   ↓        ↓
              T006     T013
T007 ─────────────────────→ T005
T008 → T010 → T011 → T012 → T013 → T014
                          ↓
                     T015 → T016 → T017 → T018 → T019 → T020 → T021
                                                              ↓
T030 → T031 → T032 → T033 → T034 → T035            T040 → T041 → T042
                          ↗ (parallel with T017)          ↓
                     T017                            T043, T044, T045
```

### 8.3 Implementation Order (Priority)

1. T001–T008 (Foundation) — must be complete before any pipeline work
2. T010–T014 (Ingestion + Integrity) — run-able after this
3. T015–T021 (Rule engine + reports) — end-to-end without LLM
4. T040–T045 (CLI + orchestration) — usable product
5. T030–T035 (LLM) — enhanced product
6. T050–T055 (Export + polish) — MVP-ready

---

## 9. Testing Strategy

### 9.1 Unit Tests

Every function/method must have at least one unit test. Key areas:

**Normalization (`test_normalization.py`)**
```python
# Test cases for date normalization:
# "01/05/2025" → "2025-05-01"
# "2025-01-15" → "2025-01-15"
# "15-01-2025" → "2025-01-15"
# Invalid date → returns None, logs warning

# Test cases for number normalization:
# "1.000.000" (Vietnamese) → 1000000.0
# "1,000,000" (US) → 1000000.0
# "1,500.50" → 1500.50
# "₫ 500,000" → 500000.0

# Test cases for currency stripping:
# "VND 100,000" → (100000.0, "VND")
# "USD 50.00" → (50.0, "USD")
```

**Rule Engine (`test_rule_engine.py`)**
```python
# Test each condition type with:
#   - Matching row (should produce finding)
#   - Non-matching row (should not produce finding)
#   - Edge value (boundary testing)
#   - Null value in target column
#   - Wrong column dtype

# Test compound conditions:
#   - AND: both sub-conditions true
#   - AND: one sub-condition false
#   - OR: both false
#   - OR: one true
```

**Trail Writer (`test_trail_writer.py`)**
```python
# Test append-only behavior
# Test hash calculation correctness
# Test chain hash on finalization
# Test verification of valid trail
# Test verification detects tampering (manual edit to JSONL)
```

**Integrity Checks (`test_integrity.py`)**
```python
# For each IC check:
#   - Clean data (no findings)
#   - Data with exactly the violation
#   - Edge cases per check
```

### 9.2 Integration Tests

**`test_pipeline_integration.py`**

| Test | Description |
|------|-------------|
| `test_csv_clean_file` | Clean CSV with no issues → CLEAN rating, 0 findings |
| `test_csv_with_nulls` | CSV with null required fields → IC-001 findings |
| `test_csv_with_duplicates` | CSV with duplicate rows → IC-002 findings |
| `test_csv_with_anomalies` | CSV with transactions triggering R001, R002, R009 → correct findings |
| `test_excel_file` | .xlsx file processing → same results as CSV equivalent |
| `test_large_file_performance` | 10,000 row file → completes in < 60s |
| `test_pipeline_resume_from_checkpoint` | Simulate crash at Layer 3 → resume from checkpoint |
| `test_trail_hash_chain` | Complete run → verify trail hash chain integrity |
| `test_report_json_schema` | Validate JSON report against expected schema |
| `test_report_markdown_format` | Validate Markdown report has required sections |

### 9.3 Test Fixtures

**Required fixture files (in `tests/fixtures/`):**

| File | Rows | Description |
|------|------|-------------|
| `clean_transactions.csv` | 100 | No anomalies, clean data |
| `transactions_with_nulls.csv` | 100 | 10 rows with required field nulls |
| `transactions_with_duplicates.csv` | 100 | 5 exact duplicate rows |
| `transactions_with_anomalies.csv` | 500 | Triggers all 20 default rules at least once |
| `large_file_10k.csv` | 10,000 | Performance testing |
| `large_file_50k.csv` | 50,000 | Boundary testing |
| `malformed_encoding.csv` | 50 | Mixed encoding file |
| `excel_single_sheet.xlsx` | 200 | Standard Excel file |
| `excel_multi_sheet.xlsx` | 200 | Excel file with 3 sheets |
| `minimal_config.yaml` | - | Minimum valid config |
| `full_config.yaml` | - | All config options specified |
| `invalid_rules.yaml` | - | Rules with various validation errors |

### 9.4 End-to-End Test Scenarios

**Scenario 1: Happy path — clean audit**
1. `ave run --file clean_transactions.csv --config minimal_config.yaml --no-llm`
2. Assert exit code 0
3. Assert report shows CLEAN rating
4. Assert 0 findings
5. Assert trail JSONL exists and hash chain valid

**Scenario 2: Full anomaly detection**
1. `ave run --file transactions_with_anomalies.csv --config full_config.yaml --no-llm`
2. Assert ≥15 findings detected
3. Assert all high-severity findings reference specific row indices
4. Assert JSON report schema valid
5. Assert Markdown report contains findings table

**Scenario 3: LLM-assisted detection (requires Ollama running)**
1. `ave run --file transactions_with_anomalies.csv --llm ollama --llm-model mistral:7b`
2. Assert LLM findings have `detection_method: llm`
3. Assert all LLM findings have valid `reasoning` text
4. Assert all LLM row_index values are valid

**Scenario 4: Error recovery**
1. Run pipeline on large file
2. Kill process during Layer 3
3. Restart with same command
4. Assert prompt to resume
5. Assert final output equivalent to uninterrupted run

### 9.5 Performance Benchmarks (CI-enforced)

```python
# test_performance.py
def test_10k_rows_no_llm_under_60s():
    start = time.time()
    run_pipeline("large_file_10k.csv", llm_enabled=False)
    assert time.time() - start < 60

def test_50k_rows_no_llm_under_120s():
    start = time.time()
    run_pipeline("large_file_50k.csv", llm_enabled=False)
    assert time.time() - start < 120
```

---

## 10. AI Coding Instructions

### 10.1 Coding Conventions

**Language & Style:**
- Python 3.11+ syntax throughout. Use `match` statements for condition type dispatch in rule engine.
- Type hints on ALL function signatures (parameters and return types). No untyped functions.
- Use dataclasses for all data models. Use Pydantic for config validation only.
- Docstrings on all public functions: Google style (`Args:`, `Returns:`, `Raises:`).
- Max line length: 100 characters.
- Use f-strings for string formatting. No `.format()` or `%` formatting.
- Ruff for linting + formatting. Config: `line-length = 100`.

**Naming Conventions:**
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`
- Layer modules named: `layer{N}_{name}.py`

**Error Handling:**
- Define custom exception hierarchy in `ave/exceptions.py`:
  ```
  AveError (base)
  ├── ConfigError
  ├── IngestionError
  ├── RuleValidationError
  ├── PipelineError
  ├── LLMError
  │   ├── LLMUnavailableError
  │   └── LLMResponseError
  └── StorageError
  ```
- Always catch specific exceptions, not bare `except:`
- Re-raise with context: `raise IngestionError("Failed to parse CSV") from e`
- Never swallow exceptions silently — always log at minimum

**Immutability:**
- Never modify the normalized DataFrame after Layer 1 completes. All layers work on views or copies.
- Source file is NEVER written to. Open source files with `open(path, 'r')` or Pandas read functions only.

### 10.2 File/Module Boundaries

| Module | Responsibility | Must NOT |
|--------|---------------|----------|
| `cli.py` | Parse CLI args, call orchestrator, display output | Contain business logic |
| `config.py` | Load and validate config/rules | Perform file I/O beyond YAML loading |
| `orchestrator.py` | Wire LangGraph nodes, manage context lifecycle | Contain layer-specific logic |
| `layer*.py` modules | Implement one pipeline layer | Import from other layer modules |
| `rule_engine.py` | Evaluate rules against DataFrame | Know about LLM or reporting |
| `llm_client.py` | Send/receive LLM requests | Know about rule engine or pipeline state |
| `trail_writer.py` | Write and verify JSONL trail | Know about findings or rules |
| `database.py` | All SQLite operations | Know about pipeline logic |
| `*_exporter.py` | Convert findings to output format | Read from database |

### 10.3 Key Implementation Priorities

**Priority 1 (implement first, get right):**
1. Data normalization (Layer 1) — all downstream layers depend on clean data
2. Audit trail immutability — the core trust mechanism of the product
3. Rule engine condition evaluation — correctness is critical (false negatives are unacceptable)

**Priority 2 (correctness over performance):**
4. Integrity checks IC-001 through IC-010
5. Finding data structure — must contain all evidence for human review

**Priority 3 (optimize after correctness):**
6. Performance optimization (Polars vs Pandas threshold)
7. LLM integration (optional in MVP)
8. PDF export

### 10.4 Known Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| LangGraph API changes between versions | High — breaks orchestrator | Pin LangGraph version in `pyproject.toml`. Add integration test that validates graph execution. |
| Polars API differs significantly from Pandas | Medium — confusing for future devs | Abstract DataFrame operations behind a thin `DataFrameAdapter` class that works with both. |
| LLM returns structurally valid but semantically wrong JSON | Medium — false findings | Always cross-validate LLM-stated evidence (row_index, values) against actual DataFrame data before creating findings. |
| WeasyPrint requires system-level dependencies (Cairo, Pango) | Low-Medium — PDF generation fails silently | Make PDF an optional dependency. Always generate JSON + Markdown. Check WeasyPrint availability at startup if PDF requested. |
| Ollama model names vary across versions | Low — wrong model reference | Document tested models. Provide `ave check-llm` command that lists available models. |
| SHA-256 hash collision in trail verification | Negligible | Standard assumption. Document that SHA-256 is used. |
| Vietnamese locale number parsing conflicts with US locale | High — silent wrong values | Implement explicit locale detection: check if thousands separator is `.` and decimal is `,` by analyzing column data distribution. Log which locale was detected. |

### 10.5 Assumptions Made (Explicit List)

1. **Single user, single machine:** No concurrency requirements. SQLite without WAL mode is sufficient.
2. **Auditor is CLI-comfortable:** CLI is the only interface in MVP. No UI scaffolding needed.
3. **Input files are well-formed enough to open:** Corrupt/binary files handled with graceful error, not attempted repair.
4. **API keys via environment variables:** Never stored in config files. `.env` file support via `python-dotenv` is nice-to-have.
5. **Ollama runs on localhost:11434:** Default Ollama address. Configurable via `AVE_OLLAMA_URL` env var.
6. **All monetary amounts in single currency per file:** Multi-currency within one file is handled (store currency type per column) but cross-currency arithmetic is not performed.
7. **Date columns are identifiable:** Either by column name (contains `date`, `time`, `ngay`) or by being configured in `columns:` config section. If unidentifiable, treat as text.
8. **Session data is not sensitive enough to encrypt at rest:** Local file permissions (`600`) are sufficient for MVP.
9. **No internet access required for core pipeline:** Core pipeline (Layer 1–5 without LLM) runs 100% offline.
10. **Fiscal year follows calendar year by default:** `fiscal_year_end_month: 12`, `fiscal_year_end_day: 31`. Override in config.
11. **Vietnamese number format is primary target:** Thousands separator is `.`, decimal separator is `,`. Auto-detection implemented.
12. **LangGraph version ≥ 0.2.x:** API surface used (StateGraph, add_node, compile) is stable in 0.2+.
13. **`ave` is installed as a package:** `pyproject.toml` defines `[project.scripts] ave = "ave.cli:app"`.

---

*End of AVE AI-Ready Context Document v1.0*

*Generated: 2026-05-02 | Source: AVE PRD v1.0 (01/05/2025)*
