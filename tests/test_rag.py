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


def test_salient_terms_drops_stopwords_keeps_name():
    assert rag._salient_terms("how much did I say to Alex?") == ["alex"]


def test_salient_terms_keeps_content_words():
    terms = rag._salient_terms("what's my garage cleanout budget?")
    assert "garage" in terms and "cleanout" in terms and "budget" in terms
    assert "my" not in terms and "what" not in terms


def test_merge_puts_lexical_first_and_dedupes():
    assert rag._merge(["A", "B"], ["B", "C", "D"], 3) == ["A", "B", "C"]


def test_merge_respects_k():
    assert rag._merge(["A"], ["B", "C", "D"], 2) == ["A", "B"]
