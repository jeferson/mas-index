# Copilot Instructions

## Project Overview

`mas-index` is a batch DOCX-to-Markdown conversion and Elasticsearch indexing pipeline with a RAG (Retrieval-Augmented Generation) query interface. It exposes a `mas-index` CLI built with Click.

## Commands

```bash
# Install (with dev dependencies)
pip install -e ".[dev]"
pip install -e ".[semantic]"   # optional: adds sentence-transformers for future embeddings

# Run the CLI
mas-index run                  # full pipeline: convert + index all DOCX files
mas-index convert              # convert DOCX → Markdown only
mas-index index                # index already-converted files into Elasticsearch
mas-index status               # show per-file processing state from SQLite tracker
mas-index ask "your question"  # RAG: search chunks and stream Claude answer

# Lint / format
ruff check src/
ruff format src/

# Tests
pytest                                          # run all tests
pytest tests/test_foo.py::test_bar -v          # run a single test

# Infrastructure
docker compose up -d            # start Elasticsearch + Kibana
docker compose down             # stop
```

Elasticsearch runs at `http://localhost:9200` (credentials: `elastic:changeme`). Kibana runs at `http://localhost:80`. All settings can be overridden via a `.env` file — see `.env.example` for all variables.

## Architecture

The pipeline has four sequential stages, each implemented as its own module:

```
DOCX file
  │
  ▼ converter.py   — Docling (SimplePipeline/DOCX) → raw markdown
                     python-docx reads Word outline levels to identify headings
                     _postprocess_markdown(): adds ## headings, strips TOC, prepends title
  │
  ▼ chunker.py     — splits post-processed markdown on ## boundaries
                     each section → ChunkModel(topic=heading, text=body)
  │
  ▼ indexer.py     — bulk-writes to two Elasticsearch indices:
                       mas-documents  (full document, BM25 on title+markdown)
                       mas-chunks     (individual sections, BM25 on text)
  │
  ▼ tracker.py     — records per-file state in SQLite (pending/converted/indexed/failed)
                     uses SHA-256 file hash for idempotency (skips unchanged files)
```

The `asker.py` module handles queries: it runs a BM25 `match` search against `mas-chunks`, builds a context string from the top-N results, then streams a Claude response.

## Key Conventions

### Data models
- `DocumentModel` — the full converted document; `doc_id` and `file_hash` are both the SHA-256 of the source DOCX.
- `ChunkModel` — one `##` section; `chunk_id` is `"{doc_id}_{chunk_index}"`.
- Both are Pydantic v2 `BaseModel`; serialise with `.model_dump(mode="json")` before sending to Elasticsearch.

### Configuration
All runtime settings live in `config.py` as a Pydantic `BaseSettings` class (`Settings`). Every field maps 1-to-1 to an env var (e.g. `es_host` ↔ `ES_HOST`). Instantiate with `Settings()` — it auto-loads `.env`.

### Tracker idempotency
`tracker.needs_processing(path, hash)` returns `True` only when the file is new, has changed (different hash), or previously failed. Re-runs skip already-indexed files automatically.

### Converter post-processing
Docling does not reliably emit `##` headings for DOCX files that use custom styles. The converter works around this with two strategies (in `_postprocess_markdown`):
1. python-docx walks the Word `w:outlineLvl` style hierarchy to collect heading texts → promotes matching plain lines to `##`.
2. ALL-CAPS heuristic for lines that still look like headings but weren't captured.

TOC blocks (`**SUMÁRIO**` pattern) are stripped during post-processing.

### Elasticsearch indices
Index mappings are defined as module-level dicts (`DOCUMENTS_MAPPING`, `CHUNKS_MAPPING`) in `indexer.py`. The `topic` field on chunks is `keyword` (not `text`) — use exact-match or aggregation queries on it. Dense vector embedding is stubbed out (commented) in `CHUNKS_MAPPING` for future semantic search.

### Logging
Every module uses `logger = logging.getLogger(__name__)`. Verbosity is controlled by `--verbose` / `-v` on the CLI root group.

### CLI structure
All five commands (`convert`, `index`, `run`, `status`, `ask`) share the same `Settings()` initialisation pattern. `run` is the combined pipeline command.
