import json
import os

import httpx

from larvis.config import settings


def _configured() -> bool:
    return bool(
        settings.skylight_email and settings.skylight_password and settings.skylight_frame_id
    )


def _parse_session(data: dict) -> dict:
    node = data.get("data", data)
    attrs = node.get("attributes", node)
    token = attrs.get("authentication_token") or attrs.get("token")
    user_id = str(node.get("id") or attrs.get("user_id") or "")
    return {"user_id": user_id, "token": token}


def _build_header(creds: dict) -> dict:
    # Per Task 2 capture. Community implementations use "Basic <user_id> <token>".
    return {
        "Authorization": f"Basic {creds['user_id']} {creds['token']}",
        "Content-Type": "application/json",
    }


def _save_creds(creds: dict) -> None:
    path = settings.skylight_token_path
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(creds, f)


def _load_creds() -> dict | None:
    path = settings.skylight_token_path
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _sign_in() -> dict:
    if not _configured():
        raise RuntimeError(
            "Skylight not configured — set SKYLIGHT_EMAIL/PASSWORD/FRAME_ID in .env."
        )
    url = f"{settings.skylight_base_url.rstrip('/')}/sessions"
    resp = httpx.post(
        url,
        json={"email": settings.skylight_email, "password": settings.skylight_password},
        timeout=30,
    )
    resp.raise_for_status()
    creds = _parse_session(resp.json())
    _save_creds(creds)
    return creds


def auth_header(force_refresh: bool = False) -> dict:
    creds = None if force_refresh else _load_creds()
    if not creds:
        creds = _sign_in()
    return _build_header(creds)
