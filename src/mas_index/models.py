from datetime import datetime, timezone

from pydantic import BaseModel, Field


class DocumentModel(BaseModel):
    doc_id: str
    title: str
    source_path: str
    markdown: str
    images: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    file_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChunkModel(BaseModel):
    chunk_id: str
    doc_id: str
    topic: str = ""
    text: str
    chunk_index: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
