from fastmcp import FastMCP

from larvis import rag
from larvis.agents.gcal import tools as gcal_tools
from larvis.agents.gmail import tools as gmail_tools
from larvis.agents.lifeos import tools as lifeos_tools
from larvis.agents.skylight import tools as skylight_tools
from larvis.agents.ynab import tools as ynab_tools
from larvis.health import get_status
from larvis.orchestrator import tools as orchestrator_tools

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


@mcp.tool()
def ynab_sync() -> str:
    """Refresh local YNAB cache from the YNAB API (delta sync)."""
    return ynab_tools.sync()


@mcp.tool()
def ynab_status() -> str:
    """Budget dashboard — ready to assign, age of money, account total, over-budget categories."""
    return ynab_tools.status()


@mcp.tool()
def ynab_ask(query: str) -> str:
    """Ask a natural language question about your YNAB budget. Run ynab_sync first."""
    return ynab_tools.ask(query)


@mcp.tool()
def ynab_upcoming() -> str:
    """List scheduled transactions due in the next 14 days."""
    return ynab_tools.upcoming()


@mcp.tool()
def calendar_agenda(range: str = "today") -> str:
    """Your calendar agenda. range="today" (full day) or "week" (next 7 days)."""
    return gcal_tools.agenda(range)


@mcp.tool()
def calendar_find_time(duration_minutes: int, within: str = "week") -> str:
    """Find open slots >= duration_minutes within working hours. within="today" or "week"."""
    return gcal_tools.find_time(duration_minutes, within)


@mcp.tool()
def calendar_ask(query: str) -> str:
    """Ask a natural-language question about your calendar (next 7 days)."""
    return gcal_tools.ask(query)


@mcp.tool()
def calendar_status() -> str:
    """Calendar auth/health check — confirms authorization and lists configured calendars."""
    return gcal_tools.status()


@mcp.tool()
def gmail_triage(within: str = "") -> str:
    """Prioritized digest of unread mail across all accounts. within="" (default 48h), "today", "week", or a Gmail newer_than token like "3d"."""
    return gmail_tools.triage(within)


@mcp.tool()
def gmail_search(query: str) -> str:
    """Search mail across all accounts. Supports Gmail operators (from:, subject:, newer_than:)."""
    return gmail_tools.search(query)


@mcp.tool()
def gmail_ask(query: str) -> str:
    """Ask a natural-language question about your recent email (last 7 days)."""
    return gmail_tools.ask(query)


@mcp.tool()
def gmail_status() -> str:
    """Gmail auth/health check — per-account authorization and unread counts."""
    return gmail_tools.status()


@mcp.tool()
def skylight_chores(within: str = "today") -> str:
    """List Skylight chores grouped by family member (+ Up for Grabs). within="today" or "week"."""
    return skylight_tools.chores(within)


@mcp.tool()
def skylight_add_chore(member: str, summary: str, when: str = "today") -> str:
    """Add/assign a chore. member = a family member name or "up-for-grabs". when=today/tomorrow/YYYY-MM-DD."""
    return skylight_tools.add_chore(member, summary, when)


@mcp.tool()
def skylight_complete_chore(chore_id: str) -> str:
    """Mark a Skylight chore complete by its id (from skylight_chores)."""
    return skylight_tools.complete_chore(chore_id)


@mcp.tool()
def skylight_status() -> str:
    """Skylight auth/health check — confirms sign-in and lists frame + members."""
    return skylight_tools.status()


@mcp.tool()
def larvis_orchestrate(query: str) -> str:
    """Larvis front door — routes your request across all agents and answers, or proposes a write to confirm."""
    return orchestrator_tools.orchestrate(query)


@mcp.tool()
def larvis_confirm(token: str) -> str:
    """Execute a write action that larvis_orchestrate proposed (pass the token it returned)."""
    return orchestrator_tools.confirm(token)


def main() -> None:
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8765)
