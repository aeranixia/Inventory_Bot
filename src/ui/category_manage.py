# src/ui/category_manage.py
from __future__ import annotations

import discord
from discord.ui import View, Button, Select, Modal, TextInput

from utils.perm import is_admin
from repo.category_repo import (
    list_categories,
    create_or_reactivate_category,
    deactivate_category_and_move_items_to_etc,
)

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

        new = create_or_reactivate_category(self.conn, interaction.guild_id, str(self.name.value))
        cats = list_categories(self.conn, interaction.guild_id, include_inactive=True)
        emb = _build_embed(self.guild, cats)

        await interaction.response.edit_message(
            content=f"✅ 카테고리 적용 완료: **{new['name']}**",
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

        try:
            moved, _etc_id = deactivate_category_and_move_items_to_etc(
                conn, interaction.guild_id, view.selected_category_id
            )
            cats = list_categories(conn, interaction.guild_id, include_inactive=True)
            emb = _build_embed(interaction.guild, cats)
            await interaction.response.edit_message(
                content=f"✅ 카테고리 비활성화 완료. 관련 품목 {moved}개를 **기타**로 이동했습니다.",
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
