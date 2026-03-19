import hashlib
import logging
import re
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, WordFormatOption
from docling.pipeline.simple_pipeline import SimplePipeline
from docling_core.types.doc.base import ImageRefMode
from docx import Document as DocxDocument
from docx.oxml.ns import qn

from .models import DocumentModel

logger = logging.getLogger(__name__)


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _get_outline_level(para) -> int | None:
    """Read w:outlineLvl from paragraph's direct formatting and style hierarchy.

    Returns 0-8 for headings, None for body text.
    """
    # Check direct paragraph formatting first
    pPr = para._element.find(qn("w:pPr"))
    if pPr is not None:
        outline = pPr.find(qn("w:outlineLvl"))
        if outline is not None:
            val = outline.get(qn("w:val"))
            if val is not None:
                level = int(val)
                if 0 <= level <= 8:
                    return level

    # Walk the style hierarchy
    style = para.style
    while style is not None:
        style_elem = style.element
        sPPr = style_elem.find(qn("w:pPr"))
        if sPPr is not None:
            outline = sPPr.find(qn("w:outlineLvl"))
            if outline is not None:
                val = outline.get(qn("w:val"))
                if val is not None:
                    level = int(val)
                    if 0 <= level <= 8:
                        return level
        # Move to base (parent) style
        base = style.base_style
        if base is style:
            break
        style = base

    return None


def _extract_heading_texts(docx_path: Path) -> set[str]:
    """Scan all paragraphs with python-docx, return set of heading texts."""
    doc = DocxDocument(str(docx_path))
    headings = set()
    for para in doc.paragraphs:
        # Skip TOC entries
        if para.style and para.style.name and para.style.name.lower().startswith("toc"):
            continue
        text = para.text.strip()
        if not text:
            continue
        if _get_outline_level(para) is not None:
            headings.add(text)
    return headings


def _postprocess_markdown(raw_md: str, heading_texts: set[str], title: str) -> str:
    """Transform raw Docling markdown into properly headed markdown."""
    # 1. Remove leading cover image
    md = re.sub(r"^<!-- image -->\s*\n", "", raw_md)

    # 2. Remove TOC block: **SUMÁRIO** line followed by text\tNUMBER lines
    md = re.sub(
        r"\*\*SUMÁRIO\*\*\s*\n(?:\S[^\n]*\t\d+\s*\n)*",
        "",
        md,
    )

    lines = md.split("\n")
    result = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip lines that are already markdown headings, tables, or HTML comments
        if stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("<!--"):
            result.append(line)
            i += 1
            continue

        # Skip empty lines
        if not stripped:
            result.append(line)
            i += 1
            continue

        # Check if line matches a known heading text
        if stripped in heading_texts:
            result.append(f"## {stripped}")
            i += 1
            continue

        # ALL CAPS heuristic: standalone, short, all uppercase letters
        if (
            len(stripped) < 100
            and stripped == stripped.upper()
            and re.search(r"[A-ZÀ-Ú]", stripped)
            and not stripped.startswith("|")
            and not stripped.startswith("<!--")
        ):
            result.append(f"## {stripped}")
            i += 1
            continue

        # Sub-label heuristic: short line followed within 2 lines by <!-- image -->
        if len(stripped) < 100 and not stripped.startswith("|"):
            has_image_nearby = False
            for j in range(1, 3):
                if i + j < len(lines) and lines[i + j].strip() == "<!-- image -->":
                    has_image_nearby = True
                    break
            if has_image_nearby:
                result.append(f"### {stripped}")
                i += 1
                continue

        result.append(line)
        i += 1

    # 4. Prepend title
    body = "\n".join(result).strip()
    md = f"# {title}\n\n{body}\n"

    # 5. Collapse 3+ blank lines to 2
    md = re.sub(r"\n{3,}", "\n\n", md)

    return md


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
    raw_markdown = doc.export_to_markdown(image_mode=ImageRefMode.REFERENCED)

    # Post-process: add headings, remove TOC, add title
    heading_texts = _extract_heading_texts(source_path)
    title = source_path.stem.replace("-", " ").replace("_", " ").title()
    markdown = _postprocess_markdown(raw_markdown, heading_texts, title)

    # Save markdown file
    md_path = doc_output / f"{source_path.stem}.md"
    md_path.write_text(markdown, encoding="utf-8")

    # Collect image paths (if any were exported)
    images = [str(p.relative_to(output_dir)) for p in image_dir.glob("*") if p.is_file()]

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
