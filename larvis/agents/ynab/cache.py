import sqlite3
from datetime import datetime, timezone
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
            (budget_id, server_knowledge, datetime.now(timezone.utc).isoformat()),
        )


def is_synced() -> bool:
    with _conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM sync_meta").fetchone()
    return row["n"] > 0


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
