# src/repo/category_repo.py
from __future__ import annotations

import sqlite3
from typing import Any

from utils.time_kst import now_kst

ETC_CATEGORY_NAME = "기타"


def list_categories(conn: sqlite3.Connection, guild_id: int, include_inactive: bool = False) -> list[dict]:
    sql = (
        "SELECT id, name, is_active, deactivated_at, sort_order, created_at, updated_at "
        "FROM categories WHERE guild_id=? "
    )
    params: list[Any] = [guild_id]
    if not include_inactive:
        sql += "AND is_active=1 "
    sql += "ORDER BY sort_order ASC, name ASC"
    rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": r[0],
                "name": r[1],
                "is_active": r[2],
                "deactivated_at": r[3],
                "sort_order": r[4],
                "created_at": r[5],
                "updated_at": r[6],
            }
        )
    return out


def get_or_create_etc_category(conn: sqlite3.Connection, guild_id: int) -> int:
    row = conn.execute(
        "SELECT id FROM categories WHERE guild_id=? AND name=?",
        (guild_id, ETC_CATEGORY_NAME),
    ).fetchone()
    if row:
        return int(row[0])

    k = now_kst().kst_text
    cur = conn.execute(
        "INSERT INTO categories (guild_id, name, is_active, deactivated_at, sort_order, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (guild_id, ETC_CATEGORY_NAME, 1, None, 0, k, k),
    )
    conn.commit()
    return int(cur.lastrowid)


def create_or_reactivate_category(conn: sqlite3.Connection, guild_id: int, name: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("카테고리명을 입력해 주세요.")

    row = conn.execute(
        "SELECT id, is_active FROM categories WHERE guild_id=? AND name=?",
        (guild_id, name),
    ).fetchone()

    k = now_kst().kst_text

    if row:
        cat_id, is_active = int(row[0]), int(row[1])
        if is_active == 1:
            return {"id": cat_id, "name": name, "reactivated": False}

        conn.execute(
            "UPDATE categories SET is_active=1, deactivated_at=NULL, updated_at=? WHERE id=?",
            (k, cat_id),
        )
        conn.commit()
        return {"id": cat_id, "name": name, "reactivated": True}

    cur = conn.execute(
        "INSERT INTO categories (guild_id, name, is_active, deactivated_at, sort_order, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (guild_id, name, 1, None, 999, k, k),
    )
    conn.commit()
    return {"id": int(cur.lastrowid), "name": name, "reactivated": False}


def deactivate_category_and_move_items_to_etc(conn: sqlite3.Connection, guild_id: int, category_id: int) -> dict:
    # etc는 비활성 금지
    etc_id = get_or_create_etc_category(conn, guild_id)
    if int(category_id) == int(etc_id):
        raise ValueError("'기타' 카테고리는 비활성화할 수 없어요.")

    row = conn.execute(
        "SELECT id, name, is_active FROM categories WHERE guild_id=? AND id=?",
        (guild_id, category_id),
    ).fetchone()
    if not row:
        raise ValueError("카테고리를 찾지 못했어요.")

    cat_name = str(row[1])
    if int(row[2]) == 0:
        return {"id": int(row[0]), "name": cat_name, "already": True, "moved": 0}

    # 품목 이동(비활성 카테고리의 품목은 기타로)
    moved = conn.execute(
        "UPDATE items SET category_id=?, updated_at=? WHERE guild_id=? AND category_id=?",
        (etc_id, now_kst().kst_text, guild_id, category_id),
    ).rowcount

    k = now_kst().kst_text
    conn.execute(
        "UPDATE categories SET is_active=0, deactivated_at=?, updated_at=? WHERE guild_id=? AND id=?",
        (k, k, guild_id, category_id),
    )
    conn.commit()
    return {"id": int(row[0]), "name": cat_name, "already": False, "moved": moved}
