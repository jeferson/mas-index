import logging
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .asker import ask as ask_question
from .chunker import chunk_document
from .config import Settings
from .converter import convert_docx, create_converter, file_hash
from .indexer import Indexer
from .tracker import Tracker

console = Console()
logger = logging.getLogger("mas_index")


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def get_docx_files(input_dir: Path) -> list[Path]:
    return sorted(input_dir.glob("**/*.docx"))


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def cli(verbose: bool) -> None:
    """mas-index: DOCX to Markdown conversion and Elasticsearch indexing."""
    setup_logging(verbose)


@cli.command()
@click.option("--input-dir", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--output-dir", type=click.Path(path_type=Path), default=None)
def convert(input_dir: Path | None, output_dir: Path | None) -> None:
    """Convert DOCX files to markdown."""
    settings = Settings()
    input_dir = input_dir or settings.input_dir
    output_dir = output_dir or settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    tracker = Tracker(settings.tracker_db)
    files = get_docx_files(input_dir)

    if not files:
        console.print(f"[yellow]No DOCX files found in {input_dir}[/yellow]")
        return

    converter_instance = create_converter()
    converted = 0
    failed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Converting...", total=len(files))

        for docx_path in files:
            fh = file_hash(docx_path)
            path_str = str(docx_path)

            if not tracker.needs_processing(path_str, fh):
                progress.advance(task)
                continue

            tracker.set_pending(path_str, fh)
            progress.update(task, description=f"Converting {docx_path.name}...")

            try:
                doc_model, docling_doc = convert_docx(
                    docx_path, output_dir, converter_instance, input_dir
                )
                chunks = chunk_document(doc_model.markdown, doc_model.doc_id, doc_model.relative_path)
                tracker.set_converted(path_str)
                converted += 1
                logger.info(
                    "Converted %s (%d chunks)", docx_path.name, len(chunks)
                )
            except Exception as e:
                tracker.set_failed(path_str, str(e))
                failed += 1
                logger.error("Failed to convert %s: %s", docx_path.name, e)

            progress.advance(task)

    console.print(f"\n[green]Converted: {converted}[/green]  [red]Failed: {failed}[/red]")
    tracker.close()


@cli.command()
@click.option("--input-dir", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--output-dir", type=click.Path(path_type=Path), default=None)
@click.option("--recreate-index", is_flag=True, help="Delete and recreate ES indices")
def index(
    input_dir: Path | None,
    output_dir: Path | None,
    recreate_index: bool,
) -> None:
    """Index converted documents into Elasticsearch."""
    settings = Settings()
    input_dir = input_dir or settings.input_dir
    output_dir = output_dir or settings.output_dir

    indexer = Indexer(settings)
    if not indexer.ping():
        console.print("[red]Cannot connect to Elasticsearch at {settings.es_host}[/red]")
        raise click.Abort()

    indexer.ensure_indices(recreate=recreate_index)
    tracker = Tracker(settings.tracker_db)
    converter_instance = create_converter()

    files = get_docx_files(input_dir)
    indexed = 0
    failed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Indexing...", total=len(files))

        for docx_path in files:
            fh = file_hash(docx_path)
            path_str = str(docx_path)

            if not tracker.needs_processing(path_str, fh):
                progress.advance(task)
                continue

            progress.update(task, description=f"Indexing {docx_path.name}...")

            try:
                doc_model, docling_doc = convert_docx(
                    docx_path, output_dir, converter_instance, input_dir
                )
                chunks = chunk_document(doc_model.markdown, doc_model.doc_id, doc_model.relative_path)

                indexer.index_document(doc_model)
                success, errors = indexer.index_chunks(chunks)

                if errors:
                    tracker.set_failed(path_str, f"Chunk indexing errors: {len(errors)}")
                    failed += 1
                else:
                    tracker.set_indexed(path_str)
                    indexed += 1
                    logger.info(
                        "Indexed %s (%d chunks)", docx_path.name, success
                    )
            except Exception as e:
                tracker.set_failed(path_str, str(e))
                failed += 1
                logger.error("Failed to index %s: %s", docx_path.name, e)

            progress.advance(task)

    console.print(f"\n[green]Indexed: {indexed}[/green]  [red]Failed: {failed}[/red]")
    indexer.close()
    tracker.close()


@cli.command()
@click.option("--input-dir", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--output-dir", type=click.Path(path_type=Path), default=None)
@click.option("--recreate-index", is_flag=True, help="Delete and recreate ES indices")
def run(
    input_dir: Path | None,
    output_dir: Path | None,
    recreate_index: bool,
) -> None:
    """Convert and index DOCX files (combined pipeline)."""
    settings = Settings()
    input_dir = input_dir or settings.input_dir
    output_dir = output_dir or settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    indexer = Indexer(settings)
    if not indexer.ping():
        console.print(f"[red]Cannot connect to Elasticsearch at {settings.es_host}[/red]")
        raise click.Abort()

    indexer.ensure_indices(recreate=recreate_index)
    tracker = Tracker(settings.tracker_db)
    converter_instance = create_converter()

    files = get_docx_files(input_dir)
    if not files:
        console.print(f"[yellow]No DOCX files found in {input_dir}[/yellow]")
        return

    console.print(f"Found [bold]{len(files)}[/bold] DOCX file(s)")

    processed = 0
    failed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Processing...", total=len(files))

        for docx_path in files:
            fh = file_hash(docx_path)
            path_str = str(docx_path)

            if not tracker.needs_processing(path_str, fh):
                progress.advance(task)
                continue

            tracker.set_pending(path_str, fh)
            progress.update(task, description=f"Processing {docx_path.name}...")

            try:
                # Convert
                doc_model, docling_doc = convert_docx(
                    docx_path, output_dir, converter_instance, input_dir
                )

                # Chunk
                chunks = chunk_document(doc_model.markdown, doc_model.doc_id, doc_model.relative_path)

                # Index
                indexer.index_document(doc_model)
                success, errors = indexer.index_chunks(chunks)

                if errors:
                    tracker.set_failed(path_str, f"Chunk indexing errors: {len(errors)}")
                    failed += 1
                else:
                    tracker.set_indexed(path_str)
                    processed += 1
                    logger.info(
                        "Processed %s (%d chunks)", docx_path.name, success
                    )
            except Exception as e:
                tracker.set_failed(path_str, str(e))
                failed += 1
                logger.error("Failed to process %s: %s", docx_path.name, e)

            progress.advance(task)

    console.print(
        f"\n[green]Processed: {processed}[/green]  [red]Failed: {failed}[/red]"
    )
    indexer.close()
    tracker.close()


@cli.command()
def status() -> None:
    """Show processing status."""
    settings = Settings()
    tracker = Tracker(settings.tracker_db)
    counts = tracker.get_status_counts()

    table = Table(title="Processing Status")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")

    total = 0
    for s in ["pending", "converted", "indexed", "failed"]:
        count = counts.get(s, 0)
        total += count
        style = {"indexed": "green", "failed": "red", "pending": "yellow"}.get(s, "")
        table.add_row(s, str(count), style=style)

    table.add_row("total", str(total), style="bold")
    console.print(table)

    failed = tracker.get_failed()
    if failed:
        console.print("\n[red bold]Failed files:[/red bold]")
        for f in failed:
            console.print(f"  {f['file_path']}: {f['error_message']}")

    tracker.close()


@cli.command()
@click.argument("question")
@click.option("--chunks", "-n", default=None, type=int, help="Number of chunks to retrieve (default: RAG_CHUNKS setting)")
def ask(question: str, chunks: int | None) -> None:
    """Ask a question about your indexed documents using Claude."""
    settings = Settings()

    if not settings.anthropic_api_key:
        console.print("[red]ANTHROPIC_API_KEY is not set. Add it to your .env file.[/red]")
        raise click.Abort()

    if chunks is not None:
        settings.rag_chunks = chunks

    ask_question(question, settings)
