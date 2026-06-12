import json
import os

import click
from google_auth_oauthlib.flow import InstalledAppFlow

from larvis import rag
from larvis.config import settings
from larvis.health import get_status
from larvis.indexer import index_vault

GCAL_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


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


@cli.command(name="gcal-auth")
def gcal_auth() -> None:
    """One-time Google Calendar OAuth — opens a browser for read-only consent."""
    os.makedirs(os.path.dirname(settings.gcal_token_path) or ".", exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(
        settings.gcal_credentials_path, GCAL_SCOPES
    )
    creds = flow.run_local_server(port=0)
    with open(settings.gcal_token_path, "w") as f:
        f.write(creds.to_json())
    click.echo(f"Authorized. Token saved to {settings.gcal_token_path}")


@cli.command(name="gmail-auth")
@click.argument("account")
def gmail_auth(account: str) -> None:
    """One-time Gmail OAuth for ACCOUNT (email) — opens a browser for read-only consent."""
    from larvis.agents.gmail import auth as gmail_auth_mod

    os.makedirs(settings.gmail_token_dir, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(
        settings.gmail_credentials_path, GMAIL_SCOPES
    )
    creds = flow.run_local_server(port=0)
    path = gmail_auth_mod.token_path(account)
    with open(path, "w") as f:
        f.write(creds.to_json())
    click.echo(f"Authorized {account}. Token saved to {path}")


@cli.command()
@click.argument("query")
def orchestrate(query: str) -> None:
    """Ask Larvis anything — routes across all agents and answers."""
    from larvis.orchestrator import tools as orchestrator_tools

    click.echo(orchestrator_tools.orchestrate(query))
