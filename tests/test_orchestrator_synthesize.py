from larvis.orchestrator import synthesize


class _FakeOllama:
    def __init__(self, text):
        self._text = text

    def __call__(self, *a, **k):
        return self

    def generate(self, *a, **k):
        return type("R", (), {"response": self._text})()


def test_synthesize_uses_ollama(monkeypatch):
    monkeypatch.setattr(synthesize.ollama, "Client", _FakeOllama("Friday works."))
    out = synthesize.synthesize("date night?", {"calendar": "free fri", "ynab": "$120"})
    assert out == "Friday works."


def test_synthesize_degrades_to_concat_when_ollama_down(monkeypatch):
    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("ollama down")

    monkeypatch.setattr(synthesize.ollama, "Client", Boom)
    out = synthesize.synthesize("date night?", {"calendar": "free fri", "ynab": "$120"})
    assert "calendar" in out and "free fri" in out and "$120" in out
