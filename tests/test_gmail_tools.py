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
