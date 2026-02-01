# src/ui/item_action_search.py
from __future__ import annotations

import discord
from discord.ui import Modal, TextInput, View, Select

from repo.item_repo import search_items
from ui.item_actions import _InOutModal, _AdjustModal  # reuse existing modals


def _item_label(name: str, code: str | None) -> str:
    s = f"{name} ({code})" if code else name
    return s[:100]


def _item_desc(category_name: str, qty: int | None) -> str:
    q = "?" if qty is None else str(qty)
    return f"{category_name} · 재고 {q}"[:100]


class _ActionItemSelect(Select):
    def __init__(self, items: list[dict], action: str):
        self.items = items
        self.action = action  # IN / OUT / ADJUST
        opts = []
        for it in items:
            opts.append(
                discord.SelectOption(
                    label=_item_label(it.get("name", ""), it.get("code")),
                    value=str(it.get("id")),
                    description=_item_desc(it.get("category_name", "기타"), it.get("qty")),
                )
            )
        placeholder = "품목을 선택하세요"
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=opts)

    async def callback(self, interaction: discord.Interaction):
        try:
            chosen_id = int(self.values[0])
            chosen = next((x for x in self.items if int(x.get("id")) == chosen_id), None)
            if not chosen:
                return await interaction.response.send_message("선택한 품목을 찾지 못했어요.", ephemeral=True)

            name = str(chosen.get("name") or "")

            if self.action == "IN":
                return await interaction.response.send_modal(_InOutModal(chosen_id, name, "IN"))
            if self.action == "OUT":
                return await interaction.response.send_modal(_InOutModal(chosen_id, name, "OUT"))
            return await interaction.response.send_modal(_AdjustModal(chosen_id, name))
        except Exception as e:
            try:
                await interaction.response.send_message(f"처리 실패: `{type(e).__name__}: {e}`", ephemeral=True)
            except Exception:
                pass


class ActionItemPickView(View):
    def __init__(self, items: list[dict], action: str):
        super().__init__(timeout=5 * 60)
        self.add_item(_ActionItemSelect(items, action))


class ActionItemSearchModal(Modal):
    q = TextInput(
        label="검색어 (품목명 또는 코드)",
        placeholder="예: 팔물탕 / 49 / G15",
        required=True,
        max_length=50,
    )

    def __init__(self, conn, guild_id: int, action: str):
        title_map = {"IN": "입고할 품목 검색", "OUT": "출고할 품목 검색", "ADJUST": "정정할 품목 검색"}
        super().__init__(title=title_map.get(action, "품목 검색"))
        self.conn = conn
        self.guild_id = guild_id
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        keyword = str(self.q.value).strip()
        items = search_items(self.conn, self.guild_id, keyword, limit=20)

        if not items:
            return await interaction.response.send_message(
                f"검색 결과가 없어요: `{keyword}`\n"
                "다른 키워드(품목명 일부 / 코드 일부)로 다시 시도해 주세요.",
                ephemeral=True,
            )

        view = ActionItemPickView(items, self.action)
        action_kor = {"IN": "입고", "OUT": "출고", "ADJUST": "정정"}.get(self.action, "처리")
        await interaction.response.send_message(
            f"{action_kor}할 품목을 선택하세요. (검색 결과 {len(items)}개, 최대 20개 표시)",
            ephemeral=True,
            view=view,
        )
