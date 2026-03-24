# mas-index

Batch DOCX-to-Markdown conversion and Elasticsearch indexing pipeline with RAG (Retrieval-Augmented Generation) support powered by Claude AI.

## Features

- **Document Conversion** — Convert DOCX files to Markdown using [docling](https://github.com/DS4SD/docling)
- **Semantic Chunking** — Split documents into hierarchical chunks for fine-grained search
- **Elasticsearch Indexing** — Full-text search over documents and chunks
- **RAG Q&A** — Ask natural-language questions about your indexed documents via Claude
- **Change Detection** — SHA-256 hashing skips unchanged files on re-runs
- **Progress Tracking** — SQLite-backed status tracking with rich terminal output

## Requirements

- Python 3.10+
- Docker & Docker Compose (for Elasticsearch and Kibana)
- An [Anthropic API key](https://console.anthropic.com/) (for the `ask` command)

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/jeferson/mas-index.git
cd mas-index
pip install -e .
```

For development tools (pytest, ruff):

```bash
pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your credentials and paths
```

Key variables in `.env`:

| Variable | Description | Default |
|---|---|---|
| `ES_HOST` | Elasticsearch URL | `http://localhost:9200` |
| `ES_USER` | Elasticsearch user | `elastic` |
| `ES_PASSWORD` | Elasticsearch password | `changeme` |
| `INPUT_DIR` | Directory containing DOCX files | `data/input` |
| `OUTPUT_DIR` | Directory for converted Markdown | `data/output` |
| `ANTHROPIC_API_KEY` | Anthropic API key | — |

See [`.env.example`](.env.example) for the full list.

### 3. Start Elasticsearch

```bash
docker compose up -d
```

This launches Elasticsearch 8.17 and Kibana on their default ports.

### 4. Run the pipeline

```bash
# Convert DOCX files and index them in one step
mas-index run --input-dir data/input --output-dir data/output

# Or run each stage separately
mas-index convert --input-dir data/input --output-dir data/output
mas-index index --input-dir data/output
```

### 5. Query your documents

```bash
mas-index ask "What are the main topics covered?"
```

## CLI Reference

```
mas-index [OPTIONS] COMMAND [ARGS]...
```

| Command | Description |
|---|---|
| `convert` | Convert DOCX files to Markdown |
| `index` | Index converted Markdown into Elasticsearch |
| `run` | Convert and index in a single step |
| `status` | Show processing status for tracked files |
| `ask` | Ask a question about the indexed documents |

Use `mas-index COMMAND --help` for detailed options on each command.

Global option: `--verbose` enables debug-level logging.

## Project Structure

```
src/mas_index/
├── cli.py          # Click CLI commands
├── config.py       # Pydantic settings (reads .env)
├── models.py       # Data models
├── converter.py    # DOCX → Markdown conversion
├── chunker.py      # Hierarchical document chunking
├── indexer.py      # Elasticsearch bulk indexing
├── tracker.py      # SQLite processing tracker
└── asker.py        # RAG question answering with Claude
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Lint
ruff check .

# Run tests
pytest
```
