# src/repo/schema_guard.py
from __future__ import annotations

import sqlite3

def _has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == col for r in rows)

def ensure_items_schema(conn: sqlite3.Connection):
    """
    기존 DB에 items.image_url 컬럼이 없으면 추가
    (apply_schema 재실행 시 duplicate column 에러 방지용)
    """
    if not _has_column(conn, "items", "image_url"):
        conn.execute("ALTER TABLE items ADD COLUMN image_url TEXT")
        conn.commit()
