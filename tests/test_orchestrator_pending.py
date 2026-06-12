from larvis.orchestrator import pending


def test_propose_returns_token_and_get_retrieves():
    token = pending.propose({"tool": "x", "params": {"a": 1}})
    assert pending.get(token) == {"tool": "x", "params": {"a": 1}}


def test_execute_calls_registry_and_clears(monkeypatch):
    calls = {}

    def fake(**kwargs):
        calls.update(kwargs)
        return "done"

    token = pending.propose({"tool": "do_thing", "params": {"member": "Cal"}})
    out = pending.execute(token, {"do_thing": fake})
    assert out == "done"
    assert calls == {"member": "Cal"}
    assert pending.get(token) is None  # single-use, cleared


def test_execute_unknown_token():
    assert "No pending action" in pending.execute("nope", {})


def test_execute_unknown_tool():
    token = pending.propose({"tool": "missing", "params": {}})
    assert "Unknown action tool" in pending.execute(token, {})
