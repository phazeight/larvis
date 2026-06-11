import json
import os

import httpx

from larvis.config import settings

# Skylight uses OAuth2. There is no email/password endpoint — the access token is
# obtained interactively once (captured from the app), then refreshed headlessly.
# Seed .skylight/token.json with {"access_token": ..., "refresh_token": ...}.
CLIENT_ID = "skylight-mobile"


def _load_creds() -> dict | None:
    path = settings.skylight_token_path
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _save_creds(creds: dict) -> None:
    path = settings.skylight_token_path
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(creds, f)


def _require_creds() -> dict:
    creds = _load_creds()
    if not creds or not creds.get("access_token"):
        raise RuntimeError(
            "Skylight not authorized — seed .skylight/token.json with access_token + "
            "refresh_token (capture once from the Skylight web app)."
        )
    return creds


def auth_header() -> dict:
    return {"Authorization": f"Bearer {_require_creds()['access_token']}"}


def refresh() -> dict:
    """Exchange the refresh token for a fresh access token; persist both."""
    creds = _require_creds()
    url = f"{settings.skylight_base_url.rstrip('/')}/oauth/token"
    resp = httpx.post(
        url,
        data={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": creds["refresh_token"],
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    new = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", creds["refresh_token"]),
    }
    _save_creds(new)
    return {"Authorization": f"Bearer {new['access_token']}"}
