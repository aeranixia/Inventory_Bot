# src/dashboard.py
from __future__ import annotations

import discord
import sqlite3

from repo.settings_repo import get_settings, set_dashboard_message_id
from ui.dashboard_view import DashboardView

# 현재/과거 대시보드 제목(버전 바뀌며 제목이 달라져도 중복 핀이 쌓이지 않게)
DASHBOARD_TITLE = "재고 대시보드"
_LEGACY_TITLES = {
    "재고 대시보드",
    "재고 봇 대시보드",
    "📦 재고 관리 대시보드",
}


def _is_dashboard_message(msg: discord.Message, *, bot_id: int | None) -> bool:
    """대시보드로 추정되는 메시지인지(과거 버전 포함)."""
    # 봇 메시지만 정리(안전)
    if bot_id and getattr(msg.author, "id", None) != bot_id:
        return False

    # (1) embed title 기준(가장 흔한 케이스)
    if msg.embeds and msg.embeds[0].title:
        title = str(msg.embeds[0].title)
        if title in _LEGACY_TITLES:
            return True
        if "대시보드" in title:
            return True

    # (2) 컴포넌트 custom_id 프리픽스 기준(타이틀이 달라진 경우)
    try:
        for row in (msg.components or []):
            for child in getattr(row, "children", []) or []:
                cid = getattr(child, "custom_id", None)
                if cid and str(cid).startswith("inv:dash:"):
                    return True
    except Exception:
        pass

    return False


def build_dashboard_embed(guild: discord.Guild) -> discord.Embed:
    emb = discord.Embed(
        title=DASHBOARD_TITLE,
        description="아래 버튼으로 입고/출고/정정/검색을 진행하세요.",
    )
    emb.set_footer(text=f"{guild.name} · 재고관리")
    return emb


async def _cleanup_dashboard_pins(channel: discord.TextChannel, keep_message_id: int) -> None:
    """같은 채널에서 대시보드 핀이 여러 개 생기는 상황 대비.

    과거 버전에서 제목/임베드가 조금씩 달라져서 중복이 쌓일 수 있음.
    keep_message_id를 제외한 '대시보드로 추정되는' 봇 메시지 핀을 해제하고(가능하면) 삭제한다.
    """
    try:
        pins = await channel.pins()
    except discord.Forbidden:
        return

    bot_member = channel.guild.me
    bot_id = bot_member.id if bot_member else None

    for msg in pins:
        if msg.id == keep_message_id:
            continue

        if not _is_dashboard_message(msg, bot_id=bot_id):
            continue

        # 핀 해제
        try:
            await msg.unpin()
        except discord.Forbidden:
            pass

        # 메시지 삭제(권한 없으면 스킵)
        try:
            await msg.delete()
        except discord.Forbidden:
            pass


async def ensure_dashboard_message(
    conn: sqlite3.Connection,
    guild: discord.Guild,
    channel: discord.TextChannel,
) -> int:
    """
    - settings.dashboard_message_id가 있으면 그 메시지를 edit
    - 없거나/삭제됐으면 새로 올리고 pin
    - 그리고 채널 내 중복 핀 정리
    """
    s = get_settings(conn, guild.id)
    msg_id = s.get("dashboard_message_id")

    view = DashboardView()
    embed = build_dashboard_embed(guild)

    if msg_id:
        try:
            msg = await channel.fetch_message(int(msg_id))
            await msg.edit(embed=embed, view=view)
            await _cleanup_dashboard_pins(channel, keep_message_id=int(msg.id))
            return int(msg.id)
        except discord.NotFound:
            set_dashboard_message_id(conn, guild.id, None)
        except discord.Forbidden:
            raise

    # 새로 생성
    msg = await channel.send(embed=embed, view=view)
    try:
        await msg.pin()
    except discord.Forbidden:
        pass

    set_dashboard_message_id(conn, guild.id, int(msg.id))
    await _cleanup_dashboard_pins(channel, keep_message_id=int(msg.id))
    return int(msg.id)
