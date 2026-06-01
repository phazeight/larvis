from fastmcp import FastMCP

from larvis import rag
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


def main() -> None:
    mcp.run(transport="sse", host="0.0.0.0", port=8765)
