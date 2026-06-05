from fastmcp import FastMCP

from larvis import rag
from larvis.agents.lifeos import tools as lifeos_tools
from larvis.health import get_status

mcp = FastMCP("Larvis")


@mcp.tool()
def larvis_ask(query: str) -> str:
    """Ask a question answered using your LifeOS vault as context."""
    if get_status()["index_docs"] == 0:
        return "Vault not indexed — run `larvis reindex` first."
    return rag.ask(query)


@mcp.tool()
def larvis_search(query: str, top_k: int = 5) -> list[str]:
    """Semantic search over your LifeOS vault. Returns raw matching chunks."""
    return rag.search(query, top_k)


@mcp.tool()
def larvis_status() -> dict:
    """Health check — Ollama status, ChromaDB doc count, model config."""
    return get_status()


@mcp.tool()
def lifeos_briefing(session_id: str) -> str:
    """Morning kickoff — active projects, overdue tasks, open commitments from vault."""
    return lifeos_tools.briefing(session_id)


@mcp.tool()
def lifeos_ask(query: str, session_id: str) -> str:
    """Ask a question with conversation memory and vault context."""
    return lifeos_tools.ask(query, session_id)


@mcp.tool()
def lifeos_commit(text: str) -> str:
    """Store a commitment or decision that persists across sessions."""
    return lifeos_tools.commit(text)


@mcp.tool()
def lifeos_sync_tasks() -> str:
    """Scan vault for #to-linear checkbox tasks and create Linear issues via lb."""
    return lifeos_tools.sync_tasks()


def main() -> None:
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8765)
