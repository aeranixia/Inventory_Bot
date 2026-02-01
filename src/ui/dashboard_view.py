# src/ui/dashboard_view.py
from __future__ import annotations

import discord
from discord.ui import View, Button

from utils.perm import is_admin


class DashboardView(View):
    def __init__(self):
        super().__init__(timeout=None)  # ✅ persistent view 조건 1

        self.add_item(_BtnIncoming())
        self.add_item(_BtnOutgoing())
        self.add_item(_BtnAdjust())
        self.add_item(_BtnSearch())
        self.add_item(_BtnAddItem())


class _BtnIncoming(Button):
    def __init__(self):
        super().__init__(
            label="입고",
            style=discord.ButtonStyle.success,
            custom_id="inv:dash:incoming",  # ✅ persistent view 조건 2
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("서버에서만 사용할 수 있어요.", ephemeral=True)
        if not is_admin(interaction, interaction.client.conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)

        from ui.item_action_search import ActionItemSearchModal
        await interaction.response.send_modal(
            ActionItemSearchModal(interaction.client.conn, interaction.guild_id, action="IN")
        )


class _BtnOutgoing(Button):
    def __init__(self):
        super().__init__(
            label="출고",
            style=discord.ButtonStyle.primary,
            custom_id="inv:dash:outgoing",
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("서버에서만 사용할 수 있어요.", ephemeral=True)
        if not is_admin(interaction, interaction.client.conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)

        from ui.item_action_search import ActionItemSearchModal
        await interaction.response.send_modal(
            ActionItemSearchModal(interaction.client.conn, interaction.guild_id, action="OUT")
        )


class _BtnAdjust(Button):
    def __init__(self):
        super().__init__(
            label="정정(사유 필수)",
            style=discord.ButtonStyle.danger,
            custom_id="inv:dash:adjust",
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("서버에서만 사용할 수 있어요.", ephemeral=True)
        if not is_admin(interaction, interaction.client.conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)

        from ui.item_action_search import ActionItemSearchModal
        await interaction.response.send_modal(
            ActionItemSearchModal(interaction.client.conn, interaction.guild_id, action="ADJUST")
        )


class _BtnSearch(Button):
    def __init__(self):
        super().__init__(
            label="품목 검색",
            style=discord.ButtonStyle.secondary,
            custom_id="inv:dash:search",
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("서버에서만 사용할 수 있어요.", ephemeral=True)

        from ui.search_router import start_item_search
        await start_item_search(interaction)


class _BtnAddItem(Button):
    def __init__(self):
        super().__init__(
            label="품목 추가",
            style=discord.ButtonStyle.success,
            custom_id="inv:dash:add_item",
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("서버에서만 사용할 수 있어요.", ephemeral=True)

        conn = interaction.client.conn
        from ui.item_add import AddItemStartView
        await interaction.response.send_message(
            "추가할 품목의 **카테고리를 선택**하세요.",
            ephemeral=True,
            view=AddItemStartView(conn, interaction.guild_id),
        )
