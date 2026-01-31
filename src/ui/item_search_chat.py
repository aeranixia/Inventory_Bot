# src/ui/item_search_chat.py
from __future__ import annotations

import asyncio
import discord

from repo.item_repo import search_items
from ui.item_search import ItemSearchResultsView  # 기존 select 결과 뷰 재사용


class _CancelView(discord.ui.View):
    def __init__(self, cancel_event: asyncio.Event):
        super().__init__(timeout=70)  # 안내 시간보다 조금 길게
        self._cancel_event = cancel_event

    @discord.ui.button(
        label="취소",
        style=discord.ButtonStyle.danger,
        custom_id="inv:search:chat:cancel",
    )
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._cancel_event.set()
        # 이 메시지는 에페메랄로 보낼 예정이라 edit 가능
        await interaction.response.edit_message(
            content="❌ 검색이 취소되었습니다.",
            view=None,
        )


async def start_item_search_chat(interaction: discord.Interaction):
    """
    채팅 입력 기반 품목 검색 (현재는 라우터에서 호출 안 하면 비활성 상태)
    흐름:
    1) 에페메랄로 '이 채널에 검색어를 입력' 안내 + 취소 버튼
    2) 유저가 채널에 입력한 다음 메시지를 60초간 대기
    3) 입력 메시지는 가능하면 삭제(권한 있으면)
    4) 결과는 에페메랄로 Select 목록 표시
    """
    if not interaction.guild:
        return await interaction.response.send_message("서버에서만 사용할 수 있어요.", ephemeral=True)

    # 인터랙션 응답은 3초 안에 해야 하므로 먼저 응답
    cancel_event = asyncio.Event()
    view = _CancelView(cancel_event)

    await interaction.response.send_message(
        "🔎 **이 채널에 검색어를 입력해 주세요.** (60초)\n"
        "- 품목명 일부 또는 코드 일부 (예: `팔물탕`, `49`, `G15`)\n"
        "- 입력한 메시지는 가능하면 자동 삭제돼요.\n"
        "※ 비밀번호/개인정보 입력은 필요 없어요.",
        ephemeral=True,
        view=view,
    )

    # 채널에 안내 메시지를 굳이 남기고 싶지 않으면 아래 블록은 삭제해도 됨.
    # (직원들이 어디에 입력해야 하는지 헷갈려하면 유용)
    prompt_msg = None
    try:
        prompt_msg = await interaction.channel.send(
            f"{interaction.user.mention} 🔎 검색어를 입력해 주세요. (60초)  `취소하려면 에페메랄 창에서 취소 버튼`"
        )
    except Exception:
        pass

    def msg_check(m: discord.Message) -> bool:
        return (
            m.author.id == interaction.user.id
            and m.channel.id == interaction.channel.id
            and (m.content or "").strip() != ""
        )

    try:
        # cancel_event vs message wait 중 먼저 끝나는 걸 선택
        msg_task = asyncio.create_task(interaction.client.wait_for("message", check=msg_check, timeout=60))
        cancel_task = asyncio.create_task(cancel_event.wait())
        done, pending = await asyncio.wait({msg_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED)

        for t in pending:
            t.cancel()

        if cancel_task in done:
            # 취소됨
            if prompt_msg:
                try:
                    await prompt_msg.delete()
                except Exception:
                    pass
            return

        msg: discord.Message = msg_task.result()
        keyword = (msg.content or "").strip()

        # 입력 메시지 삭제 시도 (권한 없으면 무시)
        try:
            await msg.delete()
        except Exception:
            pass

        if prompt_msg:
            try:
                await prompt_msg.delete()
            except Exception:
                pass

        conn = interaction.client.conn
        items = search_items(conn, interaction.guild_id, keyword, limit=20)

        if not items:
            return await interaction.followup.send(
                f"검색 결과가 없어요: `{keyword}`\n"
                "다른 키워드(품목명 일부 / 코드 일부)로 다시 시도해 주세요.",
                ephemeral=True,
            )

        await interaction.followup.send(
            f"검색 결과 {len(items)}개 (최대 20개 표시)\n"
            "원하는 품목을 선택하면 상세가 표시됩니다.",
            ephemeral=True,
            view=ItemSearchResultsView(items),
        )

    except asyncio.TimeoutError:
        if prompt_msg:
            try:
                await prompt_msg.delete()
            except Exception:
                pass
        try:
            await interaction.followup.send("⏱️ 60초 동안 입력이 없어서 검색이 종료됐어요.", ephemeral=True)
        except Exception:
            pass
