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
