import json

from larvis import openai_api


def test_last_user_message_picks_last_user_turn():
    msgs = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "second"},
    ]
    assert openai_api.last_user_message(msgs) == "second"


def test_last_user_message_empty_when_no_user():
    assert openai_api.last_user_message([]) == ""
    assert openai_api.last_user_message([{"role": "assistant", "content": "x"}]) == ""


def test_answer_routes_vault_model_to_rag(monkeypatch):
    monkeypatch.setattr(openai_api.rag, "ask", lambda q: f"RAG:{q}")
    monkeypatch.setattr(openai_api.orchestrator_tools, "orchestrate", lambda q: "ORCH")
    assert openai_api.answer("larvis-vault", "hi") == "RAG:hi"


def test_answer_routes_default_and_unknown_to_orchestrator(monkeypatch):
    monkeypatch.setattr(openai_api.rag, "ask", lambda q: "RAG")
    monkeypatch.setattr(openai_api.orchestrator_tools, "orchestrate", lambda q: f"ORCH:{q}")
    assert openai_api.answer("larvis", "hi") == "ORCH:hi"
    assert openai_api.answer("something-else", "hi") == "ORCH:hi"


def test_completion_response_shape():
    r = openai_api.completion_response("larvis-vault", "hello")
    assert r["object"] == "chat.completion"
    assert r["model"] == "larvis-vault"
    assert r["choices"][0]["message"] == {"role": "assistant", "content": "hello"}
    assert r["choices"][0]["finish_reason"] == "stop"
    assert r["id"].startswith("chatcmpl-")


def test_stream_chunks_format():
    chunks = list(openai_api.stream_chunks("larvis", "hi there"))
    assert chunks[-1] == "data: [DONE]\n\n"
    first = json.loads(chunks[0][len("data: "):])
    assert first["object"] == "chat.completion.chunk"
    assert first["choices"][0]["delta"]["content"] == "hi there"
    stop = json.loads(chunks[1][len("data: "):])
    assert stop["choices"][0]["finish_reason"] == "stop"


def test_models_response_lists_both():
    r = openai_api.models_response()
    ids = [m["id"] for m in r["data"]]
    assert r["object"] == "list"
    assert "larvis-vault" in ids and "larvis" in ids
