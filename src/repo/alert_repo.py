# src/repo/alert_repo.py
from __future__ import annotations

import sqlite3
from utils.time_kst import now_kst


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def should_send_low_stock_alert(conn: sqlite3.Connection, guild_id: int, item_id: int, now_below: bool) -> bool:
    """
    now_below=True: 이번 상태가 경고 상태(<= warn_below)
    - 이전에 경고를 안 보냈던 상태에서 below로 진입하면 True
    - 이미 below 상태면 False (스팸 방지)
    now_below=False:
    - 경고 상태 해제 처리만 하고 False
    """
    cols = _cols(conn, "alert_state")
    k = now_kst()

    row = conn.execute(
        "SELECT * FROM alert_state WHERE guild_id=? AND item_id=?",
        (guild_id, item_id),
    ).fetchone()

    # row_factory 유무 대응
    prev_alerting = 0
    if row:
        try:
            prev_alerting = int(dict(row).get("is_alerting", 0))
        except Exception:
            # 대충 3번째 컬럼이 is_alerting일 가능성도 있지만 확신 불가 → 안전하게 0 처리
            prev_alerting = 0

    # below로 새 진입이면 알림
    send = (now_below and prev_alerting == 0)

    # upsert/update
    if row is None:
        fields = {"guild_id": guild_id, "item_id": item_id}
        if "is_alerting" in cols:
            fields["is_alerting"] = 1 if now_below else 0
        if "updated_at_kst_text" in cols:
            fields["updated_at_kst_text"] = k.kst_text
        if "updated_at_epoch" in cols:
            fields["updated_at_epoch"] = k.epoch

        keys = list(fields.keys())
        qs = ", ".join(["?"] * len(keys))
        conn.execute(f"INSERT INTO alert_state ({', '.join(keys)}) VALUES ({qs})", tuple(fields[k] for k in keys))
    else:
        sets = []
        vals = []
        if "is_alerting" in cols:
            sets.append("is_alerting=?")
            vals.append(1 if now_below else 0)
        if "updated_at_kst_text" in cols:
            sets.append("updated_at_kst_text=?")
            vals.append(k.kst_text)
        if "updated_at_epoch" in cols:
            sets.append("updated_at_epoch=?")
            vals.append(k.epoch)

        if sets:
            vals.extend([guild_id, item_id])
            conn.execute(f"UPDATE alert_state SET {', '.join(sets)} WHERE guild_id=? AND item_id=?", tuple(vals))

    conn.commit()
    return send
