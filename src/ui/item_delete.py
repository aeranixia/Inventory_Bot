# src/ui/item_delete.py
from __future__ import annotations

import discord
from discord.ui import View, Button, Modal, TextInput

from repo.item_repo import deactivate_item
from repo.movement_repo import log_simple_event
from utils.perm import is_admin


class _DeactivateItemModal(Modal):
    reason = TextInput(
        label="사유(필수)",
        placeholder="예: 단종 / 오입력 / 품목 통합",
        required=True,
        max_length=200,
    )

    def __init__(self, item_id: int, item_name: str):
        super().__init__(title=f"품목 삭제(비활성화) · {item_name}")
        self.item_id = item_id
        self.item_name = item_name

    async def on_submit(self, interaction: discord.Interaction):
        if not is_admin(interaction, interaction.client.conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)

        r = str(self.reason.value or "").strip()
        try:
            deactivate_item(interaction.client.conn, interaction.guild_id, self.item_id, r)

            log_simple_event(
                interaction.client.conn,
                interaction.guild_id,
                action="ITEM_DEACTIVATE",
                item_id=self.item_id,
                item_name=self.item_name,
                reason=r,
                actor_name=interaction.user.display_name,
                actor_id=interaction.user.id,
            )

            await interaction.response.send_message(
                f"✅ 품목을 삭제(비활성화)했어요.\n"
                f"- 품목: {self.item_name}\n"
                f"- 사유: {r}",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(f"처리 실패: `{type(e).__name__}: {e}`", ephemeral=True)


class _BtnDeactivate(Button):
    def __init__(self, item_id: int, item_name: str):
        super().__init__(label="품목 삭제(비활성화)", style=discord.ButtonStyle.danger)
        self.item_id = item_id
        self.item_name = item_name

    async def callback(self, interaction: discord.Interaction):
        if not is_admin(interaction, interaction.client.conn):
            return await interaction.response.send_message("권한이 없어요.", ephemeral=True)
        await interaction.response.send_modal(_DeactivateItemModal(self.item_id, self.item_name))


class ItemDeactivateView(View):
    def __init__(self, item_id: int, item_name: str, base_view: View | None = None):
        super().__init__(timeout=10 * 60)
        if base_view:
            for child in list(base_view.children):
                self.add_item(child)
        self.add_item(_BtnDeactivate(item_id, item_name))
