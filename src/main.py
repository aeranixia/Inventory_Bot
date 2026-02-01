# src/main.py
from __future__ import annotations

import os
import traceback

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

from db import connect, apply_schema
from utils.time_kst import now_kst
from utils.perm import is_admin

from repo.bootstrap_repo import ensure_initialized
from repo.settings_repo import get_settings, ensure_settings_schema
from repo.schema_guard import ensure_items_schema, ensure_categories_schema

from ui.settings_view import SettingsView
from ui.dashboard_view import DashboardView

from reporting import (
    force_send_daily_reports,
    force_send_monthly_prev_month,
)

from ui.category_manage import CategoryManageView
from repo.category_repo import list_categories

from backup import run_daily_backup, run_monthly_archive, force_backup_now, list_backup_files


load_dotenv()

# ---- Intents ----
INTENTS = discord.Intents.default()
INTENTS.guilds = True
INTENTS.members = True          # 봇 관리자 역할 부여/회수에 필요
INTENTS.message_content = True  # 채팅 입력(검색 chat 버전), 이미지 업로드 플로우에 필요

# ---- Optional: fast sync / cleanup guild ----
CLEANUP_GUILD_ID = int(os.environ.get("CLEANUP_GUILD_ID", "0"))
CLEANUP_GUILD_OBJ = discord.Object(id=CLEANUP_GUILD_ID) if CLEANUP_GUILD_ID else None


class InventoryBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)
        self.conn = None  # sqlite3.Connection

    async def setup_hook(self):
        
        # ✅ DB 스키마 가드(기존 DB에도 컬럼 자동 추가)
        ensure_settings_schema(self.conn)
        ensure_items_schema(self.conn)
        ensure_categories_schema(self.conn)

        # ✅ persistent view 등록 (재시작 후에도 대시보드 버튼 살아있게)
        self.add_view(DashboardView())

        # ✅ 루프는 여기서 '딱 한 번'만 시작
        if not self._report_loop.is_running():
            self._report_loop.start()

        # ✅ 길드 커맨드 잔재 정리(필요 시) + 빠른 반영(선택)
        if CLEANUP_GUILD_OBJ:
            # 1) 잔재 삭제
            self.tree.clear_commands(guild=CLEANUP_GUILD_OBJ)
            await self.tree.sync(guild=CLEANUP_GUILD_OBJ)
            print(f"[SYNC] Cleared guild commands on: {CLEANUP_GUILD_ID}")

            # 2) 글로벌 커맨드를 길드로 복사(즉시 보이게)
            self.tree.copy_global_to(guild=CLEANUP_GUILD_OBJ)
            await self.tree.sync(guild=CLEANUP_GUILD_OBJ)
            print(f"[SYNC] Copied global -> guild: {CLEANUP_GUILD_ID}")

        # ✅ 글로벌 커맨드 동기화(반영은 느릴 수 있음)
        await self.tree.sync()
        print("[SYNC] Global sync requested")
    from repo.category_repo import ensure_categories_schema


    @tasks.loop(minutes=1)
    async def _report_loop(self):
        # 순환 import/의존성 꼬임 방지: 여기서 import
        from reporting import run_daily_reports, run_quarterly_cleanup

        for g in list(self.guilds):
            try:
                await run_daily_reports(self, g)
                await run_quarterly_cleanup(self, g)
                await run_daily_backup(self, g)      # 기본 18:40 KST
                await run_monthly_archive(self, g)
            except Exception as e:
                print("[REPORT_LOOP_ERROR]", repr(e))

    @_report_loop.before_loop
    async def _before_report_loop(self):
        await self.wait_until_ready()


bot = InventoryBot()


@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} (id={bot.user.id})")


# ---- Slash command: /설정 ----
@bot.tree.command(name="설정", description="재고 봇 설정 패널을 엽니다.")
async def settings_cmd(inter: discord.Interaction):
    if not inter.guild:
        return await inter.response.send_message("서버에서만 사용할 수 있어요.", ephemeral=True)

    await inter.response.defer(ephemeral=True)

    try:
        # 1) 서버 초기화(기본 카테고리/설정 row 보장)
        k = now_kst()
        ensure_initialized(bot.conn, inter.guild_id, k.kst_text)

        # 2) 설정 패널 표시
        s = get_settings(bot.conn, inter.guild_id)
        emb = SettingsView.build_embed(inter.guild, s)
        view = SettingsView.build_view(bot.conn, inter.guild)
        await inter.followup.send(embed=emb, view=view, ephemeral=True)

    except Exception as e:
        print("[ERROR] /설정 처리 중 예외 발생")
        traceback.print_exc()
        try:
            await inter.followup.send(
                f"설정 패널을 여는 중 오류가 발생했어요:\n`{type(e).__name__}: {e}`",
                ephemeral=True,
            )
        except Exception:
            pass


# ---- Slash command: /리포트 ----
@bot.tree.command(name="리포트", description="지금 즉시 리포트를 업로드합니다(관리자 전용).")
@app_commands.choices(
    종류=[
        app_commands.Choice(name="일일(오늘) - 재고+로그", value="daily"),
        app_commands.Choice(name="월간(지난달) - 누적 로그", value="monthly_prev"),
    ]
)
async def report_cmd(inter: discord.Interaction, 종류: app_commands.Choice[str]):
    if not inter.guild:
        return await inter.response.send_message("서버에서만 사용할 수 있어요.", ephemeral=True)

    if not is_admin(inter, bot.conn):
        return await inter.response.send_message("권한이 없어요.", ephemeral=True)

    await inter.response.defer(ephemeral=True)

    try:
        if 종류.value == "daily":
            ok = await force_send_daily_reports(bot, inter.guild, mark_done=True)
            if not ok:
                return await inter.followup.send(
                    "리포트 채널이 설정되지 않았어요. `/설정`에서 재고_알림(리포트) 채널을 먼저 지정해 주세요.",
                    ephemeral=True,
                )
            return await inter.followup.send("✅ 일일 리포트를 업로드했어요.", ephemeral=True)

        if 종류.value == "monthly_prev":
            ok = await force_send_monthly_prev_month(bot, inter.guild, mark_done=True)
            if not ok:
                return await inter.followup.send(
                    "리포트 채널이 설정되지 않았어요. `/설정`에서 재고_알림(리포트) 채널을 먼저 지정해 주세요.",
                    ephemeral=True,
                )
            return await inter.followup.send("✅ 지난달 월간 누적 로그를 업로드했어요.", ephemeral=True)

        return await inter.followup.send("알 수 없는 종류입니다.", ephemeral=True)

    except Exception as e:
        traceback.print_exc()
        return await inter.followup.send(f"처리 실패: `{type(e).__name__}: {e}`", ephemeral=True)


# ---- Slash command: /백업 ----
@bot.tree.command(name="백업", description="지금 즉시 DB 백업을 생성합니다(관리자 전용).")
async def backup_cmd(inter: discord.Interaction):
    if not inter.guild:
        return await inter.response.send_message("서버에서만 사용할 수 있어요.", ephemeral=True)

    if not is_admin(inter, bot.conn):
        return await inter.response.send_message("권한이 없어요.", ephemeral=True)

    await inter.response.defer(ephemeral=True)

    try:
        ok, msg = await force_backup_now(bot, inter.guild)
        await inter.followup.send(f"✅ {msg}", ephemeral=True)
    except Exception as e:
        traceback.print_exc()
        await inter.followup.send(f"백업 실패: `{type(e).__name__}: {e}`", ephemeral=True)


# ---- Slash command: /백업목록 ----
@bot.tree.command(name="백업목록", description="서버에 저장된 백업 파일 목록을 보여줍니다(관리자 전용).")
@app_commands.describe(개수="표시할 개수(최대 50)")
async def backup_list_cmd(inter: discord.Interaction, 개수: int = 20):
    if not inter.guild:
        return await inter.response.send_message("서버에서만 사용할 수 있어요.", ephemeral=True)

    if not is_admin(inter, bot.conn):
        return await inter.response.send_message("권한이 없어요.", ephemeral=True)

    n = max(1, min(int(개수), 50))
    files = list_backup_files(limit=n)

    if not files:
        return await inter.response.send_message("백업 파일이 아직 없어요.", ephemeral=True)

    lines = [f"- `{name}` ({size_mb:.2f}MB)" for (name, size_mb, _mtime) in files]
    text = "🗂️ **백업 목록(최신순)**\n" + "\n".join(lines)
    await inter.response.send_message(text, ephemeral=True)


# ---- Slash command: /카테고리관리 ----
@bot.tree.command(name="카테고리관리", description="카테고리 추가/비활성화(삭제)를 관리합니다.")
async def category_manage_cmd(inter: discord.Interaction):
    if not inter.guild:
        return await inter.response.send_message("서버에서만 사용할 수 있어요.", ephemeral=True)

    if not is_admin(inter, bot.conn):
        return await inter.response.send_message("권한이 없어요.", ephemeral=True)

    cats = list_categories(bot.conn, inter.guild_id, include_inactive=True)
    emb = discord.Embed(title="카테고리 관리", description="추가/비활성화(삭제 대체)를 할 수 있어요.")

    act = [c["name"] for c in cats if c["is_active"] == 1]
    ina = [c["name"] for c in cats if c["is_active"] == 0]
    emb.add_field(name=f"활성({len(act)})", value="\n".join([f"- {n}" for n in act]) or "- 없음", inline=False)
    emb.add_field(name=f"비활성({len(ina)})", value="\n".join([f"- {n}" for n in ina]) or "- 없음", inline=False)

    await inter.response.send_message(embed=emb, view=CategoryManageView(bot.conn, inter.guild), ephemeral=True)


# ---- Slash command: /명령정리 ----
@bot.tree.command(name="명령정리", description="슬래시 명령 중복(길드 잔재)을 정리합니다. (관리자 전용)")
async def cleanup_cmd(inter: discord.Interaction):
    if not inter.guild:
        return await inter.response.send_message("서버에서만 사용할 수 있어요.", ephemeral=True)

    if not is_admin(inter, bot.conn):
        return await inter.response.send_message("권한이 없어요.", ephemeral=True)

    await inter.response.defer(ephemeral=True)

    bot.tree.clear_commands(guild=inter.guild)
    await bot.tree.sync(guild=inter.guild)

    # 바로 보이게 다시 복사
    bot.tree.copy_global_to(guild=inter.guild)
    await bot.tree.sync(guild=inter.guild)

    await inter.followup.send(
        "✅ 길드(서버) 커맨드 잔재를 정리했어요. 이제 중복이 사라져야 정상입니다.",
        ephemeral=True,
    )


# -------------------------------------- #
def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is missing. Set it in .env or environment variables.")

    db_path = os.environ.get("DB_PATH", "./data/inventory.db")

    bot.conn = connect(db_path)
    apply_schema(bot.conn, "./src/schema.sql")

    bot.run(token)


if __name__ == "__main__":
    main()
