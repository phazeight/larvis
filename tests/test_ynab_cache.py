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
