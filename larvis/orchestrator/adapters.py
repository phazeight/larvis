import json

import ollama

from larvis import rag
from larvis.agents.gcal import tools as gcal_tools
from larvis.agents.gmail import tools as gmail_tools
from larvis.agents.lifeos import tools as lifeos_tools
from larvis.agents.skylight import tools as skylight_tools
from larvis.agents.ynab import tools as ynab_tools
from larvis.config import settings


def _read_calendar(query, session_id):
    return gcal_tools.ask(query)


def _read_ynab(query, session_id):
    return ynab_tools.ask(query)


def _read_gmail(query, session_id):
    return gmail_tools.ask(query)


def _read_vault(query, session_id):
    return rag.ask(query)


def _read_lifeos(query, session_id):
    return lifeos_tools.ask(query, session_id)


def _read_skylight(query, session_id):
    return skylight_tools.chores("week")


READ_ADAPTERS = {
    "calendar": _read_calendar,
    "ynab": _read_ynab,
    "gmail": _read_gmail,
    "vault": _read_vault,
    "lifeos": _read_lifeos,
    "skylight": _read_skylight,
}

WRITE_TOOLS = {
    "skylight_add_chore": skylight_tools.add_chore,
    "lifeos_commit": lifeos_tools.commit,
}


def gather(agents: list[str], query: str, session_id: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for agent in agents:
        adapter = READ_ADAPTERS.get(agent)
        if not adapter:
            continue
        try:
            blocks[agent] = adapter(query, session_id)
        except Exception as e:
            blocks[agent] = f"{agent} error: {e}"
    return blocks


def _extract_prompt(action: dict, query: str) -> str:
    fields = ", ".join(action["fields"])
    return (
        f"Extract a flat JSON object with EXACTLY these keys: {fields}.\n"
        "Rules: copy values EXACTLY as written in the request. Never replace a name with "
        "a pronoun like 'you' or 'me' — use the literal name. For a 'when' field use today, "
        "tomorrow, or YYYY-MM-DD. Output ONLY the JSON object, no prose.\n"
        'Example — Request: "add wash dishes to Sam tomorrow" -> '
        '{"member": "Sam", "summary": "wash dishes", "when": "tomorrow"}\n\n'
        f"Request: {query}"
    )


def extract_params(action: dict, query: str) -> dict:
    fields = ", ".join(action["fields"])
    try:
        resp = ollama.Client(host=settings.ollama_host).generate(
            model=settings.ollama_model,
            prompt=_extract_prompt(action, query),
        )
        text = resp.response
        text = text[text.find("{"): text.rfind("}") + 1]
        parsed = json.loads(text)
    except Exception as e:
        raise ValueError(f"could not extract {fields}") from e
    return {k: parsed.get(k) for k in action["fields"]}
