from __future__ import annotations

import math
import discord
from discord.ui import View, Select, Button

from repo.category_repo import list_active_categories
from repo.item_repo import (
    list_items_by_category,
    count_items_by_category,
    count_active_items,
)

PAGE_SIZE = 12


def _fmt_item_line(it: dict) -> str:
    name = str(it.get("name") or "").strip() or "(이름없음)"
    code = str(it.get("code") or "").strip()
    qty = int(it.get("qty") or 0)
    warn = int(it.get("warn_below") or 0)
    storage = str(it.get("storage_location") or "").strip()
    note = str(it.get("note") or "").strip()

    bits = [f"**{name}**"]
    if code:
        bits.append(f"`{code}`")
    bits.append(f"수량: **{qty}**")
    if warn > 0:
        bits.append(f"(경고<{warn})")
    if storage:
        bits.append(f"위치: {storage}")
    if note:
        bits.append(f"메모: {note}")

    return " · ".join(bits)


class _CategorySelect(Select):
    def __init__(self, categories: list[dict], current_category_id: int | None):
        self.categories = categories

        opts = []
        for c in categories[:25]:
            cid = str(c.get("id") or "")
            label = str(c.get("name") or "")[:100] or "(이름없음)"
            opts.append(
                discord.SelectOption(
                    label=label,
                    value=cid,
                    default=(current_category_id is not None and str(current_category_id) == cid),
                )
            )

        # 카테고리가 하나도 없으면 빈 options로 Select 생성이 안 되므로 방어
        if not opts:
            opts = [
                discord.SelectOption(
                    label="(카테고리 없음)",
                    value="__none__",
                    description="먼저 /카테고리관리에서 카테고리를 추가하세요",
                )
            ]
            super().__init__(placeholder="카테고리 없음", min_values=1, max_values=1, options=opts, disabled=True)
        else:
            super().__init__(placeholder="카테고리 선택", min_values=1, max_values=1, options=opts)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, ItemListView):
            return

        raw = (self.values[0] if self.values else "").strip()
        if not raw.isdigit():
            return await interaction.response.send_message("카테고리를 다시 선택해 주세요.", ephemeral=True)

        view.category_id = int(raw)
        view.page = 1

        await view._update_message(interaction)


class _BtnPrev(Button):
    def __init__(self):
        super().__init__(label="◀", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, ItemListView):
            return
        if view.page > 1:
            view.page -= 1
        await view._update_message(interaction)


class _BtnNext(Button):
    def __init__(self):
        super().__init__(label="▶", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, ItemListView):
            return
        if view.page < view.total_pages:
            view.page += 1
        await view._update_message(interaction)


class ItemListView(View):
    """
    전체보기 UI:
    - 카테고리 선택(select)
    - 페이지 이동(prev/next)
    - 각 카테고리별 품목을 페이지 단위로 표시
    """

    def __init__(self, conn, guild_id: int):
        super().__init__(timeout=120)

        self.conn = conn
        self.guild_id = int(guild_id)
        self.category_id: int | None = None
        self.page = 1
        self.total_pages = 1

        # children은 send()에서 categories 확정 후 구성한다.

    async def send(self, interaction: discord.Interaction):
        # ✅ (요구사항) 품목이 하나도 없으면 “없다” 안내하고 끝
        total = count_active_items(self.conn, self.guild_id)
        if total <= 0:
            msg = "등록된 품목이 없어요. 먼저 **품목 추가**를 해 주세요."
            if interaction.response.is_done():
                return await interaction.followup.send(msg, ephemeral=True)
            return await interaction.response.send_message(msg, ephemeral=True)

        cats = list_active_categories(self.conn, self.guild_id)
        if cats:
            self.category_id = int(cats[0]["id"])
        else:
            # 카테고리가 없으면, (이론상 ensure_initialized로 생길 텐데) 혹시 몰라 방어
            msg = "카테고리가 없어요. 먼저 `/카테고리관리`에서 카테고리를 추가해 주세요."
            if interaction.response.is_done():
                return await interaction.followup.send(msg, ephemeral=True)
            return await interaction.response.send_message(msg, ephemeral=True)

        # children 구성(처음 1회)
        self.clear_items()
        self.add_item(_CategorySelect(cats, self.category_id))
        self.add_item(_BtnPrev())
        self.add_item(_BtnNext())

        emb = await self._render_embed()

        if interaction.response.is_done():
            await interaction.followup.send(embed=emb, view=self, ephemeral=True)
        else:
            await interaction.response.send_message(embed=emb, view=self, ephemeral=True)

    async def _render_embed(self) -> discord.Embed:
        # 현재 카테고리 기준 count / paging
        assert self.category_id is not None

        total = count_items_by_category(self.conn, self.guild_id, self.category_id)
        self.total_pages = max(1, math.ceil(total / PAGE_SIZE))
        self.page = max(1, min(self.page, self.total_pages))

        offset = (self.page - 1) * PAGE_SIZE
        items = list_items_by_category(
            self.conn,
            self.guild_id,
            self.category_id,
            offset=offset,
            limit=PAGE_SIZE,
        )

        # 카테고리명 찾기
        cat_name = "카테고리"
        for c in list_active_categories(self.conn, self.guild_id):
            if int(c["id"]) == int(self.category_id):
                cat_name = str(c["name"])
                break

        emb = discord.Embed(
            title=f"📦 전체보기 · {cat_name}",
            description=f"페이지 **{self.page}/{self.total_pages}** · 총 **{total}**개",
        )

        if not items:
            emb.add_field(name="품목", value="(이 카테고리에 품목이 없어요)", inline=False)
            return emb

        lines = [_fmt_item_line(it) for it in items]
        emb.add_field(name="품목", value="\n".join(lines)[:3900], inline=False)
        return emb

    async def _update_message(self, interaction: discord.Interaction):
        emb = await self._render_embed()

        # 컴포넌트 interaction은 message가 존재한다.
        try:
            await interaction.response.edit_message(embed=emb, view=self)
        except Exception:
            # 이미 응답이 끝났거나 edit 실패 시 followup으로
            try:
                await interaction.followup.send(embed=emb, view=self, ephemeral=True)
            except Exception:
                pass
