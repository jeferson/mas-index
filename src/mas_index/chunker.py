import logging
import re

from .models import ChunkModel

logger = logging.getLogger(__name__)


def chunk_document(
    markdown: str,
    doc_id: str,
) -> list[ChunkModel]:
    """Chunk post-processed markdown into section-based pieces.

    Splits on ## headings. Each section becomes a chunk with the heading
    as ``topic`` and the body as ``text``. Sub-headings (###) are kept
    inline within the parent section's text.
    """
    sections: list[tuple[str, str]] = []  # (topic, body)
    current_topic = ""
    current_lines: list[str] = []

    for line in markdown.splitlines():
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            # Flush previous section
            body = "\n".join(current_lines).strip()
            if current_topic or body:
                sections.append((current_topic, body))
            current_topic = m.group(1).strip()
            current_lines = []
        elif re.match(r"^#\s+", line):
            # Top-level title — use as first topic, skip as content
            current_topic = re.sub(r"^#\s+", "", line).strip()
            current_lines = []
        else:
            current_lines.append(line)

    # Flush last section
    body = "\n".join(current_lines).strip()
    if current_topic or body:
        sections.append((current_topic, body))

    results = []
    idx = 0
    for topic, text in sections:
        if not text:
            continue

        results.append(
            ChunkModel(
                chunk_id=f"{doc_id}_{idx}",
                doc_id=doc_id,
                topic=topic,
                text=text,
                chunk_index=idx,
            )
        )
        idx += 1

    logger.info("Chunked document %s into %d chunks", doc_id[:12], len(results))
    return results
