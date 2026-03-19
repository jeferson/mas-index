import logging

from google import genai
from google.genai import types
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
            "_source": ["text", "topic", "doc_id", "chunk_index"],
        },
    )
    return [hit["_source"] for hit in result["hits"]["hits"]]


def build_context(chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        topic = chunk.get("topic") or "—"
        parts.append(f"[Excerpt {i} | topic: {topic}]\n{chunk['text']}")
    return "\n\n---\n\n".join(parts)


def ask(question: str, settings: Settings) -> None:
    """Search relevant chunks and stream a Gemini answer to stdout."""
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

    client = genai.Client(api_key=settings.gemini_api_key)

    for chunk in client.models.generate_content_stream(
        model=settings.gemini_model,
        contents=f"Documents:\n\n{context}\n\nQuestion: {question}",
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
    ):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print()  # newline after streamed response
