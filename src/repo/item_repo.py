# src/repo/item_repo.py
from __future__ import annotations

import sqlite3
from utils.time_kst import now_kst


def _as_int(v, default: int = 0) -> int:
    """UI/모달에서 빈 문자열이 들어오는 케이스 방어."""
    if v is None:
        return default
    if isinstance(v, int):
        return v
    s = str(v).strip().replace(",", "")
    if s == "":
        return default
    return int(s)


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
            _as_int(category_id, default=0),
            (name or "").strip(),
            (code or "").strip() or None,
            _as_int(qty, default=0),
            _as_int(warn_below, default=0),
            (note or "").strip(),
            (storage_location or "").strip(),
            (image_url or "").strip(),
            k,
            k,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def count_active_items(conn: sqlite3.Connection, guild_id: int, category_id: int | None = None) -> int:
    """활성(is_active=1) 품목 수를 반환합니다.
    - category_id가 주어지면 해당 카테고리만 카운트
    - None이면 서버 전체 카운트
    """
    if category_id is None:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM items
            WHERE guild_id=? AND is_active=1
            """,
            (guild_id,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM items
            WHERE guild_id=? AND category_id=? AND is_active=1
            """,
            (guild_id, category_id),
        ).fetchone()
    return int(row[0] if row else 0)

def list_active_items(
    conn: sqlite3.Connection,
    guild_id: int,
    category_id: int,
    *,
    offset: int = 0,
    limit: int = 20,
) -> list[dict]:
    """특정 카테고리의 활성 품목 목록(페이지네이션)"""
    rows = conn.execute(
        """
        SELECT
            i.id, i.name, i.code, i.image_url,
            i.qty, i.warn_below,
            i.note, i.storage_location,
            COALESCE(c.name,'기타') AS category_name
        FROM items i
        LEFT JOIN categories c ON c.id=i.category_id
        WHERE i.guild_id=? AND i.category_id=? AND i.is_active=1
        ORDER BY i.name ASC
        LIMIT ? OFFSET ?
        """,
        (guild_id, category_id, int(limit), int(offset)),
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
                "warn_below": r[5],
                "note": r[6],
                "storage_location": r[7],
                "category_name": r[8],
            }
        )
    return out

def count_items_by_category(conn: sqlite3.Connection, guild_id: int, category_id: int) -> int:
    row = conn.execute(
        """SELECT COUNT(1) FROM items
           WHERE guild_id=? AND category_id=? AND is_active=1""",
        (guild_id, category_id),
    ).fetchone()
    return int(row[0] if row else 0)


def list_items_by_category(
    conn: sqlite3.Connection,
    guild_id: int,
    category_id: int,
    offset: int = 0,
    limit: int = 20,
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            i.id, i.name, i.code, i.image_url,
            i.qty, i.warn_below,
            COALESCE(c.name,'기타') AS category_name,
            i.note, i.storage_location
        FROM items i
        LEFT JOIN categories c ON c.id=i.category_id
        WHERE i.guild_id=? AND i.category_id=? AND i.is_active=1
        ORDER BY i.name ASC
        LIMIT ? OFFSET ?
        """,
        (guild_id, category_id, int(limit), int(offset)),
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
                "warn_below": r[5],
                "category_name": r[6],
                "note": r[7],
                "storage_location": r[8],
            }
        )
    return out


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
    """품목 비활성화(삭제 대체).

    reason은 현재 items 테이블에 저장하지 않지만,
    UI/호출부 호환을 위해 파라미터로 유지합니다.
    """
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
