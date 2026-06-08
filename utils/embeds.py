"""
ops_core.utils.embeds
~~~~~~~~~~~~~~~~~~~~~

Centralized embed builders for the Approval Queue.
All embeds are constructed here to keep views/services thin
and ensure a consistent visual style.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord

from ..constants import (
    COLOUR_APPROVED,
    COLOUR_DENIED,
    COLOUR_PENDING,
    COLOUR_PRIMARY,
    COG_NAME,
    COG_VERSION,
)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Public Approval Panel  (posted in a public channel for users)
# ---------------------------------------------------------------------------

def build_approval_panel_embed() -> discord.Embed:
    """Build the public-facing approval panel embed."""
    embed = discord.Embed(
        title="\U0001f4cb  Role Approval Request",
        description=(
            "Need a role?  Click the button below to submit a request.\n\n"
            "**How it works:**\n"
            "1. Click **\U0001f4dd Request Role** below.\n"
            "2. Fill in the role key, your reason, and any evidence.\n"
            "3. An admin will review your request and approve or deny it.\n"
            "4. You'll receive a DM with the outcome."
        ),
        colour=COLOUR_PRIMARY,
    )
    embed.set_footer(text=f"{COG_NAME} v{COG_VERSION} • Approval Queue")
    return embed


# ---------------------------------------------------------------------------
# Admin Review Embed  (posted in the approval review channel)
# ---------------------------------------------------------------------------

def build_review_embed(
    request_data: dict,
    guild: discord.Guild,
) -> discord.Embed:
    """Build the admin review embed for a pending approval request."""
    status = request_data["status"]
    if status == "approved":
        colour = COLOUR_APPROVED
    elif status == "denied":
        colour = COLOUR_DENIED
    else:
        colour = COLOUR_PENDING

    user_id = request_data["user_id"]
    role_id = request_data["role_id"]

    embed = discord.Embed(
        title=f"\U0001f4e5  Approval Request — {request_data['request_id']}",
        colour=colour,
        timestamp=datetime.fromisoformat(request_data["created_at"]),
    )
    embed.add_field(
        name="Requester",
        value=f"<@{user_id}> (`{user_id}`)",
        inline=True,
    )
    embed.add_field(
        name="Requested Role",
        value=f"<@&{role_id}> (`{role_id}`)",
        inline=True,
    )
    embed.add_field(
        name="Role Key",
        value=f"`{request_data['role_key']}`",
        inline=True,
    )
    embed.add_field(
        name="Reason",
        value=request_data.get("reason") or "*No reason provided.*",
        inline=False,
    )
    evidence = request_data.get("evidence")
    if evidence:
        embed.add_field(name="Evidence / Proof", value=evidence, inline=False)
    embed.add_field(
        name="Status",
        value=f"`{status.upper()}`",
        inline=True,
    )

    # If resolved, show who resolved it and when
    if request_data.get("resolved_by"):
        embed.add_field(
            name="Resolved By",
            value=f"<@{request_data['resolved_by']}>",
            inline=True,
        )
    if request_data.get("resolved_at"):
        resolved_dt = datetime.fromisoformat(request_data["resolved_at"])
        embed.add_field(
            name="Resolved At",
            value=discord.utils.format_dt(resolved_dt, style="F"),
            inline=True,
        )

    embed.set_footer(text=f"{COG_NAME} • Approval Queue")
    return embed


# ---------------------------------------------------------------------------
# Admin Log Embed  (posted in the log channel, compact)
# ---------------------------------------------------------------------------

def build_approval_log_embed(
    request_data: dict,
    action: str,
    admin: discord.Member | discord.User,
) -> discord.Embed:
    """Build a compact log embed for the admin log channel."""
    colour = COLOUR_APPROVED if action == "approved" else COLOUR_DENIED
    emoji = "\u2705" if action == "approved" else "\u274c"

    embed = discord.Embed(
        title=f"{emoji}  Approval {action.capitalize()} — {request_data['request_id']}",
        colour=colour,
        timestamp=datetime.now(tz=timezone.utc),
    )
    embed.add_field(
        name="User",
        value=f"<@{request_data['user_id']}>",
        inline=True,
    )
    embed.add_field(
        name="Role",
        value=f"<@&{request_data['role_id']}> (`{request_data['role_key']}`)",
        inline=True,
    )
    embed.add_field(
        name="Admin",
        value=f"{admin.mention}",
        inline=True,
    )
    embed.set_footer(text=f"{COG_NAME} • Log")
    return embed


# ---------------------------------------------------------------------------
# User DM Embed  (sent to the requesting user)
# ---------------------------------------------------------------------------

def build_dm_embed(
    request_data: dict,
    action: str,
    guild_name: str,
) -> discord.Embed:
    """Build a DM notification embed for the requesting user."""
    if action == "approved":
        colour = COLOUR_APPROVED
        emoji = "\u2705"
        title = f"{emoji}  Role Request Approved"
        description = (
            f"Your request for **{request_data['role_key']}** in "
            f"**{guild_name}** has been **approved**!\n\n"
            f"The role has been granted to you."
        )
    else:
        colour = COLOUR_DENIED
        emoji = "\u274c"
        title = f"{emoji}  Role Request Denied"
        description = (
            f"Your request for **{request_data['role_key']}** in "
            f"**{guild_name}** has been **denied**."
        )

    embed = discord.Embed(
        title=title,
        description=description,
        colour=colour,
        timestamp=datetime.now(tz=timezone.utc),
    )
    embed.add_field(
        name="Request ID",
        value=f"`{request_data['request_id']}`",
        inline=True,
    )
    embed.set_footer(text=f"{COG_NAME} • {guild_name}")
    return embed
