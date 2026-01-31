# src/repo/movement_repo.py
from __future__ import annotations

import sqlite3
from utils.time_kst import now_kst


def _get_item_row(conn: sqlite3.Connection, guild_id: int, item_id: int) -> dict:
    row = conn.execute(
        """
        SELECT
            i.id, i.name, i.code, i.qty, i.warn_below, i.category_id,
            COALESCE(c.name, '기타') AS category_name
        FROM items i
        LEFT JOIN categories c
          ON c.id = i.category_id AND c.guild_id = i.guild_id
        WHERE i.guild_id = ? AND i.id = ? AND i.is_active = 1
        """,
        (guild_id, item_id),
    ).fetchone()

    if not row:
        raise ValueError("품목을 찾을 수 없어요(비활성화 포함).")

    # row_factory 유무 모두 대응
    try:
        return dict(row)
    except Exception:
        keys = ["id", "name", "code", "qty", "warn_below", "category_id", "category_name"]
        return {k: row[i] for i, k in enumerate(keys)}


def apply_stock_change(
    conn: sqlite3.Connection,
    guild_id: int,
    item_id: int,
    action: str,  # "IN" | "OUT" | "ADJUST"
    amount: int | None,
    new_qty: int | None,
    reason: str,
    actor_name: str,
    actor_id: int,
) -> dict:
    """
    트랜잭션으로 items.qty 업데이트 + movements 기록(스키마 고정)
    - IN/OUT: amount 사용
    - ADJUST: new_qty 사용 (delta 자동 계산)
    """
    k = now_kst()
    reason = (reason or "").strip()

    if action == "ADJUST" and not reason:
        raise ValueError("정정은 사유가 필수입니다.")

    cur = conn.cursor()
    cur.execute("BEGIN")

    item = _get_item_row(conn, guild_id, item_id)
    item_name = str(item["name"])
    item_code = item.get("code")
    cat_name = str(item.get("category_name") or "기타")
    before = int(item["qty"])
    warn_below = item.get("warn_below")

    if action in ("IN", "OUT"):
        if amount is None:
            cur.execute("ROLLBACK")
            raise ValueError("수량이 필요해요.")
        if int(amount) <= 0:
            cur.execute("ROLLBACK")
            raise ValueError("수량은 1 이상이어야 해요.")
        delta = int(amount) if action == "IN" else -int(amount)
        after = before + delta
        if after < 0:
            cur.execute("ROLLBACK")
            raise ValueError("출고 수량이 현재 재고보다 많아요.")

    elif action == "ADJUST":
        if new_qty is None:
            cur.execute("ROLLBACK")
            raise ValueError("정정 재고값이 필요해요.")
        if int(new_qty) < 0:
            cur.execute("ROLLBACK")
            raise ValueError("재고는 0 이상이어야 해요.")
        after = int(new_qty)
        delta = after - before

    else:
        cur.execute("ROLLBACK")
        raise ValueError("알 수 없는 동작입니다.")

    # items 업데이트
    cur.execute(
        "UPDATE items SET qty=?, updated_at=? WHERE guild_id=? AND id=?",
        (after, k.kst_text, guild_id, item_id),
    )

    # movements 기록 (✅ 네가 준 스키마 그대로)
    cur.execute(
        """
        INSERT INTO movements (
            guild_id, item_id,
            item_name_snapshot, item_code_snapshot, category_name_snapshot, image_url,
            action, qty_change, before_qty, after_qty,
            reason, success, error_message,
            discord_name, discord_id,
            created_at_kst_text, created_at_epoch
        ) VALUES (
            ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?
        )
        """,
        (
            guild_id, item_id,
            item_name, item_code, cat_name, None,
            action, delta, before, after,
            reason, 1, "",
            actor_name, actor_id,
            k.kst_text, k.epoch,
        ),
    )

    conn.commit()

    return {
        "item_id": item_id,
        "item_name": item_name,
        "item_code": item_code,
        "category_name": cat_name,
        "before": before,
        "after": after,
        "delta": delta,
        "warn_below": warn_below,
        "kst_text": k.kst_text,  # YYYY/MM/DD HH:MM:SS 형태로 이미 맞춰둔 now_kst 사용 전제
    }
