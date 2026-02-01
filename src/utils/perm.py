# src/utils/perm.py
from __future__ import annotations
import discord
import sqlite3

from repo.settings_repo import get_settings


def is_owner(inter: discord.Interaction) -> bool:
    return bool(inter.guild and inter.user and inter.user.id == inter.guild.owner_id)


def is_bot_admin(inter: discord.Interaction, conn: sqlite3.Connection) -> bool:
    if not inter.guild or not isinstance(inter.user, discord.Member):
        return False
    s = get_settings(conn, inter.guild.id)
    role_id = s.get("bot_admin_role_id")
    if not role_id:
        return False
    return any(r.id == int(role_id) for r in inter.user.roles)


def is_admin(inter: discord.Interaction, conn: sqlite3.Connection) -> bool:
    return is_owner(inter) or is_bot_admin(inter, conn)
