# src/repo/report_repo.py
from __future__ import annotations
import sqlite3
from typing import Any

def list_items_for_report(conn: sqlite3.Connection, guild_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            i.id, i.name, i.code, i.qty, i.warn_below,
            COALESCE(i.storage_location,'') AS storage_location,
            COALESCE(i.note,'') AS note,
            i.is_active,
            COALESCE(c.name,'기타') AS category_name
        FROM items i
        LEFT JOIN categories c
          ON c.id = i.category_id AND c.guild_id = i.guild_id
        WHERE i.guild_id = ?
        ORDER BY i.is_active DESC, category_name ASC, i.name ASC
        """,
        (guild_id,),
    ).fetchall()

    out = []
    for r in rows:
        try:
            out.append(dict(r))
        except Exception:
            keys = ["id","name","code","qty","warn_below","storage_location","note","is_active","category_name"]
            out.append({k: r[i] for i, k in enumerate(keys)})
    return out


def list_movements_in_epoch_range(conn: sqlite3.Connection, guild_id: int, start_epoch: int, end_epoch: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            id, guild_id, item_id, item_name_snapshot, item_code_snapshot, category_name_snapshot,
            action, qty_change, before_qty, after_qty,
            reason, discord_name, created_at_kst_text, created_at_epoch
        FROM movements
        WHERE guild_id = ?
          AND created_at_epoch >= ?
          AND created_at_epoch < ?
        ORDER BY created_at_epoch ASC, id ASC
        """,
        (guild_id, start_epoch, end_epoch),
    ).fetchall()

    out = []
    for r in rows:
        try:
            out.append(dict(r))
        except Exception:
            keys = ["id","guild_id","item_id","item_name_snapshot","item_code_snapshot","category_name_snapshot",
                    "action","qty_change","before_qty","after_qty","reason","discord_name","created_at_kst_text","created_at_epoch"]
            out.append({k: r[i] for i, k in enumerate(keys)})
    return out


def delete_movements_before_epoch(conn: sqlite3.Connection, guild_id: int, cutoff_epoch: int) -> int:
    cur = conn.execute(
        "DELETE FROM movements WHERE guild_id=? AND created_at_epoch < ?",
        (guild_id, cutoff_epoch),
    )
    conn.commit()
    return int(cur.rowcount)
