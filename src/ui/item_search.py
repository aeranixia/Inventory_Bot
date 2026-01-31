# src/ui/item_search.py
from __future__ import annotations

import discord
from discord.ui import Modal, TextInput, View, Select
from repo.item_repo import search_items
from ui.item_actions import ItemActionsView

def _item_label(name: str, code: str | None) -> str:
    # Select label은 최대 100자
    if code:
        s = f"{name} ({code})"
    else:
        s = name
    return s[:100]

def _item_desc(category_name: str, qty: int | None) -> str:
    # Select description은 최대 100자
    q = "?" if qty is None else str(qty)
    s = f"{category_name} · 재고 {q}"
    return s[:100]

def build_item_embed(guild: discord.Guild, item: dict) -> discord.Embed:
    name = item.get("name") or "(이름 없음)"
    code = item.get("code") or "-"
    qty = item.get("qty")
    cat = item.get("category_name") or "기타"
    note = item.get("note") or "-"
    loc = item.get("storage_location") or "-"

    emb = discord.Embed(title=name, description="품목 상세")
    emb.add_field(name="코드", value=str(code), inline=True)
    emb.add_field(name="카테고리", value=str(cat), inline=True)
    emb.add_field(name="현재 재고", value=str(qty), inline=True)
    emb.add_field(name="보관 위치", value=str(loc), inline=False)
    emb.add_field(name="메모", value=str(note), inline=False)
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

        view = ItemSearchResultsView(items)
        await interaction.response.send_message(
            f"검색 결과 {len(items)}개 (최대 20개 표시)\n"
            "원하는 품목을 선택하면 상세가 표시됩니다.",
            ephemeral=True,
            view=view,
        )


class ItemResultSelect(Select):
    def __init__(self, items: list[dict]):
        self.items = items
        opts = []
        for it in items:
            opts.append(
                discord.SelectOption(
                    label=_item_label(it.get("name",""), it.get("code")),
                    value=str(it.get("id")),
                    description=_item_desc(it.get("category_name","기타"), it.get("qty")),
                )
            )
        super().__init__(
            placeholder="품목을 선택하세요",
            min_values=1,
            max_values=1,
            options=opts,
        )

    async def callback(self, interaction: discord.Interaction):
        # ✅ 0) 먼저 ACK(3초 타임아웃 방지)
        try:
            await interaction.response.defer(ephemeral=True)  # thinking=True 금지(버전차이/컴포넌트 차이)
        except Exception:
            pass

        try:
            chosen_id = int(self.values[0])
            chosen = next((x for x in self.items if int(x.get("id")) == chosen_id), None)
            if not chosen:
                return await interaction.followup.send("선택한 품목을 찾지 못했어요.", ephemeral=True)

            emb = build_item_embed(interaction.guild, chosen)

            # ✅ 1) 여기서 import(순환/초기 로딩 문제 회피)
            from ui.item_actions import ItemActionsView

            await interaction.followup.send(
                embed=emb,
                ephemeral=True,
                view=ItemActionsView(
                    item_id=chosen_id,
                    item_name=str(chosen.get("name") or ""),
                ),
            )

        except Exception as e:
            # ✅ 2) 실패해도 사용자에게 원인 표시
            try:
                await interaction.followup.send(
                    f"표시 실패: `{type(e).__name__}: {e}`",
                    ephemeral=True,
                )
            except Exception:
                pass

    async def on_error(self, interaction: discord.Interaction, error: Exception, item=None):
        # ✅ 콜백 예외가 나도 interaction failed 대신 메시지로 보여주기
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"오류: `{type(error).__name__}: {error}`",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"오류: `{type(error).__name__}: {error}`",
                    ephemeral=True,
                )
        except Exception:
            pass



class ItemSearchResultsView(View):
    def __init__(self, items: list[dict]):
        super().__init__(timeout=5 * 60)
        self.add_item(ItemResultSelect(items))
