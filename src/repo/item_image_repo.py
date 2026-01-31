# src/repo/item_image_repo.py
from __future__ import annotations
import sqlite3
from utils.time_kst import now_kst

def set_item_image(conn: sqlite3.Connection, guild_id: int, item_id: int, image_url: str):
    k = now_kst()
    with conn:
        conn.execute(
            "UPDATE items SET image_url=?, updated_at=? WHERE guild_id=? AND id=?",
            (image_url, k.kst_text, guild_id, item_id),
        )
    return k
