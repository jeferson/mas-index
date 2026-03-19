import logging

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from .config import Settings
from .models import ChunkModel, DocumentModel

logger = logging.getLogger(__name__)

DOCUMENTS_MAPPING = {
    "mappings": {
        "properties": {
            "doc_id": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "english"},
            "source_path": {"type": "keyword"},
            "markdown": {"type": "text", "analyzer": "english"},
            "images": {"type": "keyword"},
            "metadata": {"type": "object", "enabled": True},
            "file_hash": {"type": "keyword"},
            "created_at": {"type": "date"},
        }
    }
}

CHUNKS_MAPPING = {
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "doc_id": {"type": "keyword"},
            "text": {"type": "text", "analyzer": "english"},
            "headings": {"type": "text"},
            "chunk_index": {"type": "integer"},
            # Future: uncomment for semantic search
            # "embedding": {"type": "dense_vector", "dims": 384, "index": True, "similarity": "cosine"},
        }
    }
}


class Indexer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.es = Elasticsearch(
            settings.es_host,
            basic_auth=(settings.es_user, settings.es_password),
        )

    def ping(self) -> bool:
        return self.es.ping()

    def ensure_indices(self, recreate: bool = False) -> None:
        for name, mapping in [
            (self.settings.documents_index, DOCUMENTS_MAPPING),
            (self.settings.chunks_index, CHUNKS_MAPPING),
        ]:
            if recreate and self.es.indices.exists(index=name):
                logger.info("Deleting index %s", name)
                self.es.indices.delete(index=name)
            if not self.es.indices.exists(index=name):
                logger.info("Creating index %s", name)
                self.es.indices.create(index=name, body=mapping)

    def index_document(self, doc: DocumentModel) -> None:
        self.es.index(
            index=self.settings.documents_index,
            id=doc.doc_id,
            document=doc.model_dump(mode="json"),
        )

    def index_chunks(self, chunks: list[ChunkModel]) -> tuple[int, list]:
        if not chunks:
            return 0, []

        actions = [
            {
                "_index": self.settings.chunks_index,
                "_id": chunk.chunk_id,
                "_source": chunk.model_dump(mode="json"),
            }
            for chunk in chunks
        ]

        success, errors = bulk(
            self.es,
            actions,
            chunk_size=self.settings.batch_size,
            raise_on_error=False,
        )
        if errors:
            logger.error("Bulk indexing had %d errors", len(errors))
        return success, errors

    def close(self) -> None:
        self.es.close()
