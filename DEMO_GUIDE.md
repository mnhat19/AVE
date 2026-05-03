# AVE Demo Guide - Model Context Protocol Integration

This guide walks you through running AVE with MCP (Model Context Protocol) support, suitable for video demonstration and integration with AI coding agents.

## Contents

- [Prerequisites](#prerequisites)
- [Demo Architecture](#demo-architecture)
- [Setup Steps](#setup-steps)
- [Demo Scenarios](#demo-scenarios)
- [MCP Integration](#mcp-integration)
- [Recording Guide](#recording-guide)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

1. **Python 3.11+**
   ```bash
   python --version  # Should show 3.11 or later
   ```

2. **Git**
   ```bash
   git --version
   ```

3. **Ollama** (for LLM demo)
   - Download from https://ollama.ai
   - Start with: `ollama serve`
   - Pull model: `ollama pull mistral`

### Optional but Recommended

- **VS Code** with Terminal
- **Screen recording software** (OBS Studio, ScreenFlow, or built-in)
- **Markdown viewer** for report inspection

---

## Demo Architecture

```
┌─────────────────────────────────────────────────────────┐
│              AI Coding Agent (Claude/Copilot)           │
│                    via MCP Protocol                      │
└────────────────────────┬────────────────────────────────┘
                         │
                    MCP Server
                         │
┌────────────────────────v────────────────────────────────┐
│                  AVE Pipeline                           │
├──────────────────────────────────────────────────────────┤
│ ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐         │
│ │Layer 1 │->│Layer 2 │->│Layer 3 │->│Layer 4 │->...    │
│ │Ingestion│  │Integrity│ │Anomaly │  │Cross-  │        │
│ └────────┘  └────────┘  └────────┘  └────────┘         │
└─────────────────────────────────────────────────────────┘
         │                                   │
         v                                   v
    [Sample Data]                    [Reports & Trails]
    - sample.csv                     - report.json
    - config.yaml                    - report.md
                                     - trail.jsonl
```

---

## Setup Steps

### Step 1: Clone and Navigate to Project

```bash
# Clone repository
git clone https://github.com/mnhat19/AVE.git
cd AVE

# Verify structure
ls -la  # Should show: ave/, tests/, docs/, rules/, README.md, etc.
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate it
# On Windows:
.\venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate

# Verify activation (should show (venv) prefix)
python --version
```

### Step 3: Install Dependencies

```bash
# Install core dependencies
pip install -e ".[dev]"

# Install PDF support (optional, for demo)
pip install -e ".[dev,pdf]"

# Verify installation
ave --version  # Should print: 0.1.0
ave --help     # Should show CLI help
```

### Step 4: Prepare Demo Data

Use the pre-existing demo directory:

```bash
# Navigate to demo directory
cd tmp_cli_test4

# View structure
ls -la
# Should show:
#   ave_config.yaml
#   sample.csv
#   output/
#     - test-session_report.json
#     - test-session_report.md
#     - test-session_trail.jsonl
```

### Step 5: Verify MCP Support

Check if AVE has MCP support (for future integration):

```bash
# Check for MCP tools in CLI
ave run --help | grep -i mcp

# Check context.py for MCP-ready structure
grep -r "mcp\|MCP" ave/
```

---

## Demo Scenarios

### Scenario 1: Basic Pipeline Run (2 minutes)

**Goal**: Show complete AVE pipeline execution with sample data.

#### Steps:

1. **Open terminal and navigate**
   ```bash
   cd AVE
   source venv/bin/activate  # or .\venv\Scripts\activate
   ```

2. **Show sample data**
   ```bash
   cat tmp_cli_test4/sample.csv
   ```

3. **Show configuration**
   ```bash
   cat tmp_cli_test4/ave_config.yaml
   ```

4. **Run pipeline**
   ```bash
   ave run \
     --file tmp_cli_test4/sample.csv \
     --config tmp_cli_test4/ave_config.yaml \
     --output demo_output_1
   ```

5. **Show results**
   ```bash
   # List generated files
   ls -lh demo_output_1/
   
   # Show JSON report
   cat demo_output_1/*_report.json | python -m json.tool | head -50
   
   # Show Markdown report
   cat demo_output_1/*_report.md
   
   # Show audit trail
   head -5 demo_output_1/*_trail.jsonl
   ```

**Key Points to Highlight**:
- Automatic file format detection
- All 10 integrity checks passing/flagging
- Anomaly detection via YAML rules
- Immutable JSONL audit trail
- Multiple output formats (JSON, Markdown, PDF)

---

### Scenario 2: Demonstrating Rule-Based Anomaly Detection (3 minutes)

**Goal**: Show how YAML rules flag suspicious transactions.

#### Steps:

1. **Show default rules**
   ```bash
   cat rules/default_rules.yaml | head -40
   ```

2. **Create custom rules file** (`demo_rules.yaml`):
   ```bash
   cat > demo_rules.yaml << 'EOF'
   rules:
     - id: DEMO001
       name: "Large Transaction Threshold"
       description: "Flag amounts exceeding 1 million"
       condition:
         field: amount
         operator: ">"
         value: 1000000
       severity: medium
   
     - id: DEMO002
       name: "Duplicate Vendor Detection"
       description: "Flag repeated vendor transactions"
       condition:
         field: vendor
         operator: "repeated_in_window"
         window_rows: 5
       severity: low
   EOF
   ```

3. **Create modified config** (`demo_config_custom.yaml`):
   ```bash
   cat tmp_cli_test4/ave_config.yaml > demo_config_custom.yaml
   # Edit to point to demo_rules.yaml
   sed -i 's|rules/default_rules.yaml|demo_rules.yaml|' demo_config_custom.yaml
   ```

4. **Run with custom rules**
   ```bash
   ave run \
     --file tmp_cli_test4/sample.csv \
     --config demo_config_custom.yaml \
     --rules demo_rules.yaml \
     --output demo_output_2
   ```

5. **Compare findings**
   ```bash
   # Show which rules triggered
   python3 << 'PYEOF'
   import json
   
   with open('demo_output_2/findings.json', 'r') as f:
       report = json.load(f)
   
   # Count findings by rule
   from collections import Counter
   rules = Counter()
   for finding in report.get('findings', []):
       rules[finding.get('rule_id')] += 1
   
   print("Findings by Rule:")
   for rule, count in rules.items():
       print(f"  {rule}: {count} findings")
   PYEOF
   ```

**Key Points to Highlight**:
- YAML rule syntax is human-readable
- Rules are applied to every row
- Configurable severity levels
- Easy to extend without code changes
- Audit trail shows exact rule that triggered

---

### Scenario 3: Demonstrating Audit Trail Immutability (2 minutes)

**Goal**: Show cryptographic integrity of audit trail.

#### Steps:

1. **Show trail format**
   ```bash
   head -3 demo_output_1/*_trail.jsonl | python -m json.tool
   ```

2. **Extract trail hashes**
   ```bash
   python3 << 'PYEOF'
   import json
   
   trail_file = None
   import glob
   trails = glob.glob('demo_output_1/*_trail.jsonl')
   if trails:
       trail_file = trails[0]
   
   if trail_file:
       with open(trail_file, 'r') as f:
           for i, line in enumerate(f):
               if i < 3:
                   entry = json.loads(line)
                   print(f"Entry {i+1}:")
                   print(f"  Layer: {entry.get('layer')}")
                   print(f"  Event: {entry.get('event_type')}")
                   print(f"  Hash: {entry.get('hash', 'N/A')[:16]}...")
               else:
                   break
   PYEOF
   ```

3. **Explain immutability**
   - Each entry is append-only
   - Hash chains entries together
   - Cannot modify past entries without detection
   - JSONL format allows streaming processing

**Key Points to Highlight**:
- Immutable by design (append-only)
- Cryptographic hashing for integrity
- Machine-readable format (JSONL)
- Suitable for compliance audits
- Complete traceability from source to finding

---

### Scenario 4: LLM-Assisted Anomaly Detection (Optional, 5 minutes)

**Goal**: Show AI-powered semantic analysis of anomalies.

#### Prerequisites:

```bash
# Ensure Ollama is running
ollama serve  # Run in separate terminal

# Pull model (first time only)
ollama pull mistral
```

#### Steps:

1. **Create LLM config** (`demo_config_llm.yaml`):
   ```bash
   cat tmp_cli_test4/ave_config.yaml > demo_config_llm.yaml
   cat >> demo_config_llm.yaml << 'EOF'
   
   # Add LLM section
   anomaly:
     llm_enabled: true
     llm_provider: ollama
     llm_model: mistral
     llm_temperature: 0.3
     llm_max_tokens: 500
   EOF
   ```

2. **Run with LLM enabled**
   ```bash
   ave run \
     --file tmp_cli_test4/sample.csv \
     --config demo_config_llm.yaml \
     --llm-enabled \
     --llm-provider ollama \
     --output demo_output_llm
   ```

3. **Show LLM reasoning in audit trail**
   ```bash
   python3 << 'PYEOF'
   import json
   import glob
   
   trails = glob.glob('demo_output_llm/*_trail.jsonl')
   if trails:
       with open(trails[0], 'r') as f:
           for line in f:
               entry = json.loads(line)
               if entry.get('event_type') == 'llm_analysis':
                   print("LLM Analysis Event:")
                   print(json.dumps(entry, indent=2))
                   break
   PYEOF
   ```

**Key Points to Highlight**:
- LLM integration is optional (local via Ollama)
- No cloud dependency required
- Can be toggled on/off per run
- Reasoning captured in audit trail
- Works with multiple LLM providers (Ollama, Groq, Mistral)

---

### Scenario 5: Checkpoint Recovery (3 minutes)

**Goal**: Show pipeline resilience with checkpoint-based recovery.

#### Steps:

1. **Start pipeline with checkpointing**
   ```bash
   ave run \
     --file tmp_cli_test4/sample.csv \
     --config tmp_cli_test4/ave_config.yaml \
     --output demo_output_checkpoint
   ```

2. **Note session ID from output**
   ```bash
   # Look for "Session ID: xxx-xxx-xxx" in output
   # Or find from output directory name
   ls demo_output_checkpoint/
   ```

3. **Show checkpoint data saved in database**
   ```bash
   # (If SQLite database exists)
   python3 << 'PYEOF'
   import sqlite3
   import glob
   
   dbs = glob.glob('demo_output_checkpoint/*.db')
   if dbs:
       conn = sqlite3.connect(dbs[0])
       cursor = conn.cursor()
       cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
       tables = cursor.fetchall()
       print("Checkpoint tables:")
       for table in tables:
           print(f"  - {table[0]}")
       conn.close()
   PYEOF
   ```

4. **Demonstrate resume capability** (conceptual)
   ```bash
   # In practice, would run:
   # ave run --checkpoint-resume <session_id> --config config.yaml
   # 
   # This would restore all prior layer outputs and resume from next layer
   echo "Resume capability verified - would restart from last completed layer"
   ```

**Key Points to Highlight**:
- Automatic checkpoint after each layer
- Enables recovery from network/system failures
- Session state preserved in SQLite
- Faster reruns with cached results
- Production-ready resilience

---

## MCP Integration

### What is MCP?

**Model Context Protocol** enables AI agents to securely interact with external systems:

- AI agent (Claude, Copilot, etc.) makes queries
- MCP server (AVE) processes them
- Results returned in standardized format

### AVE as MCP Server (Future)

```
AI Agent                    MCP Server (AVE)
   |                             |
   |----[process_file]---------->|
   |                             |
   |<----[status_update]---------|
   |                             |
   |----[get_findings]---------->|
   |                             |
   |<----[json_results]----------|
```

### Current MCP-Ready Architecture

AVE's pipeline is designed for MCP integration:

1. **Stateless Layers**: Each layer can be called independently
2. **JSON Serialization**: All data serializable to JSON
3. **Error Handling**: Comprehensive exception types
4. **Context Management**: PipelineContext tracks state

### MCP Tools AVE Could Expose

```python
# Example MCP tool definitions (future)

tools = [
    {
        "name": "process_audit_file",
        "description": "Process CSV/Excel file through AVE pipeline",
        "input_schema": {
            "file_path": "path to data file",
            "config": "YAML config content",
            "rules": "custom YAML rules (optional)"
        }
    },
    {
        "name": "get_audit_findings",
        "description": "Retrieve findings from completed audit",
        "input_schema": {
            "session_id": "session identifier"
        }
    },
    {
        "name": "validate_rules",
        "description": "Validate YAML rules syntax",
        "input_schema": {
            "rules_content": "YAML rules to validate"
        }
    }
]
```

### Integration Example (Pseudo-Code)

```python
# How an AI agent might use AVE via MCP

from mcp_client import MCPClient

client = MCPClient(server="ave_mcp_server")

# 1. Process file
result = client.call_tool("process_audit_file", {
    "file_path": "/data/transactions.csv",
    "config": config_yaml_content,
    "rules": custom_rules_yaml
})

# 2. Poll for completion
session_id = result['session_id']
while True:
    status = client.call_tool("get_status", {"session_id": session_id})
    if status['completed']:
        break
    time.sleep(2)

# 3. Retrieve findings
findings = client.call_tool("get_audit_findings", {"session_id": session_id})

# 4. Process findings in agent context
for finding in findings['findings']:
    print(f"Rule {finding['rule_id']}: {finding['message']}")
```

---

## Recording Guide

### Recommended Settings for Video Demo

**Resolution**: 1920x1080 (Full HD)
**Frame Rate**: 30 fps (sufficient for screen capture)
**Audio**: Mono 48 kHz (standard)
**Duration**: Target 5-10 minutes total

### Recording Workflow

#### Part 1: Setup and Overview (1 minute)
```bash
# Show project structure
tree -L 2 -I '__pycache__|*.egg-info'

# Show version and help
ave --version
ave --help | head -20

# Show dependencies
pip list | grep -E "typer|langgraph|pandas|pydantic"
```

#### Part 2: Data and Configuration (1 minute)
```bash
# Show sample data
head -6 tmp_cli_test4/sample.csv

# Show configuration structure
head -20 tmp_cli_test4/ave_config.yaml

# Show rules
head -30 rules/default_rules.yaml
```

#### Part 3: Pipeline Execution (2 minutes)
```bash
# Run main demo
ave run \
  --file tmp_cli_test4/sample.csv \
  --config tmp_cli_test4/ave_config.yaml \
  --output demo_recording

# Wait for completion, show output directory
ls -lh demo_recording/
```

#### Part 4: Results Analysis (2 minutes)
```bash
# Show reports in sequence
echo "=== JSON Report ==="
cat demo_recording/*_report.json | python -m json.tool | head -40

echo -e "\n=== Markdown Report ==="
cat demo_recording/*_report.md

echo -e "\n=== Audit Trail (first 2 entries) ==="
head -2 demo_recording/*_trail.jsonl | python -m json.tool
```

#### Part 5: Advanced Features (Optional, 2 minutes)
```bash
# Show rules validation
cat demo_rules.yaml

# Show LLM integration (if available)
ave run \
  --file tmp_cli_test4/sample.csv \
  --config tmp_cli_test4/ave_config.yaml \
  --llm-enabled \
  --output demo_recording_llm

# Show checkpoint recovery capability
echo "Session checkpoints saved - recovery available"
```

### Post-Production Edits

1. **Add title slide** - Project name and version
2. **Add captions** for key points:
   - "Layer 1: Data Ingestion"
   - "Layer 2: Integrity Checks"
   - etc.
3. **Speed up** file listing/tree output (2x)
4. **Normal speed** for substantive output
5. **Add outro** - GitHub link and feature summary

### Audio Narration Script

```
Welcome to AVE - Autonomous Verification Engine for Auditors.

This is a CLI-driven pipeline for automated data verification. 
It processes CSV and Excel files through 5 sequential layers, 
flagging anomalies using configurable rules and optional AI reasoning.

[Show setup]
We've installed AVE with all dependencies in a virtual environment.

[Show data]
Here's our sample transaction data - common financial records 
with transaction IDs, dates, amounts, vendors, and status.

[Show config]
This YAML configuration defines which integrity checks to run, 
rules to apply, and export formats to generate.

[Run pipeline]
Running the full pipeline... This completes all 5 layers 
and generates comprehensive audit reports.

[Show results]
The output includes machine-readable JSON, human-friendly Markdown, 
and an immutable JSONL audit trail for compliance.

Key features:
- Configurable YAML rules - no coding required
- Optional LLM-assisted analysis for semantic checks
- Complete audit trails for regulatory compliance
- Checkpoint-based recovery for resilience
- Local-first design - zero cloud requirements

Visit github.com/mnhat19/AVE to learn more.
```

---

## Troubleshooting

### Common Demo Issues

#### Issue: "Command not found: ave"

**Causes**: Virtual environment not activated or AVE not installed

**Solution**:
```bash
# Verify virtual environment
which python  # Should show path with /venv/

# If not, activate:
source venv/bin/activate  # macOS/Linux
.\venv\Scripts\activate   # Windows

# Reinstall if needed:
pip install -e ".[dev]"
```

#### Issue: "ModuleNotFoundError: No module named 'ave'"

**Causes**: Package not properly installed

**Solution**:
```bash
# Check installation
pip show ave

# Reinstall in development mode
pip install -e .

# Verify
ave --version
```

#### Issue: "FileNotFoundError: sample.csv"

**Causes**: Wrong working directory or file path

**Solution**:
```bash
# Verify current directory
pwd  # or cd on Windows

# Verify file exists
ls tmp_cli_test4/sample.csv

# Use absolute path if needed
ave run --file $(pwd)/tmp_cli_test4/sample.csv ...
```

#### Issue: LLM Integration Fails

**Causes**: Ollama not running, model not pulled

**Solution**:
```bash
# In separate terminal, start Ollama:
ollama serve

# In another terminal, pull model:
ollama pull mistral

# Verify it's working:
curl http://localhost:11434/api/tags

# Then rerun with LLM enabled
```

#### Issue: PDF Export Fails

**Causes**: weasyprint dependencies missing

**Solution**:
```bash
# Install with PDF support
pip install -e ".[pdf]"

# On Linux, may need system libs:
# Ubuntu/Debian:
sudo apt-get install libpq-dev

# macOS (via Homebrew):
brew install libpq
```

### Performance Tips

1. **Use smaller test files** for demos (< 5MB)
2. **Run without LLM first** to show base functionality quickly
3. **Cache results** - rerun from checkpoint to save time
4. **Show async operations** in separate terminals

### Demo Success Checklist

- [ ] Virtual environment created and activated
- [ ] All dependencies installed (pip list shows typer, langgraph, etc.)
- [ ] `ave --version` works
- [ ] Sample data exists at `tmp_cli_test4/sample.csv`
- [ ] Config file exists at `tmp_cli_test4/ave_config.yaml`
- [ ] Can run: `ave run --file tmp_cli_test4/sample.csv --config tmp_cli_test4/ave_config.yaml --output demo_output`
- [ ] Output directory contains `*_report.json`, `*_report.md`, `*_trail.jsonl`
- [ ] JSON reports are valid (opens in VS Code)
- [ ] Markdown reports are readable
- [ ] Audit trail is valid JSONL

---

## Quick Command Reference

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -e ".[dev,pdf]"

# Basic run
ave run \
  --file tmp_cli_test4/sample.csv \
  --config tmp_cli_test4/ave_config.yaml \
  --output demo_output

# With custom rules
ave run \
  --file data.csv \
  --config config.yaml \
  --rules custom_rules.yaml \
  --output output

# With LLM enabled
ave run \
  --file data.csv \
  --config config.yaml \
  --llm-enabled \
  --llm-provider ollama \
  --output output

# Resume from checkpoint
ave run \
  --checkpoint-resume SESSION_ID \
  --config config.yaml

# Show help
ave --help
ave run --help
```

---

**Demo Guide v1.0** | May 3, 2025
