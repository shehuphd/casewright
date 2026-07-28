# Casewright

**Version 1.0.1** · Built by [Mo Shehu](https://mohammedshehu.com)

A lightweight chargeback representment workbench. Takes a chargeback case, reads the relevant scheme reason-code rules, reviews attached merchant evidence, and produces an analyst-ready workup with a recommendation and evidence checklist.

Supports OpenAI and Anthropic models. Runs locally or behind a cloud deployment (Azure Container Apps or similar). No external services beyond the LLM API.

<img width="1363" height="788" alt="image" src="https://github.com/user-attachments/assets/c4c7843e-b844-4398-a3f2-f5e293569410" />


## Quick start

### 1. Clone

```bash
git clone https://github.com/shehuphd/casewright.git
cd casewright
```

### 2. Add evidence documents

Copy your evidence PDFs and images into `data/documents/`:

```bash
cp /path/to/evidence/files/* data/documents/
```

Or set `DOCUMENTS_DIR` in `.env` to an absolute path elsewhere.

### 3. Configure your API key

Copy `.env.example` to `.env` and fill in your key — **or** skip this and enter it via the in-app Settings panel on first launch.

```bash
cp .env.example .env
```

```env
LLM_PROVIDER=openai           # or: anthropic
LLM_API_KEY=sk-...
LLM_TEXT_MODEL=gpt-4.1-mini   # or: claude-sonnet-4-6, etc.
```

### 4. Launch

| Platform | How to run |
|---|---|
| **macOS** | Double-click `launch.command` in Finder |
| **Linux** | Run `./launch.sh` in your terminal |
| **Windows** | Double-click `launch.bat` in Explorer |

On first run the launcher creates a virtual environment and installs dependencies automatically. Subsequent launches skip straight to startup.

> **macOS note:** if Gatekeeper blocks the script, right-click → Open the first time to approve it.

> **Windows note:** `launch.bat` requires Python to be on your PATH. Install from python.org and tick "Add to PATH" during setup.

The launcher finds a free port automatically (5050 by default, with fallback) and opens the app in your browser.

To reset all generated workups without losing case data:

```bash
python reset_outputs.py
```

## Project structure

```
launch.command          Double-click launcher (macOS)
launch.sh               Shell launcher (Linux)
launch.bat              Double-click launcher (Windows)
app.py                  Flask API + entry point
reset_outputs.py        Clear all workup files
src/
  config.py             .env loading and settings management
  data_loader.py        Load and validate cases.json
  rule_loader.py        Load reason codes from data/reason_codes.md
  document_extractor.py pypdf text extraction + image encoding
  prompt_builder.py     Build LLM prompt from case + rule + documents
  llm_client.py         OpenAI and Anthropic client (configurable)
  schema.py             Output schema + validation
  analysis_store.py     Read/write workup JSON files
  tracing.py            TraceAct configuration and helpers
data/
  cases.json            Chargeback cases
  reason_codes.md       Scheme reason-code rules (human-readable)
  documents/            Evidence PDFs and images
outputs/
  workups/              Generated workup JSON files (one per case)
templates/
  index.html            Single-page analyst workbench UI
```

## How document processing works

**PDFs** are extracted with `pypdf`. Text is assembled page-by-page with page-number markers so the LLM can cite specific pages. Long documents are truncated at ~15,000 characters with a note.

**Images** (PNG, JPG) are base64-encoded and sent as vision input. Both OpenAI and Anthropic support this.

**Prompt injection safety:** the system prompt instructs the LLM to treat all merchant evidence as untrusted content and to ignore any instructions found inside documents. Documents that appear to contain injection attempts are flagged as `invalid` rather than assessed.

## Audit trail

Every analysis run is traced with [TraceAct](https://github.com/traceact/traceact) (≥ 0.10.0). Each trace records the rule that was loaded, every evidence file read and its extraction status, the assembled prompt size, the model call with its duration and usage, schema validation, and the workup written to disk. Failures are captured with the exception type and message.

Tracing is optional. If TraceAct isn't installed the app still runs — every tracing call becomes a no-op so the dependency can never block an analyst.

Traces are written to `logs/traces.jsonl`. The **Audit trail** button sits in the badge row next to the confidence score on any processed case. Clicking it opens the TraceAct viewer scoped to the Casewright trace log. You can also explore traces from the command line:

```bash
traceact view logs/traces.jsonl
```

Or query them programmatically:

```python
from traceact import TraceLog

log = TraceLog("logs/traces.jsonl")
log.filter(action="case.analyse", status="failed").render_table()
```

API keys and other credentials are redacted before anything is written. The viewer binds to localhost only — never expose it to a network without authentication in front of it, since traces contain case data.

## LLM output

Each analysis produces a JSON workup in `outputs/workups/{case_id}.json` containing:

| Field | Description |
|---|---|
| `reason_code_summary` | Plain-English issuer allegation and scheme requirement summary |
| `evidence_assessment` | Per-requirement status with document citations |
| `representment_rationale` | 3–5 sentence rationale, editable in the UI |
| `recommended_action` | `represent` / `accept_liability` / `request_more_evidence` |
| `confidence` | `High` / `Medium` / `Low` |
| `request_more_evidence` | Specific items to request from the merchant |
| `analyst_override` | Saved when the analyst overrides the recommendation |
| `processing_notes` | Model, token estimate, extraction status, limitations |

Evidence assessment statuses: `satisfied` · `partial` · `missing` · `needs_review` · `not_applicable` · `invalid`

- **`invalid`** — document is unrelated to the transaction, corrupt, or contains a prompt injection attempt. Not assessed against scheme requirements.

## Demo limitations

- No authentication or multi-user support
- No production database — workups are flat JSON files
- PDF text extraction fails on scanned/image-only PDFs (marked `invalid`)
- Reason-code rules are simplified; real scheme rules are substantially more complex
- Very long documents are truncated at ~15,000 characters

## Production improvements and customisations

- Auth + role-based access
- Persistent database with audit log
- Robust OCR pipeline (Tesseract or cloud) for scanned PDFs
- Document preview with cited-page highlighting
- Case-management API integration
- Batch queue processing with async workers
- Model evaluation suite against known case outcomes
- Human-feedback loop for recommendation quality
- PII redaction before LLM processing
- Prompt-injection test suite against adversarial evidence files
- Policy/rule versioning as scheme rules update

