# src/db.py
from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def _is_ignorable_schema_error(e: sqlite3.OperationalError) -> bool:
    msg = str(e).lower()
    return (
        "duplicate column name" in msg
        or "already exists" in msg
        or "duplicate" in msg and "column" in msg
    )


def apply_schema(conn: sqlite3.Connection, schema_path: str) -> None:
    """
    schema.sql을 여러 번 실행해도 안전하게(가능한 한) 적용.
    - duplicate column name / already exists 류는 무시
    """
    sql = Path(schema_path).read_text(encoding="utf-8")

    # 아주 단순 분해(우리 schema.sql 형태에 충분)
    statements = [s.strip() for s in sql.split(";") if s.strip()]

    for stmt in statements:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as e:
            if _is_ignorable_schema_error(e):
                continue
            raise

    conn.commit()
