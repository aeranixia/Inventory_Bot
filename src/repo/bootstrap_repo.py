# src/repo/bootstrap_repo.py
from __future__ import annotations

import sqlite3
from typing import Optional


DEFAULT_CATEGORIES = [
    ("해벽산", 10),
    ("보험약", 20),
    ("스틱약", 30),
    ("공진단", 40),
    ("기타", 999),
]


def ensure_initialized(conn: sqlite3.Connection, guild_id: int, now_kst_text: str) -> int:
    """
    Ensures:
      - settings row exists
      - default categories exist
      - '기타' category exists and is_active=1

    Returns:
      - etc_category_id (카테고리 '기타'의 id)
    """
    # 트랜잭션(동시성/안정성)
    conn.execute("BEGIN IMMEDIATE;")
    try:
        # 1) settings row 보장
        conn.execute(
            "INSERT OR IGNORE INTO settings (guild_id) VALUES (?);",
            (guild_id,),
        )

        # 2) 기본 카테고리 보장(없으면 생성)
        for name, order in DEFAULT_CATEGORIES:
            conn.execute(
                """
                INSERT OR IGNORE INTO categories
                  (guild_id, name, is_active, sort_order, created_at, updated_at)
                VALUES
                  (?, ?, 1, ?, ?, ?);
                """,
                (guild_id, name, order, now_kst_text, now_kst_text),
            )

        # 3) '기타'는 무조건 활성 유지(혹시 비활성화된 적 있으면 켜줌)
        conn.execute(
            """
            UPDATE categories
               SET is_active = 1,
                   updated_at = ?
             WHERE guild_id = ?
               AND name = '기타';
            """,
            (now_kst_text, guild_id),
        )

        # 4) '기타' id 반환
        row = conn.execute(
            "SELECT id FROM categories WHERE guild_id=? AND name='기타';",
            (guild_id,),
        ).fetchone()

        if not row:
            # 이건 사실상 발생하면 안 되지만, 안전장치
            raise RuntimeError("Failed to ensure '기타' category.")

        etc_id = int(row["id"])

        conn.commit()
        return etc_id

    except Exception:
        conn.rollback()
        raise
