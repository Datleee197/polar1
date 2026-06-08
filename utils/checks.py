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


# ===========================================================================
# TICKET SYSTEM PERMISSION CHECKS
# ===========================================================================

def can_create_ticket_thread(guild: discord.Guild, channel: discord.TextChannel) -> tuple[bool, str | None]:
    """Check if bot can create private threads in the given channel."""
    me = guild.me
    if me is None:
        return False, "Bot member object not found."

    perms = channel.permissions_for(me)
    if not perms.send_messages_in_threads:
        return False, f"Bot is missing **Send Messages in Threads** in {channel.mention}."
    if not perms.create_private_threads:
        return False, f"Bot is missing **Create Private Threads** in {channel.mention}."
    return True, None


def can_create_ticket_channel(guild: discord.Guild, category: discord.CategoryChannel | None = None) -> tuple[bool, str | None]:
    """Check if bot can create text channels (with overrides) in the guild/category."""
    me = guild.me
    if me is None:
        return False, "Bot member object not found."

    # If falling back to a specific category, check perms there.
    # Otherwise check guild level manage_channels.
    if category:
        perms = category.permissions_for(me)
    else:
        perms = guild.me.guild_permissions

    if not perms.manage_channels:
        return False, "Bot is missing **Manage Channels** permission to create a fallback ticket channel."
    if not perms.manage_roles:
        return False, "Bot is missing **Manage Roles** permission (needed for channel permission overwrites)."
    return True, None


def can_archive_transcript(guild: discord.Guild, channel: discord.TextChannel) -> tuple[bool, str | None]:
    """Check if bot can send the transcript file to the archive channel."""
    me = guild.me
    if me is None:
        return False, "Bot member object not found."

    perms = channel.permissions_for(me)
    if not perms.send_messages:
        return False, f"Bot is missing **Send Messages** in {channel.mention}."
    if not perms.attach_files:
        return False, f"Bot is missing **Attach Files** in {channel.mention}."
    return True, None


def can_read_ticket_history(guild: discord.Guild, channel_or_thread: discord.TextChannel | discord.Thread) -> tuple[bool, str | None]:
    """Check if bot can read message history to generate transcript."""
    me = guild.me
    if me is None:
        return False, "Bot member object not found."

    if isinstance(channel_or_thread, discord.Thread):
        perms = channel_or_thread.parent.permissions_for(me)
    else:
        perms = channel_or_thread.permissions_for(me)

    if not perms.read_message_history:
        return False, f"Bot is missing **Read Message History** in {channel_or_thread.mention}."
    return True, None

