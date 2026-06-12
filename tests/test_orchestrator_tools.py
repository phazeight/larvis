from larvis.orchestrator import adapters, pending, router, synthesize, tools


def test_orchestrate_read_path(monkeypatch):
    monkeypatch.setattr(router, "is_write_intent", lambda q: False)
    monkeypatch.setattr(router, "route", lambda q: ["calendar"])
    monkeypatch.setattr(adapters, "gather", lambda agents, q, sid: {"calendar": "x"})
    monkeypatch.setattr(synthesize, "synthesize", lambda q, blocks: "ANSWER")
    assert tools.orchestrate("what's today?") == "ANSWER"


def test_orchestrate_write_proposal(monkeypatch):
    monkeypatch.setattr(router, "is_write_intent", lambda q: True)
    monkeypatch.setattr(
        router, "detect_action",
        lambda q: {"tool": "skylight_add_chore", "fields": ["member", "summary", "when"]},
    )
    monkeypatch.setattr(
        adapters, "extract_params",
        lambda action, q: {"member": "Cal", "summary": "trash", "when": "today"},
    )
    out = tools.orchestrate("add trash to Cal")
    assert "Proposed" in out and "Cal" in out and "larvis_confirm" in out


def test_orchestrate_write_unknown_action(monkeypatch):
    monkeypatch.setattr(router, "is_write_intent", lambda q: True)
    monkeypatch.setattr(router, "detect_action", lambda q: None)
    assert "don't have a tool" in tools.orchestrate("create a spreadsheet")


def test_orchestrate_write_extract_fails(monkeypatch):
    monkeypatch.setattr(router, "is_write_intent", lambda q: True)
    monkeypatch.setattr(
        router, "detect_action",
        lambda q: {"tool": "lifeos_commit", "fields": ["text"]},
    )

    def boom(action, q):
        raise ValueError("nope")

    monkeypatch.setattr(adapters, "extract_params", boom)
    assert "be explicit" in tools.orchestrate("remind me")


def test_confirm_executes(monkeypatch):
    calls = {}
    monkeypatch.setattr(adapters, "WRITE_TOOLS", {"t": lambda **k: calls.update(k) or "OK"})
    token = pending.propose({"tool": "t", "params": {"x": 1}})
    assert tools.confirm(token) == "OK"
    assert calls == {"x": 1}
