import re

AGENT_KEYWORDS = {
    "calendar": ["calendar", "schedule", "meeting", "agenda", "free", "busy",
                 "appointment", "when am i", "my week", "my day", "time"],
    "ynab": ["budget", "spend", "afford", "money", "cost", "bill", "paycheck",
             "category", "dollars", "$"],
    "gmail": ["email", "inbox", "mail", "message", "unread", "reply"],
    "skylight": ["chore", "chores", "up for grabs", "kids"],
    "lifeos": ["task", "project", "todo", "commitment", "overdue", "remind", "remember"],
    "vault": ["note", "notes", "journal", "vault", "wrote", "document"],
}

WRITE_VERBS = ["add", "create", "schedule", "mark", "complete", "assign", "remind", "remember"]


def route(query: str) -> list[str]:
    q = query.lower()
    hits = [agent for agent, kws in AGENT_KEYWORDS.items() if any(k in q for k in kws)]
    return hits or ["lifeos"]


def is_write_intent(query: str) -> bool:
    q = query.lower()
    return any(re.search(rf"\b{re.escape(v)}\b", q) for v in WRITE_VERBS)


def detect_action(query: str) -> dict | None:
    q = query.lower()
    if "chore" in q:
        return {"tool": "skylight_add_chore", "fields": ["member", "summary", "when"]}
    if any(k in q for k in ["remind", "remember", "commit", "note that"]):
        return {"tool": "lifeos_commit", "fields": ["text"]}
    return None
