# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run full pipeline: convert all DOCX files in data/input and index to Elasticsearch
mas-index run

# Ask a question (uses RAG with Claude to search indexed content)
mas-index ask "your question here"

# Check processing status
mas-index status

# Lint/format code
ruff check src/
ruff format src/
```

## Project Overview

`mas-index` is a batch processing pipeline that converts DOCX documents to semantic chunks and indexes them into Elasticsearch for RAG (Retrieval-Augmented Generation) queries. The pipeline is exposed through a Click CLI with five commands: `convert`, `index`, `run`, `status`, and `ask`.

**Key workflow:**
1. User places `.docx` files in `data/input/`
2. `mas-index run` processes them: DOCX → Markdown → Chunks → Elasticsearch
3. `mas-index ask "question"` searches chunks and streams an LLM-powered answer (Gemini by default, Claude via config)

## Architecture

The pipeline has four sequential processing stages:

```
data/input/*.docx
  │
  ├─→ converter.py
  │   • Docling (SimplePipeline) parses DOCX to raw markdown
  │   • python-docx extracts Word outline levels (w:outlineLvl) to identify headings
  │   • _postprocess_markdown() adds ## section headings, strips TOC, prepends title
  │   • Output: DocumentModel with full post-processed markdown
  │
  ├─→ chunker.py
  │   • Splits post-processed markdown on ## section boundaries
  │   • Each section → ChunkModel(topic=heading_text, text=body)
  │   • Sub-headings (###) kept inline within section body
  │   • Output: list[ChunkModel]
  │
  ├─→ indexer.py
  │   • Bulk-writes to two Elasticsearch indices via `bulk()` helper
  │   • mas-documents: full document (BM25 on title+markdown, keyword on source_path)
  │   • mas-chunks: individual sections (BM25 on text, keyword on topic)
  │   • Elasticsearch running at http://localhost:9200 (elastic:changeme)
  │
  └─→ tracker.py
      • Records per-file state in SQLite: pending → converted → indexed (or failed)
      • Uses SHA-256(file_bytes) for idempotency — skips unchanged files on re-run
      • Located at data/tracker.db
```

**Query path:**
- `asker.py` receives a question from CLI
- Runs BM25 `match` search on `mas-chunks` index (searches `text` field)
- Retrieves top-N chunks (configurable via `RAG_CHUNKS` setting)
- Builds context string with excerpt headers: `[Excerpt i | topic: {heading}]`
- Streams LLM response using Gemini API (default) or Claude API (if configured)

## Data Models

Both defined in `models.py` as Pydantic v2 `BaseModel`:

**DocumentModel**
- `doc_id`: SHA-256 of source DOCX bytes (unique identifier)
- `title`: Titlecased filename (e.g., "Mas Test" from "mas-test.docx")
- `source_path`: Full path to source DOCX file
- `relative_path`: Path relative to input directory (e.g., "NOVOS OU MIGRADOS/Alerta 99/DES/file.docx")
- `markdown`: Full post-processed markdown (with ## headings)
- `images`: List of extracted image paths (not currently used)
- `metadata`: Dict for future expansion
- `file_hash`: SHA-256 of source for tracker idempotency

**ChunkModel**
- `chunk_id`: Composite ID: `"{doc_id}_{chunk_index}"` (Elasticsearch ID)
- `doc_id`: SHA-256 of source DOCX
- `topic`: The ## heading text (e.g., "INTRODUÇÃO")
- `text`: Full section body (including ### sub-sections)
- `chunk_index`: Sequential 0-based section index within document
- `relative_path`: Same as parent document (allows filtering by source file)
- `created_at`: ISO-8601 UTC timestamp

## Configuration

All settings live in `config.py` as a Pydantic `BaseSettings` class. Every field maps to an env var:

```python
es_host = "http://localhost:9200"           # ES_HOST
es_user = "elastic"                         # ES_USER
es_password = "changeme"                    # ES_PASSWORD
input_dir = Path("data/input")              # INPUT_DIR
output_dir = Path("data/output")            # OUTPUT_DIR
tracker_db = Path("data/tracker.db")        # TRACKER_DB
documents_index = "mas-documents"           # DOCUMENTS_INDEX
chunks_index = "mas-chunks"                 # CHUNKS_INDEX
batch_size = 50                             # BATCH_SIZE (Elasticsearch bulk chunk size)
gemini_api_key = ""                         # GEMINI_API_KEY (for RAG answer generation)
gemini_model = "gemini-2.5-flash-lite"      # GEMINI_MODEL
anthropic_api_key = ""                      # ANTHROPIC_API_KEY (optional: if switching to Claude)
claude_model = "claude-opus-4-6"            # CLAUDE_MODEL (optional: if switching to Claude)
rag_chunks = 5                              # RAG_CHUNKS (top-N chunks to retrieve)
```

Override via `.env` file (auto-loaded). See `.env.example` for all variables.

## Key Implementation Details

### Converter post-processing (`converter.py`)

Docling does not reliably emit `##` headings for DOCX files with custom styles. Two strategies work around this in `_postprocess_markdown()`:

1. **Outline level extraction**: `_extract_heading_texts()` walks the Word `w:outlineLvl` hierarchy via python-docx to collect heading texts. `_postprocess_markdown()` then promotes matching plain lines to `## headings`.

2. **ALL-CAPS heuristic**: Lines that are < 100 chars, ALL uppercase, contain letters, and aren't tables/HTML comments → promoted to `## headings`.

3. **TOC removal**: Detects and removes TOC blocks (`**SUMÁRIO**` pattern with tab-separated page refs).

### Chunker (`chunker.py`)

- Splits on `^## ` (exactly two hashes at line start)
- **Never skips sub-headings (###)** — kept inline in section body
- Each chunk must have non-empty text (empty sections skipped)
- Chunk indices are contiguous after filtering (recomputed with manual counter)
- Tab characters replaced with spaces (legacy Docling cleanup)

### Tracker idempotency (`tracker.py`)

`needs_processing(path, hash)` returns `True` only when:
- File is new (not in tracker)
- File hash differs from tracked hash (content changed)
- Previous attempt failed (status = "failed")

Re-runs skip already-indexed files automatically. To force re-processing: `rm data/tracker.db && mas-index run --recreate-index`.

### Elasticsearch indices

Mappings defined in `indexer.py`:

**CHUNKS_MAPPING:**
- `chunk_id`: keyword (exact match only)
- `doc_id`: keyword
- `topic`: keyword (for faceting/filtering, not analyzed)
- `text`: text with English analyzer (stemming + stopwords for BM25)
- `chunk_index`: integer
- `relative_path`: keyword (for filtering by source file path)
- `created_at`: date

**DOCUMENTS_MAPPING:**
- `doc_id`: keyword
- `title`: text with English analyzer
- `source_path`: keyword (full path)
- `relative_path`: keyword (path relative to input directory)
- `markdown`: text with English analyzer
- `images`: keyword array
- `metadata`: object
- `file_hash`: keyword
- `created_at`: date

Future: `embedding` field (dense_vector) is stubbed out for semantic search.

### CLI structure

All five commands follow the same pattern:
1. Instantiate `Settings()` — auto-loads `.env`
2. Create/connect to indexer, tracker, converter as needed
3. Loop over DOCX files, call stage function, update tracker
4. Progress displayed via `rich.Progress`

Logging controlled by `--verbose` / `-v` flag on root group.

## Development Commands

```bash
# Install (dev = pytest + ruff, semantic = sentence-transformers for future use)
pip install -e ".[dev]"
pip install -e ".[semantic]"

# Format code
ruff format src/

# Lint with fixes
ruff check src/ --fix

# Run Elasticsearch + Kibana (required for pipeline)
docker compose up -d

# Stop services
docker compose down

# View Elasticsearch indices (curl is faster than Kibana for debugging)
curl -u elastic:changeme http://localhost:9200/mas-chunks/_search?size=5

# Check tracker status (SQLite)
sqlite3 data/tracker.db "SELECT file_path, status FROM tracker ORDER BY updated_at DESC LIMIT 10;"
```

## Common Patterns

### Adding a new command
1. Add `@cli.command()` function in `cli.py`
2. Call `Settings()` to load config
3. Create `Indexer()`, `Tracker()`, etc. as needed
4. Use `Progress()` for long-running loops
5. Always close resources: `indexer.close()`, `tracker.close()`

### Querying Elasticsearch manually
Use `curl` with basic auth:
```bash
curl -s -u elastic:changeme \
  'http://localhost:9200/mas-chunks/_search?pretty' \
  -d '{"query": {"match": {"text": "your search term"}}, "size": 10}'
```

### Debugging chunk content
- Check `data/output/` directory for converted markdown files
- Run `mas-index status` to see per-file state
- Query `mas-chunks` index directly to inspect chunk text/topic splits

## Recent Architectural Changes

**markdown-based-chunking branch (commit c3f8e6a):**
- Switched from Docling's `HierarchicalChunker` (raw doc) to markdown-based splitting
- Chunks now split on `##` section boundaries from post-processed markdown
- Replaced `headings: list[str]` field with `topic: str` field
- Reduced ~22 noisy chunks per doc to ~9 semantic sections
- Each section has clear topic context (heading) + full body text

**feature/relative-path branch (commit cf0a715):**
- Added `relative_path` field to both `DocumentModel` and `ChunkModel`
- Stores file path relative to input directory (e.g., `"NOVOS OU MIGRADOS/Alerta 99/DES/file.docx"`)
- Allows filtering/querying chunks by source file without joining
- `source_path` (full path) preserved for backward compatibility

**Gemini API integration (in progress):**
- Switched default RAG engine from Claude API to Google Gemini API
- Uses `google-genai` SDK for answer generation
- Configuration via `GEMINI_API_KEY` and `GEMINI_MODEL` env vars
- Claude API still available as alternative (set `ANTHROPIC_API_KEY` to use)

## Testing

No test suite yet. Tests would belong in `tests/` directory and use `pytest`.

Example structure (if adding):
```python
# tests/test_chunker.py
import pytest
from mas_index.chunker import chunk_document

def test_chunk_document_splits_on_level_2_headings():
    markdown = "# Title\n\n## Section A\n\nBody A\n\n## Section B\n\nBody B"
    chunks = chunk_document(markdown, "doc-123")
    assert len(chunks) == 2
    assert chunks[0].topic == "Section A"
    assert chunks[1].topic == "Section B"
```

## Troubleshooting

| Issue | Diagnosis |
|-------|-----------|
| `ConnectionError: Elasticsearch not reachable` | Run `docker compose up -d` to start ES |
| No chunks appear after indexing | Check `mas-index status` — if status="failed", see error message in tracker |
| Chunks have wrong `topic` | Verify post-processed markdown in `data/output/` has correct `##` headings |
| `GEMINI_API_KEY` error on `ask` | Set `GEMINI_API_KEY` in `.env` or environment (Gemini is default LLM) |
| Want to use Claude instead of Gemini | Set `ANTHROPIC_API_KEY` in `.env` and modify `asker.py` to use Claude SDK |
| Duplicate processing on re-run | Delete `data/tracker.db` and re-run (will reprocess all files) |
