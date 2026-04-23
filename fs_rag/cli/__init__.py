"""Command-line interface for FS-RAG."""

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from fs_rag.core import get_config, get_logger
from fs_rag.indexer import FilesystemIndexer
from fs_rag.search import HybridSearchEngine
from fs_rag.rag import get_rag_pipeline

logger = get_logger(__name__)
console = Console()


@click.group()
def cli():
    """FS-RAG: Filesystem Indexing and RAG-Powered Q&A."""
    pass


@cli.command()
@click.argument("directory", type=click.Path(exists=True))
@click.option("--force", is_flag=True, help="Force reindex even if files are already indexed")
def index(directory: str, force: bool):
    """Index a directory for search."""
    try:
        indexer = FilesystemIndexer()
        directory_path = Path(directory)

        console.print(f"[blue]Indexing directory:[/blue] {directory_path}")

        stats = indexer.index_directory(directory_path, force_reindex=force)

        console.print(Panel(f"""
[green]✓ Indexing Complete[/green]

Files processed: {stats['files_processed']}
Chunks created: {stats['chunks_created']}
Documents embedded: {stats['documents_embedded']}
Errors: {stats['errors']}
        """, title="Index Statistics"))

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Indexing failed: {e}")
        exit(1)


@cli.command()
def stats():
    """Show index statistics."""
    try:
        indexer = FilesystemIndexer()
        stats = indexer.get_index_stats()

        table = Table(title="Index Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        for key, value in stats.items():
            table.add_row(key, str(value))

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Failed to get stats: {e}")
        exit(1)


@cli.command()
@click.argument("query")
@click.option("--method", type=click.Choice(["keyword", "semantic", "hybrid"]), default="hybrid")
@click.option("--top-k", type=int, default=5)
def search(query: str, method: str, top_k: int):
    """Search the index."""
    try:
        search_engine = HybridSearchEngine()
        results = search_engine.search(query, top_k=top_k, method=method)

        if not results:
            console.print("[yellow]No results found.[/yellow]")
            return

        console.print(f"\n[blue]Search Results for:[/blue] '{query}' ({method} search)\n")

        for i, result in enumerate(results, 1):
            console.print(f"[cyan]{i}. {result.file_path}[/cyan] (score: {result.score:.3f})")
            preview = result.content[:200].replace("\n", " ")
            if len(result.content) > 200:
                preview += "..."
            console.print(f"   {preview}\n")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Search failed: {e}")
        exit(1)


@cli.command()
@click.argument("question")
@click.option("--method", type=click.Choice(["keyword", "semantic", "hybrid"]), default="hybrid")
@click.option("--top-k", type=int, default=5)
@click.option("--sources", is_flag=True, help="Show source documents")
def ask(question: str, method: str, top_k: int, sources: bool):
    """Ask a question about indexed documents."""
    try:
        rag = get_rag_pipeline()
        response = rag.answer_question(
            question,
            top_k=top_k,
            search_method=method,
            include_sources=sources
        )

        console.print(Panel(response["answer"], title="Answer"))

        if sources and response.get("sources"):
            console.print("\n[cyan]Sources:[/cyan]")
            for i, source in enumerate(response["sources"], 1):
                console.print(f"[cyan]{i}. {source['file']}[/cyan] (score: {source['score']})")
                console.print(f"   {source['preview']}...\n")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Question answering failed: {e}")
        exit(1)


@cli.command()
def clear():
    """Clear the entire index."""
    if click.confirm("[red]Are you sure you want to clear the entire index?[/red]"):
        try:
            indexer = FilesystemIndexer()
            indexer.clear_index()
            console.print("[green]✓ Index cleared[/green]")
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            logger.error(f"Clear failed: {e}")
            exit(1)


@cli.command()
def config():
    """Show current configuration."""
    try:
        cfg = get_config()

        table = Table(title="Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")

        for key, value in cfg.dict().items():
            table.add_row(key, str(value))

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Failed to show config: {e}")
        exit(1)


if __name__ == "__main__":
    cli()
