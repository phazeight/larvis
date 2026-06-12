import pytest

from larvis.orchestrator import adapters


def test_gather_dispatches_to_agent(monkeypatch):
    monkeypatch.setattr(adapters.gcal_tools, "ask", lambda q: "CAL ANSWER")
    blocks = adapters.gather(["calendar"], "free friday?", "sid")
    assert blocks == {"calendar": "CAL ANSWER"}


def test_gather_catches_agent_error(monkeypatch):
    def boom(q):
        raise RuntimeError("down")

    monkeypatch.setattr(adapters.ynab_tools, "ask", boom)
    blocks = adapters.gather(["ynab"], "budget?", "sid")
    assert "ynab error" in blocks["ynab"]


def test_write_tools_registry_has_known_actions():
    assert "skylight_add_chore" in adapters.WRITE_TOOLS
    assert "lifeos_commit" in adapters.WRITE_TOOLS


class _FakeOllama:
    def __init__(self, text):
        self._text = text

    def __call__(self, *a, **k):
        return self

    def generate(self, *a, **k):
        return type("R", (), {"response": self._text})()


def test_extract_params_parses_json(monkeypatch):
    monkeypatch.setattr(
        adapters.ollama,
        "Client",
        _FakeOllama('{"member": "Cal", "summary": "trash", "when": "tomorrow"}'),
    )
    action = {"tool": "skylight_add_chore", "fields": ["member", "summary", "when"]}
    params = adapters.extract_params(action, "add trash to cal tomorrow")
    assert params == {"member": "Cal", "summary": "trash", "when": "tomorrow"}


def test_extract_params_raises_on_garbage(monkeypatch):
    monkeypatch.setattr(adapters.ollama, "Client", _FakeOllama("i cannot help"))
    action = {"tool": "lifeos_commit", "fields": ["text"]}
    with pytest.raises(ValueError):
        adapters.extract_params(action, "remember milk")
