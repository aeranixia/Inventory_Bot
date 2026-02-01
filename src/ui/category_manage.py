# src/ui/category_manage.py
from __future__ import annotations

import discord
from discord.ui import View, Button, Select, Modal, TextInput

from utils.perm import is_admin
from repo.category_repo import list_categories,create_or_reactivate_category, deactivate_category_and_move_items_to_etc

from repo.movement_repo import log_system_event, log_simple_event
from utils.time_kst import now_kst

def _build_embed(guild: discord.Guild, cats: list[dict]) -> discord.Embed:
    emb = discord.Embed(title="카테고리 관리", description="추가/비활성화(삭제 대체)를 할 수 있어요.")
    act = [c for c in cats if c["is_active"] == 1]
    ina = [c for c in cats if c["is_active"] == 0]

    emb.add_field(
        name=f"활성({len(act)})",
        value="\n".join([f"- {c['name']}" for c in act]) or "- 없음",
        inline=False,
    )
    emb.add_field(
        name=f"비활성({len(ina)})",
        value="\n".join([f"- {c['name']}" for c in ina]) or "- 없음",
        inline=False,
    )
    emb.set_footer(text=f"{guild.name} · '기타'는 항상 활성 유지")
    return emb

class _AddCategoryModal(Modal, title="카테고리 추가"):
    name = TextInput(label="카테고리 이름", placeholder="예: 해벽산 / 보험약 / 스틱약 / 공진단 / 기타", max_length=50)

    def __init__(self, conn, guild: discord.Guild):
        super().__init__()
        self.conn = conn
        self.guild = guild

    async def on_submit(self, interaction: discord.Interaction):
        if not is_admin(interaction, self.conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)

        name = str(self.name.value).strip()
        new = create_or_reactivate_category(self.conn, interaction.guild_id, name)

        # ✅ 로그: 추가/재활성화
        k = now_kst()
        act = "CATEGORY_CREATE" if new.get("action") == "created" else "CATEGORY_REACTIVATE"
        log_system_event(
            self.conn,
            interaction.guild_id,
            action=act,
            reason=f"카테고리 {'추가' if act=='CATEGORY_CREATE' else '재활성화'}: {new['name']}",
            actor_name=interaction.user.display_name,
            actor_id=interaction.user.id,
            kst_text=k.kst_text,
            epoch=k.epoch,
        )
        cats = list_categories(self.conn, interaction.guild_id, include_inactive=True)
        emb = _build_embed(self.guild, cats)

        label = "추가" if act == "CATEGORY_CREATE" else "재활성화"
        await interaction.response.edit_message(
            content=f"✅ 카테고리 {label} 완료: **{new['name']}**",
            embed=emb,
            view=CategoryManageView(self.conn, self.guild),
        )

class _CategorySelect(Select):
    def __init__(self, conn, guild_id: int):
        self.conn = conn
        self.guild_id = guild_id

        cats = list_categories(conn, guild_id, include_inactive=True)
        opts = []
        for c in cats:
            label = c["name"]
            desc = "활성" if c["is_active"] == 1 else "비활성"
            opts.append(discord.SelectOption(label=label[:100], value=str(c["id"]), description=desc))
        super().__init__(placeholder="비활성화할 카테고리 선택", min_values=1, max_values=1, options=opts)

    async def callback(self, interaction: discord.Interaction):
        view: CategoryManageView = self.view  # type: ignore
        view.selected_category_id = int(self.values[0])
        # 셀렉트만 누른 건 “표시 업데이트”만
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

class CategoryManageView(View):
    def __init__(self, conn, guild: discord.Guild):
        super().__init__(timeout=10 * 60)
        self.conn = conn
        self.guild = guild
        self.selected_category_id: int | None = None

        self.add_item(_CategorySelect(conn, guild.id))
        self.add_item(_BtnAddCategory())
        self.add_item(_BtnDeactivateCategory())
        self.add_item(_BtnRefresh())

class _BtnAddCategory(Button):
    def __init__(self):
        super().__init__(label="카테고리 추가", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        conn = interaction.client.conn
        if not is_admin(interaction, conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)
        await interaction.response.send_modal(_AddCategoryModal(conn, interaction.guild))

class _BtnDeactivateCategory(Button):
    def __init__(self):
        super().__init__(label="선택 카테고리 비활성화(삭제)", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        conn = interaction.client.conn
        if not is_admin(interaction, conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)

        view: CategoryManageView = self.view  # type: ignore
        if not view.selected_category_id:
            return await interaction.response.send_message("먼저 카테고리를 선택해 주세요.", ephemeral=True)

        # 기타는 고정 카테고리
        cats_now = list_categories(conn, interaction.guild_id, include_inactive=True)
        picked = next((c for c in cats_now if int(c["id"]) == int(view.selected_category_id)), None)
        if picked and str(picked.get("name")) == "기타":
            return await interaction.response.send_message("'기타' 카테고리는 비활성화할 수 없어요.", ephemeral=True)

        try:
            out = deactivate_category_and_move_items_to_etc(conn, interaction.guild_id, view.selected_category_id)

            # 로그: 카테고리 비활성화 + 품목 이동
            k = now_kst()
            log_system_event(
                conn,
                interaction.guild_id,
                action="CATEGORY_DEACTIVATE",
                reason=f"카테고리 비활성화: {out['category_name']} (이동 {len(out['moved_item_ids'])}개 -> 기타)",
                actor_name=interaction.user.display_name,
                actor_id=interaction.user.id,
                kst_text=k.kst_text,
                epoch=k.epoch,
            )

            for item_id in out["moved_item_ids"]:
                log_simple_event(
                    conn,
                    interaction.guild_id,
                    item_id=int(item_id),
                    action="CATEGORY_MOVE",
                    reason=f"카테고리 '{out['category_name']}' 비활성화로 기타로 이동",
                    actor_name=interaction.user.display_name,
                    actor_id=interaction.user.id,
                    kst_text=k.kst_text,
                    epoch=k.epoch,
                )

            cats = list_categories(conn, interaction.guild_id, include_inactive=True)
            emb = _build_embed(interaction.guild, cats)
            await interaction.response.edit_message(
                content=f"✅ 카테고리 비활성화 완료. 관련 품목 {len(out['moved_item_ids'])}개를 **기타**로 이동했습니다.",
                embed=emb,
                view=CategoryManageView(conn, interaction.guild),
            )
        except Exception as e:
            await interaction.response.send_message(f"처리 실패: {e}", ephemeral=True)

class _BtnRefresh(Button):
    def __init__(self):
        super().__init__(label="새로고침", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        conn = interaction.client.conn
        cats = list_categories(conn, interaction.guild_id, include_inactive=True)
        emb = _build_embed(interaction.guild, cats)
        await interaction.response.edit_message(content=None, embed=emb, view=CategoryManageView(conn, interaction.guild))
