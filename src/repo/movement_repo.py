# src/repo/movement_repo.py
from __future__ import annotations

import sqlite3
from utils.time_kst import now_kst


def _get_item_row(conn: sqlite3.Connection, guild_id: int, item_id: int) -> dict:
    row = conn.execute(
        """
        SELECT
            i.id, i.name, i.code, i.image_url, i.qty, i.warn_below, i.category_id,
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
        keys = ["id", "name", "code", "image_url", "qty", "warn_below", "category_id", "category_name"]
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
    image_url = str(item.get("image_url") or "")
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
            item_name, item_code, cat_name, image_url,
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

def log_simple_event(
    conn: sqlite3.Connection,
    guild_id: int,
    item_id: int | None = None,
    action: str | None = None,
    reason: str = "",
    actor_name: str = "",
    actor_id: int = 0,
    kst_text: str | None = None,
    epoch: int | None = None,
    image_url: str | None = None,
    **_ignored,
):
    """품목 관련 이벤트를 movements에 기록.

    - 예전 코드에서 키워드 인자(item_name 등)를 넘겨도 무시하도록 호환 처리.
    - 시간(kst_text/epoch)을 생략하면 자동으로 now_kst()로 채웁니다.
    """
    if item_id is None or action is None:
        raise ValueError("item_id/action is required")
    if kst_text is None or epoch is None:
        from utils.time_kst import now_kst
        k = now_kst()
        kst_text = k.kst_text
        epoch = k.epoch
    # 스냅샷용
    row = conn.execute(
        "SELECT i.name, i.code, COALESCE(c.name,'기타'), COALESCE(i.image_url,'') "
        "FROM items i LEFT JOIN categories c ON c.id=i.category_id "
        "WHERE i.guild_id=? AND i.id=? LIMIT 1",
        (guild_id, item_id),
    ).fetchone()

    item_name = row[0] if row else ""
    item_code = row[1] if row else None
    cat_name = row[2] if row else ""
    # 매개변수로 image_url을 못 받았으면 items.image_url을 사용
    image_url = image_url or (row[3] if row else "") or ""

    conn.execute(
        "INSERT INTO movements("
        "guild_id, item_id, item_name_snapshot, item_code_snapshot, category_name_snapshot, "
        "image_url, action, qty_change, before_qty, after_qty, reason, success, error_message, "
        "discord_name, discord_id, created_at_kst_text, created_at_epoch"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            guild_id, item_id, item_name, item_code, cat_name,
            image_url, action, 0, None, None, reason, 1, "",
            actor_name, actor_id, kst_text, epoch
        ),
    )
    conn.commit()


def log_system_event(
    conn: sqlite3.Connection,
    guild_id: int,
    action: str,
    reason: str,
    actor_name: str,
    actor_id: int,
    kst_text: str,
    epoch: int,
):
    """item_id 없이 남기는 시스템 로그(카테고리 변경 등)"""
    conn.execute(
        "INSERT INTO movements("
        "guild_id, item_id, item_name_snapshot, item_code_snapshot, category_name_snapshot, "
        "image_url, action, qty_change, before_qty, after_qty, reason, success, error_message, "
        "discord_name, discord_id, created_at_kst_text, created_at_epoch"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            guild_id, None, "", None, "",
            "", action, 0, None, None, reason, 1, "",
            actor_name, actor_id, kst_text, epoch,
        ),
    )
    conn.commit()
