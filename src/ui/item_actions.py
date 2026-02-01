# src/ui/item_actions.py
from __future__ import annotations

import discord
from discord.ui import View, Button, Modal, TextInput

from repo.movement_repo import apply_stock_change
from repo.settings_repo import get_settings
from repo.alert_repo import should_send_low_stock_alert


def _to_int(text: str) -> int:
    s = (text or "").strip().replace(",", "")
    if not s:
        raise ValueError("숫자를 입력해 주세요.")
    return int(s)


async def _send_alert_if_configured(
    interaction: discord.Interaction,
    msg: str,
):
    """설정된 재고_알림 채널에 로그 메시지 전송"""
    try:
        conn = interaction.client.conn
        s = get_settings(conn, interaction.guild_id)
        ch_id = s.get("alert_channel_id") or s.get("report_channel_id")
        if not ch_id:
            return
        ch = interaction.guild.get_channel(int(ch_id))
        if isinstance(ch, discord.TextChannel):
            await ch.send(msg)
    except Exception:
        pass


class _InOutModal(Modal):
    qty = TextInput(label="수량(숫자)", placeholder="예: 20", required=True, max_length=12)
    reason = TextInput(label="사유(선택)", placeholder="예: 추가 입고 / 사용 / 폐기", required=False, max_length=200)

    def __init__(self, item_id: int, item_name: str, action: str):
        title = "입고" if action == "IN" else "출고"
        super().__init__(title=f"{title} · {item_name}")
        self.item_id = item_id
        self.item_name = item_name
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = _to_int(str(self.qty.value))
            reason = str(self.reason.value or "").strip()

            result = apply_stock_change(
                interaction.client.conn,
                interaction.guild_id,
                self.item_id,
                action=self.action,
                amount=qty,
                new_qty=None,
                reason=reason,
                actor_name=interaction.user.display_name,
                actor_id=interaction.user.id,
            )

             # ✅ 재고 경고(스팸 방지)
            warn = result.get("warn_below")
            if warn is not None:
                now_below = (int(result["after"]) <= int(warn))
                if should_send_low_stock_alert(interaction.client.conn, interaction.guild_id, result["item_id"], now_below):
                    await _send_alert_if_configured(
                        interaction,
                        f"⚠️ 재고 경고: {result['item_name']} (현재 {result['after']} / 기준 {warn})",
                    )

            action_kor = "입고" if self.action == "IN" else "출고"
            # 알림 채널 로그(원하는 포맷 유지)
            await _send_alert_if_configured(
                interaction,
                f"{action_kor} {result['item_name']} {abs(result['delta'])} "
                f"{interaction.user.display_name}({result['kst_text']})"
                + (f" / 사유: {reason}" if reason else ""),
            )

            await interaction.response.send_message(
                f"✅ {action_kor} 완료\n"
                f"- 품목: {result['item_name']}\n"
                f"- 변동: {abs(result['delta'])}\n"
                f"- 재고: {result['before']} → {result['after']}\n"
                f"- 시간: {result['kst_text']}",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(f"처리 실패: `{type(e).__name__}: {e}`", ephemeral=True)


class _AdjustModal(Modal):
    new_qty = TextInput(label="정정 후 재고(숫자)", placeholder="예: 100", required=True, max_length=12)
    reason = TextInput(label="사유(필수)", placeholder="예: 누락/오입력/실사 결과", required=True, max_length=200)

    def __init__(self, item_id: int, item_name: str):
        super().__init__(title=f"정정 · {item_name}")
        self.item_id = item_id
        self.item_name = item_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_qty = _to_int(str(self.new_qty.value))
            reason = str(self.reason.value or "").strip()

            result = apply_stock_change(
                interaction.client.conn,
                interaction.guild_id,
                self.item_id,
                action="ADJUST",
                amount=None,
                new_qty=new_qty,
                reason=reason,
                actor_name=interaction.user.display_name,
                actor_id=interaction.user.id,
            )

            # ✅ 재고 경고(스팸 방지)
            warn = result.get("warn_below")
            if warn is not None:
                now_below = (int(result["after"]) <= int(warn))
                if should_send_low_stock_alert(interaction.client.conn, interaction.guild_id, result["item_id"], now_below):
                    await _send_alert_if_configured(
                        interaction,
                        f"⚠️ 재고 경고: {result['item_name']} (현재 {result['after']} / 기준 {warn})",
                    )

            # 알림 채널 로그(정정은 before/after 포함)
            await _send_alert_if_configured(
                interaction,
                f"정정 {result['item_name']} {result['after']} (기존 {result['before']} → {result['after']}) "
                f"{interaction.user.display_name}({result['kst_text']}) / 사유: {reason}",
            )

            sign = "+" if result["delta"] >= 0 else ""
            await interaction.response.send_message(
                f"✅ 정정 완료\n"
                f"- 품목: {result['item_name']}\n"
                f"- 재고: {result['before']} → {result['after']} ({sign}{result['delta']})\n"
                f"- 사유: {reason}\n"
                f"- 시간: {result['kst_text']}",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(f"처리 실패: `{type(e).__name__}: {e}`", ephemeral=True)


class ItemActionsView(View):
    """
    품목 상세 화면에 붙일 버튼 3개
    """
    def __init__(self, item_id: int, item_name: str):
        super().__init__(timeout=10 * 60)
        self.item_id = item_id
        self.item_name = item_name

        # persistent가 필요하면 custom_id를 붙여줘야 함 (지금은 상세 화면 ephemeral로 쓰는 걸 추천)
        self.add_item(_BtnIn(item_id, item_name))
        self.add_item(_BtnOut(item_id, item_name))
        self.add_item(_BtnAdjust(item_id, item_name))


class _BtnIn(Button):
    def __init__(self, item_id: int, item_name: str):
        super().__init__(label="입고", style=discord.ButtonStyle.success)
        self.item_id = item_id
        self.item_name = item_name

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(_InOutModal(self.item_id, self.item_name, "IN"))


class _BtnOut(Button):
    def __init__(self, item_id: int, item_name: str):
        super().__init__(label="출고", style=discord.ButtonStyle.danger)
        self.item_id = item_id
        self.item_name = item_name

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(_InOutModal(self.item_id, self.item_name, "OUT"))


class _BtnAdjust(Button):
    def __init__(self, item_id: int, item_name: str):
        super().__init__(label="정정(사유필수)", style=discord.ButtonStyle.secondary)
        self.item_id = item_id
        self.item_name = item_name

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(_AdjustModal(self.item_id, self.item_name))

