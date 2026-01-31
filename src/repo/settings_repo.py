# src/repo/settings_repo.py
from __future__ import annotations

import sqlite3
from typing import Any, Optional


def get_settings(conn: sqlite3.Connection, guild_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM settings WHERE guild_id=?", (guild_id,)).fetchone()
    return dict(row) if row else {}


def ensure_settings_row(conn: sqlite3.Connection, guild_id: int) -> None:
    conn.execute("INSERT OR IGNORE INTO settings(guild_id) VALUES (?)", (guild_id,))
    conn.commit()


def update_settings(conn: sqlite3.Connection, guild_id: int, **fields: Any) -> None:
    """
    Example: update_settings(conn, gid, dashboard_channel_id=123, report_hour=18)
    """
    if not fields:
        return
    keys = list(fields.keys())
    sets = ", ".join([f"{k}=?" for k in keys])
    values = [fields[k] for k in keys]
    values.append(guild_id)
    conn.execute(f"UPDATE settings SET {sets} WHERE guild_id=?", values)
    conn.commit()


def set_dashboard_message_id(conn: sqlite3.Connection, guild_id: int, message_id: int | None) -> None:
    conn.execute(
        "UPDATE settings SET dashboard_message_id=? WHERE guild_id=?",
        (message_id, guild_id),
    )
    conn.commit()


def insert_movement_update_settings(
    conn: sqlite3.Connection,
    guild_id: int,
    reason: str,
    discord_name: str,
    discord_id: Optional[int],
    created_at_kst_text: str,
    created_at_epoch: int,
    success: int = 1,
    error_message: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO movements (
          guild_id,
          item_id,
          item_name_snapshot,
          item_code_snapshot,
          category_name_snapshot,
          action,
          qty_change,
          before_qty,
          after_qty,
          reason,
          success,
          error_message,
          discord_name,
          discord_id,
          created_at_kst_text,
          created_at_epoch
        ) VALUES (
          ?, NULL, '', '', '',
          'UPDATE_SETTINGS',
          0, 0, 0,
          ?,
          ?, ?,
          ?, ?,
          ?, ?
        );
        """,
        (
            guild_id,
            reason,
            success,
            error_message,
            discord_name,
            discord_id,
            created_at_kst_text,
            created_at_epoch,
        ),
    )
    conn.commit()


def _ensure_settings_columns(conn: sqlite3.Connection):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(settings)").fetchall()}

    # 마지막 일일 업로드 날짜 (YYYY-MM-DD)
    if "last_daily_report_date" not in cols:
        conn.execute("ALTER TABLE settings ADD COLUMN last_daily_report_date TEXT")

    # 마지막 월간 업로드 (YYYY-MM)
    if "last_monthly_report_ym" not in cols:
        conn.execute("ALTER TABLE settings ADD COLUMN last_monthly_report_ym TEXT")

    # 마지막 분기 정리 실행 (YYYY-Qn)
    if "last_quarter_cleanup" not in cols:
        conn.execute("ALTER TABLE settings ADD COLUMN last_quarter_cleanup TEXT")

    conn.commit()


def ensure_settings_schema(conn: sqlite3.Connection):
    _ensure_settings_columns(conn)