# src/repo/item_repo.py
from __future__ import annotations

import sqlite3
from utils.time_kst import now_kst


def add_item(
    conn: sqlite3.Connection,
    guild_id: int,
    category_id: int,
    name: str,
    code: str | None = None,
    qty: int = 0,
    warn_below: int = 0,
    note: str = "",
    storage_location: str = "",
):
    k = now_kst().kst_text
    conn.execute(
        """
        INSERT INTO items (
            guild_id, category_id, name, code, qty, warn_below, note, storage_location,
            is_active, created_at, updated_at
        )
        VALUES (?,?,?,?,?,?,?,?,1,?,?)
        """,
        (guild_id, category_id, name, code, qty, warn_below, note, storage_location, k, k),
    )
    conn.commit()


def search_items(conn: sqlite3.Connection, guild_id: int, keyword: str, limit: int = 20) -> list[dict]:
    kw = f"%{keyword.strip()}%"
    rows = conn.execute(
        """
        SELECT
            i.id, i.name, i.code, i.image_url,
            i.qty, c.name AS category_name,
            i.note, i.storage_location
        FROM items i
        LEFT JOIN categories c ON c.id=i.category_id
        WHERE i.guild_id=?
          AND i.is_active=1
          AND (i.name LIKE ? OR i.code LIKE ?)
        ORDER BY i.name ASC
        LIMIT ?
        """,
        (guild_id, kw, kw, limit),
    ).fetchall()

    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "id": r[0],
                "name": r[1],
                "code": r[2],
                "image_url": r[3],
                "qty": r[4],
                "category_name": r[5],
                "note": r[6],
                "storage_location": r[7],
            }
        )
    return out


def deactivate_item(conn: sqlite3.Connection, guild_id: int, item_id: int, reason: str):
    k = now_kst().kst_text
    conn.execute(
        "UPDATE items SET is_active=0, deactivated_at=?, updated_at=? WHERE guild_id=? AND id=?",
        (reason, k, guild_id, item_id),
    )
    conn.commit()
