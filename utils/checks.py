"""
ops_core.utils.checks
~~~~~~~~~~~~~~~~~~~~~

Permission and state validation helpers.
"""

from __future__ import annotations

import discord


def can_bot_manage_role(
    guild: discord.Guild, role: discord.Role
) -> tuple[bool, str | None]:
    """Check whether the bot can assign/remove *role* in *guild*.

    Returns ``(True, None)`` on success, or ``(False, reason)`` on failure.
    """
    me = guild.me
    if me is None:
        return False, "Bot member object not found in guild."

    # Check Manage Roles permission
    if not me.guild_permissions.manage_roles:
        return False, "Bot is missing the **Manage Roles** permission."

    # Check hierarchy — bot's top role must be strictly above the target role
    if me.top_role <= role:
        return (
            False,
            f"Bot's top role ({me.top_role.mention}) is not higher than "
            f"{role.mention}. Move the bot's role above it in Server Settings → Roles.",
        )

    return True, None


def validate_approval_target(
    guild: discord.Guild,
    role_id: int,
    member: discord.Member | None,
) -> tuple[bool, str | None, discord.Role | None]:
    """Validate that *role_id* exists and the bot can manage it.

    Also checks whether *member* already has the role.

    Returns ``(ok, error_message, role_object)``.
    """
    role = guild.get_role(role_id)
    if role is None:
        return (
            False,
            "The configured role no longer exists in this server.  "
            "An admin should update the approval role options.",
            None,
        )

    ok, reason = can_bot_manage_role(guild, role)
    if not ok:
        return False, reason, role

    if member is not None and role in member.roles:
        return False, f"{member.mention} already has the {role.mention} role.", role

    return True, None, role
