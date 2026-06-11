from larvis.agents.gmail import client, tools


def _m(account="luke@gmail.com", name="Bob", subject="Invoice", snippet="please pay",
       body="please pay", labels=None):
    return {
        "id": "1",
        "account": account,
        "from_name": name,
        "from_addr": "bob@x.com",
        "subject": subject,
        "date": "Wed, 11 Jun 2026",
        "snippet": snippet,
        "body": body,
        "labels": labels or [],
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


class _FakeOllama:
    """Stub ollama.Client whose generate() returns a fixed response string."""

    def __init__(self, text):
        self._text = text

    def __call__(self, *a, **k):
        return self

    def generate(self, *a, **k):
        return type("R", (), {"response": self._text})()


# --- label fallback (deterministic) ---

def test_classify_by_labels_promotions_is_noise():
    assert tools._classify_by_labels(_m(labels=["CATEGORY_PROMOTIONS"])) == "noise"


def test_classify_by_labels_social_is_noise():
    assert tools._classify_by_labels(_m(labels=["CATEGORY_SOCIAL"])) == "noise"


def test_classify_by_labels_starred_is_attention():
    assert tools._classify_by_labels(_m(labels=["STARRED", "CATEGORY_UPDATES"])) == "attention"


def test_classify_by_labels_personal_is_attention():
    assert tools._classify_by_labels(_m(labels=["CATEGORY_PERSONAL"])) == "attention"


def test_classify_by_labels_default_is_fyi():
    assert tools._classify_by_labels(_m(labels=["CATEGORY_UPDATES"])) == "fyi"
    assert tools._classify_by_labels(_m(labels=[])) == "fyi"


def test_classify_by_labels_ignores_gmail_important():
    # Gmail's IMPORTANT flag is too noisy (over-applied to shipping/newsletters) to trust.
    assert tools._classify_by_labels(_m(labels=["IMPORTANT", "CATEGORY_UPDATES"])) == "fyi"


# --- LLM-based classify ---

def test_classify_uses_llm_verdict(monkeypatch):
    monkeypatch.setattr(tools.ollama, "Client", _FakeOllama("ATTENTION"))
    assert tools._classify(_m(labels=["CATEGORY_UPDATES"], subject="Your Rx is ready")) == "attention"


def test_classify_llm_noise_verdict(monkeypatch):
    monkeypatch.setattr(tools.ollama, "Client", _FakeOllama("this is NOISE"))
    assert tools._classify(_m(labels=["CATEGORY_UPDATES"])) == "noise"


def test_classify_promotions_shortcut_skips_llm(monkeypatch):
    class Boom:
        def __init__(self, *a, **k):
            raise AssertionError("LLM should not be called for promo mail")

    monkeypatch.setattr(tools.ollama, "Client", Boom)
    assert tools._classify(_m(labels=["CATEGORY_PROMOTIONS"])) == "noise"


def test_classify_falls_back_to_labels_when_ollama_down(monkeypatch):
    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("ollama down")

    monkeypatch.setattr(tools.ollama, "Client", Boom)
    assert tools._classify(_m(labels=["CATEGORY_PERSONAL"])) == "attention"


def test_gist_falls_back_to_snippet_when_ollama_down(monkeypatch):
    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("ollama down")

    monkeypatch.setattr(tools.ollama, "Client", Boom)
    out = tools._gist(_m(snippet="please pay the invoice"))
    assert "please pay the invoice" in out


def test_triage_buckets_and_aggregates_noise(monkeypatch):
    msgs = [
        _m(name="Roanne", subject="School registration"),
        _m(name="Trezor", subject="Workflow event"),
        _m(name="Spammer", subject="50% off!"),
        _m(name="Spammer2", subject="Buy now"),
    ]
    verdict = {"Roanne": "attention", "Trezor": "fyi", "Spammer": "noise", "Spammer2": "noise"}
    monkeypatch.setattr(client, "collect", lambda q: (msgs, []))
    monkeypatch.setattr(tools, "_gist", lambda m: "GIST")
    monkeypatch.setattr(tools, "_classify", lambda m: verdict[m["from_name"]])
    out = tools.triage()
    assert "NEEDS ATTENTION (1)" in out
    assert "Roanne" in out and "GIST" in out
    assert "FYI (1)" in out and "Trezor" in out
    assert "NOISE: 2" in out
    assert "Spammer" not in out  # noise is aggregated, not listed


def test_triage_no_attention_shows_placeholder(monkeypatch):
    monkeypatch.setattr(client, "collect", lambda q: ([_m()], []))
    monkeypatch.setattr(tools, "_gist", lambda m: "GIST")
    monkeypatch.setattr(tools, "_classify", lambda m: "fyi")
    out = tools.triage()
    assert "NEEDS ATTENTION (0)" in out
