from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    es_host: str = "http://localhost:9200"
    es_user: str = "elastic"
    es_password: str = "changeme"
    input_dir: Path = Path("data/input")
    output_dir: Path = Path("data/output")
    tracker_db: Path = Path("data/tracker.db")
    documents_index: str = "mas-documents"
    chunks_index: str = "mas-chunks"
    batch_size: int = 50
    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-4-6"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    rag_chunks: int = 5

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
