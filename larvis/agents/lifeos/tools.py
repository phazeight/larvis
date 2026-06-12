import re
from datetime import date
from pathlib import Path

import ollama

from larvis.agents.lifeos import memory, linear_sync
from larvis.config import settings
from larvis.rag import search as vault_search

_UNCHECKED_TASK = re.compile(r"^- \[ \] (.+)$", re.MULTILINE)
_DUE_DATE = re.compile(r"📅\s*(\d{4}-\d{2}-\d{2})")


def find_overdue_tasks(vault_path, today: str) -> list[dict]:
    """Unchecked tasks with a 📅 due date strictly before `today` (ISO string)."""
    overdue: list[dict] = []
    for md_file in Path(vault_path).rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in _UNCHECKED_TASK.finditer(content):
            line = match.group(1).strip()
            due = _DUE_DATE.search(line)
            if due and due.group(1) < today:
                overdue.append({"text": line, "due": due.group(1)})
    overdue.sort(key=lambda o: o["due"], reverse=True)  # most recently due first
    return overdue


def briefing(session_id: str) -> str:
    today = date.today().isoformat()

    project_chunks = vault_search("active projects status", top_k=5)
    task_chunks = vault_search("overdue tasks this week", top_k=5)
    overdue = find_overdue_tasks(settings.vault_path, today)
    commitments = memory.get_open_commitments()

    if not project_chunks and not task_chunks and not commitments and not overdue:
        return "Vault not indexed — run `larvis reindex` first."

    context_parts = []
    if project_chunks:
        context_parts.append("Active project context:\n" + "\n---\n".join(project_chunks))
    if overdue:
        shown = overdue[:10]  # most recently due first
        overdue_lines = "\n".join(f"- {o['text']} (due {o['due']})" for o in shown)
        more = f"\n(+{len(overdue) - len(shown)} more overdue)" if len(overdue) > len(shown) else ""
        context_parts.append(
            f"OVERDUE tasks (unchecked, past due as of {today}; most recent first) — "
            f"list these explicitly:\n" + overdue_lines + more
        )
    if task_chunks:
        context_parts.append("Task context:\n" + "\n---\n".join(task_chunks))
    if commitments:
        commitment_lines = "\n".join(
            f"- {c['text']} (since {c['created_at'][:10]})" for c in commitments
        )
        context_parts.append(f"Open commitments:\n{commitment_lines}")

    prompt = (
        f"You are Larvis, a personal assistant. Today is {today}.\n"
        "Give a concise morning briefing using the context below. "
        "List active projects, surface anything overdue or needing attention, "
        "and remind the user of open commitments. Be brief and actionable.\n\n"
        + "\n\n".join(context_parts)
    )

    resp = ollama.Client(host=settings.ollama_host).generate(
        model=settings.ollama_model, prompt=prompt
    )
    response_text = resp.response
    memory.add_turn(session_id, "assistant", response_text)
    return response_text


def ask(query: str, session_id: str) -> str:
    memory.add_turn(session_id, "user", query)

    history = memory.get_session_context(session_id, last_n=10)
    chunks = vault_search(query, top_k=5)
    context = "\n\n---\n\n".join(chunks)

    history_lines = "\n".join(
        f"{t['role'].capitalize()}: {t['content']}" for t in history[:-1]
    )

    prompt_parts = ["You are Larvis, a personal assistant with memory of this conversation.\n"]
    if history_lines:
        prompt_parts.append(f"Conversation so far:\n{history_lines}\n")
    if context:
        prompt_parts.append(f"Vault context:\n{context}\n")
    prompt_parts.append(f"User: {query}")

    resp = ollama.Client(host=settings.ollama_host).generate(
        model=settings.ollama_model, prompt="\n".join(prompt_parts)
    )
    response_text = resp.response
    memory.add_turn(session_id, "assistant", response_text)
    return response_text


def commit(text: str) -> str:
    memory.add_commitment(text)
    return f"Committed: {text}"


def sync_tasks() -> str:
    try:
        count = linear_sync.sync_tasks()
        if count == 0:
            return "No tasks pending sync."
        return f"{count} task(s) synced to Linear."
    except RuntimeError as e:
        return str(e)
