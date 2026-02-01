# src/backup.py
from __future__ import annotations

import os
import re
import sqlite3
import zipfile
from pathlib import Path
from datetime import datetime, timedelta

import discord

from utils.time_kst import now_kst
from repo.settings_repo import get_settings


# 기본값: ./data/backups
def _backup_dir() -> Path:
    p = os.environ.get("BACKUP_DIR", "./data/backups")
    d = Path(p)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _marker_path() -> Path:
    return _backup_dir() / ".last_backup_date"


def _monthly_marker_path() -> Path:
    return _backup_dir() / ".last_monthly_archive_ym"

def _read_last_monthly_archive_ym() -> str:
    try:
        return _monthly_marker_path().read_text(encoding="utf-8").strip()
    except Exception:
        return ""

def _write_last_monthly_archive_ym(ym: str) -> None:
    try:
        _monthly_marker_path().write_text(ym, encoding="utf-8")
    except Exception:
        pass


def _read_last_backup_date() -> str:
    try:
        return _marker_path().read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _write_last_backup_date(date_text: str) -> None:
    try:
        _marker_path().write_text(date_text, encoding="utf-8")
    except Exception:
        pass


def _cleanup_old_backups(keep_days: int = 60) -> None:
    """
    오래된 백업 파일 정리(기본 60일 보관).
    """
    d = _backup_dir()
    cutoff = now_kst().dt - timedelta(days=keep_days)

    for p in d.glob("inventory_backup_*.db"):
        m = re.search(r"inventory_backup_(\d{4}-\d{2}-\d{2})\.db$", p.name)
        if not m:
            continue
        try:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d")
            if dt < cutoff.replace(tzinfo=None):
                p.unlink(missing_ok=True)
        except Exception:
            pass

    for p in d.glob("inventory_backup_*.zip"):
        m = re.search(r"inventory_backup_(\d{4}-\d{2}-\d{2})\.zip$", p.name)
        if not m:
            continue
        try:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d")
            if dt < cutoff.replace(tzinfo=None):
                p.unlink(missing_ok=True)
        except Exception:
            pass


def _make_zip(db_path: Path) -> Path:
    zip_path = db_path.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(db_path, arcname=db_path.name)
    return zip_path


async def _get_alert_channel(client, guild: discord.Guild):
    # alert_channel_id 또는 report_channel_id로 알림 보냄
    s = get_settings(client.conn, guild.id)
    ch_id = s.get("alert_channel_id") or s.get("report_channel_id")
    if not ch_id:
        return None
    ch = guild.get_channel(int(ch_id))
    return ch if isinstance(ch, discord.TextChannel) else None


def do_backup_sqlite(src_conn: sqlite3.Connection, target_path: Path) -> None:
    """
    sqlite3 백업 API로 안전하게 스냅샷 생성.
    """
    # 혹시 모를 flush
    try:
        src_conn.commit()
    except Exception:
        pass

    dst_conn = sqlite3.connect(str(target_path))
    try:
        src_conn.backup(dst_conn)  # 온라인 백업
        dst_conn.commit()
    finally:
        dst_conn.close()


async def run_daily_backup(client, guild: discord.Guild, hour: int = 18, minute: int = 40) -> None:
    """
    ✅ 매일 (기본 18:40 KST) DB 백업 실행
    - 18:30 리포트 후 10분 뒤로 기본 설정
    - 하루 1번만 수행(.last_backup_date로 중복 방지)
    """
    k = now_kst()
    dt = k.dt
    today = dt.strftime("%Y-%m-%d")

    scheduled = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if dt < scheduled:
        return

    if _read_last_backup_date() == today:
        return

    d = _backup_dir()
    db_file = d / f"inventory_backup_{today}.db"

    do_backup_sqlite(client.conn, db_file)

    # 정리
    _cleanup_old_backups(keep_days=60)

    # 알림 채널에 결과만 남기기(파일 업로드는 용량 안전할 때만)
    ch = await _get_alert_channel(client, guild)
    if ch:
        size = db_file.stat().st_size
        size_mb = size / (1024 * 1024)

        # 디스코드 기본 업로드 제한(안전하게 8MB 기준)
        MAX_UPLOAD = 8 * 1024 * 1024

        # zip 만들어서 더 작아지면 올리기 시도
        zip_path = _make_zip(db_file)
        zip_size = zip_path.stat().st_size

        if zip_size <= MAX_UPLOAD:
            await ch.send(
                content=f"🗄️ DB 백업 완료 ({today})",
                file=discord.File(fp=str(zip_path), filename=zip_path.name),
            )
        else:
            await ch.send(
                f"🗄️ DB 백업 완료 ({today})\n"
                f"- 파일: `{db_file.name}` ({size_mb:.2f}MB)\n"
                f"- zip이 8MB를 초과해서 채널 업로드는 생략했어요. (서버에 저장됨)"
            )

    _write_last_backup_date(today)


async def force_backup_now(client, guild: discord.Guild) -> tuple[bool, str]:
    """
    ✅ 관리자 수동 백업: 지금 즉시 백업 생성 + (가능하면) 업로드
    """
    k = now_kst()
    dt = k.dt
    today = dt.strftime("%Y-%m-%d")

    d = _backup_dir()
    db_file = d / f"inventory_backup_{today}.db"

    do_backup_sqlite(client.conn, db_file)
    _cleanup_old_backups(keep_days=60)

    ch = await _get_alert_channel(client, guild)
    if not ch:
        return False, "리포트/알림 채널이 미설정이라 업로드는 못 했어요. 서버에 백업 파일은 저장됐어요."

    MAX_UPLOAD = 8 * 1024 * 1024
    zip_path = _make_zip(db_file)

    if zip_path.stat().st_size <= MAX_UPLOAD:
        await ch.send(
            content=f"🗄️ (수동) DB 백업 완료 ({today})",
            file=discord.File(fp=str(zip_path), filename=zip_path.name),
        )
        return True, "채널 업로드까지 완료했어요."
    else:
        size_mb = db_file.stat().st_size / (1024 * 1024)
        await ch.send(
            f"🗄️ (수동) DB 백업 완료 ({today})\n"
            f"- 파일: `{db_file.name}` ({size_mb:.2f}MB)\n"
            f"- zip이 8MB를 초과해서 채널 업로드는 생략했어요. (서버에 저장됨)"
        )
        return True, "백업은 했고, 용량 때문에 채널 업로드는 생략됐어요."


def list_backup_files(limit: int = 20) -> list[tuple[str, float, float]]:
    """
    returns [(filename, size_mb, mtime_epoch), ...] newest first
    """
    d = _backup_dir()
    files = []
    for p in d.glob("inventory_backup_*"):
        if p.is_file():
            size_mb = p.stat().st_size / (1024 * 1024)
            files.append((p.name, size_mb, p.stat().st_mtime))
    files.sort(key=lambda x: x[2], reverse=True)
    return files[:max(1, min(limit, 50))]


async def run_monthly_archive(client, guild: discord.Guild, hour: int = 18, minute: int = 50) -> None:
    """
    ✅ 매달 1일 (기본 18:50 KST) 에 '지난달 백업들'을 ZIP로 묶어 업로드 시도
    - 1일로 하는 이유: 월말에 서버가 꺼져도 다음날(1일) 살아나면 처리 가능
    - 중복 업로드 방지: .last_monthly_archive_ym
    """
    k = now_kst()
    dt = k.dt

    # 매달 1일만
    if dt.day != 1:
        return

    scheduled = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if dt < scheduled:
        return

    # 지난달
    prev_month_dt = (dt.replace(day=1) - timedelta(days=1))
    ym = prev_month_dt.strftime("%Y-%m")

    if _read_last_monthly_archive_ym() == ym:
        return

    d = _backup_dir()

    # 지난달의 일일 백업(.db)만 모아서 zip 만들기
    # 파일명: inventory_backup_YYYY-MM-DD.db
    prefix = f"inventory_backup_{ym}-"  # 예: inventory_backup_2026-01-
    db_files = sorted([p for p in d.glob(f"{prefix}*.db") if p.is_file()])

    # 없으면 종료(아직 백업이 없거나 파일 규칙 변경 등)
    if not db_files:
        ch = await _get_alert_channel(client, guild)
        if ch:
            await ch.send(f"📦 월간 백업 ZIP 생성 시도({ym}) → 해당 월의 일일 백업 파일이 없어서 건너뛰었어요.")
        _write_last_monthly_archive_ym(ym)
        return

    zip_path = d / f"inventory_backup_{ym}.zip"
    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in db_files:
                zf.write(p, arcname=p.name)
    except Exception:
        # zip 생성 실패
        ch = await _get_alert_channel(client, guild)
        if ch:
            await ch.send(f"📦 월간 백업 ZIP 생성 실패({ym})")
        return

    # 업로드 시도(8MB 기준)
    ch = await _get_alert_channel(client, guild)
    if ch:
        MAX_UPLOAD = 8 * 1024 * 1024
        zsize = zip_path.stat().st_size
        zmb = zsize / (1024 * 1024)

        if zsize <= MAX_UPLOAD:
            await ch.send(
                content=f"📦 월간 DB 백업 ZIP ({ym})",
                file=discord.File(fp=str(zip_path), filename=zip_path.name),
            )
        else:
            await ch.send(
                f"📦 월간 DB 백업 ZIP 생성 완료({ym})\n"
                f"- 파일: `{zip_path.name}` ({zmb:.2f}MB)\n"
                f"- 8MB 초과로 채널 업로드는 생략했어요. (서버에 저장됨)"
            )

    _write_last_monthly_archive_ym(ym)
