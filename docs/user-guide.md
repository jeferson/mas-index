# mas-index User Guide

`mas-index` indexes your DOCX documents into Elasticsearch and lets you ask questions about them using AI (Gemini or Claude).

---

## Prerequisites

- Docker (for Elasticsearch)
- Python 3.10+
- A Gemini API key ([Google AI Studio](https://aistudio.google.com/))

---

## Installation

```bash
git clone <repository>
cd mas-index
pip install -e ".[dev]"
```

Start Elasticsearch (and Kibana):

```bash
docker compose up -d
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

The only required change for basic usage is your Gemini API key:

```env
GEMINI_API_KEY=your-api-key-here
```

### All settings

| Variable | Default | Description |
|---|---|---|
| `ES_HOST` | `http://localhost:9200` | Elasticsearch URL |
| `ES_USER` | `elastic` | Elasticsearch username |
| `ES_PASSWORD` | `changeme` | Elasticsearch password |
| `INPUT_DIR` | `data/input` | Directory to scan for DOCX files |
| `OUTPUT_DIR` | `data/output` | Directory for converted markdown files |
| `TRACKER_DB` | `data/tracker.db` | SQLite file for processing state |
| `GEMINI_API_KEY` | _(required)_ | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` | Gemini model to use |
| `ANTHROPIC_API_KEY` | _(optional)_ | Anthropic Claude API key (alternative to Gemini) |
| `CLAUDE_MODEL` | `claude-opus-4-6` | Claude model (if using Claude) |
| `RAG_CHUNKS` | `5` | Number of document sections retrieved per question |
| `BATCH_SIZE` | `50` | Elasticsearch bulk indexing batch size |

---

## Basic Usage

### 1. Add your documents

Place `.docx` files anywhere inside `data/input/`. Subdirectories are supported:

```
data/input/
├── report.docx
└── NOVOS OU MIGRADOS/
    └── Alerta 99/
        └── DES/
            └── MAS - Alerta 99 - DES v1.2.docx
```

### 2. Index your documents

```bash
mas-index run
```

This converts every DOCX to markdown, splits it into sections, and indexes everything into Elasticsearch. Only new or changed files are processed — re-running is safe and fast.

### 3. Ask a question

```bash
mas-index ask "What is the network topology?"
```

The tool searches your indexed documents for the most relevant sections and streams an AI-generated answer based on their content.

---

## Commands

### `mas-index run`

Converts and indexes all DOCX files in the input directory.

```bash
mas-index run [OPTIONS]

Options:
  --input-dir PATH     Override the input directory
  --output-dir PATH    Override the output directory
  --recreate-index     Delete and recreate Elasticsearch indices (use when
                       changing the index schema)
```

**Examples:**

```bash
# Standard run (processes only new/changed files)
mas-index run

# Force reprocess everything from scratch
rm data/tracker.db && mas-index run --recreate-index

# Use a different input directory
mas-index run --input-dir /path/to/docs
```

### `mas-index ask`

Searches indexed documents and streams an AI-powered answer.

```bash
mas-index ask [OPTIONS] QUESTION

Options:
  -n, --chunks INTEGER  Number of sections to retrieve (overrides RAG_CHUNKS)
```

**Examples:**

```bash
mas-index ask "What are the main components of the system?"
mas-index ask "Who is responsible for the SATQ area?"
mas-index ask -n 10 "Describe all server dependencies"
```

### `mas-index status`

Shows how many files are in each processing state.

```bash
mas-index status
```

Output:

```
      Processing Status
┏━━━━━━━━━━━┳━━━━━━━┓
┃ Status    ┃ Count ┃
┡━━━━━━━━━━━╇━━━━━━━┩
│ pending   │     0 │
│ converted │     0 │
│ indexed   │     3 │
│ failed    │     0 │
│ total     │     3 │
└───────────┴───────┘
```

### `mas-index convert`

Converts DOCX files to markdown only (no indexing).

```bash
mas-index convert [--input-dir PATH] [--output-dir PATH]
```

Converted markdown files are saved to `data/output/<filename>/<filename>.md`. Useful for inspecting how a document was parsed before indexing.

### `mas-index index`

Indexes already-converted documents (no conversion step).

```bash
mas-index index [--input-dir PATH] [--output-dir PATH] [--recreate-index]
```

### Global option: `--verbose`

Pass `-v` to any command to see detailed logs:

```bash
mas-index -v run
mas-index -v ask "your question"
```

---

## How It Works

When you run `mas-index run`, each DOCX goes through four stages:

1. **Convert** — Docling parses the DOCX to markdown. Section headings are detected from the Word outline structure and ALL-CAPS heuristics. The table of contents is stripped.

2. **Chunk** — The markdown is split on `##` section headings. Each section becomes one chunk with a `topic` (the heading) and `text` (the body).

3. **Index** — Chunks and the full document are written to Elasticsearch:
   - `mas-documents` — one entry per file (full markdown, title, paths)
   - `mas-chunks` — one entry per section (topic, text, source path)

4. **Track** — A SQLite file (`data/tracker.db`) records the state of each file. Files are identified by SHA-256 hash, so renaming without changing content won't trigger reprocessing.

When you run `mas-index ask`, the question is searched against the `text` field of all chunks using BM25 full-text search. The top matching sections are assembled into a context prompt and sent to Gemini (or Claude), which generates a grounded answer.

---

## Troubleshooting

**`ConnectionError: Elasticsearch not reachable`**
Elasticsearch isn't running. Start it with:
```bash
docker compose up -d
```

**File shows as `failed` in status**
Run with `--verbose` to see the error:
```bash
mas-index -v run
```
Fix the root cause, then reprocess the file — failed files are automatically retried on the next `run`.

**Document was re-indexed but answers don't reflect changes**
The tracker uses file content hash, not modification time. If the file changed, it will be picked up. If you want to force re-index regardless:
```bash
rm data/tracker.db && mas-index run --recreate-index
```

**Sections are missing or have wrong topics**
Inspect the converted markdown to see how the document was parsed:
```bash
cat data/output/<filename>/<filename>.md
```
Section headings appear as `## HEADING`. If headings are wrong, the DOCX may use unusual styles not captured by the outline-level or ALL-CAPS detection.

**`GEMINI_API_KEY` not set error**
Add your key to `.env`:
```env
GEMINI_API_KEY=your-api-key-here
```

---

## Kibana (optional)

Kibana provides a visual interface for exploring indexed data. It runs at `http://localhost:80` after `docker compose up -d`.

Log in with username `elastic` and password `changeme`, then browse the `mas-documents` and `mas-chunks` indices under **Discover**.
