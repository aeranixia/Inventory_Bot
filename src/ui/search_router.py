# src/ui/search_router.py
from __future__ import annotations
import discord

from repo.settings_repo import get_settings

async def start_item_search(interaction: discord.Interaction):
    """
    검색 시작 진입점.
    - 기능은 둘 다 구현해두되
    - 현재는 'modal'만 타도록 강제(활성화 보류)
    """
    conn = interaction.client.conn
    s = get_settings(conn, interaction.guild_id)

    # ✅ 보류: 어떤 값이든 지금은 modal로 고정
    mode = "modal"  # ← 나중에 s.get("search_mode","modal")로 바꾸면 전환됨

    if mode == "chat":
        from ui.item_search_chat import start_item_search_chat
        return await start_item_search_chat(interaction)

    # default: modal
    from ui.item_search import ItemSearchModal
    await interaction.response.send_modal(ItemSearchModal(conn, interaction.guild_id))
