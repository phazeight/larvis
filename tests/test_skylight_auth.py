import json

from larvis.agents.skylight import auth


def test_configured_requires_all_three(monkeypatch):
    monkeypatch.setattr(auth.settings, "skylight_email", "a@b.com")
    monkeypatch.setattr(auth.settings, "skylight_password", "pw")
    monkeypatch.setattr(auth.settings, "skylight_frame_id", "")
    assert auth._configured() is False
    monkeypatch.setattr(auth.settings, "skylight_frame_id", "frame1")
    assert auth._configured() is True


def test_parse_session_extracts_user_id_and_token():
    raw = {"data": {"id": "999", "attributes": {"authentication_token": "tok123"}}}
    creds = auth._parse_session(raw)
    assert creds == {"user_id": "999", "token": "tok123"}


def test_build_header_uses_basic_user_token():
    header = auth._build_header({"user_id": "999", "token": "tok123"})
    assert header["Authorization"] == "Basic 999 tok123"


def test_token_cache_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "token.json"
    monkeypatch.setattr(auth.settings, "skylight_token_path", str(path))
    auth._save_creds({"user_id": "1", "token": "t"})
    assert auth._load_creds() == {"user_id": "1", "token": "t"}


def test_load_creds_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(auth.settings, "skylight_token_path", str(tmp_path / "nope.json"))
    assert auth._load_creds() is None
