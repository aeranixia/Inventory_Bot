# src/main.py
from __future__ import annotations

import os
import traceback
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from utils.perm import is_admin

from db import connect, apply_schema
from utils.time_kst import now_kst
from repo.bootstrap_repo import ensure_initialized
from repo.settings_repo import get_settings, ensure_settings_schema
from ui.settings_view import SettingsView
from ui.dashboard_view import DashboardView  # persistent view 등록용
from reporting import force_send_daily_reports, force_send_monthly_prev_month

from backup import run_daily_backup, run_monthly_archive, force_backup_now, list_backup_files
from utils.perm import is_admin



load_dotenv()

# ---- Intents ----
INTENTS = discord.Intents.default()
INTENTS.guilds = True
INTENTS.members = True          # 봇 관리자 역할 부여/회수에 필요
INTENTS.message_content = True  # 채팅 입력(검색 chat 버전) 받을 때 필요

# ---- Dev guild for cleanup ----
DEV_GUILD_ID = int(os.environ.get("DEV_GUILD_ID", "0"))


class InventoryBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)
        self.conn = None  # sqlite3.Connection

    async def setup_hook(self):
        # settings 컬럼 자동 보강
        ensure_settings_schema(self.conn)

        # ✅ persistent view(재시작 후에도 버튼 살아있게)
        self.add_view(DashboardView())

        # ✅ DEV 길드 커맨드 정리(선택)
        if DEV_GUILD_ID:
            guild_obj = discord.Object(id=DEV_GUILD_ID)

            # ✅ 글로벌 커맨드를 DEV 서버로 복사 → 즉시 반영용
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
            print(f"[SYNC] Synced commands to DEV guild: {DEV_GUILD_ID}")
        else:
            # ✅ 글로벌 동기화(전파가 늦게 보일 수 있음)
            await self.tree.sync()
            print("[SYNC] Global sync requested")


        # ✅ 루프 시작(중복 start 방지)
        if not self._report_loop.is_running():
            self._report_loop.start()

    @tasks.loop(minutes=1)
    async def _report_loop(self):
        # 순환 import/의존성 꼬임 방지: 여기서 import
        from reporting import run_daily_reports, run_quarterly_cleanup

        for g in list(self.guilds):
            try:
                await run_daily_reports(self, g)
                await run_quarterly_cleanup(self, g)
                await run_daily_backup(self, g)  # 기본 18:40 KST
                await run_daily_backup(self, g)
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

    # thinking=True는 환경에 따라 UI가 거슬릴 수 있어서 생략(안전)
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

    # ✅ 권한 체크(대표/봇관리자)
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

    lines = []
    for name, size_mb, mtime in files:
        # 보기 편하게 소수 2자리
        lines.append(f"- `{name}` ({size_mb:.2f}MB)")

    text = "🗂️ **백업 목록(최신순)**\n" + "\n".join(lines)
    await inter.response.send_message(text, ephemeral=True)


# -------------------------------------- #
def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is missing. Set it in .env or environment variables.")

    db_path = os.environ.get("DB_PATH", "./data/inventory.db")

    # DB 연결 + 스키마 적용
    bot.conn = connect(db_path)
    apply_schema(bot.conn, "./src/schema.sql")

    bot.run(token)


if __name__ == "__main__":
    main()
