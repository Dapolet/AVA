import os
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                model TEXT,
                temperature REAL,
                max_tokens INTEGER,
                latency_ms INTEGER,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                cost_usd REAL,
                price_per_1k REAL,
                status TEXT,
                error TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS plugin_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                plugin_id TEXT,
                action TEXT,
                status TEXT,
                error TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                actor TEXT,
                action TEXT,
                details TEXT
            )
        """)
        conn.commit()
        _ensure_columns(conn, "requests", {
            "cost_usd": "REAL",
            "price_per_1k": "REAL"
        })
    finally:
        conn.close()


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: Dict[str, str]) -> None:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}
    for name, col_type in columns.items():
        if name not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")
    conn.commit()


def log_request(
    db_path: str,
    model: str,
    temperature: float,
    max_tokens: int,
    latency_ms: int,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    total_tokens: Optional[int],
    cost_usd: Optional[float],
    price_per_1k: Optional[float],
    status: str,
    error: str
) -> None:
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO requests (
                ts, model, temperature, max_tokens, latency_ms,
                prompt_tokens, completion_tokens, total_tokens,
                cost_usd, price_per_1k, status, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            model,
            temperature,
            max_tokens,
            latency_ms,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            cost_usd,
            price_per_1k,
            status,
            error
        ))
        conn.commit()
    finally:
        conn.close()


def log_plugin_run(
    db_path: str,
    plugin_id: str,
    action: str,
    status: str,
    error: str
) -> None:
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO plugin_runs (ts, plugin_id, action, status, error)
            VALUES (?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            plugin_id,
            action,
            status,
            error
        ))
        conn.commit()
    finally:
        conn.close()


def log_admin_action(
    db_path: str,
    actor: str,
    action: str,
    details: str
) -> None:
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO admin_audit (ts, actor, action, details)
            VALUES (?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            actor,
            action,
            details
        ))
        conn.commit()
    finally:
        conn.close()


def fetch_all(db_path: str, query: str, params: Optional[tuple] = None) -> List[Dict]:
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(query, params or ())
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
