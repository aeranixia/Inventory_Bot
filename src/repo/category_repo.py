cat > /opt/inventorybot/src/repo/category_repo.py <<'PY'
from __future__ import annotations

import sqlite3
from typing import Any

def _has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == col for r in rows)

def _as_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}

def list_categories(conn: sqlite3.Connection, guild_id: int, include_inactive: bool = False) -> list[dict]:
    """
    categories 스키마가 구버전(deactivated_at 없음)이어도 동작하도록 방어.
    """
    conn.row_factory = sqlite3.Row
    has_deactivated_at = _has_column(conn, "categories", "deactivated_at")

    cols = ["id", "guild_id", "name", "is_active", "created_at", "updated_at"]
    if has_deactivated_at:
        cols.append("deactivated_at")

    sql = f"SELECT {', '.join(cols)} FROM categories WHERE guild_id = ?"
    params: list[Any] = [guild_id]

    if not include_inactive:
        sql += " AND is_active = 1"

    sql += " ORDER BY name COLLATE NOCASE"

    rows = conn.execute(sql, params).fetchall()
    out: list[dict] = []
    for r in rows:
        d = _as_dict(r)
        if not has_deactivated_at:
            d["deactivated_at"] = None
        out.append(d)
    return out

def get_category_by_name(conn: sqlite3.Connection, guild_id: int, name: str, include_inactive: bool = True) -> dict | None:
    conn.row_factory = sqlite3.Row
    has_deactivated_at = _has_column(conn, "categories", "deactivated_at")

    cols = ["id", "guild_id", "name", "is_active", "created_at", "updated_at"]
    if has_deactivated_at:
        cols.append("deactivated_at")

    sql = f"SELECT {', '.join(cols)} FROM categories WHERE guild_id=? AND lower(name)=lower(?)"
    params: list[Any] = [guild_id, name.strip()]

    if not include_inactive:
        sql += " AND is_active = 1"

    row = conn.execute(sql, params).fetchone()
    if not row:
        return None

    d = _as_dict(row)
    if not has_deactivated_at:
        d["deactivated_at"] = None
    return d

def create_category(conn: sqlite3.Connection, guild_id: int, name: str, created_at: str) -> int:
    """
    같은 이름이 비활성 상태면 새로 만들지 말고 활성화(정책).
    """
    name = name.strip()
    if not name:
        raise ValueError("카테고리 이름이 비어있어요.")

    existing = get_category_by_name(conn, guild_id, name, include_inactive=True)
    if existing:
        if int(existing.get("is_active", 1)) == 0:
            reactivate_category(conn, guild_id, int(existing["id"]), updated_at=created_at)
            return int(existing["id"])
        raise ValueError("이미 존재하는 카테고리입니다.")

    conn.execute(
        """
        INSERT INTO categories (guild_id, name, is_active, created_at, updated_at)
        VALUES (?, ?, 1, ?, ?)
        """,
        (guild_id, name, created_at, created_at),
    )
    conn.commit()
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

def deactivate_category(conn: sqlite3.Connection, guild_id: int, category_id: int, updated_at: str):
    """
    비활성화(삭제 대체). deactivated_at 컬럼이 없으면 is_active만 내림.
    """
    has_deactivated_at = _has_column(conn, "categories", "deactivated_at")
    if has_deactivated_at:
        conn.execute(
            """
            UPDATE categories
               SET is_active = 0,
                   deactivated_at = ?,
                   updated_at = ?
             WHERE guild_id = ? AND id = ?
            """,
            (updated_at, updated_at, guild_id, category_id),
        )
    else:
        conn.execute(
            """
            UPDATE categories
               SET is_active = 0,
                   updated_at = ?
             WHERE guild_id = ? AND id = ?
            """,
            (updated_at, guild_id, category_id),
        )
    conn.commit()

def reactivate_category(conn: sqlite3.Connection, guild_id: int, category_id: int, updated_at: str):
    """
    비활성 카테고리 다시 활성화. deactivated_at 있으면 NULL로.
    """
    has_deactivated_at = _has_column(conn, "categories", "deactivated_at")
    if has_deactivated_at:
        conn.execute(
            """
            UPDATE categories
               SET is_active = 1,
                   deactivated_at = NULL,
                   updated_at = ?
             WHERE guild_id = ? AND id = ?
            """,
            (updated_at, guild_id, category_id),
        )
    else:
        conn.execute(
            """
            UPDATE categories
               SET is_active = 1,
                   updated_at = ?
             WHERE guild_id = ? AND id = ?
            """,
            (updated_at, guild_id, category_id),
        )
    conn.commit()
PY
