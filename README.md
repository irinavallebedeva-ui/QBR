# QBR Portfolio Health Report System

Analyses project email threads and generates an evidence-backed Portfolio Health Report for engineering leadership. Highlights unresolved action items and emerging risks — no hallucination.

## Project Structure

```
project/
├── config.py                ← all tunable parameters (cues, thresholds, models)
├── analytical_engine.py     ← pipeline orchestrator (entry point)
├── email_parser.py          ← ingestion: reads files, parses emails, groups by project
├── detection.py             ← analytical core: noise filter, signal extraction, resolution
├── enrichment.py            ← AI layer: prompts, two-tier LLM, validation, security
├── report.py                ← Markdown report builder
├── Blueprint.md             ← architecture document
├── README.md                ← this file
└── emails/                  ← test data (.txt files + optional Colleagues.txt)
```

## AI Model Choices & Justification

| Model | Where used | Why |
|---|---|---|
| `gpt-4o-mini` | Tier 1 — all open flags | Fast and cheap. Classifies genuine vs false positive, extracts owner + priority. ~10x less cost per call than gpt-4o. Handles volume. |
| `gpt-4o` | Tier 2 — HIGH-priority flags only | Most accurate. Used sparingly — only re-analyses flags Tier 1 rated HIGH. Ensures the critical items get the best classification. |

**Why two tiers?**
Running `gpt-4o` on every flag is expensive and unnecessary — most flags are straightforward. Two tiers gets accuracy where it matters (critical flags) while keeping costs low on the rest.

**Why is AI optional?**
The deterministic pipeline (noise filter → signal extraction → resolution detection) does the heavy lifting and produces a fully functional report. AI enrichment adds owner extraction and priority classification on top — useful, but the system never depends on it.

**Known limitations without an API key:**
The deterministic path has 5 known inaccuracies on the test dataset. All 5 are caught and corrected by the LLM enrichment tier when an API key is provided.

| # | What happens | Why | LLM fixes it by |
|---|---|---|---|
| 1–2 | A "please review" request covering multiple items is marked RESOLVED when only one item is addressed | Regex matches the first resolution cue it finds — it cannot verify that all items in scope were actually handled | Checking whether the resolution covers the full scope of the original request |
| 3–4 | Two questions stay OPEN even though they were answered | The replies use natural language ("I think yes…", "the client liked it…") without any resolution-cue keyword ("done", "fixed", "I'll handle", etc.) | Understanding that a reply semantically answers the question, regardless of exact wording |
| 5 | A "please" inside a quoted error-message string (`"please check!"`) triggers a false action flag | Regex cannot distinguish a "please" that is part of a UX copy example from one that is an actual request | Recognising that the "please" is inside a quoted string, not a real request |

## How to Run

### Requirements

- Python 3.10+
- `openai>=1.0` (only needed for LLM enrichment — see `requirements.txt`)

### Without AI (free, works immediately)

```bash
python analytical_engine.py --email-dir ./emails
```

### With AI enrichment

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-your-key-here
python analytical_engine.py --email-dir ./emails
```

### Google Colab

Run these as **separate cells** in order:

```python
# Cell 1 — install dependencies
!pip install -r requirements.txt
```

```python
# Cell 2 — set the API key (do NOT use !export, it doesn't persist across cells)
import os
os.environ["OPENAI_API_KEY"] = "sk-proj-your-key-here"
```

```python
# Cell 3 — run the pipeline
!python analytical_engine.py --email-dir ./emails
```

⚠️ `!export OPENAI_API_KEY=...` does **not** work in Colab. The `export` runs in a subprocess that exits immediately — the variable is never visible to Python. Use `os.environ` instead.

> **No OpenAI credit?** No problem. The system works fully without an API key — just skip Cell 2 and run Cell 3 directly. You get a complete, accurate report (35 flags, 10 open, 25 resolved). The only difference is the 5 known limitations listed above. When you add credit to your OpenAI account later, just set the key in Cell 2 and re-run — the LLM enrichment activates automatically, no code changes needed.

## Output

- **`report.md`** — the Portfolio Health Report
- **`debug.json`** — pipeline metrics (emails loaded, flags found, runtime, etc.)

## Security

- API key is read from environment variable only — never in code or logs
- Email content is treated as untrusted input (prompt injection protection)
- Sensitive data (credentials, tokens) is detected and blocked before sending to LLM
- File paths are validated to prevent directory traversal
- Email bodies are capped at a configurable max length
