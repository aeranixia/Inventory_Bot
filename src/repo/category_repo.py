# src/repo/category_repo.py
from __future__ import annotations

import sqlite3
from utils.time_kst import now_kst

def list_categories(conn: sqlite3.Connection, guild_id: int, include_inactive: bool = True) -> list[dict]:
    if include_inactive:
        rows = conn.execute(
            "SELECT id, name, is_active, deactivated_at, created_at FROM categories "
            "WHERE guild_id=? ORDER BY is_active DESC, name ASC",
            (guild_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name, is_active, deactivated_at, created_at FROM categories "
            "WHERE guild_id=? AND is_active=1 ORDER BY name ASC",
            (guild_id,),
        ).fetchall()

    out = []
    for r in rows:
        out.append({
            "id": r[0],
            "name": r[1],
            "is_active": int(r[2]),
            "deactivated_at": r[3],
            "created_at": r[4],
        })
    return out

def get_or_create_etc_category(conn: sqlite3.Connection, guild_id: int) -> dict:
    row = conn.execute(
        "SELECT id, name, is_active FROM categories WHERE guild_id=? AND name=? LIMIT 1",
        (guild_id, "기타"),
    ).fetchone()
    if row:
        # 기타가 비활성이라면 활성화
        if int(row[2]) == 0:
            conn.execute(
                "UPDATE categories SET is_active=1, deactivated_at=NULL WHERE id=?",
                (row[0],),
            )
            conn.commit()
        return {"id": row[0], "name": row[1]}
    # 없으면 생성
    k = now_kst()
    conn.execute(
        "INSERT INTO categories(guild_id, name, is_active, created_at) VALUES(?,?,1,?)",
        (guild_id, "기타", k.kst_text),
    )
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"id": new_id, "name": "기타"}

def create_or_reactivate_category(conn: sqlite3.Connection, guild_id: int, name: str) -> dict:
    """
    - 같은 이름 카테고리가 있으면: 비활성→활성화, 활성→그대로
    - 없으면 생성
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("카테고리 이름을 입력해 주세요.")
    if name == "기타":
        # 기타는 항상 존재/활성화 정책
        return get_or_create_etc_category(conn, guild_id)

    row = conn.execute(
        "SELECT id, is_active FROM categories WHERE guild_id=? AND name=? LIMIT 1",
        (guild_id, name),
    ).fetchone()
    if row:
        if int(row[1]) == 0:
            conn.execute(
                "UPDATE categories SET is_active=1, deactivated_at=NULL WHERE id=?",
                (row[0],),
            )
            conn.commit()
        return {"id": row[0], "name": name}

    k = now_kst()
    conn.execute(
        "INSERT INTO categories(guild_id, name, is_active, created_at) VALUES(?,?,1,?)",
        (guild_id, name, k.kst_text),
    )
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"id": new_id, "name": name}

def deactivate_category_and_move_items_to_etc(
    conn: sqlite3.Connection,
    guild_id: int,
    category_id: int,
) -> tuple[int, int]:
    """
    카테고리 비활성화 + 해당 카테고리를 참조하는 품목들은 '기타'로 자동 이동
    return: (moved_item_count, etc_category_id)
    """
    # 대상 카테고리 조회
    row = conn.execute(
        "SELECT id, name FROM categories WHERE guild_id=? AND id=? LIMIT 1",
        (guild_id, category_id),
    ).fetchone()
    if not row:
        raise ValueError("카테고리를 찾지 못했어요.")
    if row[1] == "기타":
        raise ValueError("'기타' 카테고리는 비활성화할 수 없어요.")

    etc = get_or_create_etc_category(conn, guild_id)

    k = now_kst()
    with conn:
        # 1) 아이템들 이동
        cur = conn.execute(
            "UPDATE items SET category_id=?, updated_at=? "
            "WHERE guild_id=? AND category_id=?",
            (etc["id"], k.kst_text, guild_id, category_id),
        )
        moved = cur.rowcount

        # 2) 카테고리 비활성화
        conn.execute(
            "UPDATE categories SET is_active=0, deactivated_at=? "
            "WHERE guild_id=? AND id=?",
            (k.kst_text, guild_id, category_id),
        )

    return moved, int(etc["id"])
