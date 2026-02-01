# src/ui/item_image.py
from __future__ import annotations

import discord
from discord.ui import View, Button

from repo.item_image_repo import set_item_image
from repo.movement_repo import log_simple_event
from repo.settings_repo import get_settings
from utils.time_kst import now_kst

async def _send_alert(interaction: discord.Interaction, text: str, image_url: str | None = None):
    try:
        conn = interaction.client.conn
        s = get_settings(conn, interaction.guild_id)
        ch_id = s.get("alert_channel_id") or s.get("report_channel_id")
        if not ch_id:
            return
        ch = interaction.guild.get_channel(int(ch_id))
        if isinstance(ch, discord.TextChannel):
            if image_url:
                emb = discord.Embed(description=text)
                emb.set_image(url=image_url)
                await ch.send(embed=emb)
            else:
                await ch.send(text)
    except Exception:
        pass

class ItemImageView(View):
    def __init__(self, item_id: int, item_name: str, base_view: View | None = None):
        super().__init__(timeout=10 * 60)
        self.item_id = item_id
        self.item_name = item_name

        if base_view:
            for child in list(base_view.children):
                self.add_item(child)

        self.add_item(_BtnUploadImage(item_id, item_name))

class _BtnUploadImage(Button):
    def __init__(self, item_id: int, item_name: str):
        super().__init__(label="사진 업로드", style=discord.ButtonStyle.primary)
        self.item_id = item_id
        self.item_name = item_name

    async def callback(self, interaction: discord.Interaction):
        # 안내 메시지는 “채널”에 나가야 첨부가 가능
        prompt = await interaction.channel.send(
            f"{interaction.user.mention} **{self.item_name}** 사진을 올려주세요.\n"
            f"- 이 메시지에 **사진(첨부)** 로 답장해 주세요.\n"
            f"- 2분 내 업로드하면 자동 저장됩니다."
        )
        await interaction.response.send_message("사진 업로드 안내를 채널에 올렸어요. 그 메시지에 사진 첨부로 답장해 주세요.", ephemeral=True)

        def check(m: discord.Message):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel.id
                and m.reference is not None
                and m.reference.message_id == prompt.id
                and len(m.attachments) > 0
            )

        try:
            msg: discord.Message = await interaction.client.wait_for("message", timeout=120.0, check=check)
        except Exception:
            try:
                await prompt.edit(content="⏱️ 시간 초과: 사진 업로드가 취소되었습니다.")
            except Exception:
                pass
            return

        # 첫 첨부만 사용
        att = msg.attachments[0]
        image_url = att.url

        # DB 저장
        k = set_item_image(interaction.client.conn, interaction.guild_id, self.item_id, image_url)

        # movements 로그
        log_simple_event(
            interaction.client.conn,
            guild_id=interaction.guild_id,
            item_id=self.item_id,
            action="ITEM_IMAGE_SET",
            reason="품목 사진 업로드",
            actor_name=interaction.user.display_name,
            actor_id=interaction.user.id,
            kst_text=k.kst_text,
            epoch=k.epoch,
            image_url=image_url,
        )

        # 알림 채널 기록(요청한 형태)
        await _send_alert(
            interaction,
            f"✅ 사진이 정상적으로 저장되었습니다: {self.item_name} / {interaction.user.display_name}({k.kst_text})",
            image_url=image_url,
        )

        # 채널 정리(권한 있으면 삭제)
        try:
            await msg.delete()
        except Exception:
            pass
        try:
            await prompt.delete()
        except Exception:
            pass
