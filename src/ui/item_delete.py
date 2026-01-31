# src/ui/item_delete.py
from __future__ import annotations

import discord
from discord.ui import View, Button, Modal, TextInput

from repo.item_repo import deactivate_item
from repo.movement_repo import log_simple_event
from utils.time_kst import now_kst

class _DeleteReasonModal(Modal, title="품목 비활성화(삭제) 사유 입력"):
    reason = TextInput(
        label="사유(필수)",
        placeholder="예: 더 이상 사용하지 않음 / 등록 오류 / 대체 품목으로 전환",
        required=True,
        max_length=200,
    )

    def __init__(self, item_id: int, item_name: str):
        super().__init__()
        self.item_id = item_id
        self.item_name = item_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            r = deactivate_item(interaction.client.conn, interaction.guild_id, self.item_id, str(self.reason.value))

            # movements에 “이벤트 로그” 남기기 (qty 변화 없음)
            k = now_kst()
            log_simple_event(
                interaction.client.conn,
                guild_id=interaction.guild_id,
                item_id=self.item_id,
                action="ITEM_DEACTIVATE",
                reason=f"품목 비활성화(삭제): {self.reason.value}",
                actor_name=interaction.user.display_name,
                actor_id=interaction.user.id,
                kst_text=k.kst_text,
                epoch=k.epoch,
            )

            await interaction.response.send_message(
                f"✅ 품목 비활성화 완료\n"
                f"- 품목: {r['name']}\n"
                f"- 시간: {r['kst_text']}\n"
                f"- 사유: {self.reason.value}",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(f"처리 실패: {e}", ephemeral=True)

class ItemDeactivateView(View):
    """
    기존 view(입고/출고/정정) 위에 '품목 삭제(비활성화)' 버튼을 추가하는 wrapper
    """
    def __init__(self, item_id: int, item_name: str, base_view: View):
        super().__init__(timeout=10 * 60)
        self.item_id = item_id
        self.item_name = item_name

        # base_view의 children 복사(버튼들)
        for child in base_view.children:
            self.add_item(child)

        self.add_item(_BtnDeactivate(item_id, item_name))

class _BtnDeactivate(Button):
    def __init__(self, item_id: int, item_name: str):
        super().__init__(label="품목 삭제(비활성화)", style=discord.ButtonStyle.danger)
        self.item_id = item_id
        self.item_name = item_name

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(_DeleteReasonModal(self.item_id, self.item_name))
