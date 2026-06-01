import json

import click

from larvis import rag
from larvis.health import get_status
from larvis.indexer import index_vault


@click.group()
def cli() -> None:
    """Larvis — personal AI productivity assistant."""


@cli.command()
@click.argument("query")
def ask(query: str) -> None:
    """Ask a question using your vault as context."""
    if get_status()["index_docs"] == 0:
        click.echo("Vault not indexed — run `larvis reindex` first.")
        return
    click.echo(rag.ask(query))


@cli.command()
@click.argument("query")
@click.option("--top-k", default=5, show_default=True, help="Number of chunks to return")
def search(query: str, top_k: int) -> None:
    """Semantic search over your vault. Returns raw matching chunks."""
    chunks = rag.search(query, top_k)
    for i, chunk in enumerate(chunks, 1):
        click.echo(f"\n--- Result {i} ---")
        click.echo(chunk)


@cli.command()
def reindex() -> None:
    """Re-index the vault into ChromaDB."""
    click.echo("Indexing vault...")
    count = index_vault()
    click.echo(f"Done — {count} chunks indexed.")


@cli.command()
def status() -> None:
    """Health check — Ollama, ChromaDB, index state."""
    click.echo(json.dumps(get_status(), indent=2))
