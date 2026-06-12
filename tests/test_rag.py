from larvis import rag


def test_ask_returns_no_info_when_no_chunks(monkeypatch):
    monkeypatch.setattr(rag, "search", lambda q: [])

    class Boom:
        def __init__(self, *a, **k):
            raise AssertionError("LLM must not be called when there is no context")

    monkeypatch.setattr(rag.ollama, "Client", Boom)
    assert rag.ask("what did I say to Alex?") == rag._NO_INFO


def test_ask_ignores_blank_chunks(monkeypatch):
    monkeypatch.setattr(rag, "search", lambda q: ["   ", ""])

    class Boom:
        def __init__(self, *a, **k):
            raise AssertionError("LLM must not be called when context is blank")

    monkeypatch.setattr(rag.ollama, "Client", Boom)
    assert rag.ask("anything?") == rag._NO_INFO


def test_build_prompt_has_grounding_guardrail():
    p = rag._build_prompt("how much to Alex?", "some context")
    low = p.lower()
    assert "only" in low
    assert "outside knowledge" in low
    assert rag._NO_INFO in p
