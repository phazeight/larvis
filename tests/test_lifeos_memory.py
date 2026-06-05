import larvis.agents.lifeos.memory as mem


def test_add_and_get_turns(monkeypatch, tmp_path):
    monkeypatch.setattr(mem, "DB_PATH", tmp_path / "test.db")
    mem.add_turn("sess1", "user", "hello world")
    mem.add_turn("sess1", "assistant", "hi there")
    context = mem.get_session_context("sess1")
    assert len(context) == 2
    assert context[0]["role"] == "user"
    assert context[0]["content"] == "hello world"
    assert context[1]["role"] == "assistant"


def test_get_session_context_only_returns_own_session(monkeypatch, tmp_path):
    monkeypatch.setattr(mem, "DB_PATH", tmp_path / "test.db")
    mem.add_turn("sess-a", "user", "from session a")
    mem.add_turn("sess-b", "user", "from session b")
    context = mem.get_session_context("sess-a")
    assert len(context) == 1
    assert context[0]["content"] == "from session a"


def test_get_session_context_respects_last_n(monkeypatch, tmp_path):
    monkeypatch.setattr(mem, "DB_PATH", tmp_path / "test.db")
    for i in range(15):
        mem.add_turn("sess1", "user", f"message {i}")
    context = mem.get_session_context("sess1", last_n=5)
    assert len(context) == 5
    assert context[-1]["content"] == "message 14"


def test_add_and_get_commitments(monkeypatch, tmp_path):
    monkeypatch.setattr(mem, "DB_PATH", tmp_path / "test.db")
    mem.add_commitment("Finish learn_go this week")
    commitments = mem.get_open_commitments()
    assert len(commitments) == 1
    assert commitments[0]["text"] == "Finish learn_go this week"
    assert commitments[0]["resolved_at"] is None


def test_is_task_synced_returns_false_for_new_task(monkeypatch, tmp_path):
    monkeypatch.setattr(mem, "DB_PATH", tmp_path / "test.db")
    assert mem.is_task_synced("notes/todo.md", "Fix dishwasher") is False


def test_mark_and_check_task_synced(monkeypatch, tmp_path):
    monkeypatch.setattr(mem, "DB_PATH", tmp_path / "test.db")
    mem.mark_task_synced("notes/todo.md", "Fix dishwasher", "PHA-99")
    assert mem.is_task_synced("notes/todo.md", "Fix dishwasher") is True


def test_mark_task_synced_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(mem, "DB_PATH", tmp_path / "test.db")
    mem.mark_task_synced("notes/todo.md", "Fix dishwasher", "PHA-99")
    mem.mark_task_synced("notes/todo.md", "Fix dishwasher", "PHA-99")
    assert mem.is_task_synced("notes/todo.md", "Fix dishwasher") is True
