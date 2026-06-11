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
