"""Command-line interface for FS-RAG."""

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markup import escape

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
@click.argument("directory", type=click.Path(exists=True), required=False)
@click.option("--force", is_flag=True, help="Force reindex even if files are already indexed")
@click.option("--resume", type=str, help="Resume a previous session by session ID")
@click.option("--interactive", is_flag=True, help="Show available sessions and let user choose")
def index(directory: Optional[str], force: bool, resume: Optional[str], interactive: bool):
    """Index a directory for search or resume a previous session.
    
    Examples:
        # Index a directory
        fs-rag index /data/documents
        
        # Resume a specific session
        fs-rag index --resume abc123def456
        
        # Let user choose which session to resume
        fs-rag index --interactive
    """
    try:
        indexer = FilesystemIndexer()
        
        # Validate arguments
        if resume and interactive:
            console.print("[red]Error:[/red] Cannot use both --resume and --interactive")
            exit(1)
        
        if resume and directory:
            console.print("[red]Error:[/red] Cannot specify directory with --resume")
            exit(1)
        
        if not resume and not interactive and not directory:
            console.print("[red]Error:[/red] Must specify DIRECTORY or use --resume/--interactive")
            exit(1)
        
        # Handle resumption
        if resume:
            console.print(f"[blue]Resuming session:[/blue] {resume}")
            stats = indexer.index_directory(resume_session_id=resume)
        elif interactive:
            console.print("[blue]Showing available sessions...[/blue]")
            stats = indexer.index_directory(interactive=True)
        else:
            # Normal indexing
            directory_path = Path(directory)
            console.print(f"[blue]Indexing directory:[/blue] {directory_path}")
            stats = indexer.index_directory(directory_path, force_reindex=force)
        
        console.print(Panel(f"""
[green]✓ Indexing Complete[/green]

Files processed: {stats['files_processed']}
Chunks created: {stats['chunks_created']}
Documents embedded: {stats['documents_embedded']}
Errors: {stats['errors']}
Skipped: {stats.get('skipped', 0)}
        """, title="Index Statistics"))

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Indexing failed: {e}")
        exit(1)


@cli.command()
def sessions():
    """List recent indexing sessions."""
    try:
        indexer = FilesystemIndexer()
        sessions = indexer.get_recent_sessions(limit=10)
        
        if not sessions:
            console.print("[yellow]No sessions found.[/yellow]")
            return
        
        table = Table(title="Recent Indexing Sessions")
        table.add_column("Session ID", style="cyan", width=20)
        table.add_column("Status", style="green")
        table.add_column("Files", justify="right", style="blue")
        table.add_column("Errors", justify="right", style="red")
        table.add_column("Directory", style="yellow")
        
        for session in sessions:
            session_id = session['session_id'][:16] + ".."
            status = session['status']
            total = session['total_files'] or 0
            errors = session['total_errors'] or 0
            root_dir = Path(session['root_dir']).name if session['root_dir'] else 'unknown'
            
            table.add_row(session_id, status, str(total), str(errors), root_dir)
        
        console.print(table)
        
        # Show option to resume
        console.print("\n[cyan]Tip:[/cyan] Use 'fs-rag index --resume <session_id>' to resume a session")
        console.print("or 'fs-rag index --interactive' to choose interactively\n")
        
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Failed to list sessions: {e}")
        exit(1)
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
            include_sources=sources,
            request_type='cli'
        )

        # Escape answer
        console.print(Panel(escape(response["answer"]), title="Answer"))

        if sources and response.get("sources"):
            console.print("\n[cyan]Sources:[/cyan]")
            for i, source in enumerate(response["sources"], 1):
                file = escape(source["file"])
                preview = escape(source["preview"])

                console.print(f"[cyan]{i}. {file}[/cyan] (score: {source['score']})")
                console.print(f"   {preview}...\n")

    except Exception as e:
        console.print(f"[red]Error:[/red] {escape(str(e))}")
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
