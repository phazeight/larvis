# Larvis Phase 3 — YNAB Financial Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a YNAB Financial Agent with four MCP tools (ynab_sync, ynab_status, ynab_ask, ynab_upcoming) that cache YNAB budget data locally in SQLite and answer natural language questions with Python-computed facts narrated by Ollama.

**Architecture:** A new `larvis/agents/ynab/` package follows the Phase 2 agent pattern. `client.py` fetches from the YNAB REST API via `httpx` (already in the project) into a local SQLite cache at `.ynab/cache.db`. `tools.py` assembles structured context from the cache; Python handles all math and Ollama handles narration only.

**Tech Stack:** Python 3.12, httpx (YNAB REST API), sqlite3 (cache), ollama (narration), FastMCP (MCP registration). No new dependencies — httpx is already in `pyproject.toml`.

**Spec:** `docs/superpowers/specs/2026-06-10-larvis-phase3-design.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `larvis/agents/ynab/__init__.py` | Package marker |
| Create | `larvis/agents/ynab/cache.py` | SQLite schema (6 tables), upsert + read helpers |
| Create | `larvis/agents/ynab/client.py` | YNAB REST API fetch → cache upsert |
| Create | `larvis/agents/ynab/tools.py` | 4 MCP tool functions |
| Create | `tests/test_ynab_cache.py` | Unit tests for cache.py |
| Create | `tests/test_ynab_tools.py` | Unit tests for tools.py |
| Modify | `larvis/config.py` | Add `ynab_api_key`, `ynab_budget_id` fields |
| Modify | `larvis/server.py` | Register 4 ynab tools |
| Modify | `pyproject.toml` | No new deps needed — httpx already present |
| Modify | `.env.example` | Add YNAB_API_KEY, YNAB_BUDGET_ID |
| Modify | `docker-compose.yml` | Add YNAB env vars + `.ynab/` bind mount |
| Modify | `.gitignore` | Ignore `.ynab/cache.db` |
| Modify | `CLAUDE.md` | Document ynab tools + config |

---

## Task 1: Scaffold — init files, config, env, gitignore

**Files:**
- Create: `larvis/agents/ynab/__init__.py`
- Modify: `larvis/config.py`
- Modify: `.env.example`
- Modify: `.gitignore`

- [ ] **Step 1: Create the ynab agent package marker**

```bash
touch /Users/phazeight/repos/larvis/larvis/agents/ynab/__init__.py
```

- [ ] **Step 2: Add YNAB config fields to `larvis/config.py`**

Open `larvis/config.py`. Replace the entire file with:

```python
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    vault_path: Path
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_embed_model: str = "nomic-embed-text"
    chroma_host: str = "http://localhost:8000"
    chroma_collection: str = "vault"
    rag_top_k: int = 5
    chunk_size: int = 500
    chunk_overlap: int = 50
    ynab_api_key: str = ""
    ynab_budget_id: str = "last-used"


settings = Settings()
```

- [ ] **Step 3: Add YNAB vars to `.env.example`**

Append to `.env.example`:

```
# YNAB Financial Agent (Phase 3)
# Generate at: YNAB → Account Settings → Developer Settings → Personal Access Tokens
YNAB_API_KEY=
YNAB_BUDGET_ID=last-used
```

- [ ] **Step 4: Add `.ynab/` to `.gitignore`**

Append to `.gitignore`:

```
.ynab/cache.db
```

- [ ] **Step 5: Verify config loads with new fields**

```bash
cd /Users/phazeight/repos/larvis
uv run python -c "from larvis.config import settings; print(settings.ynab_budget_id)"
```

Expected output: `last-used`

- [ ] **Step 6: Commit**

```bash
git add larvis/agents/ynab/__init__.py larvis/config.py .env.example .gitignore
git commit -m "chore: scaffold ynab agent package + config fields"
```

---

## Task 2: cache.py — schema + write helpers (TDD)

**Files:**
- Create: `larvis/agents/ynab/cache.py`
- Create: `tests/test_ynab_cache.py`

- [ ] **Step 1: Write failing tests for schema creation and write helpers**

Create `tests/test_ynab_cache.py`:

```python
import larvis.agents.ynab.cache as cache


def test_tables_created(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    conn = cache._conn()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert {"accounts", "categories", "transactions", "scheduled", "months", "sync_meta"} == tables


def test_upsert_accounts(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    cache.upsert_accounts([
        {"id": "a1", "name": "Checking", "type": "checking",
         "balance": 100000, "cleared_balance": 100000, "on_budget": True, "deleted": False},
    ])
    with cache._conn() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id = 'a1'").fetchone()
    assert row["name"] == "Checking"
    assert row["balance"] == 100000


def test_upsert_accounts_replaces_on_conflict(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    cache.upsert_accounts([
        {"id": "a1", "name": "Checking", "type": "checking",
         "balance": 100000, "cleared_balance": 100000, "on_budget": True, "deleted": False},
    ])
    cache.upsert_accounts([
        {"id": "a1", "name": "Checking", "type": "checking",
         "balance": 200000, "cleared_balance": 200000, "on_budget": True, "deleted": False},
    ])
    with cache._conn() as conn:
        rows = conn.execute("SELECT * FROM accounts WHERE id = 'a1'").fetchall()
    assert len(rows) == 1
    assert rows[0]["balance"] == 200000


def test_upsert_categories(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    cache.upsert_categories([
        {"id": "c1", "category_group_name": "Food", "name": "Groceries",
         "budgeted": 50000, "activity": -35000, "balance": 15000, "deleted": False},
    ], "2026-06-01")
    with cache._conn() as conn:
        row = conn.execute("SELECT * FROM categories WHERE id = 'c1'").fetchone()
    assert row["name"] == "Groceries"
    assert row["month"] == "2026-06-01"
    assert row["budgeted"] == 50000


def test_upsert_categories_composite_key(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    cache.upsert_categories([
        {"id": "c1", "category_group_name": "Food", "name": "Groceries",
         "budgeted": 50000, "activity": -35000, "balance": 15000, "deleted": False},
    ], "2026-05-01")
    cache.upsert_categories([
        {"id": "c1", "category_group_name": "Food", "name": "Groceries",
         "budgeted": 60000, "activity": -20000, "balance": 40000, "deleted": False},
    ], "2026-06-01")
    with cache._conn() as conn:
        rows = conn.execute("SELECT * FROM categories WHERE id = 'c1' ORDER BY month").fetchall()
    assert len(rows) == 2
    assert rows[0]["month"] == "2026-05-01"
    assert rows[1]["month"] == "2026-06-01"


def test_upsert_transactions(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    cache.upsert_transactions([
        {"id": "t1", "date": "2026-06-05", "amount": -35000,
         "payee_name": "Whole Foods", "category_name": "Groceries",
         "memo": None, "cleared": "cleared", "deleted": False},
    ])
    with cache._conn() as conn:
        row = conn.execute("SELECT * FROM transactions WHERE id = 't1'").fetchone()
    assert row["payee_name"] == "Whole Foods"
    assert row["amount"] == -35000


def test_upsert_scheduled(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    cache.upsert_scheduled([
        {"id": "s1", "frequency": "monthly", "date_next": "2026-06-15",
         "amount": -100000, "payee_name": "Netflix",
         "category_name": "Subscriptions", "memo": None},
    ])
    with cache._conn() as conn:
        row = conn.execute("SELECT * FROM scheduled WHERE id = 's1'").fetchone()
    assert row["payee_name"] == "Netflix"
    assert row["next_date"] == "2026-06-15"


def test_upsert_month(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    cache.upsert_month({
        "month": "2026-06-01", "income": 500000, "budgeted": 450000,
        "activity": -300000, "to_be_budgeted": 50000, "age_of_money": 30,
    })
    with cache._conn() as conn:
        row = conn.execute("SELECT * FROM months WHERE month = '2026-06-01'").fetchone()
    assert row["to_be_budgeted"] == 50000
    assert row["age_of_money"] == 30


def test_update_sync_meta(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    cache.update_sync_meta("budget-123", 9876)
    with cache._conn() as conn:
        row = conn.execute("SELECT * FROM sync_meta WHERE budget_id = 'budget-123'").fetchone()
    assert row["last_knowledge_of_server"] == 9876
    assert row["synced_at"] is not None


def test_is_synced_false_initially(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    assert cache.is_synced() is False


def test_is_synced_true_after_sync_meta(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    cache.update_sync_meta("budget-123", 1)
    assert cache.is_synced() is True
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
cd /Users/phazeight/repos/larvis
uv run pytest tests/test_ynab_cache.py -v 2>&1 | head -30
```

Expected: errors importing `larvis.agents.ynab.cache`

- [ ] **Step 3: Implement `cache.py` — schema + write helpers**

Create `larvis/agents/ynab/cache.py`:

```python
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / ".ynab" / "cache.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            name TEXT,
            type TEXT,
            balance INTEGER,
            cleared_balance INTEGER,
            on_budget INTEGER,
            deleted INTEGER
        );
        CREATE TABLE IF NOT EXISTS categories (
            id TEXT,
            month TEXT,
            group_name TEXT,
            name TEXT,
            budgeted INTEGER,
            activity INTEGER,
            balance INTEGER,
            deleted INTEGER,
            PRIMARY KEY (id, month)
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            date TEXT,
            amount INTEGER,
            payee_name TEXT,
            category_name TEXT,
            memo TEXT,
            cleared TEXT,
            deleted INTEGER
        );
        CREATE TABLE IF NOT EXISTS scheduled (
            id TEXT PRIMARY KEY,
            frequency TEXT,
            next_date TEXT,
            amount INTEGER,
            payee_name TEXT,
            category_name TEXT,
            memo TEXT
        );
        CREATE TABLE IF NOT EXISTS months (
            month TEXT PRIMARY KEY,
            income INTEGER DEFAULT 0,
            budgeted INTEGER DEFAULT 0,
            activity INTEGER DEFAULT 0,
            to_be_budgeted INTEGER DEFAULT 0,
            age_of_money INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sync_meta (
            budget_id TEXT PRIMARY KEY,
            last_knowledge_of_server INTEGER DEFAULT 0,
            synced_at TEXT
        );
    """)
    conn.commit()


def upsert_accounts(accounts: list[dict]) -> None:
    with _conn() as conn:
        for a in accounts:
            conn.execute(
                "INSERT OR REPLACE INTO accounts VALUES (?,?,?,?,?,?,?)",
                (a["id"], a["name"], a["type"], a["balance"], a["cleared_balance"],
                 int(a.get("on_budget", False)), int(a.get("deleted", False))),
            )


def upsert_categories(categories: list[dict], month: str) -> None:
    with _conn() as conn:
        for c in categories:
            conn.execute(
                "INSERT OR REPLACE INTO categories VALUES (?,?,?,?,?,?,?,?)",
                (c["id"], month, c.get("category_group_name", ""), c["name"],
                 c.get("budgeted", 0), c.get("activity", 0), c.get("balance", 0),
                 int(c.get("deleted", False))),
            )


def upsert_transactions(transactions: list[dict]) -> None:
    with _conn() as conn:
        for t in transactions:
            conn.execute(
                "INSERT OR REPLACE INTO transactions VALUES (?,?,?,?,?,?,?,?)",
                (t["id"], t["date"], t["amount"], t.get("payee_name") or "",
                 t.get("category_name") or "", t.get("memo") or "",
                 t.get("cleared", ""), int(t.get("deleted", False))),
            )


def upsert_scheduled(scheduled: list[dict]) -> None:
    with _conn() as conn:
        for s in scheduled:
            conn.execute(
                "INSERT OR REPLACE INTO scheduled VALUES (?,?,?,?,?,?,?)",
                (s["id"], s.get("frequency", ""), s.get("date_next", ""),
                 s.get("amount", 0), s.get("payee_name") or "",
                 s.get("category_name") or "", s.get("memo") or ""),
            )


def upsert_month(month: dict) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO months VALUES (?,?,?,?,?,?)",
            (month["month"], month.get("income", 0), month.get("budgeted", 0),
             month.get("activity", 0), month.get("to_be_budgeted", 0),
             month.get("age_of_money", 0)),
        )


def update_sync_meta(budget_id: str, server_knowledge: int) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sync_meta VALUES (?,?,?)",
            (budget_id, server_knowledge, datetime.utcnow().isoformat()),
        )


def is_synced() -> bool:
    with _conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM sync_meta").fetchone()
    return row["n"] > 0
```

- [ ] **Step 4: Run write helper tests — expect all pass**

```bash
uv run pytest tests/test_ynab_cache.py -v 2>&1 | tail -20
```

Expected: all 12 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add larvis/agents/ynab/cache.py tests/test_ynab_cache.py
git commit -m "feat: ynab cache schema + write helpers (TDD)"
```

---

## Task 3: cache.py — read helpers (TDD)

**Files:**
- Modify: `larvis/agents/ynab/cache.py`
- Modify: `tests/test_ynab_cache.py`

- [ ] **Step 1: Add failing tests for read helpers**

Append to `tests/test_ynab_cache.py`:

```python
def test_get_accounts_excludes_deleted_and_off_budget(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    cache.upsert_accounts([
        {"id": "a1", "name": "Checking", "type": "checking",
         "balance": 100000, "cleared_balance": 100000, "on_budget": True, "deleted": False},
        {"id": "a2", "name": "Savings", "type": "savings",
         "balance": 500000, "cleared_balance": 500000, "on_budget": False, "deleted": False},
        {"id": "a3", "name": "Old", "type": "checking",
         "balance": 0, "cleared_balance": 0, "on_budget": True, "deleted": True},
    ])
    accounts = cache.get_accounts()
    assert len(accounts) == 1
    assert accounts[0]["name"] == "Checking"


def test_get_categories_filters_by_month_and_deleted(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    cache.upsert_categories([
        {"id": "c1", "category_group_name": "Food", "name": "Groceries",
         "budgeted": 50000, "activity": -35000, "balance": 15000, "deleted": False},
        {"id": "c2", "category_group_name": "Food", "name": "Dining",
         "budgeted": 20000, "activity": -25000, "balance": -5000, "deleted": True},
    ], "2026-06-01")
    cache.upsert_categories([
        {"id": "c1", "category_group_name": "Food", "name": "Groceries",
         "budgeted": 40000, "activity": -10000, "balance": 30000, "deleted": False},
    ], "2026-05-01")
    cats = cache.get_categories("2026-06-01")
    assert len(cats) == 1
    assert cats[0]["name"] == "Groceries"
    assert cats[0]["budgeted"] == 50000


def test_get_transactions_filters_by_date(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    cache.upsert_transactions([
        {"id": "t1", "date": "2026-06-05", "amount": -35000,
         "payee_name": "Whole Foods", "category_name": "Groceries",
         "memo": None, "cleared": "cleared", "deleted": False},
        {"id": "t2", "date": "2026-04-01", "amount": -10000,
         "payee_name": "Old Store", "category_name": "Shopping",
         "memo": None, "cleared": "cleared", "deleted": False},
        {"id": "t3", "date": "2026-06-01", "amount": -5000,
         "payee_name": "Gas Station", "category_name": "Auto",
         "memo": None, "cleared": "cleared", "deleted": True},
    ])
    txns = cache.get_transactions("2026-05-01")
    assert len(txns) == 1
    assert txns[0]["payee_name"] == "Whole Foods"


def test_get_scheduled_filters_within_days(monkeypatch, tmp_path):
    from datetime import date, timedelta
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    today = date.today()
    soon = (today + timedelta(days=7)).isoformat()
    far = (today + timedelta(days=30)).isoformat()
    past = (today - timedelta(days=1)).isoformat()
    cache.upsert_scheduled([
        {"id": "s1", "frequency": "monthly", "date_next": soon,
         "amount": -100000, "payee_name": "Netflix",
         "category_name": "Subscriptions", "memo": None},
        {"id": "s2", "frequency": "monthly", "date_next": far,
         "amount": -50000, "payee_name": "Annual Fee",
         "category_name": "Fees", "memo": None},
        {"id": "s3", "frequency": "monthly", "date_next": past,
         "amount": -20000, "payee_name": "Old Bill",
         "category_name": "Bills", "memo": None},
    ])
    upcoming = cache.get_scheduled(within_days=14)
    assert len(upcoming) == 1
    assert upcoming[0]["payee_name"] == "Netflix"


def test_get_month_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    cache.upsert_month({
        "month": "2026-06-01", "income": 500000, "budgeted": 450000,
        "activity": -300000, "to_be_budgeted": 50000, "age_of_money": 30,
    })
    summary = cache.get_month_summary("2026-06-01")
    assert summary["income"] == 500000
    assert summary["to_be_budgeted"] == 50000
    assert summary["age_of_money"] == 30


def test_get_month_summary_returns_zeros_if_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    summary = cache.get_month_summary("2026-01-01")
    assert summary["to_be_budgeted"] == 0
    assert summary["age_of_money"] == 0
```

- [ ] **Step 2: Run new tests — expect 6 failures**

```bash
uv run pytest tests/test_ynab_cache.py -v -k "get_accounts or get_categories or get_transactions or get_scheduled or get_month" 2>&1 | tail -15
```

Expected: 6 failures (AttributeError on missing functions)

- [ ] **Step 3: Implement read helpers — append to `larvis/agents/ynab/cache.py`**

```python
def get_accounts() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM accounts WHERE deleted = 0 AND on_budget = 1"
        ).fetchall()
    return [dict(r) for r in rows]


def get_categories(month: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM categories WHERE month = ? AND deleted = 0",
            (month,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_transactions(since_date: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE date >= ? AND deleted = 0 ORDER BY date DESC",
            (since_date,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_scheduled(within_days: int = 14) -> list[dict]:
    from datetime import date, timedelta
    today = date.today().isoformat()
    cutoff = (date.today() + timedelta(days=within_days)).isoformat()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled WHERE next_date >= ? AND next_date <= ? ORDER BY next_date",
            (today, cutoff),
        ).fetchall()
    return [dict(r) for r in rows]


def get_month_summary(month: str) -> dict:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM months WHERE month = ?", (month,)
        ).fetchone()
    if row is None:
        return {"month": month, "income": 0, "budgeted": 0,
                "activity": 0, "to_be_budgeted": 0, "age_of_money": 0}
    return dict(row)
```

- [ ] **Step 4: Run all cache tests — expect all pass**

```bash
uv run pytest tests/test_ynab_cache.py -v
```

Expected: all 18 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add larvis/agents/ynab/cache.py tests/test_ynab_cache.py
git commit -m "feat: ynab cache read helpers (TDD)"
```

---

## Task 4: client.py — YNAB API sync

**Files:**
- Create: `larvis/agents/ynab/client.py`

No unit tests for client.py — it makes live HTTP calls. Integration-tested in Task 8 smoke test.

- [ ] **Step 1: Create `larvis/agents/ynab/client.py`**

```python
from dataclasses import dataclass
from datetime import date, timedelta

import httpx

from larvis.agents.ynab import cache

YNAB_BASE = "https://api.ynab.com/v1"


@dataclass
class SyncResult:
    accounts: int
    categories: int
    transactions: int
    scheduled: int


def sync_budget(api_key: str, budget_id: str) -> SyncResult:
    current_month = date.today().strftime("%Y-%m-01")
    since_date = (date.today() - timedelta(days=90)).isoformat()
    headers = {"Authorization": f"Bearer {api_key}"}

    with httpx.Client(timeout=30) as client:
        # Accounts
        r = client.get(f"{YNAB_BASE}/budgets/{budget_id}/accounts", headers=headers)
        r.raise_for_status()
        accounts_data = [a for a in r.json()["data"]["accounts"] if not a.get("deleted")]

        # Current month detail (categories + month summary)
        r = client.get(
            f"{YNAB_BASE}/budgets/{budget_id}/months/{current_month}", headers=headers
        )
        r.raise_for_status()
        month_data = r.json()["data"]["month"]
        categories_data = month_data.get("categories", [])

        # Transactions (last 90 days, with delta)
        last_knowledge = _get_last_knowledge(budget_id)
        params: dict = {"since_date": since_date}
        if last_knowledge:
            params["last_knowledge_of_server"] = last_knowledge
        r = client.get(
            f"{YNAB_BASE}/budgets/{budget_id}/transactions",
            headers=headers,
            params=params,
        )
        r.raise_for_status()
        txn_resp = r.json()["data"]
        transactions_data = txn_resp["transactions"]
        server_knowledge = txn_resp.get("server_knowledge", 0)

        # Scheduled transactions
        r = client.get(
            f"{YNAB_BASE}/budgets/{budget_id}/scheduled_transactions", headers=headers
        )
        r.raise_for_status()
        scheduled_data = [
            s for s in r.json()["data"]["scheduled_transactions"] if not s.get("deleted")
        ]

    cache.upsert_accounts(accounts_data)
    cache.upsert_categories(categories_data, current_month)
    cache.upsert_month({
        "month": current_month,
        "income": month_data.get("income", 0),
        "budgeted": month_data.get("budgeted", 0),
        "activity": month_data.get("activity", 0),
        "to_be_budgeted": month_data.get("to_be_budgeted", 0),
        "age_of_money": month_data.get("age_of_money", 0),
    })
    cache.upsert_transactions(transactions_data)
    cache.upsert_scheduled(scheduled_data)
    cache.update_sync_meta(budget_id, server_knowledge)

    return SyncResult(
        accounts=len(accounts_data),
        categories=len(categories_data),
        transactions=len(transactions_data),
        scheduled=len(scheduled_data),
    )


def _get_last_knowledge(budget_id: str) -> int:
    import sqlite3
    if not cache.DB_PATH.exists():
        return 0
    try:
        conn = sqlite3.connect(cache.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT last_knowledge_of_server FROM sync_meta WHERE budget_id = ?",
            (budget_id,),
        ).fetchone()
        conn.close()
        return row["last_knowledge_of_server"] if row else 0
    except sqlite3.OperationalError:
        return 0
```

- [ ] **Step 2: Verify import resolves**

```bash
uv run python -c "from larvis.agents.ynab.client import sync_budget; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add larvis/agents/ynab/client.py
git commit -m "feat: ynab api client with delta sync"
```

---

## Task 5: tools.py — ynab_sync + ynab_status (TDD)

**Files:**
- Create: `larvis/agents/ynab/tools.py` (partial — sync + status only)
- Create: `tests/test_ynab_tools.py`

- [ ] **Step 1: Write failing tests for ynab_sync and ynab_status**

Create `tests/test_ynab_tools.py`:

```python
from unittest.mock import patch, MagicMock
import larvis.agents.ynab.cache as cache
import larvis.agents.ynab.tools as tools


def test_ynab_sync_returns_not_configured_if_no_api_key(monkeypatch):
    monkeypatch.setattr("larvis.config.settings.ynab_api_key", "")
    result = tools.sync()
    assert "YNAB_API_KEY" in result


def test_ynab_sync_calls_client_and_returns_counts(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr("larvis.config.settings.ynab_api_key", "test-key")
    monkeypatch.setattr("larvis.config.settings.ynab_budget_id", "budget-1")
    mock_result = MagicMock(accounts=3, categories=42, transactions=187, scheduled=8)
    with patch("larvis.agents.ynab.client.sync_budget", return_value=mock_result):
        result = tools.sync()
    assert "3 accounts" in result
    assert "42 categories" in result
    assert "187 transactions" in result
    assert "8 scheduled" in result


def test_ynab_status_returns_not_synced_if_cache_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    result = tools.status()
    assert "ynab_sync" in result.lower() or "not synced" in result.lower()


def test_ynab_status_returns_formatted_dashboard(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    # Seed cache with test data
    cache.upsert_month({
        "month": "2026-06-01", "income": 500000, "budgeted": 450000,
        "activity": -300000, "to_be_budgeted": 50000, "age_of_money": 30,
    })
    cache.upsert_accounts([
        {"id": "a1", "name": "Checking", "type": "checking",
         "balance": 1000000, "cleared_balance": 1000000, "on_budget": True, "deleted": False},
    ])
    cache.upsert_categories([
        {"id": "c1", "category_group_name": "Food", "name": "Groceries",
         "budgeted": 50000, "activity": -60000, "balance": -10000, "deleted": False},
        {"id": "c2", "category_group_name": "Transport", "name": "Gas",
         "budgeted": 30000, "activity": -20000, "balance": 10000, "deleted": False},
    ], "2026-06-01")
    cache.update_sync_meta("budget-1", 1)
    result = tools.status()
    assert "$50.00" in result          # ready to assign
    assert "$1,000.00" in result       # account total
    assert "Groceries" in result       # over-budget category
    assert "-$10.00" in result         # over-budget amount
    assert "30" in result              # age of money
```

- [ ] **Step 2: Run tests — expect failures**

```bash
uv run pytest tests/test_ynab_tools.py -v 2>&1 | head -20
```

Expected: ImportError (tools module not found)

- [ ] **Step 3: Implement sync() and status() in `larvis/agents/ynab/tools.py`**

Create `larvis/agents/ynab/tools.py`:

```python
from datetime import date

from larvis.agents.ynab import cache, client
from larvis.config import settings


def _fmt(milliunits: int) -> str:
    dollars = milliunits / 1000
    if dollars < 0:
        return f"-${abs(dollars):,.2f}"
    return f"${dollars:,.2f}"


def sync() -> str:
    if not settings.ynab_api_key:
        return "YNAB_API_KEY not configured — add it to .env and restart."
    try:
        result = client.sync_budget(settings.ynab_api_key, settings.ynab_budget_id)
        return (
            f"Synced: {result.accounts} accounts, {result.categories} categories, "
            f"{result.transactions} transactions, {result.scheduled} scheduled."
        )
    except Exception as e:
        return f"Sync failed: {e}"


def status() -> str:
    if not cache.is_synced():
        return "YNAB not synced — call ynab_sync() first."

    current_month = date.today().strftime("%Y-%m-01")
    summary = cache.get_month_summary(current_month)
    accounts = cache.get_accounts()
    categories = cache.get_categories(current_month)

    total_balance = sum(a["balance"] for a in accounts)
    over_budget = sorted(
        [c for c in categories if c["balance"] < 0],
        key=lambda c: c["balance"],
    )

    lines = [
        f"=== Budget Status ({current_month[:7]}) ===",
        f"Ready to Assign:  {_fmt(summary['to_be_budgeted'])}",
        f"Age of Money:     {summary['age_of_money']} days",
        f"On-Budget Total:  {_fmt(total_balance)}",
    ]

    if over_budget:
        lines.append(f"\nOver Budget ({len(over_budget)} categories):")
        for c in over_budget:
            lines.append(f"  {c['group_name']} / {c['name']}: {_fmt(c['balance'])}")
    else:
        lines.append("\nNo categories over budget.")

    return "\n".join(lines)
```

- [ ] **Step 4: Run sync + status tests — expect all pass**

```bash
uv run pytest tests/test_ynab_tools.py -v -k "sync or status"
```

Expected: 4 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add larvis/agents/ynab/tools.py tests/test_ynab_tools.py
git commit -m "feat: ynab_sync + ynab_status tools (TDD)"
```

---

## Task 6: tools.py — ynab_ask + ynab_upcoming (TDD)

**Files:**
- Modify: `larvis/agents/ynab/tools.py`
- Modify: `tests/test_ynab_tools.py`

- [ ] **Step 1: Add failing tests for ynab_ask and ynab_upcoming**

Append to `tests/test_ynab_tools.py`:

```python
def test_ynab_upcoming_returns_not_synced_if_cache_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    result = tools.upcoming()
    assert "not synced" in result.lower()


def test_ynab_upcoming_returns_sorted_bills(monkeypatch, tmp_path):
    from datetime import date, timedelta
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    cache.update_sync_meta("b1", 1)
    soon = (date.today() + timedelta(days=3)).isoformat()
    later = (date.today() + timedelta(days=10)).isoformat()
    cache.upsert_scheduled([
        {"id": "s2", "frequency": "monthly", "date_next": later,
         "amount": -50000, "payee_name": "Rent", "category_name": "Housing", "memo": None},
        {"id": "s1", "frequency": "monthly", "date_next": soon,
         "amount": -100000, "payee_name": "Netflix", "category_name": "Subscriptions", "memo": None},
    ])
    result = tools.upcoming()
    assert "Netflix" in result
    assert "Rent" in result
    netflix_pos = result.index("Netflix")
    rent_pos = result.index("Rent")
    assert netflix_pos < rent_pos   # Netflix is sooner, should appear first


def test_ynab_upcoming_returns_none_due_message(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    cache.update_sync_meta("b1", 1)
    result = tools.upcoming()
    assert "none" in result.lower() or "no scheduled" in result.lower()


def test_ynab_ask_returns_not_synced_if_cache_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    result = tools.ask("how much is left in groceries?")
    assert "not synced" in result.lower()


def test_ynab_ask_returns_structured_data_when_ollama_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "DB_PATH", tmp_path / "test.db")
    cache.update_sync_meta("b1", 1)
    cache.upsert_month({
        "month": "2026-06-01", "income": 500000, "budgeted": 450000,
        "activity": -300000, "to_be_budgeted": 50000, "age_of_money": 30,
    })
    cache.upsert_accounts([
        {"id": "a1", "name": "Checking", "type": "checking",
         "balance": 1000000, "cleared_balance": 1000000, "on_budget": True, "deleted": False},
    ])
    with patch("larvis.agents.ynab.tools.ollama") as mock_ollama:
        mock_ollama.Client.side_effect = Exception("Ollama unavailable")
        result = tools.ask("what is my budget status?")
    # Falls back to raw context — should still have useful data
    assert "Checking" in result or "$1,000.00" in result or "50.00" in result
```

- [ ] **Step 2: Run new tests — expect 5 failures**

```bash
uv run pytest tests/test_ynab_tools.py -v -k "upcoming or ask" 2>&1 | tail -15
```

Expected: AttributeError (upcoming/ask not defined)

- [ ] **Step 3: Add upcoming() and ask() to `larvis/agents/ynab/tools.py`**

Append to `larvis/agents/ynab/tools.py` (after the existing `status()` function):

```python
def upcoming() -> str:
    if not cache.is_synced():
        return "YNAB not synced — call ynab_sync() first."

    bills = cache.get_scheduled(within_days=14)
    if not bills:
        return "No scheduled transactions due in the next 14 days."

    lines = ["=== Upcoming Bills (next 14 days) ==="]
    for b in bills:
        lines.append(
            f"  {b['next_date']}  {b['payee_name'] or 'Unknown'}  "
            f"{_fmt(abs(b['amount']))}  [{b['frequency']}]"
            + (f"  — {b['category_name']}" if b['category_name'] else "")
        )
    return "\n".join(lines)


def ask(query: str) -> str:
    if not cache.is_synced():
        return "YNAB not synced — call ynab_sync() first."

    context = _build_context(query)
    try:
        resp = ollama.Client(host=settings.ollama_host).generate(
            model=settings.ollama_model,
            prompt=(
                "You are a personal finance assistant. Answer the question using ONLY "
                "the budget data below. Do not invent or estimate numbers — if the data "
                "does not contain the answer, say so.\n\n"
                f"Budget data:\n{context}\n\n"
                f"Question: {query}"
            ),
        )
        return resp.response
    except Exception:
        return context


def _build_context(query: str) -> str:
    from datetime import timedelta

    q = query.lower()
    current_month = date.today().strftime("%Y-%m-01")
    parts = []

    # Month summary always included
    summary = cache.get_month_summary(current_month)
    parts.append(
        f"Budget summary ({current_month[:7]}):\n"
        f"  Income: {_fmt(summary['income'])}\n"
        f"  Budgeted: {_fmt(summary['budgeted'])}\n"
        f"  Activity: {_fmt(summary['activity'])}\n"
        f"  Ready to Assign: {_fmt(summary['to_be_budgeted'])}\n"
        f"  Age of Money: {summary['age_of_money']} days"
    )

    # Accounts always included
    accounts = cache.get_accounts()
    if accounts:
        lines = [f"  {a['name']} ({a['type']}): {_fmt(a['balance'])}" for a in accounts]
        parts.append("Account balances:\n" + "\n".join(lines))

    # Categories if budget/spending keywords
    budget_kws = ["budget", "categor", "spend", "left", "remain", "over", "assign",
                  "groceri", "food", "dining", "util", "subscript", "entertain", "how much"]
    if any(kw in q for kw in budget_kws):
        cats = cache.get_categories(current_month)
        if cats:
            lines = [
                f"  {c['group_name']} / {c['name']}: "
                f"budgeted {_fmt(c['budgeted'])}, "
                f"spent {_fmt(abs(c['activity']))}, "
                f"left {_fmt(c['balance'])}"
                for c in cats
            ]
            parts.append("Category budgets this month:\n" + "\n".join(lines))

    # Recent transactions if transaction keywords
    txn_kws = ["transact", "recent", "paid", "bought", "spent at", "purchas", "history", "last month"]
    if any(kw in q for kw in txn_kws):
        since = (date.today() - timedelta(days=30)).isoformat()
        txns = cache.get_transactions(since)[:25]
        if txns:
            lines = [
                f"  {t['date']}  {t['payee_name'] or 'Unknown'} "
                f"[{t['category_name'] or 'Uncategorized'}]: "
                f"{_fmt(abs(t['amount']))}"
                for t in txns
            ]
            parts.append("Recent transactions (last 30 days):\n" + "\n".join(lines))

    return "\n\n".join(parts)
```

Also add the `ollama` import to the top of `tools.py`. The full import block at the top of `tools.py` should be:

```python
from datetime import date

import ollama

from larvis.agents.ynab import cache, client
from larvis.config import settings
```

- [ ] **Step 4: Run all tools tests — expect all pass**

```bash
uv run pytest tests/test_ynab_tools.py -v
```

Expected: all 9 tests PASSED

- [ ] **Step 5: Run full test suite — no regressions**

```bash
uv run pytest -v
```

Expected: all tests PASSED (15 existing + 9 new = 24+)

- [ ] **Step 6: Commit**

```bash
git add larvis/agents/ynab/tools.py tests/test_ynab_tools.py
git commit -m "feat: ynab_ask + ynab_upcoming tools (TDD)"
```

---

## Task 7: Wire into server.py + infra updates

**Files:**
- Modify: `larvis/server.py`
- Modify: `docker-compose.yml`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Register 4 YNAB tools in `larvis/server.py`**

Add the import and four tool registrations. The full updated `server.py`:

```python
from fastmcp import FastMCP

from larvis import rag
from larvis.agents.lifeos import tools as lifeos_tools
from larvis.agents.ynab import tools as ynab_tools
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


@mcp.tool()
def ynab_sync() -> str:
    """Refresh local YNAB cache from the YNAB API (delta sync)."""
    return ynab_tools.sync()


@mcp.tool()
def ynab_status() -> str:
    """Budget dashboard — ready to assign, age of money, account total, over-budget categories."""
    return ynab_tools.status()


@mcp.tool()
def ynab_ask(query: str) -> str:
    """Ask a natural language question about your YNAB budget. Run ynab_sync first."""
    return ynab_tools.ask(query)


@mcp.tool()
def ynab_upcoming() -> str:
    """List scheduled transactions due in the next 14 days."""
    return ynab_tools.upcoming()


def main() -> None:
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8765)
```

- [ ] **Step 2: Update `docker-compose.yml` — add YNAB env vars and bind mount**

The updated larvis service section of `docker-compose.yml`:

```yaml
  larvis:
    build: .
    ports:
      - "8765:8765"
    env_file: .env
    environment:
      OLLAMA_HOST: http://host.docker.internal:11434
      CHROMA_HOST: http://chromadb:8000
      VAULT_PATH: /vault
      LINEAR_API_KEY: ${LINEAR_API_KEY}
      LB_TEAM_KEY: ${LB_TEAM_KEY:-PHA}
      YNAB_API_KEY: ${YNAB_API_KEY}
      YNAB_BUDGET_ID: ${YNAB_BUDGET_ID:-last-used}
    volumes:
      - ${VAULT_PATH}:/vault:ro
      - ./.memory:/app/.memory
      - ./.ynab:/app/.ynab
    depends_on:
      - chromadb
```

- [ ] **Step 3: Update `CLAUDE.md` — add YNAB tools table entry and config**

In `CLAUDE.md`, add the 4 ynab tools to the MCP tools table:

```markdown
| `ynab_sync` | `() -> str` | Refresh local YNAB cache from YNAB API |
| `ynab_status` | `() -> str` | Budget dashboard — TBB, age of money, over-budget |
| `ynab_ask` | `(query: str) -> str` | NL budget query — Python math, Ollama narrates |
| `ynab_upcoming` | `() -> str` | Scheduled transactions due in next 14 days |
```

Add to Known issues table:

```markdown
| YNAB cache empty on first run | Run `ynab_sync()` once to populate — persists across restarts |
```

- [ ] **Step 4: Add `mcp__larvis__ynab_*` to permissions in `.claude/settings.json`**

Open `.claude/settings.json`. Update the allow list:

```json
{
  "permissions": {
    "allow": [
      "mcp__larvis__*"
    ]
  }
}
```

(Already covered by the wildcard — no change needed if it's already `mcp__larvis__*`.)

Verify:
```bash
cat /Users/phazeight/repos/larvis/.claude/settings.json
```

Expected: `"mcp__larvis__*"` is present in the allow list.

- [ ] **Step 5: Commit**

```bash
git add larvis/server.py docker-compose.yml CLAUDE.md
git commit -m "feat: register ynab MCP tools + update docker config"
```

---

## Task 8: Smoke test + Linear tracking

**Files:** No new files. Validates end-to-end with real YNAB API.

- [ ] **Step 1: Add YNAB_API_KEY to your `.env`**

```bash
# In .env, add:
# YNAB_API_KEY=<your Personal Access Token from YNAB → Account Settings → Developer Settings>
# YNAB_BUDGET_ID=last-used
```

Generate the token at: YNAB → Profile → Developer Settings → Personal Access Tokens → New Token.

- [ ] **Step 2: Rebuild and restart containers**

```bash
cd /Users/phazeight/repos/larvis
docker compose down
docker compose build larvis
docker compose up -d
sleep 12
docker compose logs larvis --tail 5
```

Expected: `Application startup complete.`

- [ ] **Step 3: Smoke test — run ynab_sync**

From Claude Code (MCP connected), call:
```
ynab_sync()
```

Expected: `"Synced: N accounts, N categories, N transactions, N scheduled."`

If you see `YNAB_API_KEY not configured`: verify `.env` has the key and container was rebuilt.

- [ ] **Step 4: Smoke test — ynab_status**

```
ynab_status()
```

Expected: formatted dashboard with Ready to Assign amount, Age of Money, on-budget total, and any over-budget categories.

- [ ] **Step 5: Smoke test — ynab_ask**

```
ynab_ask("how much do I have left in groceries this month?")
```

Expected: Ollama-narrated answer referencing the actual Groceries category balance from your budget.

- [ ] **Step 6: Smoke test — ynab_upcoming**

```
ynab_upcoming()
```

Expected: list of bills due in the next 14 days, or "No scheduled transactions due in the next 14 days."

- [ ] **Step 7: Verify cache persists across restart**

```bash
docker compose down && docker compose up -d
sleep 12
```

Then call `ynab_status()` without calling `ynab_sync()` first.

Expected: status still works (data persisted in `.ynab/cache.db` bind mount).

- [ ] **Step 8: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 9: Create Linear tasks for Phase 3 under PHA-52**

In Linear, create sub-issues under PHA-52 for each task (PHA-74 through PHA-81) and mark them Done as each task completes.

- [ ] **Step 10: Final commit**

```bash
git add .
git commit -m "chore: Phase 3 YNAB agent complete — all smoke tests passing"
```
