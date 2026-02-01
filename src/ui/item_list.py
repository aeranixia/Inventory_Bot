from __future__ import annotations

import math
import discord
from discord.ui import View, Select, Button

from repo.category_repo import list_active_categories
from repo.item_repo import list_items_by_category, count_items_by_category


PAGE_SIZE = 10


def _fmt_qty(it: dict) -> str:
    qty = int(it.get("qty") or 0)
    warn = int(it.get("warn_below") or 0)
    if warn > 0 and qty <= warn:
        return f"⚠️ {qty} (≤{warn})"
    return str(qty)


def _build_embed(guild: discord.Guild, category_name: str, items: list[dict], page: int, total_pages: int, total_count: int) -> discord.Embed:
    title = f"전체보기 - {category_name}"
    desc = f"총 **{total_count}개** (페이지 {page+1}/{max(1,total_pages)})"
    emb = discord.Embed(title=title, description=desc)

    if not items:
        emb.add_field(name="품목", value="- (비어있어요)", inline=False)
        return emb

    lines = []
    for it in items:
        name = str(it.get("name") or "")
        code = (it.get("code") or "").strip()
        loc = (it.get("storage_location") or "").strip()
        qty = _fmt_qty(it)
        bits = [f"**{name}**", f"수량: {qty}"]
        if code:
            bits.append(f"코드: `{code}`")
        if loc:
            bits.append(f"보관: {loc}")
        lines.append(" · ".join(bits))

    # 디스코드 필드 글자수 제한 고려: 한 필드에 최대 1024
    chunk = "\n".join([f"- {x}" for x in lines])
    if len(chunk) <= 1024:
        emb.add_field(name="품목", value=chunk, inline=False)
    else:
        # 길면 둘로 나눔
        mid = len(lines) // 2 or 1
        c1 = "\n".join([f"- {x}" for x in lines[:mid]])
        c2 = "\n".join([f"- {x}" for x in lines[mid:]])
        emb.add_field(name="품목(1)", value=c1[:1024] or "-", inline=False)
        emb.add_field(name="품목(2)", value=c2[:1024] or "-", inline=False)

    return emb


class _CategorySelect(Select):
    def __init__(self, parent: "ItemListView"):
        self.parent = parent
        options = []
        for c in parent.categories[:25]:  # Discord limit
            options.append(discord.SelectOption(label=c["name"], value=str(c["id"])))
        super().__init__(
            placeholder="카테고리를 선택하세요",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            self.parent.category_id = int(self.values[0])
            self.parent.page = 0
            emb = await self.parent._render(interaction.guild)
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=emb, view=self.parent)
        except Exception as e:
            await interaction.followup.send(f"표시 실패: `{type(e).__name__}: {e}`", ephemeral=True)


class _Prev(Button):
    def __init__(self, parent: "ItemListView"):
        super().__init__(label="이전", style=discord.ButtonStyle.secondary)
        self.parent = parent

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.parent.page > 0:
            self.parent.page -= 1
        emb = await self.parent._render(interaction.guild)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=emb, view=self.parent)


class _Next(Button):
    def __init__(self, parent: "ItemListView"):
        super().__init__(label="다음", style=discord.ButtonStyle.secondary)
        self.parent = parent

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.parent.page + 1 < self.parent.total_pages:
            self.parent.page += 1
        emb = await self.parent._render(interaction.guild)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=emb, view=self.parent)


class ItemListView(View):
    """카테고리별 전체보기(페이지네이션)"""

    def __init__(self, conn, guild_id: int):
        super().__init__(timeout=None)
        self.conn = conn
        self.guild_id = int(guild_id)

        self.categories = list_active_categories(conn, self.guild_id)
        self.category_id = int(self.categories[0]["id"]) if self.categories else 0
        self.page = 0
        self.total_pages = 1

        if self.categories:
            self.add_item(_CategorySelect(self))
        self.add_item(_Prev(self))
        self.add_item(_Next(self))

    async def _render(self, guild: discord.Guild) -> discord.Embed:
        if not self.categories:
            return discord.Embed(title="전체보기", description="카테고리가 없어요. 먼저 `/카테고리관리`에서 만들어 주세요.")

        total_count = count_items_by_category(self.conn, self.guild_id, self.category_id)
        self.total_pages = max(1, int(math.ceil(total_count / PAGE_SIZE)))
        self.page = max(0, min(self.page, self.total_pages - 1))

        offset = self.page * PAGE_SIZE
        items = list_items_by_category(self.conn, self.guild_id, self.category_id, offset=offset, limit=PAGE_SIZE)

        cat_name = next((c["name"] for c in self.categories if int(c["id"]) == int(self.category_id)), "카테고리")
        return _build_embed(guild, cat_name, items, self.page, self.total_pages, total_count)

    async def send(self, interaction: discord.Interaction):
        emb = await self._render(interaction.guild)
        await interaction.followup.send(embed=emb, view=self, ephemeral=True)
