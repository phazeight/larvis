from datetime import date

import ollama

from larvis.agents.lifeos import memory, linear_sync
from larvis.config import settings
from larvis.rag import search as vault_search


def briefing(session_id: str) -> str:
    today = date.today().isoformat()

    project_chunks = vault_search("active projects status", top_k=5)
    task_chunks = vault_search("overdue tasks this week", top_k=5)
    commitments = memory.get_open_commitments()

    if not project_chunks and not task_chunks and not commitments:
        return "Vault not indexed — run `larvis reindex` first."

    context_parts = []
    if project_chunks:
        context_parts.append("Active project context:\n" + "\n---\n".join(project_chunks))
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
