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
