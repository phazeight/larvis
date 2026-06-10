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
