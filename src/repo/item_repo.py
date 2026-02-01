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
    image_url: str | None = None,
) -> int:
    """품목 생성. 반환값: 생성된 item_id"""
    k = now_kst().kst_text
    cur = conn.execute(
        """
        INSERT INTO items (
            guild_id, category_id, name, code, qty, warn_below, note, storage_location,
            image_url,
            is_active, created_at, updated_at
        )
        VALUES (?,?,?,?,?,?,?,?,?,1,?,?)
        """,
        (
            guild_id,
            category_id,
            (name or "").strip(),
            (code or "").strip() or None,
            int(qty),
            int(warn_below),
            (note or "").strip(),
            (storage_location or "").strip(),
            (image_url or "").strip(),
            k,
            k,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


# 과거 코드 호환: UI/다른 모듈이 create_item을 import하는 경우가 있어 alias 제공
def create_item(
    conn: sqlite3.Connection,
    guild_id: int,
    category_id: int,
    name: str,
    code: str | None = None,
    qty: int = 0,
    warn_below: int = 0,
    note: str = "",
    storage_location: str = "",
    image_url: str | None = None,
) -> int:
    return add_item(
        conn,
        guild_id=guild_id,
        category_id=category_id,
        name=name,
        code=code,
        qty=qty,
        warn_below=warn_below,
        note=note,
        storage_location=storage_location,
        image_url=image_url,
    )


def search_items(conn: sqlite3.Connection, guild_id: int, keyword: str, limit: int = 20) -> list[dict]:
    kw = f"%{(keyword or '').strip()}%"
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
          AND (i.name LIKE ? OR IFNULL(i.code,'') LIKE ?)
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


def deactivate_item(conn: sqlite3.Connection, guild_id: int, item_id: int, reason: str = ""):
    """품목 비활성화(삭제 대체). reason은 UI/로그용 (DB 컬럼은 현재 없음)."""
    k = now_kst().kst_text
    conn.execute(
        "UPDATE items SET is_active=0, deactivated_at=?, updated_at=? WHERE guild_id=? AND id=?",
        (k, k, guild_id, item_id),
    )
    conn.commit()


def reactivate_item(conn: sqlite3.Connection, guild_id: int, item_id: int):
    k = now_kst().kst_text
    conn.execute(
        "UPDATE items SET is_active=1, deactivated_at=NULL, updated_at=? WHERE guild_id=? AND id=?",
        (k, guild_id, item_id),
    )
    conn.commit()


def set_item_image(conn: sqlite3.Connection, guild_id: int, item_id: int, image_url: str | None):
    k = now_kst().kst_text
    conn.execute(
        "UPDATE items SET image_url=?, updated_at=? WHERE guild_id=? AND id=?",
        ((image_url or "").strip(), k, guild_id, item_id),
    )
    conn.commit()


def search_items_inactive(conn: sqlite3.Connection, guild_id: int, keyword: str, limit: int = 20) -> list[dict]:
    kw = f"%{(keyword or '').strip()}%"
    rows = conn.execute(
        """
        SELECT i.id, i.name, i.code, i.qty, i.note, i.storage_location,
               COALESCE(c.name,'기타') AS category_name,
               i.image_url
        FROM items i
        LEFT JOIN categories c ON c.id=i.category_id
        WHERE i.guild_id=? AND i.is_active=0 AND (i.name LIKE ? OR IFNULL(i.code,'') LIKE ?)
        ORDER BY i.updated_at DESC
        LIMIT ?
        """,
        (guild_id, kw, kw, limit),
    ).fetchall()

    out: list[dict] = []
    for r in rows:
        # sqlite3 row_factory가 꺼져 있으면 tuple일 수 있음
        if isinstance(r, dict):
            out.append(r)
        else:
            keys = ["id","name","code","qty","note","storage_location","category_name","image_url"]
            out.append({keys[i]: r[i] for i in range(len(keys))})
    return out
