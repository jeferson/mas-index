import logging

import anthropic
from elasticsearch import Elasticsearch

from .config import Settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a helpful assistant that answers questions based strictly on the provided document excerpts.
- Answer only based on the content given. If the answer is not in the documents, say so clearly.
- Quote or reference specific sections when relevant.
- Be concise and direct."""


def search_chunks(es: Elasticsearch, index: str, question: str, n: int) -> list[dict]:
    result = es.search(
        index=index,
        body={
            "query": {"match": {"text": question}},
            "size": n,
            "_source": ["text", "headings", "doc_id", "chunk_index"],
        },
    )
    return [hit["_source"] for hit in result["hits"]["hits"]]


def build_context(chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        heading = " > ".join(chunk.get("headings") or []) or "—"
        parts.append(f"[Excerpt {i} | section: {heading}]\n{chunk['text']}")
    return "\n\n---\n\n".join(parts)


def ask(question: str, settings: Settings) -> None:
    """Search relevant chunks and stream a Claude answer to stdout."""
    es = Elasticsearch(
        settings.es_host,
        basic_auth=(settings.es_user, settings.es_password),
    )

    chunks = search_chunks(es, settings.chunks_index, question, settings.rag_chunks)
    es.close()

    if not chunks:
        print("No relevant documents found for your question.")
        return

    context = build_context(chunks)
    logger.info("Retrieved %d chunks for question", len(chunks))

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)

    with client.messages.stream(
        model=settings.claude_model,
        max_tokens=64000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Documents:\n\n{context}\n\nQuestion: {question}",
            }
        ],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
    print()  # newline after streamed response
