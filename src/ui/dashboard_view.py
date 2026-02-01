# src/ui/dashboard_view.py
from __future__ import annotations

import discord
from discord.ui import View, Button
from utils.perm import is_admin
from ui.item_action_search import ActionItemSearchModal
from ui.search_router import start_item_search



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

        try:

            await interaction.response.defer(ephemeral=True)

        except Exception:

            pass


        try:

            from utils.time_kst import now_kst

            from repo.bootstrap_repo import ensure_initialized


            k = now_kst()

            ensure_initialized(self.bot.conn, interaction.guild_id, k.kst_text)


            from ui.item_list import ItemListView

            view = ItemListView(self.bot.conn, interaction.guild_id)


            # ✅ 품목 0개면 안내 메시지

            if getattr(view, "total_all", 0) <= 0:

                return await interaction.followup.send(

                    "등록된 품목이 없어요. **[품목 추가]**로 먼저 등록해 주세요.",

                    ephemeral=True,

                )


            emb = await view._render(interaction.guild)

            await interaction.followup.send(embed=emb, view=view, ephemeral=True)


        except Exception as e:

            print("[LIST_ALL_ERROR]", repr(e))

            try:

                await interaction.followup.send(f"전체보기 실패: `{type(e).__name__}: {e}`", ephemeral=True)

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

        # ✅ 3초 타임아웃 방지

        try:

            await interaction.response.defer(ephemeral=True)

        except Exception:

            pass


        try:

            # ✅ 서버 초기화(기본 카테고리/설정 보장)

            from utils.time_kst import now_kst

            from repo.bootstrap_repo import ensure_initialized


            k = now_kst()

            ensure_initialized(self.bot.conn, interaction.guild_id, k.kst_text)


            # ✅ 카테고리 없으면 안내(빈 값 int('') 방지)

            from repo.category_repo import list_active_categories

            cats = list_active_categories(self.bot.conn, interaction.guild_id)


            if not cats:

                return await interaction.followup.send(

                    "카테고리가 아직 없어요. 먼저 `/카테고리관리`에서 카테고리를 만든 뒤 다시 시도해 주세요.",

                    ephemeral=True,

                )


            from ui.item_add import AddItemStartView

            view = AddItemStartView(self.bot.conn, interaction.guild_id)

            await interaction.followup.send("✅ 품목 추가를 시작할게요.", view=view, ephemeral=True)


        except Exception as e:

            print("[ADD_ITEM_ERROR]", repr(e))

            try:

                await interaction.followup.send(f"추가 시작 실패: `{type(e).__name__}: {e}`", ephemeral=True)

            except Exception:

                pass
