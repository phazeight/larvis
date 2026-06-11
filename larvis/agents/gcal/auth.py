import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from larvis.config import settings

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_credentials() -> Credentials:
    token_path = settings.gcal_token_path
    if not os.path.exists(token_path):
        raise RuntimeError("Calendar not authorized — run `larvis gcal-auth`.")
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, "w") as f:
                f.write(creds.to_json())
        else:
            raise RuntimeError("Calendar token invalid — run `larvis gcal-auth`.")
    return creds


def get_service():
    return build("calendar", "v3", credentials=get_credentials(), cache_discovery=False)
