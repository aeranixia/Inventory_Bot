# src/ui/item_add.py
from __future__ import annotations

import discord
from discord.ui import View, Select, Modal, TextInput

from repo.category_repo import list_active_categories
from repo.item_repo import create_item


def _to_int(text: str) -> int:
    s = (text or "").strip().replace(",", "")
    if not s:
        raise ValueError("숫자를 입력해 주세요.")
    return int(s)


def _to_int_optional(text: str, default: int = 0) -> int:
    """빈칸이면 default로 처리 (0 등)."""
    s = (text or "").strip().replace(",", "")
    if not s:
        return default
    return int(s)


class AddItemModal(Modal):
    name_in = TextInput(label="품목명", placeholder="예: 팔물탕", required=True, max_length=60)
    code_in = TextInput(label="코드(선택)", placeholder="예: 49 / G15 (없으면 비움)", required=False, max_length=30)
    qty_in = TextInput(label="초기 재고(숫자)", placeholder="예: 100 (비우면 0)", required=False, max_length=12)
    note_in = TextInput(label="메모(선택)", placeholder="예: 주의사항/비고", required=False, max_length=200)
    loc_in = TextInput(label="보관 위치(선택)", placeholder="예: 1층 탕전실 선반 A", required=False, max_length=120)

    def __init__(self, conn, guild_id: int, category_id: int, category_name: str):
        super().__init__(title=f"품목 추가 · {category_name}")
        self.conn = conn
        self.guild_id = guild_id
        self.category_id = category_id
        self.category_name = category_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = _to_int_optional(str(self.qty_in.value), default=0)
            if qty < 0:
                return await interaction.response.send_message("재고는 0 이상이어야 해요.", ephemeral=True)

            item_id = create_item(
                self.conn,
                self.guild_id,
                self.category_id,
                str(self.name_in.value),
                (str(self.code_in.value).strip() or None),
                qty,
                str(self.note_in.value),
                str(self.loc_in.value),
            )

            await interaction.response.send_message(
                f"✅ 품목이 추가되었습니다.\n"
                f"- 카테고리: {self.category_name}\n"
                f"- 품목명: {self.name_in.value}\n"
                f"- 초기 재고: {qty}\n"
                f"- 품목 ID: {item_id}",
                ephemeral=True,
                view=ContinueAddView(self.conn, self.guild_id, self.category_id, self.category_name),
            )
        except Exception as e:
            await interaction.response.send_message(f"추가 실패: `{type(e).__name__}: {e}`", ephemeral=True)


class CategorySelect(Select):
    def __init__(self, conn, guild_id: int, categories: list[dict]):
        self.conn = conn
        self.guild_id = guild_id
        self.categories = categories

        options = [
            discord.SelectOption(label=str(c["name"])[:100], value=str(c["id"]))
            for c in categories[:25]
        ]
        super().__init__(
            placeholder="카테고리를 선택하세요",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        # 간혹 선택값이 비어있는 상태로 들어오는 경우가 있어서 방어
        if not self.values or not str(self.values[0] or "").strip():
            return await interaction.response.send_message(
                "카테고리를 먼저 선택해 주세요.",
                ephemeral=True,
            )

        cid = int(self.values[0])
        c = next((x for x in self.categories if int(x["id"]) == cid), None)
        if not c:
            return await interaction.response.send_message("카테고리를 찾지 못했어요.", ephemeral=True)

        await interaction.response.send_modal(
            AddItemModal(self.conn, self.guild_id, cid, str(c["name"]))
        )

        # 에페메랄은 삭제가 안 되는 경우가 많아서 UI 제거(재사용 방지)
        try:
            await interaction.edit_original_response(
                content="✅ 카테고리 선택 완료 (이 창은 닫아도 됩니다.)",
                view=None,
            )
        except Exception:
            try:
                if interaction.message:
                    await interaction.message.edit(
                        content="✅ 카테고리 선택 완료 (이 창은 닫아도 됩니다.)",
                        view=None,
                    )
            except Exception:
                pass


class AddItemStartView(View):
    def __init__(self, conn, guild_id: int):
        super().__init__(timeout=5 * 60)
        cats = list_active_categories(conn, guild_id)
        self.add_item(CategorySelect(conn, guild_id, cats))

class ContinueAddView(View):
    def __init__(self, conn, guild_id: int, category_id: int, category_name: str):
        super().__init__(timeout=10 * 60)
        self.conn = conn
        self.guild_id = guild_id
        self.category_id = category_id
        self.category_name = category_name

    @discord.ui.button(label="같은 카테고리로 계속 추가", style=discord.ButtonStyle.success)
    async def btn_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 모달 먼저 열고(응답 사용), 그 뒤 메시지에서 버튼 제거
        await interaction.response.send_modal(
            AddItemModal(self.conn, self.guild_id, self.category_id, self.category_name)
        )
        try:
            if interaction.message:
                await interaction.message.edit(view=None)
        except Exception:
            pass

    @discord.ui.button(label="카테고리 다시 선택", style=discord.ButtonStyle.secondary)
    async def btn_reselect(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 카테고리 선택 UI 다시 띄우고, 기존 메시지는 버튼 제거
        await interaction.response.send_message(
            "추가할 품목의 **카테고리를 선택**하세요.",
            ephemeral=True,
            view=AddItemStartView(self.conn, self.guild_id),
        )
        try:
            if interaction.message:
                await interaction.message.edit(view=None)
        except Exception:
            pass

    @discord.ui.button(label="완료", style=discord.ButtonStyle.primary)
    async def btn_done(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 그냥 버튼 제거
        try:
            await interaction.response.edit_message(content="✅ 완료!", view=None)
        except Exception:
            try:
                if interaction.message:
                    await interaction.message.edit(content="✅ 완료!", view=None)
            except Exception:
                pass
