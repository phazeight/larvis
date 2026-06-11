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
