# src/dashboard.py
from __future__ import annotations

import discord
import sqlite3

from repo.settings_repo import get_settings, set_dashboard_message_id
from ui.dashboard_view import DashboardView

DASHBOARD_TITLE = "재고 대시보드"


def build_dashboard_embed(guild: discord.Guild) -> discord.Embed:
    emb = discord.Embed(
        title=DASHBOARD_TITLE,
        description="아래 버튼으로 입고/출고/정정/검색을 진행하세요.",
    )
    emb.set_footer(text=f"{guild.name} · 재고관리")
    return emb


async def _cleanup_dashboard_pins(channel: discord.TextChannel, keep_message_id: int) -> None:
    """
    같은 채널에서 대시보드 핀이 여러 개 생기는 상황 대비:
    - '재고 대시보드' 제목의 봇 메시지 중 keep_message_id를 제외한 나머지 핀 해제 + (가능하면) 삭제
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

        # 봇 메시지만 정리(안전)
        if bot_id and msg.author and msg.author.id != bot_id:
            continue

        if not msg.embeds:
            continue

        if msg.embeds[0].title != DASHBOARD_TITLE:
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
