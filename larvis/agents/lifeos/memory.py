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
