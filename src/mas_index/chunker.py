import logging
import re

from docling.chunking import HierarchicalChunker

from .models import ChunkModel

logger = logging.getLogger(__name__)

TOC_ENTRY_RE = re.compile(r"^.+\t\d+$")


def _is_toc_chunk(text: str) -> bool:
    stripped = text.strip()
    return stripped == "**SUMÁRIO**" or bool(TOC_ENTRY_RE.match(stripped))


def chunk_document(
    docling_doc: object,
    doc_id: str,
) -> list[ChunkModel]:
    """Chunk a DoclingDocument into section-based pieces."""
    chunker = HierarchicalChunker()
    chunks = list(chunker.chunk(docling_doc))

    results = []
    chunk_idx = 0
    for chunk in chunks:
        if _is_toc_chunk(chunk.text):
            continue

        text = chunk.text.replace("\t", " ")

        headings = []
        if hasattr(chunk, "meta") and hasattr(chunk.meta, "headings"):
            headings = chunk.meta.headings or []

        results.append(
            ChunkModel(
                chunk_id=f"{doc_id}_{chunk_idx}",
                doc_id=doc_id,
                text=text,
                headings=headings,
                chunk_index=chunk_idx,
            )
        )
        chunk_idx += 1

    logger.info("Chunked document %s into %d chunks", doc_id[:12], len(results))
    return results
