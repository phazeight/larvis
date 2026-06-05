# Larvis Phase 2 — LifeOS Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a LifeOS Agent to the Larvis MCP server — morning briefing, multi-turn memory, persistent commitments, and vault→Linear task sync via lb.

**Architecture:** New `larvis/agents/lifeos/` module with three internal sub-modules (memory, linear_sync, tools). `server.py` gets four new `@mcp.tool()` wrappers that delegate to the tools module. SQLite at `.memory/lifeos.db` (gitignored) stores conversation turns and commitments. `lb` CLI handles Linear sync.

**Tech Stack:** Python 3.12, SQLite (stdlib), FastMCP 3.x, ollama Python client, linear-beads (`lb`), bun (for lb install), existing larvis platform (Phase 1)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `larvis/agents/__init__.py` | Create | Package marker |
| `larvis/agents/lifeos/__init__.py` | Create | Package marker |
| `larvis/agents/lifeos/memory.py` | Create | SQLite ops — turns, commitments, synced_tasks tables |
| `larvis/agents/lifeos/linear_sync.py` | Create | Vault `#to-linear` scanner + `lb create` subprocess |
| `larvis/agents/lifeos/tools.py` | Create | Pure Python functions: briefing, ask, commit, sync_tasks |
| `larvis/server.py` | Modify | Add four `@mcp.tool()` wrappers for lifeos tools |
| `.gitignore` | Modify | Add `.memory/` |
| `.lb/config.jsonc` | Create | lb project config (committed) |
| `tests/test_lifeos_memory.py` | Create | Unit tests for all memory.py functions |
| `tests/test_lifeos_sync.py` | Create | Unit tests for scan_vault_for_tagged_tasks |
| `CLAUDE.md` | Modify | Document four new MCP tools |

---

## Task 1: Agent module scaffold

**Files:**
- Create: `larvis/agents/__init__.py`
- Create: `larvis/agents/lifeos/__init__.py`
- Modify: `.gitignore`

- [ ] **Step 1: Create package markers**

```bash
cd /Users/phazeight/repos/larvis
mkdir -p larvis/agents/lifeos
touch larvis/agents/__init__.py larvis/agents/lifeos/__init__.py
```

- [ ] **Step 2: Add .memory/ to .gitignore**

Open `.gitignore` and add this line at the bottom:
```
.memory/
```

The full `.gitignore` should now read:
```
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
dist/
*.egg-info/
.memory/
```

- [ ] **Step 3: Verify structure**

```bash
find larvis/agents -type f
```

Expected:
```
larvis/agents/__init__.py
larvis/agents/lifeos/__init__.py
```

- [ ] **Step 4: Commit**

```bash
git add larvis/agents/ .gitignore
git commit -m "chore: agent module scaffold and .memory gitignore"
```

---

## Task 2: Memory module + unit tests

**Files:**
- Create: `larvis/agents/lifeos/memory.py`
- Create: `tests/test_lifeos_memory.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_lifeos_memory.py
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
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
cd /Users/phazeight/repos/larvis
uv run pytest tests/test_lifeos_memory.py -v
```

Expected: `ModuleNotFoundError: No module named 'larvis.agents.lifeos.memory'`

- [ ] **Step 3: Implement larvis/agents/lifeos/memory.py**

```python
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / ".memory" / "lifeos.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS commitments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS synced_tasks (
            vault_file TEXT NOT NULL,
            task_text TEXT NOT NULL,
            linear_id TEXT,
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (vault_file, task_text)
        );
    """)
    conn.commit()


def get_session_context(session_id: str, last_n: int = 10) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM turns WHERE session_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, last_n),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def add_turn(session_id: str, role: str, content: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO turns (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )


def add_commitment(text: str) -> None:
    with _conn() as conn:
        conn.execute("INSERT INTO commitments (text) VALUES (?)", (text,))


def get_open_commitments() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, text, created_at, resolved_at FROM commitments "
            "WHERE resolved_at IS NULL ORDER BY created_at",
        ).fetchall()
    return [
        {"id": r["id"], "text": r["text"], "created_at": r["created_at"], "resolved_at": r["resolved_at"]}
        for r in rows
    ]


def is_task_synced(vault_file: str, task_text: str) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM synced_tasks WHERE vault_file = ? AND task_text = ?",
            (vault_file, task_text),
        ).fetchone()
    return row is not None


def mark_task_synced(vault_file: str, task_text: str, linear_id: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO synced_tasks (vault_file, task_text, linear_id) "
            "VALUES (?, ?, ?)",
            (vault_file, task_text, linear_id),
        )
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
uv run pytest tests/test_lifeos_memory.py -v
```

Expected: 7 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add larvis/agents/lifeos/memory.py tests/test_lifeos_memory.py
git commit -m "feat: lifeos memory module with SQLite turns, commitments, synced_tasks"
```

---

## Task 3: Linear sync module + unit tests

**Files:**
- Create: `larvis/agents/lifeos/linear_sync.py`
- Create: `tests/test_lifeos_sync.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_lifeos_sync.py
from pathlib import Path
import pytest
from larvis.agents.lifeos.linear_sync import scan_vault_for_tagged_tasks


def test_scan_extracts_unchecked_to_linear_tasks(tmp_path):
    note = tmp_path / "todo.md"
    note.write_text(
        "# Tasks\n\n"
        "- [ ] Fix the dishwasher #to-linear\n"
        "- [ ] Normal task\n"
        "- [x] Already done #to-linear\n"
    )
    tasks = scan_vault_for_tagged_tasks(tmp_path)
    assert len(tasks) == 1
    assert tasks[0]["task_text"] == "Fix the dishwasher"
    assert tasks[0]["vault_file"] == "todo.md"


def test_scan_strips_tag_from_task_text(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("- [ ] Buy groceries #to-linear\n")
    tasks = scan_vault_for_tagged_tasks(tmp_path)
    assert tasks[0]["task_text"] == "Buy groceries"


def test_scan_ignores_checked_tasks(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("- [x] Already done #to-linear\n")
    tasks = scan_vault_for_tagged_tasks(tmp_path)
    assert len(tasks) == 0


def test_scan_finds_tasks_in_nested_files(tmp_path):
    subdir = tmp_path / "projects" / "myproject"
    subdir.mkdir(parents=True)
    note = subdir / "tasks.md"
    note.write_text("- [ ] Deploy the server #to-linear\n")
    tasks = scan_vault_for_tagged_tasks(tmp_path)
    assert len(tasks) == 1
    assert tasks[0]["vault_file"] == "projects/myproject/tasks.md"


def test_scan_returns_empty_for_vault_with_no_tagged_tasks(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("- [ ] Just a normal task\n")
    tasks = scan_vault_for_tagged_tasks(tmp_path)
    assert len(tasks) == 0
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
uv run pytest tests/test_lifeos_sync.py -v
```

Expected: `ModuleNotFoundError: No module named 'larvis.agents.lifeos.linear_sync'`

- [ ] **Step 3: Implement larvis/agents/lifeos/linear_sync.py**

```python
import re
import subprocess
from pathlib import Path

from larvis.agents.lifeos.memory import is_task_synced, mark_task_synced
from larvis.config import settings

_TASK_PATTERN = re.compile(r"^- \[ \] (.+)$", re.MULTILINE)
_TAG = "#to-linear"


def scan_vault_for_tagged_tasks(vault_path: Path) -> list[dict]:
    tasks = []
    for md_file in vault_path.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        for match in _TASK_PATTERN.finditer(content):
            line = match.group(1)
            if _TAG not in line:
                continue
            task_text = line.replace(_TAG, "").strip()
            tasks.append({
                "vault_file": str(md_file.relative_to(vault_path)),
                "task_text": task_text,
            })
    return tasks


def sync_tasks() -> int:
    vault = Path(settings.vault_path)
    tasks = scan_vault_for_tagged_tasks(vault)
    synced = 0
    for task in tasks:
        if is_task_synced(task["vault_file"], task["task_text"]):
            continue
        try:
            result = subprocess.run(
                ["lb", "create", task["task_text"]],
                capture_output=True,
                text=True,
                timeout=30,
            )
            linear_id = result.stdout.strip().split()[-1] if result.returncode == 0 else "unknown"
            mark_task_synced(task["vault_file"], task["task_text"], linear_id)
            synced += 1
        except FileNotFoundError:
            raise RuntimeError(
                "lb not found — install with:\n"
                "  bun install -g github:nikvdp/linear-beads\n"
                "then run: lb onboard"
            )
    return synced
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
uv run pytest tests/test_lifeos_sync.py -v
```

Expected: 5 tests PASSED.

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest -v
```

Expected: all 15 tests pass (3 from `test_indexer.py` + 7 from `test_lifeos_memory.py` + 5 from `test_lifeos_sync.py`). Zero failures.

- [ ] **Step 6: Commit**

```bash
git add larvis/agents/lifeos/linear_sync.py tests/test_lifeos_sync.py
git commit -m "feat: linear sync — scan vault #to-linear tasks and lb create"
```

---

## Task 4: LifeOS tools module

**Files:**
- Create: `larvis/agents/lifeos/tools.py`

- [ ] **Step 1: Implement larvis/agents/lifeos/tools.py**

```python
from datetime import date

import ollama

from larvis.agents.lifeos import memory, linear_sync
from larvis.config import settings
from larvis.rag import search as vault_search


def briefing(session_id: str) -> str:
    today = date.today().isoformat()

    project_chunks = vault_search("active projects status", top_k=5)
    task_chunks = vault_search("overdue tasks this week", top_k=5)
    commitments = memory.get_open_commitments()

    if not project_chunks and not task_chunks and not commitments:
        return "Vault not indexed — run `larvis reindex` first."

    context_parts = []
    if project_chunks:
        context_parts.append("Active project context:\n" + "\n---\n".join(project_chunks))
    if task_chunks:
        context_parts.append("Task context:\n" + "\n---\n".join(task_chunks))
    if commitments:
        commitment_lines = "\n".join(
            f"- {c['text']} (since {c['created_at'][:10]})" for c in commitments
        )
        context_parts.append(f"Open commitments:\n{commitment_lines}")

    prompt = (
        f"You are Larvis, a personal assistant. Today is {today}.\n"
        "Give a concise morning briefing using the context below. "
        "List active projects, surface anything overdue or needing attention, "
        "and remind the user of open commitments. Be brief and actionable.\n\n"
        + "\n\n".join(context_parts)
    )

    resp = ollama.Client(host=settings.ollama_host).generate(
        model=settings.ollama_model, prompt=prompt
    )
    response_text = resp.response
    memory.add_turn(session_id, "assistant", response_text)
    return response_text


def ask(query: str, session_id: str) -> str:
    memory.add_turn(session_id, "user", query)

    history = memory.get_session_context(session_id, last_n=10)
    chunks = vault_search(query, top_k=5)
    context = "\n\n---\n\n".join(chunks)

    history_lines = "\n".join(
        f"{t['role'].capitalize()}: {t['content']}" for t in history[:-1]
    )

    prompt_parts = ["You are Larvis, a personal assistant with memory of this conversation.\n"]
    if history_lines:
        prompt_parts.append(f"Conversation so far:\n{history_lines}\n")
    if context:
        prompt_parts.append(f"Vault context:\n{context}\n")
    prompt_parts.append(f"User: {query}")

    resp = ollama.Client(host=settings.ollama_host).generate(
        model=settings.ollama_model, prompt="\n".join(prompt_parts)
    )
    response_text = resp.response
    memory.add_turn(session_id, "assistant", response_text)
    return response_text


def commit(text: str) -> str:
    memory.add_commitment(text)
    return f"Committed: {text}"


def sync_tasks() -> str:
    try:
        count = linear_sync.sync_tasks()
        if count == 0:
            return "No tasks pending sync."
        return f"{count} task(s) synced to Linear."
    except RuntimeError as e:
        return str(e)
```

- [ ] **Step 2: Verify import**

```bash
uv run python -c "from larvis.agents.lifeos.tools import briefing, ask, commit, sync_tasks; print('ok')"
```

Expected: prints `ok` with no errors.

- [ ] **Step 3: Commit**

```bash
git add larvis/agents/lifeos/tools.py
git commit -m "feat: lifeos tools — briefing, ask, commit, sync_tasks"
```

---

## Task 5: Wire tools into server.py

**Files:**
- Modify: `larvis/server.py`

- [ ] **Step 1: Add lifeos tool wrappers to server.py**

Open `larvis/server.py` and add after the existing imports and before `def main()`:

The full updated `larvis/server.py`:

```python
from fastmcp import FastMCP

from larvis import rag
from larvis.agents.lifeos import tools as lifeos_tools
from larvis.health import get_status

mcp = FastMCP("Larvis")


@mcp.tool()
def larvis_ask(query: str) -> str:
    """Ask a question answered using your LifeOS vault as context."""
    if get_status()["index_docs"] == 0:
        return "Vault not indexed — run `larvis reindex` first."
    return rag.ask(query)


@mcp.tool()
def larvis_search(query: str, top_k: int = 5) -> list[str]:
    """Semantic search over your LifeOS vault. Returns raw matching chunks."""
    return rag.search(query, top_k)


@mcp.tool()
def larvis_status() -> dict:
    """Health check — Ollama status, ChromaDB doc count, model config."""
    return get_status()


@mcp.tool()
def lifeos_briefing(session_id: str) -> str:
    """Morning kickoff — active projects, overdue tasks, open commitments from vault."""
    return lifeos_tools.briefing(session_id)


@mcp.tool()
def lifeos_ask(query: str, session_id: str) -> str:
    """Ask a question with conversation memory and vault context."""
    return lifeos_tools.ask(query, session_id)


@mcp.tool()
def lifeos_commit(text: str) -> str:
    """Store a commitment or decision that persists across sessions."""
    return lifeos_tools.commit(text)


@mcp.tool()
def lifeos_sync_tasks() -> str:
    """Scan vault for #to-linear checkbox tasks and create Linear issues via lb."""
    return lifeos_tools.sync_tasks()


def main() -> None:
    mcp.run(transport="sse", host="0.0.0.0", port=8765)
```

- [ ] **Step 2: Verify import**

```bash
uv run python -c "from larvis.server import mcp; print([t.name for t in mcp._tool_manager.list_tools()])"
```

Expected: prints a list containing `larvis_ask`, `larvis_search`, `larvis_status`, `lifeos_briefing`, `lifeos_ask`, `lifeos_commit`, `lifeos_sync_tasks`.

(Note: if `mcp._tool_manager` doesn't work in your FastMCP version, just verify the import doesn't error.)

- [ ] **Step 3: Rebuild and restart the larvis container**

```bash
cd /Users/phazeight/repos/larvis
docker compose build larvis
docker compose up -d
docker compose logs larvis | tail -20
```

Expected: larvis container starts, shows `Ollama ready.` and `Starting MCP server 'Larvis'` with no import errors.

- [ ] **Step 4: Commit**

```bash
git add larvis/server.py
git commit -m "feat: register lifeos MCP tools in server"
```

---

## Task 6: lb onboarding

**Files:**
- Create: `.lb/config.jsonc` (generated by `lb init`, then committed)

- [ ] **Step 1: Install bun (if not present)**

```bash
which bun || curl -fsSL https://bun.sh/install | bash
```

Expected: `bun` is available in PATH. If just installed, open a new terminal or run `source ~/.zshrc`.

- [ ] **Step 2: Install lb**

```bash
bun install -g github:nikvdp/linear-beads
lb --version
```

Expected: lb version printed without error.

- [ ] **Step 3: Run lb onboard from the larvis repo**

```bash
cd /Users/phazeight/repos/larvis
lb onboard
```

Follow the prompts:
- Authenticate with your Linear API key when asked
- When asked for project scope, choose `project` and select the `larvis` project (linked to PHA-52)

This creates `.lb/` in the repo. Verify:
```bash
cat .lb/config.jsonc
```

Expected: contains `repo_binding_version` and project config.

- [ ] **Step 4: Commit .lb/config.jsonc (not auth tokens)**

```bash
git add .lb/config.jsonc
git commit -m "chore: lb project config for Linear-backed task tracking"
```

Note: if `.lb/` contains auth tokens (e.g. `.lb/auth.json`), add that file to `.gitignore` first:
```bash
echo ".lb/auth.json" >> .gitignore
git add .gitignore
```

---

## Task 7: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add Phase 2 tools to the MCP tools table in CLAUDE.md**

Open `/Users/phazeight/repos/larvis/CLAUDE.md` and update the MCP tools section:

```markdown
## MCP tools (Phase 1 + 2)

| Tool | Signature | Description |
|------|-----------|-------------|
| `larvis_ask` | `(query: str) -> str` | RAG + generation |
| `larvis_search` | `(query: str, top_k?: int) -> List[str]` | Raw vault search |
| `larvis_status` | `() -> dict` | Health check |
| `lifeos_briefing` | `(session_id: str) -> str` | Morning kickoff — projects, tasks, commitments |
| `lifeos_ask` | `(query: str, session_id: str) -> str` | Memory-aware vault query |
| `lifeos_commit` | `(text: str) -> str` | Store a persistent commitment |
| `lifeos_sync_tasks` | `() -> str` | Sync vault `#to-linear` tasks to Linear via lb |
```

Also add a note about session_id and the `#to-linear` convention:

```markdown
## Session ID convention

Pass any stable string as `session_id` for lifeos tools. In Claude Code, use the conversation ID or any UUID. The same `session_id` groups conversation history together for multi-turn memory.

## Vault task sync convention

To sync a vault task to Linear, add `#to-linear` to any unchecked checkbox task:
```
- [ ] Fix the dishwasher gasket #to-linear
```
Then call `lifeos_sync_tasks` to push it to Linear via lb.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document Phase 2 lifeos MCP tools and conventions"
```

---

## Task 8: Smoke test checklist

Run after all containers are rebuilt and lb is onboarded.

- [ ] **Step 1: Confirm containers running and tools registered**

```bash
docker compose ps
uv run larvis status
```

Expected: all services up, `ollama: true`, `chromadb: true`, `index_docs: 959`.

- [ ] **Step 2: Test persistent commitment**

In Claude Code (with larvis MCP connected), call:
```
lifeos_commit("I said I'd finish learn_go by end of month")
```

Expected: `"Committed: I said I'd finish learn_go by end of month"`

Then run `make stop && make start`, reconnect, and call:
```
lifeos_briefing("test-session-01")
```

Expected: briefing mentions the commitment you just stored. This proves cross-session persistence.

- [ ] **Step 3: Test morning briefing**

```
lifeos_briefing("test-session-01")
```

Expected: coherent briefing listing your active projects (jarvis-glowup, learn_go, etc.) from vault, plus your open commitment. Response should be vault-grounded, not generic.

- [ ] **Step 4: Test in-session memory**

```
lifeos_ask("what are my active projects?", "test-session-02")
```

Then immediately:
```
lifeos_ask("which of those has the most recent activity?", "test-session-02")
```

Expected: second response references "those" correctly — it knows what was discussed in turn 1.

- [ ] **Step 5: Test vault→Linear sync**

Add a task to any vault note:
```bash
echo "- [ ] Test linear sync from Larvis #to-linear" >> /Users/phazeight/Documents/LifeOs/1.\ Projects/larvis/larvis.README.md
```

(Or add it manually in Obsidian.)

Then call:
```
lifeos_sync_tasks()
```

Expected: `"1 task(s) synced to Linear."` Verify the issue appears in your Linear workspace under the larvis project.

Call `lifeos_sync_tasks()` a second time — expected: `"No tasks pending sync."` (deduplication works).

- [ ] **Step 6: Run full test suite one more time**

```bash
uv run pytest -v
```

Expected: all tests pass.

---

## Phase 2 exit criteria

- [ ] `lifeos_briefing` returns a vault-grounded morning briefing
- [ ] `lifeos_ask` with the same `session_id` references prior turns in the same session
- [ ] `lifeos_commit` persists across `make stop && make start`
- [ ] `lifeos_sync_tasks` creates a Linear issue from a `#to-linear` vault task and deduplicates on second call
- [ ] All unit tests pass (`uv run pytest -v`)
