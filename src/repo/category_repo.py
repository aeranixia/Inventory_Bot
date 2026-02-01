# src/repo/category_repo.py
from __future__ import annotations

import sqlite3
from typing import Any

from utils.time_kst import now_kst

ETC_CATEGORY_NAME = "기타"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    try:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        return col in cols
    except Exception:
        return False


def ensure_categories_schema(conn: sqlite3.Connection):
    """
    기존 DB에서 categories 테이블/컬럼이 덜 만들어진 상태를 안전하게 보강.
    - deactivated_at 없어서 터지는 문제 해결
    - sort_order/created_at/updated_at 등도 없으면 추가
    """
    if not _table_exists(conn, "categories"):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                deactivated_at TEXT,
                sort_order INTEGER NOT NULL DEFAULT 999,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_categories_guild ON categories(guild_id)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_categories_guild_name ON categories(guild_id, name)")
        conn.commit()
        return

    # add missing columns
    adds: list[tuple[str, str]] = [
        ("is_active", "INTEGER NOT NULL DEFAULT 1"),
        ("deactivated_at", "TEXT"),
        ("sort_order", "INTEGER NOT NULL DEFAULT 999"),
        ("created_at", "TEXT"),
        ("updated_at", "TEXT"),
    ]
    for col, decl in adds:
        if not _has_column(conn, "categories", col):
            conn.execute(f"ALTER TABLE categories ADD COLUMN {col} {decl}")
    conn.commit()


def list_categories(conn: sqlite3.Connection, guild_id: int, include_inactive: bool = False) -> list[dict]:
    # 스키마 보강(안전장치)
    ensure_categories_schema(conn)

    has_deact = _has_column(conn, "categories", "deactivated_at")
    has_sort = _has_column(conn, "categories", "sort_order")
    has_created = _has_column(conn, "categories", "created_at")
    has_updated = _has_column(conn, "categories", "updated_at")

    cols = ["id", "name", "is_active"]
    cols.append("deactivated_at" if has_deact else "NULL AS deactivated_at")
    cols.append("sort_order" if has_sort else "999 AS sort_order")
    cols.append("created_at" if has_created else "NULL AS created_at")
    cols.append("updated_at" if has_updated else "NULL AS updated_at")

    sql = f"SELECT {', '.join(cols)} FROM categories WHERE guild_id=? "
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


def list_active_categories(conn: sqlite3.Connection, guild_id: int) -> list[dict]:
    """
    ✅ item_add.py에서 필요로 하는 함수
    - active 카테고리만
    - {id, name} 최소 형태
    """
    cats = list_categories(conn, guild_id, include_inactive=False)
    return [{"id": c["id"], "name": c["name"]} for c in cats]


def get_or_create_etc_category(conn: sqlite3.Connection, guild_id: int) -> int:
    ensure_categories_schema(conn)

    row = conn.execute(
        "SELECT id FROM categories WHERE guild_id=? AND name=?",
        (guild_id, ETC_CATEGORY_NAME),
    ).fetchone()
    if row:
        return int(row[0])

    k = now_kst().kst_text
    # 컬럼 존재 여부에 맞춰 INSERT
    has_deact = _has_column(conn, "categories", "deactivated_at")
    if has_deact:
        cur = conn.execute(
            "INSERT INTO categories (guild_id, name, is_active, deactivated_at, sort_order, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (guild_id, ETC_CATEGORY_NAME, 1, None, 0, k, k),
        )
    else:
        cur = conn.execute(
            "INSERT INTO categories (guild_id, name, is_active, sort_order, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (guild_id, ETC_CATEGORY_NAME, 1, 0, k, k),
        )
    conn.commit()
    return int(cur.lastrowid)


def create_or_reactivate_category(conn: sqlite3.Connection, guild_id: int, name: str) -> dict:
    ensure_categories_schema(conn)

    name = (name or "").strip()
    if not name:
        raise ValueError("카테고리명을 입력해 주세요.")

    row = conn.execute(
        "SELECT id, is_active FROM categories WHERE guild_id=? AND name=?",
        (guild_id, name),
    ).fetchone()

    k = now_kst().kst_text
    has_deact = _has_column(conn, "categories", "deactivated_at")

    if row:
        cat_id, is_active = int(row[0]), int(row[1])
        if is_active == 1:
            return {"id": cat_id, "name": name, "reactivated": False}

        if has_deact:
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

    if has_deact:
        cur = conn.execute(
            "INSERT INTO categories (guild_id, name, is_active, deactivated_at, sort_order, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (guild_id, name, 1, None, 999, k, k),
        )
    else:
        cur = conn.execute(
            "INSERT INTO categories (guild_id, name, is_active, sort_order, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (guild_id, name, 1, 999, k, k),
        )
    conn.commit()
    return {"id": int(cur.lastrowid), "name": name, "reactivated": False}


def deactivate_category_and_move_items_to_etc(conn: sqlite3.Connection, guild_id: int, category_id: int) -> dict:
    ensure_categories_schema(conn)

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

    k = now_kst().kst_text

    moved = conn.execute(
        "UPDATE items SET category_id=?, updated_at=? WHERE guild_id=? AND category_id=?",
        (etc_id, k, guild_id, category_id),
    ).rowcount

    has_deact = _has_column(conn, "categories", "deactivated_at")
    if has_deact:
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
    return {"id": int(row[0]), "name": cat_name, "already": False, "moved": moved}
