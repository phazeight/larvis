import pytest

from larvis.agents.skylight import auth


def test_token_cache_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "token.json"
    monkeypatch.setattr(auth.settings, "skylight_token_path", str(path))
    auth._save_creds({"access_token": "a", "refresh_token": "r"})
    assert auth._load_creds() == {"access_token": "a", "refresh_token": "r"}


def test_load_creds_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(auth.settings, "skylight_token_path", str(tmp_path / "nope.json"))
    assert auth._load_creds() is None


def test_auth_header_uses_bearer(tmp_path, monkeypatch):
    path = tmp_path / "token.json"
    monkeypatch.setattr(auth.settings, "skylight_token_path", str(path))
    auth._save_creds({"access_token": "abc123", "refresh_token": "r"})
    assert auth.auth_header() == {"Authorization": "Bearer abc123"}


def test_auth_header_raises_when_unseeded(tmp_path, monkeypatch):
    monkeypatch.setattr(auth.settings, "skylight_token_path", str(tmp_path / "nope.json"))
    with pytest.raises(RuntimeError, match="not authorized"):
        auth.auth_header()
