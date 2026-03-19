import logging

from docling.chunking import HybridChunker

from .models import ChunkModel

logger = logging.getLogger(__name__)


def chunk_document(
    docling_doc: object,
    doc_id: str,
    max_tokens: int = 512,
) -> list[ChunkModel]:
    """Chunk a DoclingDocument into search-ready pieces."""
    chunker = HybridChunker(max_tokens=max_tokens)
    chunks = list(chunker.chunk(docling_doc))

    results = []
    for i, chunk in enumerate(chunks):
        headings = []
        if hasattr(chunk, "meta") and hasattr(chunk.meta, "headings"):
            headings = chunk.meta.headings or []

        results.append(
            ChunkModel(
                chunk_id=f"{doc_id}_{i}",
                doc_id=doc_id,
                text=chunk.text,
                headings=headings,
                chunk_index=i,
            )
        )

    logger.info("Chunked document %s into %d chunks", doc_id[:12], len(results))
    return results
