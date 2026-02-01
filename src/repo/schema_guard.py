# src/repo/schema_guard.py
from __future__ import annotations

import sqlite3


def _has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == col for r in rows)


def ensure_categories_schema(conn: sqlite3.Connection):
    # categories.deactivated_at (optional)
    if not _has_column(conn, "categories", "deactivated_at"):
        conn.execute("ALTER TABLE categories ADD COLUMN deactivated_at TEXT")
    # categories.created_at / updated_at should exist in current schema,
    # but older DB may not have them.
    if not _has_column(conn, "categories", "created_at"):
        conn.execute("ALTER TABLE categories ADD COLUMN created_at TEXT")
    if not _has_column(conn, "categories", "updated_at"):
        conn.execute("ALTER TABLE categories ADD COLUMN updated_at TEXT")
    # sort_order is nice-to-have
    if not _has_column(conn, "categories", "sort_order"):
        conn.execute("ALTER TABLE categories ADD COLUMN sort_order INTEGER DEFAULT 999")
    conn.commit()


def ensure_items_schema(conn: sqlite3.Connection):
    # items.image_url (대표 이미지 URL)
    if not _has_column(conn, "items", "image_url"):
        conn.execute("ALTER TABLE items ADD COLUMN image_url TEXT")
    # items.storage_location (이전 스키마 호환)
    if not _has_column(conn, "items", "storage_location"):
        conn.execute("ALTER TABLE items ADD COLUMN storage_location TEXT")
    # items.note (이전 스키마 호환)
    if not _has_column(conn, "items", "note"):
        conn.execute("ALTER TABLE items ADD COLUMN note TEXT NOT NULL DEFAULT ''")
    conn.commit()
