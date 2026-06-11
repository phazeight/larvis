# Gmail Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only Gmail agent for Larvis that gives a prioritized triage digest, search, and NL Q&A over multiple inboxes via four MCP tools.

**Architecture:** Mirrors the Calendar (`gcal`) agent exactly — a package under `larvis/agents/gmail/` with `auth.py` (multi-account OAuth, one token per inbox), `client.py` (Gmail API wrapper: list/fetch/parse, cross-account merge), and `tools.py` (triage/search/ask/status). Python does all fetch/parse logic; Ollama only prioritizes and narrates. Live-fetch, no cache. Tools registered in `server.py`, OAuth driven by a `gmail-auth <account>` CLI command.

**Tech Stack:** Python 3.12, `google-api-python-client` / `google-auth` / `google-auth-oauthlib` (already present from Calendar), `ollama`, FastMCP, Click, pytest.

**Spec:** `docs/superpowers/specs/2026-06-11-larvis-gmail-agent-design.md`

---

## File structure

| File | Responsibility |
|------|----------------|
| `larvis/agents/gmail/__init__.py` | Package marker |
| `larvis/agents/gmail/auth.py` | Per-account OAuth: token path slug, load/refresh creds, build service |
| `larvis/agents/gmail/client.py` | Gmail API wrapper: MIME parse, header extract, HTML strip, fetch + cross-account collect, unread counts |
| `larvis/agents/gmail/tools.py` | The 4 tool functions: `triage`, `search`, `ask`, `status` |
| `larvis/config.py` | Add `gmail_*` settings fields |
| `larvis/server.py` | Register 4 `@mcp.tool()` wrappers |
| `larvis/cli.py` | Add `gmail-auth <account>` command |
| `docker-compose.yml` | `GMAIL_*` env + `./.gmail` bind mount |
| `tests/test_gmail_auth.py` | Unit: slug + token path |
| `tests/test_gmail_client.py` | Unit: HTML strip, body extract, header, parse_message |
| `tests/test_gmail_tools.py` | Unit: triage/search/ask/status with monkeypatched client |

---

## Task 1: Scaffold package + config + env

**Files:**
- Create: `larvis/agents/gmail/__init__.py`
- Modify: `larvis/config.py`
- Modify: `.env.example`
- Modify: `.gitignore`

- [ ] **Step 1: Create the package marker**

```bash
mkdir -p larvis/agents/gmail
touch larvis/agents/gmail/__init__.py
```

- [ ] **Step 2: Add config fields**

In `larvis/config.py`, add these fields to `Settings` after the `gcal_*` block:

```python
    gmail_accounts: str = "primary"
    gmail_credentials_path: str = ".gmail/credentials.json"
    gmail_token_dir: str = ".gmail"
    gmail_triage_query: str = "is:unread newer_than:2d"
    gmail_max_messages: int = 40
    gmail_body_chars: int = 2000
```

- [ ] **Step 3: Add `.env.example` block**

Append to `.env.example`:

```bash
# Gmail (Phase 5) — read-only. Reuses the same Google OAuth client as Calendar.
# Enable the Gmail API in the same GCP project, copy the client secret to
# .gmail/credentials.json, then run: uv run larvis gmail-auth <account-email>
GMAIL_ACCOUNTS=primary
GMAIL_CREDENTIALS_PATH=.gmail/credentials.json
GMAIL_TOKEN_DIR=.gmail
GMAIL_TRIAGE_QUERY=is:unread newer_than:2d
GMAIL_MAX_MESSAGES=40
GMAIL_BODY_CHARS=2000
```

- [ ] **Step 4: Gitignore the secrets dir**

Add to `.gitignore` (if not already present):

```
.gmail/
```

- [ ] **Step 5: Verify config loads**

Run: `uv run python -c "from larvis.config import settings; print(settings.gmail_accounts, settings.gmail_max_messages)"`
Expected: `primary 40`

- [ ] **Step 6: Commit**

```bash
git add larvis/agents/gmail/__init__.py larvis/config.py .env.example .gitignore
git commit -m "chore: scaffold gmail agent package + config"
```

---

## Task 2: `auth.py` — per-account OAuth

**Files:**
- Create: `larvis/agents/gmail/auth.py`
- Test: `tests/test_gmail_auth.py`

The pure-logic parts (`_slug`, `token_path`) are unit-tested. `get_credentials`/`get_service` do live token I/O — import/smoke checked here, exercised end-to-end in Task 7.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gmail_auth.py`:

```python
from larvis.agents.gmail import auth


def test_slug_sanitizes_email():
    assert auth._slug("coltsnramzfan88@gmail.com") == "coltsnramzfan88_gmail_com"


def test_slug_collapses_non_alnum():
    assert auth._slug("a.b+c@x.co") == "a_b_c_x_co"


def test_token_path_uses_dir_and_slug(monkeypatch):
    monkeypatch.setattr(auth.settings, "gmail_token_dir", ".gmail")
    assert auth.token_path("luke@gmail.com") == ".gmail/token-luke_gmail_com.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_gmail_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: larvis.agents.gmail.auth`

- [ ] **Step 3: Implement `auth.py`**

Create `larvis/agents/gmail/auth.py`:

```python
import os
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from larvis.config import settings

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _slug(account: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", account.strip()).strip("_")


def token_path(account: str) -> str:
    return os.path.join(settings.gmail_token_dir, f"token-{_slug(account)}.json")


def get_credentials(account: str) -> Credentials:
    path = token_path(account)
    if not os.path.exists(path):
        raise RuntimeError(
            f"Gmail not authorized for {account} — run `larvis gmail-auth {account}`."
        )
    creds = Credentials.from_authorized_user_file(path, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(path, "w") as f:
                f.write(creds.to_json())
        else:
            raise RuntimeError(
                f"Gmail token invalid for {account} — run `larvis gmail-auth {account}`."
            )
    return creds


def get_service(account: str):
    return build("gmail", "v1", credentials=get_credentials(account), cache_discovery=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_gmail_auth.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Import smoke check**

Run: `uv run python -c "from larvis.agents.gmail import auth; print('ok', auth.SCOPES)"`
Expected: `ok ['https://www.googleapis.com/auth/gmail.readonly']`

- [ ] **Step 6: Commit**

```bash
git add larvis/agents/gmail/auth.py tests/test_gmail_auth.py
git commit -m "feat: gmail per-account oauth credentials + service builder (TDD)"
```

---

## Task 3: `client.py` — Gmail API wrapper + message parsing

**Files:**
- Create: `larvis/agents/gmail/client.py`
- Test: `tests/test_gmail_client.py`

Pure parsing logic (`_strip_html`, `_decode`, `_header`, `_extract_body`, `parse_message`, `_accounts`) is TDD'd. The live network functions (`fetch_messages`, `collect`, `unread_count`) are import/smoke checked, exercised in Task 7.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gmail_client.py`:

```python
import base64

from larvis.agents.gmail import client


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("utf-8")


def _msg(plain=None, html=None, frm="Bob Jones <bob@x.com>", subject="Hello", snippet="snip"):
    parts = []
    if plain is not None:
        parts.append({"mimeType": "text/plain", "body": {"data": _b64(plain)}})
    if html is not None:
        parts.append({"mimeType": "text/html", "body": {"data": _b64(html)}})
    return {
        "id": "m1",
        "snippet": snippet,
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": frm},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Wed, 11 Jun 2026 09:00:00 -0400"},
            ],
            "parts": parts,
        },
    }


def test_strip_html_removes_tags_and_scripts():
    html = "<style>p{color:red}</style><p>Hello <b>world</b></p><script>x()</script>"
    assert client._strip_html(html) == "Hello world"


def test_header_is_case_insensitive():
    headers = [{"name": "From", "value": "a@b.com"}]
    assert client._header(headers, "from") == "a@b.com"
    assert client._header(headers, "Subject") == ""


def test_extract_body_prefers_plain_text():
    payload = _msg(plain="plain body", html="<p>html body</p>")["payload"]
    assert client._extract_body(payload) == "plain body"


def test_extract_body_falls_back_to_stripped_html():
    payload = _msg(plain=None, html="<p>html <b>only</b></p>")["payload"]
    assert client._extract_body(payload) == "html only"


def test_parse_message_normalizes_fields():
    parsed = client.parse_message(_msg(plain="hi there"), "luke@gmail.com", body_chars=1000)
    assert parsed["account"] == "luke@gmail.com"
    assert parsed["from_name"] == "Bob Jones"
    assert parsed["from_addr"] == "bob@x.com"
    assert parsed["subject"] == "Hello"
    assert parsed["body"] == "hi there"


def test_parse_message_truncates_body():
    parsed = client.parse_message(_msg(plain="x" * 100), "luke@gmail.com", body_chars=10)
    assert parsed["body"] == "x" * 10


def test_accounts_splits_and_trims(monkeypatch):
    monkeypatch.setattr(client.settings, "gmail_accounts", "a@x.com, b@y.com ,")
    assert client._accounts() == ["a@x.com", "b@y.com"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gmail_client.py -v`
Expected: FAIL with `ModuleNotFoundError: larvis.agents.gmail.client`

- [ ] **Step 3: Implement `client.py`**

Create `larvis/agents/gmail/client.py`:

```python
import base64
import re
from email.utils import parseaddr

from larvis.agents.gmail import auth
from larvis.config import settings


def _accounts() -> list[str]:
    return [a.strip() for a in settings.gmail_accounts.split(",") if a.strip()]


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _find_part(payload: dict, mime: str) -> str:
    if payload.get("mimeType") == mime:
        data = payload.get("body", {}).get("data")
        if data:
            return _decode(data)
    for part in payload.get("parts", []) or []:
        found = _find_part(part, mime)
        if found:
            return found
    return ""


def _extract_body(payload: dict) -> str:
    plain = _find_part(payload, "text/plain")
    if plain:
        return plain
    html = _find_part(payload, "text/html")
    if html:
        return _strip_html(html)
    return ""


def parse_message(msg: dict, account: str, body_chars: int) -> dict:
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    name, addr = parseaddr(_header(headers, "From"))
    return {
        "id": msg.get("id"),
        "account": account,
        "from_name": name or addr,
        "from_addr": addr,
        "subject": _header(headers, "Subject") or "(no subject)",
        "date": _header(headers, "Date"),
        "snippet": msg.get("snippet", ""),
        "body": _extract_body(payload)[:body_chars],
    }


def fetch_messages(account: str, query: str, max_results: int, body_chars: int) -> list[dict]:
    service = auth.get_service(account)
    listed = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    out: list[dict] = []
    for ref in listed.get("messages", []):
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=ref["id"], format="full")
            .execute()
        )
        out.append(parse_message(msg, account, body_chars))
    return out


def collect(query: str) -> tuple[list[dict], list[str]]:
    """Fetch parsed messages across all accounts. Returns (messages, per_account_errors)."""
    messages: list[dict] = []
    errors: list[str] = []
    for account in _accounts():
        try:
            messages.extend(
                fetch_messages(
                    account, query, settings.gmail_max_messages, settings.gmail_body_chars
                )
            )
        except Exception as e:
            errors.append(f"{account}: {e}")
    return messages, errors


def unread_count(account: str) -> int:
    service = auth.get_service(account)
    resp = service.users().labels().get(userId="me", id="UNREAD").execute()
    return resp.get("messagesUnread", 0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_gmail_client.py -v`
Expected: 7 PASSED

- [ ] **Step 5: Import smoke check**

Run: `uv run python -c "from larvis.agents.gmail import client; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add larvis/agents/gmail/client.py tests/test_gmail_client.py
git commit -m "feat: gmail api client — parse, fetch, cross-account collect (TDD)"
```

---

## Task 4: `tools.py` — triage + status

**Files:**
- Create: `larvis/agents/gmail/tools.py`
- Test: `tests/test_gmail_tools.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gmail_tools.py`:

```python
from larvis.agents.gmail import client, tools


def _m(account="luke@gmail.com", name="Bob", subject="Invoice", snippet="please pay", body="please pay"):
    return {
        "id": "1",
        "account": account,
        "from_name": name,
        "from_addr": "bob@x.com",
        "subject": subject,
        "date": "Wed, 11 Jun 2026",
        "snippet": snippet,
        "body": body,
    }


def test_triage_query_defaults_to_setting(monkeypatch):
    monkeypatch.setattr(tools.settings, "gmail_triage_query", "is:unread newer_than:2d")
    assert tools._triage_query(None) == "is:unread newer_than:2d"


def test_triage_query_maps_within():
    assert tools._triage_query("today") == "is:unread newer_than:1d"
    assert tools._triage_query("week") == "is:unread newer_than:7d"
    assert tools._triage_query("3d") == "is:unread newer_than:3d"


def test_triage_empty(monkeypatch):
    monkeypatch.setattr(client, "collect", lambda q: ([], []))
    assert "No unread mail" in tools.triage()


def test_triage_degrades_when_ollama_down(monkeypatch):
    monkeypatch.setattr(client, "collect", lambda q: ([_m(subject="Invoice")], []))

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("ollama down")

    monkeypatch.setattr(tools.ollama, "Client", Boom)
    out = tools.triage()
    assert "Invoice" in out


def test_triage_surfaces_account_errors(monkeypatch):
    monkeypatch.setattr(client, "collect", lambda q: ([], ["work@x.com: bad token"]))
    out = tools.triage()
    assert "work@x.com" in out


def test_status_lists_accounts(monkeypatch):
    monkeypatch.setattr(client, "_accounts", lambda: ["a@x.com", "b@y.com"])
    monkeypatch.setattr(client, "unread_count", lambda acct: 5)
    out = tools.status()
    assert "a@x.com" in out and "b@y.com" in out
    assert "5 unread" in out


def test_status_reports_unauthorized(monkeypatch):
    monkeypatch.setattr(client, "_accounts", lambda: ["a@x.com"])

    def boom(acct):
        raise RuntimeError("no token")

    monkeypatch.setattr(client, "unread_count", boom)
    out = tools.status()
    assert "gmail-auth" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gmail_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: larvis.agents.gmail.tools`

- [ ] **Step 3: Implement `tools.py` (triage + status + shared helpers)**

Create `larvis/agents/gmail/tools.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_gmail_tools.py -v`
Expected: 7 PASSED (triage + status + query tests)

- [ ] **Step 5: Commit**

```bash
git add larvis/agents/gmail/tools.py tests/test_gmail_tools.py
git commit -m "feat: gmail_triage + gmail_status tools (TDD)"
```

---

## Task 5: `tools.py` — search + ask

**Files:**
- Modify: `larvis/agents/gmail/tools.py`
- Modify: `tests/test_gmail_tools.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_gmail_tools.py`:

```python
def test_search_empty(monkeypatch):
    monkeypatch.setattr(client, "collect", lambda q: ([], []))
    out = tools.search("from:bob")
    assert "No messages matching" in out


def test_search_lists_matches(monkeypatch):
    monkeypatch.setattr(client, "collect", lambda q: ([_m(subject="Quote")], []))
    out = tools.search("from:bob")
    assert "Quote" in out


def test_ask_degrades_when_ollama_down(monkeypatch):
    monkeypatch.setattr(client, "collect", lambda q: ([_m(subject="Trip plans")], []))

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("ollama down")

    monkeypatch.setattr(tools.ollama, "Client", Boom)
    out = tools.ask("what are the trip plans?")
    assert "Trip plans" in out
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_gmail_tools.py -k "search or ask" -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'search'`

- [ ] **Step 3: Implement `search` + `ask`**

Append to `larvis/agents/gmail/tools.py`:

```python
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
                "You are an email assistant. Answer the question using ONLY the emails "
                "below. If the answer is not present, say so.\n\n"
                f"Emails:\n{context}\n\nQuestion: {query}"
            ),
        )
        return resp.response.strip() + _note(errors)
    except Exception:
        return context + _note(errors)
```

- [ ] **Step 4: Run the full tools test file**

Run: `uv run pytest tests/test_gmail_tools.py -v`
Expected: 10 PASSED

- [ ] **Step 5: Commit**

```bash
git add larvis/agents/gmail/tools.py tests/test_gmail_tools.py
git commit -m "feat: gmail_search + gmail_ask tools (TDD)"
```

---

## Task 6: Register MCP tools + gmail-auth CLI + docker config

**Files:**
- Modify: `larvis/server.py`
- Modify: `larvis/cli.py`
- Modify: `docker-compose.yml`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Import the tools module in `server.py`**

In `larvis/server.py`, add alongside the other agent imports (near `from larvis.agents.gcal import tools as gcal_tools`):

```python
from larvis.agents.gmail import tools as gmail_tools
```

- [ ] **Step 2: Register the 4 tool wrappers**

In `larvis/server.py`, after the `calendar_status` tool, add:

```python
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
```

- [ ] **Step 3: Verify the tools register**

Run:
```bash
uv run python -c "from larvis.server import mcp; print([t.name for t in mcp._tool_manager.list_tools()])"
```
Expected: list includes `gmail_triage`, `gmail_search`, `gmail_ask`, `gmail_status` (plus all prior tools).

- [ ] **Step 4: Add the `gmail-auth` CLI command**

In `larvis/cli.py`, add a scopes constant near `GCAL_SCOPES`:

```python
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
```

And add this command after `gcal_auth`:

```python
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
```

- [ ] **Step 5: Verify the CLI command exists**

Run: `uv run larvis gmail-auth --help`
Expected: usage text showing `ACCOUNT` argument.

- [ ] **Step 6: Wire docker-compose**

In `docker-compose.yml`, under the `larvis` service `environment:` block (next to the `GCAL_*` entries), add:

```yaml
      GMAIL_ACCOUNTS: ${GMAIL_ACCOUNTS:-primary}
      GMAIL_CREDENTIALS_PATH: ${GMAIL_CREDENTIALS_PATH:-.gmail/credentials.json}
      GMAIL_TOKEN_DIR: ${GMAIL_TOKEN_DIR:-.gmail}
      GMAIL_TRIAGE_QUERY: ${GMAIL_TRIAGE_QUERY:-is:unread newer_than:2d}
      GMAIL_MAX_MESSAGES: ${GMAIL_MAX_MESSAGES:-40}
      GMAIL_BODY_CHARS: ${GMAIL_BODY_CHARS:-2000}
```

And under the `larvis` service `volumes:` block (next to `./.gcal:/app/.gcal`), add:

```yaml
      - ./.gmail:/app/.gmail
```

- [ ] **Step 7: Update `CLAUDE.md`**

In the MCP tools table heading, change `(Phase 1 + 2 + 3 + 4)` to `(Phase 1 + 2 + 3 + 4 + 5)` and add four rows:

```
| `gmail_triage` | `(within?: str) -> str` | Prioritized unread-mail digest across accounts |
| `gmail_search` | `(query: str) -> str` | Search mail (Gmail operators) across accounts |
| `gmail_ask` | `(query: str) -> str` | NL question about your recent email (7 days) |
| `gmail_status` | `() -> str` | Per-account Gmail auth check + unread counts |
```

Add a row to the "Known issues / architecture notes" table:

```
| Gmail multi-account | One OAuth token per inbox in `.gmail/token-<email>.json`; run `larvis gmail-auth <account>` per account |
```

- [ ] **Step 8: Run the full suite (no regressions)**

Run: `uv run pytest -q`
Expected: all tests pass (54 from Phase 4 + 20 new Gmail = 74), 1 pre-existing ChromaDB warning.

- [ ] **Step 9: Commit**

```bash
git add larvis/server.py larvis/cli.py docker-compose.yml CLAUDE.md
git commit -m "feat: register gmail MCP tools + gmail-auth CLI + docker config"
```

---

## Task 7: Live smoke test + Linear tracking

**Files:** No new files. Validates end-to-end against the real Gmail accounts.

- [ ] **Step 1: One-time Google setup (manual)**

1. https://console.cloud.google.com → select the existing `lifeos-agents` project.
2. APIs & Services → Library → enable **Gmail API**.
3. APIs & Services → OAuth consent screen → ensure both accounts (`coltsnramzfan88@gmail.com`, `lucasryanthompson@gmail.com`) are **Test users**.
4. Reuse the existing Desktop OAuth client — copy the secret into `.gmail/credentials.json`:
   ```bash
   mkdir -p .gmail && cp .gcal/credentials.json .gmail/credentials.json
   ```

- [ ] **Step 2: Configure accounts in `.env`**

Set in `.env`:
```bash
GMAIL_ACCOUNTS=coltsnramzfan88@gmail.com,lucasryanthompson@gmail.com
```

- [ ] **Step 3: Authorize each account (one-time, on the Mac)**

```bash
uv run larvis gmail-auth coltsnramzfan88@gmail.com
uv run larvis gmail-auth lucasryanthompson@gmail.com
```
A browser opens for each; sign in as that account and approve read-only. Expected per run: `Authorized <account>. Token saved to .gmail/token-<slug>.json`. Verify two tokens exist: `ls .gmail/`.

- [ ] **Step 4: Rebuild and restart the container**

```bash
docker compose build larvis
docker compose up -d larvis
sleep 12
docker compose logs larvis --tail 5
```
Expected: `Application startup complete.`

- [ ] **Step 5: Smoke test — `gmail_status`**

From Claude Code (reconnect larvis MCP via `/mcp` first), call `gmail_status()`.
Expected: both accounts listed as authorized with unread counts.

- [ ] **Step 6: Smoke test — `gmail_triage`**

Call `gmail_triage()`.
Expected: a prioritized digest grouped by account, real people first, promotions aggregated (or `No unread mail in the triage window.`).

- [ ] **Step 7: Smoke test — `gmail_search`**

Call `gmail_search("newer_than:7d from:me")` (or any known sender).
Expected: a ranked list of matching messages across accounts.

- [ ] **Step 8: Smoke test — `gmail_ask`**

Call `gmail_ask("what's the most important thing in my inbox right now?")`.
Expected: an Ollama-narrated answer grounded in real recent mail.

- [ ] **Step 9: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass (74), 1 pre-existing ChromaDB warning.

- [ ] **Step 10: Linear tracking under PHA-52**

Create sub-issues under PHA-52 for each Phase 5 task and mark them Done as completed (mirrors PHA-82…89).

- [ ] **Step 11: Open the PR**

```bash
git push -u origin phase5-gmail-agent
gh pr create --base main --head phase5-gmail-agent --title "Phase 5: Read-only Gmail agent" --body "<summary>"
```
(Merge Phase 4 PR #2 first so this PR's diff is clean against main.)

---

## Self-Review Notes

- **Spec coverage:** read-only (no write paths) ✓; multi-account with one token per inbox (`auth.token_path` + per-account `collect`) ✓; all-category unread triage (`GMAIL_TRIAGE_QUERY=is:unread newer_than:2d`, no category filter) ✓; volume guards (`GMAIL_MAX_MESSAGES` cap in `collect`, `GMAIL_BODY_CHARS` in `parse_message`, Ollama aggregation prompt) ✓; 4 tools triage/search/ask/status ✓; action items surfaced as text in triage prompt, no Linear coupling ✓; per-account error isolation (`collect` returns errors, tools surface as a note) ✓; Ollama degrade in triage/ask ✓; reuse existing Google deps ✓; live smoke + Linear tracking ✓.
- **Type consistency:** message dict shape (`account`, `from_name`, `from_addr`, `subject`, `date`, `snippet`, `body`, `id`) is produced by `parse_message` and consumed identically in `_format_raw`/`_build_context` and all tool tests. `collect(query) -> (messages, errors)` matches every call site in `triage`/`search`/`ask`. `_triage_query(within|None)`, `token_path(account)`, `unread_count(account)` signatures match their callers.
- **`within` semantics:** `_WITHIN_MAP` maps "today"→1d, "week"→7d; bare tokens ("3d") pass through; empty/None falls back to `GMAIL_TRIAGE_QUERY`. Gmail `newer_than` supports d/m/y granularity (not hours) — documented in the tool docstring.
- **Test count:** Task 2 (+3), Task 3 (+7), Task 4 (+7), Task 5 (+3) = 20 new tests → 74 total.
