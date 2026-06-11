from larvis.agents.gmail import auth


def test_slug_sanitizes_email():
    assert auth._slug("coltsnramzfan88@gmail.com") == "coltsnramzfan88_gmail_com"


def test_slug_collapses_non_alnum():
    assert auth._slug("a.b+c@x.co") == "a_b_c_x_co"


def test_token_path_uses_dir_and_slug(monkeypatch):
    monkeypatch.setattr(auth.settings, "gmail_token_dir", ".gmail")
    assert auth.token_path("luke@gmail.com") == ".gmail/token-luke_gmail_com.json"
