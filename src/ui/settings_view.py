# src/ui/settings_view.py
from __future__ import annotations

import re
import discord
from discord.ui import View, Button, Select, Modal, TextInput
from dashboard import ensure_dashboard_message


from utils.time_kst import now_kst
from utils.perm import is_admin
from repo.settings_repo import (
    get_settings,
    update_settings,
    insert_movement_update_settings,
)

# ---------- small helpers ----------

def _fmt_channel(guild: discord.Guild | None, channel_id) -> str:
    if not guild or not channel_id:
        return "미설정"
    ch = guild.get_channel(int(channel_id))
    return ch.mention if ch else f"(삭제됨: {channel_id})"


def _fmt_role(guild: discord.Guild | None, role_id) -> str:
    if not guild or not role_id:
        return "미설정"
    r = guild.get_role(int(role_id))
    return r.mention if r else f"(삭제됨: {role_id})"


def _hm_text(h: int, m: int) -> str:
    return f"{h:02d}:{m:02d}"


def _normalize_hm(text: str) -> tuple[int, int] | None:
    """
    Accepts HH:MM, minutes only 00 or 30
    """
    m = re.fullmatch(r"\s*(\d{1,2})\s*:\s*(\d{2})\s*", text)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    if not (0 <= hh <= 23):
        return None
    if mm not in (0, 30):
        return None
    return hh, mm


def _build_time_options(base_h: int, base_m: int) -> list[tuple[int, int]]:
    """
    base time ±2 hours, step 30 minutes.
    total 9 entries: -120, -90, ... , +120
    """
    base_total = base_h * 60 + base_m
    deltas = [-120, -90, -60, -30, 0, 30, 60, 90, 120]
    out: list[tuple[int, int]] = []
    for d in deltas:
        t = (base_total + d) % (24 * 60)
        out.append((t // 60, t % 60))
    return out


# ---------- Modal for direct input ----------

class ReportTimeModal(Modal, title="보고서 시간 직접 입력 (HH:MM)"):
    time_text = TextInput(
        label="시간 (예: 18:30)",
        placeholder="HH:MM (MM은 00 또는 30)",
        required=True,
        max_length=5,
    )

    def __init__(self, sv: "SettingsView"):
        super().__init__()
        self.sv = sv

    async def on_submit(self, interaction: discord.Interaction):
        parsed = _normalize_hm(str(self.time_text.value))
        if not parsed:
            return await interaction.response.send_message(
                "형식이 올바르지 않아요. 예: 18:30 (MM은 00 또는 30만 가능)",
                ephemeral=True,
            )
        h, m = parsed
        await self.sv._set_report_time(interaction, h, m, via="직접 입력")


# ---------- Select for time quick choose ----------

class ReportTimeSelect(Select):
    def __init__(self, sv: "SettingsView", base_h: int, base_m: int):
        self.sv = sv
        options = []
        for h, m in _build_time_options(base_h, base_m):
            options.append(discord.SelectOption(label=_hm_text(h, m), value=f"{h:02d}:{m:02d}"))
        super().__init__(
            placeholder="보고서 시간 선택 (±2시간, 30분 단위)",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        parsed = _normalize_hm(self.values[0])
        if not parsed:
            return await interaction.response.send_message("시간 파싱 실패", ephemeral=True)
        h, m = parsed
        await self.sv._set_report_time(interaction, h, m, via="빠른 선택")


# ---------- Role Select (existing role choose) ----------

class BotAdminRoleSelect(discord.ui.RoleSelect):
    def __init__(self, sv: "SettingsView"):
        self.sv = sv
        super().__init__(placeholder="봇 관리자 역할을 선택하세요", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if not is_admin(interaction, self.sv.conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)
        role = self.values[0]
        await self.sv._set_bot_admin_role(interaction, role)


# ---------- User Select for add/remove role ----------

class BotAdminUserSelect(discord.ui.UserSelect):
    def __init__(self, sv: "SettingsView", mode: str):
        self.sv = sv
        self.mode = mode  # "add" or "remove"
        placeholder = "봇 관리자로 지정할 유저 선택" if mode == "add" else "봇 관리자 해제할 유저 선택"
        super().__init__(placeholder=placeholder, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if not is_admin(interaction, self.sv.conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)
        user = self.values[0]
        await self.sv._apply_bot_admin_user(interaction, user, mode=self.mode)


# ---------- Main Settings View ----------

class SettingsView(View):
    def __init__(self, conn, guild: discord.Guild):
        super().__init__(timeout=15 * 60)  # 15 minutes
        self.conn = conn
        self.guild = guild

    # ---- UI builder helpers ----

    @staticmethod
    def build_embed(guild: discord.Guild, s: dict) -> discord.Embed:
        report_h = int(s.get("report_hour", 18))
        report_m = int(s.get("report_minute", 30))
        emb = discord.Embed(title="재고 봇 설정", description="현재 설정 상태입니다.")
        emb.add_field(name="재고관리 채널", value=_fmt_channel(guild, s.get("dashboard_channel_id")), inline=False)
        emb.add_field(name="재고_알림 채널", value=_fmt_channel(guild, s.get("alert_channel_id")), inline=False)
        emb.add_field(name="보고서 업로드", value=_hm_text(report_h, report_m), inline=True)
        emb.add_field(name="봇 관리자 역할", value=_fmt_role(guild, s.get("bot_admin_role_id")), inline=True)
        return emb

    @classmethod
    def build_view(cls, conn, guild: discord.Guild) -> "SettingsView":
        v = cls(conn, guild)
        v.add_item(_BtnSetDashboardChannel(v))
        v.add_item(_BtnSetAlertChannel(v))
        v.add_item(_BtnOpenReportTime(v))
        v.add_item(_BtnBotAdminMenu(v))
        return v

    # ---- internal actions ----

    async def refresh_panel(self, interaction: discord.Interaction, note: str | None = None):
        s = get_settings(self.conn, interaction.guild_id)
        emb = self.build_embed(interaction.guild, s)
        if note:
            emb.set_footer(text=note)
        new_view = SettingsView.build_view(self.conn, interaction.guild)
        await interaction.response.edit_message(embed=emb, view=new_view)

    async def _log_update(self, interaction: discord.Interaction, reason: str, success: int = 1, err: str = ""):
        k = now_kst()
        insert_movement_update_settings(
            self.conn,
            interaction.guild_id,
            reason=reason,
            discord_name=interaction.user.display_name,
            discord_id=interaction.user.id,
            created_at_kst_text=k.kst_text,
            created_at_epoch=k.epoch,
            success=success,
            error_message=err,
        )

    async def _set_dashboard_channel(self, interaction: discord.Interaction):
        if not is_admin(interaction, self.conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)

        # ✅ 이전 대시보드(채널/메시지) 정리: 채널을 옮길 때 핀이 쌓이지 않게
        s_old = get_settings(self.conn, interaction.guild_id)
        old_ch_id = s_old.get("dashboard_channel_id")
        old_msg_id = s_old.get("dashboard_message_id")

        # 새로 지정하려는 채널과 기존 채널이 다를 때만 정리
        if old_ch_id and old_msg_id and int(old_ch_id) != int(interaction.channel_id):
            old_ch = interaction.guild.get_channel(int(old_ch_id))
            if isinstance(old_ch, discord.TextChannel):
                try:
                    old_msg = await old_ch.fetch_message(int(old_msg_id))

                    # 핀 해제 + 삭제 (reason 인자 없이: 버전 호환)
                    try:
                        await old_msg.unpin()
                    except discord.Forbidden:
                        pass

                    try:
                        await old_msg.delete()
                    except discord.Forbidden:
                        pass

                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    # 채널 접근 권한 없으면 어쩔 수 없음 (그래도 DB는 새로 갱신됨)
                    pass

            # DB에 기존 message_id는 초기화(새 채널에서 새로 생성/갱신하게)
            from repo.settings_repo import set_dashboard_message_id
            set_dashboard_message_id(self.conn, interaction.guild_id, None)

        # ✅ 새 채널로 재고관리 지정
        update_settings(self.conn, interaction.guild_id, dashboard_channel_id=interaction.channel_id)

        # ✅ 새 채널에 대시보드 메시지 보장(생성/갱신 + 중복핀 정리)
        from dashboard import ensure_dashboard_message
        ch = interaction.channel
        if isinstance(ch, discord.TextChannel):
            await ensure_dashboard_message(self.conn, interaction.guild, ch)

        await self._log_update(interaction, f"재고관리 채널 지정: #{interaction.channel.name}")
        await self.refresh_panel(interaction, note="재고관리 채널이 설정되었습니다.")



    async def _set_alert_channel(self, interaction: discord.Interaction):
            if not is_admin(interaction, self.conn):
                return await interaction.response.send_message("권한이 없어요.", ephemeral=True)
            # 알림 채널 = 리포트 채널 동일 정책
            update_settings(
                self.conn,
                interaction.guild_id,
                alert_channel_id=interaction.channel_id,
                report_channel_id=interaction.channel_id,
            )
            await self._log_update(interaction, f"재고 알림 채널 지정: #{interaction.channel.name}")
            await self.refresh_panel(interaction, note="재고 알림(리포트) 채널이 설정되었습니다.")

    async def _set_report_time(self, interaction: discord.Interaction, h: int, m: int, via: str):
        if not is_admin(interaction, self.conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)

        s = get_settings(self.conn, interaction.guild_id)
        old_h = int(s.get("report_hour", 18))
        old_m = int(s.get("report_minute", 30))

        update_settings(self.conn, interaction.guild_id, report_hour=h, report_minute=m)
        await self._log_update(
            interaction,
            f"보고서 시간 변경({via}): {_hm_text(old_h, old_m)} -> {_hm_text(h, m)}",
        )

        # Select/Modal로 들어온 경우 response가 이미 사용됐을 수 있음
        if not interaction.response.is_done():
            await self.refresh_panel(interaction, note="보고서 시간이 변경되었습니다.")
        else:
            await interaction.followup.send("✅ 보고서 시간이 변경되었습니다.", ephemeral=True)

    async def _set_bot_admin_role(self, interaction: discord.Interaction, role: discord.Role):
        if not is_admin(interaction, self.conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)

        update_settings(self.conn, interaction.guild_id, bot_admin_role_id=role.id)
        await self._log_update(interaction, f"봇 관리자 역할 지정: @{role.name}")

        if not interaction.response.is_done():
            await self.refresh_panel(interaction, note="봇 관리자 역할이 지정되었습니다.")
        else:
            await interaction.followup.send("✅ 봇 관리자 역할이 지정되었습니다.", ephemeral=True)

    async def _create_bot_admin_role(self, interaction: discord.Interaction):
        if not is_admin(interaction, self.conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)

        try:
            role = await interaction.guild.create_role(
                name="봇 관리자",
                reason="재고 봇 관리자 역할 생성",
            )
            update_settings(self.conn, interaction.guild_id, bot_admin_role_id=role.id)
            await self._log_update(interaction, f"봇 관리자 역할 생성: @{role.name}")

            if not interaction.response.is_done():
                await self.refresh_panel(
                    interaction,
                    note="봇 관리자 역할이 생성되었습니다. (역할 위치: 봇 역할 위/아래 확인)",
                )
            else:
                await interaction.followup.send(
                    "✅ 봇 관리자 역할이 생성되었습니다. (역할 위치: 봇 역할이 더 위여야 부여 가능)",
                    ephemeral=True,
                )
        except discord.Forbidden:
            await self._log_update(interaction, "봇 관리자 역할 생성 실패(권한 부족)", success=0, err="Forbidden")
            return await interaction.response.send_message(
                "역할 생성 권한이 없어요. 봇에 '역할 관리(Manage Roles)' 권한이 필요해요.",
                ephemeral=True,
            )

    async def _apply_bot_admin_user(self, interaction: discord.Interaction, user: discord.abc.User, mode: str):
        s = get_settings(self.conn, interaction.guild_id)
        role_id = s.get("bot_admin_role_id")
        if not role_id:
            return await interaction.response.send_message(
                "먼저 봇 관리자 역할을 지정/생성해 주세요. (/설정 → 봇 관리자 관리)",
                ephemeral=True,
            )

        role = interaction.guild.get_role(int(role_id))
        if not role:
            update_settings(self.conn, interaction.guild_id, bot_admin_role_id=None)
            await self._log_update(interaction, "봇 관리자 역할이 삭제되어 초기화됨", success=0, err="role missing")
            return await interaction.response.send_message(
                "설정된 봇 관리자 역할이 없어졌어요. 다시 지정/생성해 주세요.",
                ephemeral=True,
            )

        if not isinstance(user, discord.Member):
            try:
                member = await interaction.guild.fetch_member(user.id)
            except Exception:
                return await interaction.response.send_message("해당 유저를 서버에서 찾을 수 없어요.", ephemeral=True)
        else:
            member = user

        try:
            if mode == "add":
                await member.add_roles(role, reason="재고 봇 관리자 지정")
                await self._log_update(interaction, f"봇 관리자 추가: {member.display_name}")
                await interaction.response.send_message(
                    f"✅ {member.mention} 님을 봇 관리자로 지정했어요.",
                    ephemeral=True,
                )
            else:
                await member.remove_roles(role, reason="재고 봇 관리자 해제")
                await self._log_update(interaction, f"봇 관리자 해제: {member.display_name}")
                await interaction.response.send_message(
                    f"✅ {member.mention} 님의 봇 관리자 권한을 해제했어요.",
                    ephemeral=True,
                )
        except discord.Forbidden:
            await self._log_update(interaction, "봇 관리자 역할 부여/회수 실패(Forbidden)", success=0, err="Forbidden")
            return await interaction.response.send_message(
                "역할을 부여/회수할 수 없어요.\n"
                "- 봇에 '역할 관리' 권한이 있는지\n"
                "- 역할 목록에서 **봇 역할이 '봇 관리자' 역할보다 위**인지 확인해 주세요.",
                ephemeral=True,
            )


# ---------- Buttons ----------

class _BtnSetDashboardChannel(Button):
    def __init__(self, sv: SettingsView):
        super().__init__(label="이 채널을 재고관리로 지정", style=discord.ButtonStyle.primary)
        self.sv = sv

    async def callback(self, interaction: discord.Interaction):
        await self.sv._set_dashboard_channel(interaction)


class _BtnSetAlertChannel(Button):
    def __init__(self, sv: SettingsView):
        super().__init__(label="이 채널을 재고_알림으로 지정", style=discord.ButtonStyle.primary)
        self.sv = sv

    async def callback(self, interaction: discord.Interaction):
        await self.sv._set_alert_channel(interaction)


class _BtnOpenReportTime(Button):
    def __init__(self, sv: SettingsView):
        super().__init__(label="보고서 시간 변경", style=discord.ButtonStyle.secondary)
        self.sv = sv

    async def callback(self, interaction: discord.Interaction):
        if not is_admin(interaction, self.sv.conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)

        s = get_settings(self.sv.conn, interaction.guild_id)
        base_h = int(s.get("report_hour", 18))
        base_m = int(s.get("report_minute", 30))

        v = View(timeout=10 * 60)
        v.add_item(ReportTimeSelect(self.sv, base_h, base_m))
        v.add_item(_BtnOpenTimeModal(self.sv))
        await interaction.response.send_message(
            "보고서 시간을 선택하거나 직접 입력하세요.",
            ephemeral=True,
            view=v,
        )


class _BtnOpenTimeModal(Button):
    def __init__(self, sv: SettingsView):
        super().__init__(label="직접 입력", style=discord.ButtonStyle.secondary)
        self.sv = sv

    async def callback(self, interaction: discord.Interaction):
        if not is_admin(interaction, self.sv.conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)
        await interaction.response.send_modal(ReportTimeModal(self.sv))


class _BtnBotAdminMenu(Button):
    def __init__(self, sv: SettingsView):
        super().__init__(label="봇 관리자 관리", style=discord.ButtonStyle.success)
        self.sv = sv

    async def callback(self, interaction: discord.Interaction):
        if not is_admin(interaction, self.sv.conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)

        s = get_settings(self.sv.conn, interaction.guild_id)
        role_id = s.get("bot_admin_role_id")

        v = View(timeout=10 * 60)
        if not role_id:
            v.add_item(_BtnCreateBotAdminRole(self.sv))
            v.add_item(BotAdminRoleSelect(self.sv))
            msg = (
                "봇 관리자 역할이 아직 없어요.\n"
                "- [봇 관리자 역할 생성] 또는\n"
                "- [기존 역할 선택]을 진행해 주세요."
            )
        else:
            v.add_item(_BtnAddBotAdmin(self.sv))
            v.add_item(_BtnRemoveBotAdmin(self.sv))
            msg = "봇 관리자 유저를 추가/해제할 수 있어요."

        await interaction.response.send_message(msg, ephemeral=True, view=v)


class _BtnCreateBotAdminRole(Button):
    def __init__(self, sv: SettingsView):
        super().__init__(label="봇 관리자 역할 생성", style=discord.ButtonStyle.success)
        self.sv = sv

    async def callback(self, interaction: discord.Interaction):
        await self.sv._create_bot_admin_role(interaction)


class _BtnAddBotAdmin(Button):
    def __init__(self, sv: SettingsView):
        super().__init__(label="봇 관리자 추가", style=discord.ButtonStyle.success)
        self.sv = sv

    async def callback(self, interaction: discord.Interaction):
        v = View(timeout=5 * 60)
        v.add_item(BotAdminUserSelect(self.sv, mode="add"))
        await interaction.response.send_message("봇 관리자로 지정할 유저를 선택하세요.", ephemeral=True, view=v)


class _BtnRemoveBotAdmin(Button):
    def __init__(self, sv: SettingsView):
        super().__init__(label="봇 관리자 해제", style=discord.ButtonStyle.danger)
        self.sv = sv

    async def callback(self, interaction: discord.Interaction):
        v = View(timeout=5 * 60)
        v.add_item(BotAdminUserSelect(self.sv, mode="remove"))
        await interaction.response.send_message("봇 관리자 권한을 해제할 유저를 선택하세요.", ephemeral=True, view=v)
