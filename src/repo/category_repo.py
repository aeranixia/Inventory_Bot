# src/repo/category_repo.py
from __future__ import annotations
import sqlite3
from typing import Any

def list_active_categories(conn: sqlite3.Connection, guild_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, name
        FROM categories
        WHERE guild_id = ? AND is_active = 1
        ORDER BY sort_order ASC, name ASC
        """,
        (guild_id,),
    ).fetchall()

    out = []
    for r in rows:
        try:
            out.append(dict(r))
        except Exception:
            out.append({"id": r[0], "name": r[1]})
    return out
