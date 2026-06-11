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


_NOISE_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL"}
# Gmail's IMPORTANT flag is deliberately excluded — it over-applies to shipping
# notifications and newsletters, polluting the attention bucket.
_ATTENTION_LABELS = {"STARRED", "CATEGORY_PERSONAL"}


def _classify_by_labels(message: dict) -> str:
    """Deterministic fallback bucket from Gmail's category labels."""
    labels = set(message.get("labels", []))
    if labels & _NOISE_LABELS:
        return "noise"
    if labels & _ATTENTION_LABELS:
        return "attention"
    return "fyi"


def _classify(message: dict) -> str:
    """Bucket a message via the LLM; falls back to label heuristics if it can't decide."""
    # Obvious marketing/social is noise — skip the LLM call entirely.
    if set(message.get("labels", [])) & _NOISE_LABELS:
        return "noise"
    try:
        resp = ollama.Client(host=settings.ollama_host).generate(
            model=settings.ollama_model,
            prompt=(
                "Classify this email into exactly one word.\n"
                "ATTENTION = the reader must personally do something soon (reply, pay, "
                "register, pick up, confirm, schedule, RSVP).\n"
                "FYI = informational only, no action (receipts, shipping updates, "
                "reports, calendar notices, account summaries).\n"
                "NOISE = marketing, promotions, newsletters, digests.\n"
                "Answer with ONLY one word: ATTENTION, FYI, or NOISE.\n\n"
                f"From: {message['from_name']}\nSubject: {message['subject']}\n"
                f"{message.get('snippet', '')[:200]}"
            ),
        )
        verdict = resp.response.strip().upper()
        for bucket in ("attention", "noise", "fyi"):
            if bucket.upper() in verdict:
                return bucket
        return _classify_by_labels(message)
    except Exception:
        return _classify_by_labels(message)


def _gist(message: dict) -> str:
    """One-line LLM gist of what the email needs; falls back to the cleaned snippet."""
    try:
        resp = ollama.Client(host=settings.ollama_host).generate(
            model=settings.ollama_model,
            prompt=(
                "In ONE short sentence, say what this email needs from the reader. "
                "No preamble, no quotes.\n\n"
                f"From: {message['from_name']}\nSubject: {message['subject']}\n"
                f"{message['body'][:400]}"
            ),
        )
        return resp.response.strip().splitlines()[0].strip()
    except Exception:
        return message.get("snippet", "")[:140]


def triage(within: str = "") -> str:
    query = _triage_query(within or None)
    try:
        messages, errors = client.collect(query)
    except Exception as e:
        return f"Gmail error: {e}"
    note = _note(errors)
    if not messages:
        return "No unread mail in the triage window." + note

    buckets: dict[str, list[dict]] = {"attention": [], "fyi": [], "noise": []}
    for m in messages:
        buckets[_classify(m)].append(m)

    lines = [f"=== Inbox triage ({len(messages)} unread) ==="]
    lines.append(f"\nNEEDS ATTENTION ({len(buckets['attention'])}):")
    if buckets["attention"]:
        for m in buckets["attention"]:
            lines.append(f"  [{m['account']}] {m['from_name']} — {m['subject']}")
            lines.append(f"     {_gist(m)}")
    else:
        lines.append("  (nothing urgent)")

    if buckets["fyi"]:
        lines.append(f"\nFYI ({len(buckets['fyi'])}):")
        for m in buckets["fyi"]:
            lines.append(f"  [{m['account']}] {m['from_name']} — {m['subject']}")

    if buckets["noise"]:
        lines.append(
            f"\nNOISE: {len(buckets['noise'])} promotional/social emails (hidden)."
        )

    return "\n".join(lines) + note


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


def search(query: str) -> str:
    try:
        messages, errors = client.collect(query)
    except Exception as e:
        return f"Gmail error: {e}"
    note = _note(errors)
    if not messages:
        return f"No messages matching: {query}" + note
    return f"=== Matches for: {query} ===" + _format_raw(messages) + note


def ask(query: str) -> str:
    # Scan recent mail (read or unread, last 7 days) so the model can answer about threads.
    try:
        messages, errors = client.collect("newer_than:7d")
    except Exception as e:
        return f"Gmail error: {e}"
    context = _build_context(messages) if messages else "No recent mail."
    try:
        resp = ollama.Client(host=settings.ollama_host).generate(
            model=settings.ollama_model,
            prompt=(
                "You are an email assistant. Answer the question in 1-3 sentences using "
                "ONLY the emails below. Name the sender/subject you relied on. If the "
                "emails do not contain the answer, reply exactly: 'I don't see anything "
                "about that in your recent mail.' Do not list unrelated emails.\n\n"
                f"Emails:\n{context}\n\nQuestion: {query}"
            ),
        )
        return resp.response.strip() + _note(errors)
    except Exception:
        return context + _note(errors)
