# src/repo/item_repo.py
from __future__ import annotations

import sqlite3

from typing import Any
from utils.time_kst import now_kst


def search_items(conn: sqlite3.Connection, guild_id: int, query: str, limit: int = 20) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []

    like = f"%{q}%"

    rows = conn.execute(
        """
        SELECT
            i.id,
            i.name,
            i.code,
            i.qty,
            COALESCE(c.name, '기타') AS category_name,
            i.note,
            i.storage_location
        FROM items i
        LEFT JOIN categories c
          ON c.id = i.category_id AND c.guild_id = i.guild_id
        WHERE i.guild_id = ?
          AND i.is_active = 1
          AND (
            i.name LIKE ?
            OR COALESCE(i.code, '') LIKE ?
          )
        ORDER BY
          CASE WHEN i.name LIKE ? THEN 0 ELSE 1 END,
          i.name ASC
        LIMIT ?
        """,
        (guild_id, like, like, f"{q}%", limit),
    ).fetchall()

    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            out.append(dict(r))
        except Exception:
            out.append(
                {
                    "id": r[0],
                    "name": r[1],
                    "code": r[2],
                    "qty": r[3],
                    "category_name": r[4],
                    "note": r[5],
                    "storage_location": r[6],
                }
            )
    return out


def create_item(
    conn: sqlite3.Connection,
    guild_id: int,
    category_id: int,
    name: str,
    code: str | None,
    qty: int,
    note: str | None,
    storage_location: str | None,
) -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")

    code = (code or "").strip() or None

    # ✅ items.note / items.storage_location 가 NOT NULL일 수 있으니 ''로 저장
    note = (note or "").strip()
    storage_location = (storage_location or "").strip()

    k = now_kst()

    cur = conn.execute(
        """
        INSERT INTO items (
            guild_id, category_id, name, code, qty,
            note, storage_location,
            is_active, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (guild_id, category_id, name, code, qty, note, storage_location, k.kst_text, k.kst_text),
    )
    conn.commit()
    return int(cur.lastrowid)


def deactivate_item(conn: sqlite3.Connection, guild_id: int, item_id: int, reason: str):
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("사유를 입력해 주세요.")

    row = conn.execute(
        "SELECT id, name, code, qty, is_active FROM items WHERE guild_id=? AND id=? LIMIT 1",
        (guild_id, item_id),
    ).fetchone()
    if not row:
        raise ValueError("품목을 찾지 못했어요.")
    if int(row[4]) == 0:
        raise ValueError("이미 비활성화된 품목이에요.")

    k = now_kst()
    with conn:
        conn.execute(
            "UPDATE items SET is_active=0, deactivated_at=?, updated_at=? WHERE guild_id=? AND id=?",
            (k.kst_text, k.kst_text, guild_id, item_id),
        )
    return {"id": row[0], "name": row[1], "code": row[2], "qty": row[3], "kst_text": k.kst_text}