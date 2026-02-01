# src/repo/category_repo.py
from __future__ import annotations

import sqlite3
from typing import Any

from utils.time_kst import now_kst

ETC_CATEGORY_NAME = "기타"


def list_categories(conn: sqlite3.Connection, guild_id: int, include_inactive: bool = False) -> list[dict]:
    # 오래된 DB 호환: 컬럼이 없으면 NULL/기본값으로 대체
    cols = {r[1] for r in conn.execute("PRAGMA table_info(categories)").fetchall()}
    has_deactivated_at = "deactivated_at" in cols
    has_sort_order = "sort_order" in cols

    deact_expr = "deactivated_at" if has_deactivated_at else "NULL AS deactivated_at"
    sort_expr = "sort_order" if has_sort_order else "999 AS sort_order"

    sql = (
        f"SELECT id, name, is_active, {deact_expr}, {sort_expr}, created_at, updated_at "
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
    cols = {r[1] for r in conn.execute("PRAGMA table_info(categories)").fetchall()}
    has_deactivated_at = "deactivated_at" in cols
    has_sort_order = "sort_order" in cols

    fields = ["guild_id", "name", "is_active"]
    values = [guild_id, ETC_CATEGORY_NAME, 1]
    if has_deactivated_at:
        fields.append("deactivated_at")
        values.append(None)
    if has_sort_order:
        fields.append("sort_order")
        values.append(0)
    fields += ["created_at", "updated_at"]
    values += [k, k]

    qs = ",".join(["?"] * len(fields))
    cur = conn.execute(
        f"INSERT INTO categories ({','.join(fields)}) VALUES ({qs})",
        tuple(values),
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

        cols = {r[1] for r in conn.execute("PRAGMA table_info(categories)")}
        if "deactivated_at" in cols:
            conn.execute(
                "UPDATE categories SET is_active=1, deactivated_at=NULL, updated_at=? WHERE id=?",
                (k, cat_id),
            )
        else:
            conn.execute(
                "UPDATE categories SET is_active=1, updated_at=? WHERE id=?",
                (k, cat_id),
            )
        conn.commit()
        return {"id": cat_id, "name": name, "reactivated": True}

    cols = {r[1] for r in conn.execute("PRAGMA table_info(categories)")}
    if "deactivated_at" in cols and "sort_order" in cols:
        cur = conn.execute(
            "INSERT INTO categories (guild_id, name, is_active, deactivated_at, sort_order, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (guild_id, name, 1, None, 999, k, k),
        )
    elif "deactivated_at" in cols:
        cur = conn.execute(
            "INSERT INTO categories (guild_id, name, is_active, deactivated_at, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (guild_id, name, 1, None, k, k),
        )
    else:
        cur = conn.execute(
            "INSERT INTO categories (guild_id, name, is_active, created_at, updated_at) VALUES (?,?,?,?,?)",
            (guild_id, name, 1, k, k),
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

    # 먼저 이동 대상 품목 ID 목록 확보(로그를 위해)
    item_rows = conn.execute(
        "SELECT id FROM items WHERE guild_id=? AND category_id=? AND is_active=1",
        (guild_id, category_id),
    ).fetchall()
    moved_item_ids = [int(r[0]) for r in item_rows]

    # 품목 이동(비활성 카테고리의 품목은 기타로)
    k_now = now_kst().kst_text
    conn.execute(
        "UPDATE items SET category_id=?, updated_at=? WHERE guild_id=? AND category_id=?",
        (etc_id, k_now, guild_id, category_id),
    )

    k = now_kst().kst_text
    cols = {r[1] for r in conn.execute("PRAGMA table_info(categories)")}
    if "deactivated_at" in cols:
        conn.execute(
            "UPDATE categories SET is_active=0, deactivated_at=?, updated_at=? WHERE guild_id=? AND id=?",
            (k, k, guild_id, category_id),
        )
    else:
        conn.execute(
            "UPDATE categories SET is_active=0, updated_at=? WHERE guild_id=? AND id=?",
            (k, guild_id, category_id),
        )
    conn.commit()
    return {
        "id": int(row[0]),
        "name": cat_name,
        "already": False,
        "moved": len(moved_item_ids),
        "moved_item_ids": moved_item_ids,
        "etc_id": etc_id,
    }
