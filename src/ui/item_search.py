# src/ui/item_search.py
from __future__ import annotations

import discord
from discord.ui import Modal, TextInput, View, Select

from repo.item_repo import search_items
from ui.item_actions import ItemActionsView
from utils.perm import is_admin


def _item_label(name: str, code: str | None) -> str:
    if code:
        s = f"{name} ({code})"
    else:
        s = name
    return s[:100]


def _item_desc(category_name: str, qty: int | None) -> str:
    q = "?" if qty is None else str(qty)
    return f"{category_name} · 재고 {q}"[:100]


def build_item_embed(guild: discord.Guild, item: dict) -> discord.Embed:
    name = item.get("name") or "(이름 없음)"
    code = item.get("code") or "-"
    qty = item.get("qty")
    cat = item.get("category_name") or "기타"
    note = item.get("note") or "-"
    loc = item.get("storage_location") or "-"
    img = item.get("image_url")

    emb = discord.Embed(title=name, description="품목 상세")
    emb.add_field(name="코드", value=str(code), inline=True)
    emb.add_field(name="카테고리", value=str(cat), inline=True)
    emb.add_field(name="현재 재고", value=str(qty), inline=True)
    emb.add_field(name="보관 위치", value=str(loc), inline=False)
    emb.add_field(name="메모", value=str(note), inline=False)
    if img:
        emb.set_image(url=str(img))
    emb.set_footer(text=f"{guild.name} · 품목 ID {item.get('id')}")
    return emb


class ItemSearchModal(Modal, title="품목 검색"):
    q = TextInput(
        label="검색어 (품목명 또는 코드)",
        placeholder="예: 팔물탕 / 49 / G15  (※ 비밀번호·개인정보 입력 X)",
        required=True,
        max_length=50,
    )

    def __init__(self, conn, guild_id: int):
        super().__init__()
        self.conn = conn
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        keyword = str(self.q.value).strip()
        items = search_items(self.conn, self.guild_id, keyword, limit=20)

        if not items:
            return await interaction.response.send_message(
                f"검색 결과가 없어요: `{keyword}`\n"
                "다른 키워드(품목명 일부 / 코드 일부)로 다시 시도해 주세요.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            f"검색 결과 {len(items)}개 (최대 20개 표시)\n"
            "원하는 품목을 선택하면 상세가 표시됩니다.",
            ephemeral=True,
            view=ItemSearchResultsView(items),
        )


class ItemResultSelect(Select):
    def __init__(self, items: list[dict]):
        self.items = items
        opts = []
        for it in items:
            opts.append(
                discord.SelectOption(
                    label=_item_label(it.get("name", ""), it.get("code")),
                    value=str(it.get("id")),
                    description=_item_desc(it.get("category_name", "기타"), it.get("qty")),
                )
            )
        super().__init__(placeholder="품목을 선택하세요", min_values=1, max_values=1, options=opts)

    async def callback(self, interaction: discord.Interaction):
        # ✅ ACK(3초 타임아웃 방지)
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        try:
            chosen_id = int(self.values[0])
            chosen = next((x for x in self.items if int(x.get("id")) == chosen_id), None)
            if not chosen:
                return await interaction.followup.send("선택한 품목을 찾지 못했어요.", ephemeral=True)

            emb = build_item_embed(interaction.guild, chosen)

            # 기본 3버튼(입고/출고/정정)
            view = ItemActionsView(item_id=chosen_id, item_name=str(chosen.get("name") or ""))

            # 사진 업로드 버튼(누구나)
            from ui.item_image import _BtnUploadImage
            view.add_item(_BtnUploadImage(chosen_id, str(chosen.get("name") or "")))

            # 품목 삭제(비활성화) 버튼(관리자)
            if is_admin(interaction, interaction.client.conn):
                from ui.item_delete import _BtnDeactivate
                view.add_item(_BtnDeactivate(chosen_id, str(chosen.get("name") or "")))

            await interaction.followup.send(embed=emb, ephemeral=True, view=view)

        except Exception as e:
            try:
                await interaction.followup.send(f"표시 실패: `{type(e).__name__}: {e}`", ephemeral=True)
            except Exception:
                pass


class ItemSearchResultsView(View):
    def __init__(self, items: list[dict]):
        super().__init__(timeout=5 * 60)
        self.add_item(ItemResultSelect(items))
