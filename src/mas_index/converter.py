import hashlib
import logging
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, WordFormatOption
from docling.pipeline.simple_pipeline import SimplePipeline
from docling_core.types.doc.base import ImageRefMode

from .models import DocumentModel

logger = logging.getLogger(__name__)


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def create_converter() -> DocumentConverter:
    return DocumentConverter(
        allowed_formats=[InputFormat.DOCX],
        format_options={
            InputFormat.DOCX: WordFormatOption(pipeline_cls=SimplePipeline),
        },
    )


def convert_docx(
    source_path: Path,
    output_dir: Path,
    converter: DocumentConverter | None = None,
) -> tuple[DocumentModel, object]:
    """Convert a DOCX file to markdown.

    Returns (DocumentModel, DoclingDocument) — the DoclingDocument is needed
    for chunking.
    """
    if converter is None:
        converter = create_converter()

    result = converter.convert(source_path)
    doc = result.document

    # Prepare output directory for this document
    doc_output = output_dir / source_path.stem
    doc_output.mkdir(parents=True, exist_ok=True)
    image_dir = doc_output / "images"
    image_dir.mkdir(exist_ok=True)

    # Export markdown with referenced images
    markdown = doc.export_to_markdown(image_mode=ImageRefMode.REFERENCED)

    # Save markdown file
    md_path = doc_output / f"{source_path.stem}.md"
    md_path.write_text(markdown, encoding="utf-8")

    # Collect image paths (if any were exported)
    images = [str(p.relative_to(output_dir)) for p in image_dir.glob("*") if p.is_file()]

    # Extract title from first heading or filename
    title = source_path.stem
    for item in doc.texts:
        if hasattr(item, "label") and "heading" in str(item.label).lower():
            title = item.text
            break

    fh = file_hash(source_path)

    model = DocumentModel(
        doc_id=fh,
        title=title,
        source_path=str(source_path),
        markdown=markdown,
        images=images,
        file_hash=fh,
    )

    return model, doc
