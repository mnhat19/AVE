# AVE - Autonomous Verification Engine for Auditors

A local-first, CLI-driven AI agent pipeline that automates repetitive data verification tasks for auditors. Process financial and accounting data with configurable rule-based anomaly detection, LLM-assisted reasoning, and produce verified findings with immutable audit trails—entirely offline.

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage Guide](#usage-guide)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Development](#development)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

AVE is designed for internal or independent auditors who need to automate verification workflows without reliance on cloud infrastructure. The system processes structured data files (CSV, Excel), applies five-layer sequential verification, and generates comprehensive audit trails for compliance and reproducibility.

### Core Principle

**AVE is advisory, not actuative.** All pipeline operations are read-only with respect to source data. Auditors retain final decision authority. Every finding is traceable to a specific source row and rule.

### Target Users

- Internal auditors (2-5 years experience)
- Independent verification professionals
- Audit firms seeking local-first solutions
- Organizations with strict data residency requirements

---

## Key Features

### Input Processing
- **Multi-format ingestion**: CSV and Excel (.xlsx) files up to 50,000 rows
- **Automatic format detection**: Detects encoding, delimiters, and sheet structure
- **Schema normalization**: Standardizes column names, data types, and values
- **Vietnamese locale support**: Handles Vietnamese number and date formats

### Five-Layer Verification Pipeline

| Layer | Purpose | Output |
|-------|---------|--------|
| **Layer 1: Ingestion** | Parse, normalize, and manifest source data | Clean DataFrame + source metadata |
| **Layer 2: Integrity** | 10 mandatory integrity checks (null, duplicates, range, format) | Integrity report with severity scores |
| **Layer 3: Anomaly Detection** | Rule-based and LLM-assisted anomaly flagging | Anomaly findings with scores |
| **Layer 4: Cross-Verification** | Verify findings against configurable rules | Cross-checked findings |
| **Layer 5: Synthesis** | Generate reports and immutable audit trails | Final reports + audit trail |

### Anomaly Detection
- **20+ configurable rules** via YAML DSL
- **Rule categories**: format validation, range checking, threshold detection, pattern matching, cross-row validation
- **LLM-assisted reasoning**: Optional integration with Ollama, Groq, or Mistral for semantic analysis
- **Severity scoring**: Automatic classification of findings by severity

### Audit Trail Management
- **Immutable JSONL trail**: Append-only transaction log of all pipeline operations
- **SQLite checkpoint database**: Metadata storage for session recovery
- **Complete traceability**: Every finding linked to source row, rule, and execution timestamp
- **Session management**: Resume interrupted pipelines from checkpoints

### Report Generation
- **Markdown reports**: Human-readable findings with inline summary statistics
- **JSON reports**: Machine-readable complete data for integration
- **PDF reports**: Professional printable audit documentation
- **Customizable templates**: Extend report generation with custom formatters

---

## System Requirements

### Minimum Specification
- **OS**: Windows 10+, macOS 10.14+, Linux (Ubuntu 20.04+)
- **Python**: 3.11 or later
- **RAM**: 4 GB (8 GB recommended for large files)
- **Disk**: 500 MB for installation + space for data processing

### Optional Dependencies
- **LLM Support**: Ollama 0.1.20+, or API access to Groq/Mistral
- **PDF Export**: libpq (Linux), included in weasyprint wheel (macOS/Windows)

### Runtime Environment Variables
```bash
# LLM Configuration (if using LLM features)
GROQ_API_KEY=your_groq_api_key          # For Groq integration
MISTRAL_API_KEY=your_mistral_api_key    # For Mistral integration
OLLAMA_BASE_URL=http://localhost:11434  # For local Ollama (default shown)
```

---

## Installation

### From Source (Development)

1. **Clone the repository**
   ```bash
   git clone https://github.com/mnhat19/AVE.git
   cd AVE
   ```

2. **Create and activate Python virtual environment**
   ```bash
   python -m venv venv
   
   # Windows
   .\venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install in development mode**
   ```bash
   pip install -e ".[dev]"
   ```

   For PDF export support:
   ```bash
   pip install -e ".[dev,pdf]"
   ```

4. **Verify installation**
   ```bash
   ave --version
   ave --help
   ```

### From PyPI (When Available)

```bash
pip install ave-audit
```

---

## Quick Start

### Basic Usage

Process a CSV file with default configuration:

```bash
ave run \
  --file data/transactions.csv \
  --config ave_config.yaml \
  --output ave_output
```

### Example with CSV File

1. **Create sample data** (`sample.csv`):
   ```csv
   transaction_id,date,amount,vendor,status
   TXN001,2025-01-15,5000000,Vendor A,completed
   TXN002,2025-01-16,500000,Vendor B,pending
   TXN003,2025-01-16,5000000,Vendor C,rejected
   TXN004,2025-01-17,-100000,Vendor A,completed
   TXN005,2025-01-17,5000000,Vendor A,completed
   ```

2. **Create configuration** (`ave_config.yaml`):
   ```yaml
   ingestion:
     encoding: utf-8
     header_row: 0
     skip_rows: []
   
   integrity:
     primary_key_columns: [transaction_id]
     required_columns: [transaction_id, date, amount, vendor]
     checks:
       IC-001:
         enabled: true
         threshold: 0
   
   anomaly:
     enabled: true
     rules_file: rules/default_rules.yaml
     llm_enabled: false
   
   synthesis:
     export_formats: [json, markdown]
     pdf_enabled: true
   ```

3. **Run the pipeline**:
   ```bash
   ave run \
     --file sample.csv \
     --config ave_config.yaml \
     --output ave_output
   ```

4. **Check outputs** in `ave_output/`:
   - `<session_id>_report.json` - Machine-readable findings
   - `<session_id>_report.md` - Human-readable summary
   - `<session_id>_report.pdf` - Professional audit report
   - `<session_id>_trail.jsonl` - Complete audit trail

### Using Excel Files

```bash
ave run \
  --file data/accounts.xlsx \
  --type xlsx \
  --sheet "Sheet1" \
  --config ave_config.yaml \
  --output ave_output
```

---

## Usage Guide

### Command Line Interface

```bash
ave --help                          # Show all commands
ave run --help                      # Show run command options
ave run --version                   # Show version
```

### Core Options

```bash
ave run \
  --file PATH                       # Input CSV or Excel file (required)
  --config PATH                     # YAML config file (required)
  --output DIR                      # Output directory (default: ./ave_output)
  --type TYPE                       # File type: csv or xlsx (auto-detected if omitted)
  --sheet NAME_OR_INDEX             # Excel sheet (0 = first, "Sheet1" = by name)
  --rules PATH                      # Custom rules file (overrides config)
  --llm-provider PROVIDER           # LLM provider: ollama, groq, mistral
  --llm-enabled                     # Enable LLM processing
  --checkpoint-resume ID            # Resume from checkpoint session
  --no-trail                        # Disable audit trail generation (not recommended)
  --no-checkpoint                   # Disable checkpoint saves
```

### Configuration File Format

```yaml
# INGESTION SETTINGS
ingestion:
  encoding: utf-8                   # Character encoding (auto-detect if omitted)
  header_row: 0                     # Row index containing column headers
  skip_rows: []                     # List of row indices to skip
  separator: ","                    # CSV delimiter (auto-detect if omitted)

# INTEGRITY CHECK SETTINGS
integrity:
  primary_key_columns: []           # Columns forming composite primary key
  required_columns: []              # Columns that must not be null
  date_min: "1900-01-01"            # Minimum valid date
  date_max: null                    # Maximum valid date (null = today + 1 day)
  
  checks:
    IC-001:                         # Null completeness check
      enabled: true
      threshold: 0
    IC-002:                         # Duplicate row detection
      enabled: true
    # ... other integrity checks

# ANOMALY DETECTION SETTINGS
anomaly:
  enabled: true
  rules_file: rules/default_rules.yaml  # YAML rules file path
  llm_enabled: false                # Enable LLM-assisted detection
  llm_provider: ollama              # Provider: ollama, groq, mistral
  severity_threshold: 1             # Minimum severity to report (1=low, 2=medium, 3=high)

# SYNTHESIS & EXPORT SETTINGS
synthesis:
  export_formats: [json, markdown]  # Formats: json, markdown, pdf
  pdf_enabled: true                 # Enable PDF generation
  markdown_include_details: true    # Include row-level details in Markdown

# PIPELINE SETTINGS
pipeline:
  checkpoint_enabled: true          # Enable checkpoint saves
  checkpoint_interval: 1            # Save after each layer
  max_file_size_mb: 500             # Maximum input file size
```

### Rules File Format

```yaml
# rules/default_rules.yaml
rules:
  - id: RUL001
    name: "Negative Amount Detection"
    description: "Flag transactions with negative amounts"
    condition:
      field: amount
      operator: "<"
      value: 0
    severity: medium

  - id: RUL002
    name: "Unusual Amount Threshold"
    description: "Flag amounts exceeding threshold"
    condition:
      field: amount
      operator: ">"
      value: 10000000
    severity: low

  - id: RUL003
    name: "Invalid Status"
    description: "Flag unknown transaction statuses"
    condition:
      field: status
      operator: "not_in"
      values: [completed, pending, rejected]
    severity: high

  - id: RUL004
    name: "Date Out of Range"
    description: "Flag future-dated transactions"
    condition:
      field: date
      operator: ">"
      value: "TODAY"
    severity: medium
```

### Resuming from Checkpoints

If a pipeline is interrupted, resume from the last checkpoint:

```bash
ave run \
  --checkpoint-resume <session_id> \
  --config ave_config.yaml
```

The system will:
1. Restore the session state from SQLite database
2. Resume from the next incomplete layer
3. Regenerate all downstream reports

---

## Architecture

### System Flow

```
                    Command Line Interface (Typer)
                              |
                              v
                    Pipeline Orchestrator
                              |
        __________|__________|__________|__________|__________
        |         |         |         |         |         |
        v         v         v         v         v         v
    Layer 1   Layer 2   Layer 3   Layer 4   Layer 5   Report
    Ingestion Integrity Anomaly  Cross-    Synthesis Export
                        Detection Verify
        |         |         |         |         |
        v_________|_________|_________|_________|
                              |
                    __________|__________
                    |                   |
                    v                   v
              SQLite Database    JSONL Audit Trail
             (Checkpoints)      (Immutable Record)
```

### Layer Responsibilities

**Layer 1 - Ingestion**
- File format detection and parsing
- Character encoding detection
- Schema normalization (headers, types, values)
- Source manifest creation

**Layer 2 - Integrity**
- 10 mandatory data quality checks
- Completeness, uniqueness, range validation
- Format consistency verification
- Severity scoring

**Layer 3 - Anomaly Detection**
- Apply configured rule set from YAML
- Optional LLM-assisted semantic analysis
- Score each anomaly by severity
- Generate detection statistics

**Layer 4 - Cross-Verification**
- Validate anomaly findings against additional rules
- Cross-reference with integrity findings
- Consolidate overlapping findings
- Prepare for final reporting

**Layer 5 - Synthesis**
- Aggregate all findings into final report
- Generate markdown, JSON, and PDF output
- Write immutable JSONL audit trail
- Save checkpoint for recovery

### Data Models

**Finding** - Represents a single audit finding
```python
class Finding:
    id: str                    # Unique finding identifier
    rule_id: str              # Originating rule
    severity: str             # high, medium, low
    row_index: int            # Source row number
    column: str               # Affected column name
    value: Any                # Current value at finding location
    message: str              # Human-readable description
    timestamp: datetime       # When finding was detected
```

**Source Manifest** - Metadata about input file
```python
class SourceManifest:
    file_name: str
    file_size_bytes: int
    file_hash: str            # SHA-256 for integrity
    row_count: int
    column_count: int
    encoding: str
    parsed_at: datetime
    schema: Dict[str, str]    # Column name -> inferred type
```

**Trail Entry** - Immutable audit trail record
```python
class TrailEntry:
    session_id: str
    timestamp: datetime
    layer: int
    event_type: str
    event_data: dict          # Layer-specific details
    hash: str                 # Chain hash for integrity
```

---

## Configuration

### Default Configuration

If no `--config` is provided, AVE uses sensible defaults:
- UTF-8 encoding, automatic separator detection
- All 10 integrity checks enabled
- All default rules from `rules/default_rules.yaml`
- JSON and Markdown export enabled
- Checkpoints enabled

Generate a template configuration:

```bash
ave run --show-config-template > my_config.yaml
```

### Customizing Rules

Create a custom rules file:

```yaml
rules:
  - id: CUSTOM001
    name: "My Custom Rule"
    description: "Detects specific business anomalies"
    condition:
      field: department
      operator: "equals"
      value: "Finance"
    severity: high
    
  - id: CUSTOM002
    name: "Cross-Column Validation"
    description: "Validates relationship between columns"
    condition:
      columns: [start_date, end_date]
      operator: "is_chronological"
    severity: medium
```

Reference in config:
```yaml
anomaly:
  rules_file: rules/custom_rules.yaml
```

### LLM Configuration

Enable LLM-assisted anomaly detection:

```bash
# Using local Ollama
ave run \
  --file data.csv \
  --llm-enabled \
  --llm-provider ollama \
  --config ave_config.yaml

# Using Groq (requires GROQ_API_KEY)
ave run \
  --file data.csv \
  --llm-enabled \
  --llm-provider groq \
  --config ave_config.yaml
```

Configure LLM in `ave_config.yaml`:
```yaml
anomaly:
  llm_enabled: true
  llm_provider: ollama
  llm_model: mistral           # For Ollama
  llm_temperature: 0.3
  llm_max_tokens: 500
```

---

## Development

### Prerequisites

- Python 3.11+
- Git
- Virtual environment tool (venv, conda, etc.)

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/mnhat19/AVE.git
cd AVE

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\activate on Windows

# Install development dependencies
pip install -e ".[dev,pdf]"

# Install pre-commit hooks
pre-commit install
```

### Code Style

This project uses Ruff for linting and formatting:

```bash
# Format code
ruff format ave tests

# Run linter
ruff check ave tests --fix

# Check code
ruff check ave tests
```

Configuration in `ruff.toml`:
```toml
line-length = 100
target-version = "py311"

[lint]
select = ["E", "F", "W", "I", "C", "B"]
ignore = ["E501", "W291"]
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=ave --cov-report=html

# Run specific test file
pytest tests/unit/test_finding.py

# Run with verbose output
pytest -v

# Run tests in parallel
pytest -n auto
```

Test structure:
- `tests/unit/` - Unit tests for individual modules
- `tests/integration/` - Integration tests for full pipeline

### Adding New Rules

1. Define rule in `rules/custom_rules.yaml`:
   ```yaml
   - id: RULE_ID
     name: "Rule Name"
     description: "What this rule detects"
     condition:
       field: column_name
       operator: "operator_type"
       value: threshold_or_pattern
     severity: high|medium|low
   ```

2. Implement handler in `ave/engines/rule_engine.py` if operator is custom

3. Test with sample data:
   ```bash
   ave run --file test_data.csv --rules rules/custom_rules.yaml --output test_output
   ```

### Adding New Export Formats

1. Create exporter class in `ave/export/`:
   ```python
   # ave/export/xml_exporter.py
   from ave.export.base import BaseExporter
   
   class XMLExporter(BaseExporter):
       def export(self, ctx: PipelineContext) -> Path:
           # Implementation
   ```

2. Register in `ave/pipeline/layer5_synthesis.py`:
   ```python
   exporters = {
       'xml': XMLExporter(),
       # ...
   }
   ```

3. Add to config options:
   ```yaml
   synthesis:
     export_formats: [json, markdown, xml]
   ```

---

## Testing

### Test Coverage Goals

Current coverage targets:
- Unit: >85% for core modules
- Integration: Critical path coverage

Run coverage report:
```bash
pytest --cov=ave --cov-report=term-missing --cov-report=html
```

### Test Categories

**Unit Tests** - Individual function/class behavior
```bash
pytest tests/unit/
```

**Integration Tests** - Full pipeline execution
```bash
pytest tests/integration/
```

**End-to-End Tests** - CLI invocation
```bash
pytest tests/integration/test_cli_orchestrator_export.py -v
```

---

## Project Structure

```
AVE/
├── ave/                          # Main package
│   ├── __init__.py               # Version and exports
│   ├── cli.py                    # CLI entry point (Typer)
│   ├── config.py                 # Configuration models
│   ├── context.py                # Pipeline context
│   ├── exceptions.py             # Custom exceptions
│   ├── orchestrator.py           # Pipeline orchestration
│   │
│   ├── engines/                  # Core engine implementations
│   │   ├── llm_client.py         # LLM routing (Ollama/Groq/Mistral)
│   │   ├── rule_engine.py        # Rule evaluation engine
│   │   └── trail_writer.py       # Audit trail persistence
│   │
│   ├── models/                   # Data models
│   │   ├── finding.py            # Finding model
│   │   ├── manifest.py           # Source manifest
│   │   └── trail.py              # Trail entry
│   │
│   ├── pipeline/                 # Five-layer pipeline
│   │   ├── layer1_ingestion.py   # Data ingestion and normalization
│   │   ├── layer2_integrity.py   # Integrity checks
│   │   ├── layer3_anomaly.py     # Anomaly detection
│   │   ├── layer4_crossverify.py # Cross-verification
│   │   └── layer5_synthesis.py   # Report generation
│   │
│   ├── export/                   # Export formatters
│   │   ├── markdown_exporter.py  # Markdown report generation
│   │   └── pdf_exporter.py       # PDF report generation
│   │
│   ├── storage/                  # Data persistence
│   │   ├── checkpoint.py         # Checkpoint management
│   │   └── database.py           # SQLite operations
│   │
│   └── utils/                    # Utility functions
│       ├── hashing.py            # File and data hashing
│       ├── logging.py            # Logging configuration
│       └── normalization.py      # Data normalization
│
├── tests/                        # Test suite
│   ├── unit/                     # Unit tests
│   ├── integration/              # Integration tests
│   └── conftest.py               # Pytest configuration
│
├── rules/                        # Rule definitions
│   ├── default_rules.yaml        # Standard audit rules
│   └── examples/                 # Example rule sets
│       ├── isa_rules.yaml        # ISA audit rules
│       └── vas_rules.yaml        # Value-added service rules
│
├── docs/                         # Documentation
│   ├── AVE_AI_Context_Document.md  # Detailed technical spec
│   └── GITHUB_OPERATING_RULES.md   # Contributing guidelines
│
├── pyproject.toml                # Project metadata and dependencies
├── setup.py                      # Legacy setup script
├── ruff.toml                     # Linting and formatting config
└── README.md                     # This file
```

---

## Troubleshooting

### Common Issues

**"File not found" error**
- Verify file path is correct and file exists
- Check relative vs absolute path usage
- Ensure current working directory is correct

**"Unsupported encoding" error**
- AVE attempts multiple encodings automatically
- For problematic files, convert to UTF-8 using:
  ```bash
  iconv -f ISO-8859-1 -t UTF-8 input.csv > output.csv
  ```

**"LLM unavailable" error**
- Verify Ollama is running: `ollama serve`
- Check Groq/Mistral API keys are set in environment
- Disable LLM and retry:
  ```bash
  ave run --file data.csv --config config.yaml  # LLM disabled by default
  ```

**"Checkpoint not found" error**
- Checkpoint session ID may be expired
- Re-run pipeline from beginning:
  ```bash
  ave run --file data.csv --config config.yaml --no-checkpoint
  ```

**Out of memory on large files**
- Reduce file size or split into chunks
- Increase available RAM to system
- Use Polars backend for files >10K rows (automatic)

### Debug Mode

Enable verbose logging:

```bash
# Set environment variable
export AVE_LOG_LEVEL=DEBUG

ave run --file data.csv --config config.yaml
```

Check logs in output directory:
```
ave_output/<session_id>.log
```

---

## Contributing

Contributions are welcome! Please see [GITHUB_OPERATING_RULES.md](docs/GITHUB_OPERATING_RULES.md) for guidelines.

### Pull Request Process

1. Create feature branch from `main`
2. Make changes with clear commit messages
3. Add tests for new functionality
4. Run `ruff format` and `ruff check --fix`
5. Ensure all tests pass: `pytest`
6. Submit PR with description of changes

### Reporting Issues

Include in bug reports:
- Python version (`python --version`)
- AVE version (`ave --version`)
- Input file sample (sanitized)
- Configuration file (sanitized)
- Full error traceback
- Steps to reproduce

---

## License

This project is proprietary software. All rights reserved.

For licensing inquiries, contact the development team.

---

## Support and Contact

- **Issues**: Open a GitHub issue for bugs and feature requests
- **Documentation**: See `docs/` directory for detailed specifications
- **Development**: See [GITHUB_OPERATING_RULES.md](docs/GITHUB_OPERATING_RULES.md)

---

## Roadmap

### Version 0.2.0 (Next)
- Multi-file batch processing
- Web UI dashboard
- Enhanced LLM integration
- Custom rule builder UI

### Version 0.3.0 (Future)
- Database connector support (PostgreSQL, MySQL)
- ERP system integration (SAP, Oracle)
- Real-time pipeline monitoring
- Advanced anomaly ML models

### Version 1.0.0 (Stable)
- Production-ready stability
- Enterprise audit compliance
- Full multi-user support
- Commercial support tiers

---

**AVE v0.1.0** | Last updated: May 3, 2025
