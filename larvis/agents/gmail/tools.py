import ollama

from larvis.agents.gmail import client
from larvis.config import settings

_WITHIN_MAP = {"today": "1d", "week": "7d"}


def _triage_query(within: str | None) -> str:
    if not within:
        return settings.gmail_triage_query
    token = _WITHIN_MAP.get(within, within)  # accepts "today"/"week" or a raw "2d"
    return f"is:unread newer_than:{token}"


def _format_raw(messages: list[dict]) -> str:
    by_account: dict[str, list[dict]] = {}
    for m in messages:
        by_account.setdefault(m["account"], []).append(m)
    lines: list[str] = []
    for account, msgs in by_account.items():
        lines.append(f"\n[{account}] ({len(msgs)} messages)")
        for m in msgs:
            lines.append(f"  - {m['from_name']} — {m['subject']}")
            if m["snippet"]:
                lines.append(f"    {m['snippet'][:120]}")
    return "\n".join(lines)


def _build_context(messages: list[dict]) -> str:
    blocks = []
    for m in messages:
        blocks.append(
            f"[{m['account']}] From: {m['from_name']} <{m['from_addr']}> | "
            f"Subject: {m['subject']}\n{m['body'][:500]}"
        )
    return "\n\n".join(blocks)


def _note(errors: list[str]) -> str:
    return "\n\n(Note: " + "; ".join(errors) + ")" if errors else ""


def triage(within: str = "") -> str:
    query = _triage_query(within or None)
    try:
        messages, errors = client.collect(query)
    except Exception as e:
        return f"Gmail error: {e}"
    note = _note(errors)
    if not messages:
        return "No unread mail in the triage window." + note
    prompt = (
        "You are an email triage assistant. Below are unread emails across the user's "
        "accounts. Produce a concise prioritized digest:\n"
        "1. Lead with messages from real people or that look important/actionable.\n"
        "2. For each, give one line: sender — subject — one-sentence gist, and an "
        "'ACTION:' line if a reply or task is needed.\n"
        "3. Collapse newsletters/promotions/automated mail into a single aggregate "
        "line at the end (e.g. '+12 promotional/newsletter emails').\n"
        "Use ONLY the emails below; do not invent anything.\n\n"
        f"Emails:\n{_build_context(messages)}"
    )
    try:
        resp = ollama.Client(host=settings.ollama_host).generate(
            model=settings.ollama_model, prompt=prompt
        )
        return resp.response.strip() + note
    except Exception:
        return _format_raw(messages) + note


def status() -> str:
    lines = ["Gmail status:"]
    for account in client._accounts():
        try:
            count = client.unread_count(account)
            lines.append(f"  ✓ {account} — authorized ({count} unread)")
        except Exception:
            lines.append(
                f"  ✗ {account} — not authorized (run `larvis gmail-auth {account}`)"
            )
    return "\n".join(lines)
