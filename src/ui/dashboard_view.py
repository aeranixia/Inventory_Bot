from __future__ import annotations

import discord
from discord.ui import View, Button
from utils.perm import is_admin
from ui.item_action_search import ActionItemSearchModal
from ui.search_router import start_item_search
from ui.item_list import ItemListView


class DashboardView(View):
    def __init__(self):
        super().__init__(timeout=None)  # ✅ persistent view 조건 1

        self.add_item(_BtnIncoming())
        self.add_item(_BtnOutgoing())
        self.add_item(_BtnAdjust())
        self.add_item(_BtnSearch())
        self.add_item(_BtnListAll())
        self.add_item(_BtnAddItem())


class _BtnListAll(Button):
    def __init__(self):
        super().__init__(
            label="전체보기",
            style=discord.ButtonStyle.secondary,
            custom_id="inv:dash:list_all",
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("서버에서만 사용할 수 있어요.", ephemeral=True)

        # 3초 타임아웃 방지
        await interaction.response.defer(ephemeral=True)

        try:
            view = ItemListView(interaction.client.conn, interaction.guild_id)
            await view.send(interaction)
        except Exception as e:
            print("[LIST_ALL_ERROR]", repr(e))
            try:
                await interaction.followup.send(
                    f"전체보기 실패: `{type(e).__name__}: {e}`",
                    ephemeral=True,
                )
            except Exception:
                pass


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

        # ✅ 첫 사용자가 /설정 을 안 눌렀어도 동작하도록 기본 row 보강
        try:
            from repo.bootstrap_repo import ensure_initialized
            from utils.time_kst import now_kst
            k = now_kst()
            ensure_initialized(conn, interaction.guild_id, k.kst_text)
        except Exception:
            # 초기화 실패해도 UI 자체는 띄우되, 이후 단계에서 에러가 나면 사용자에게 표시됨
            pass

        try:
            # 순환 import/실수로 인한 ImportError 방지: 여기서 import
            from ui.item_add import AddItemStartView

            await interaction.response.send_message(
                "추가할 품목의 **카테고리를 선택**하세요.",
                ephemeral=True,
                view=AddItemStartView(conn, interaction.guild_id),
            )
        except Exception as e:
            print("[ADD_ITEM_BTN_ERROR]", repr(e))
            await interaction.response.send_message(
                f"품목 추가 UI를 여는 중 오류가 발생했어요: `{type(e).__name__}: {e}`",
                ephemeral=True,
            )
