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
    COLOUR_TICKET_OPEN,
    COLOUR_TICKET_CLOSED,
    COLOUR_DANGER,
    TICKET_TYPES,
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


# ===========================================================================
# TICKET SYSTEM EMBEDS
# ===========================================================================

def build_support_panel_embed() -> discord.Embed:
    """Build the public-facing support panel embed."""
    embed = discord.Embed(
        title="\U0001f3ab  Support & Tickets",
        description=(
            "Need assistance? Select a ticket type from the dropdown below to contact staff.\n\n"
            "**Available options:**\n"
            f"\u2022 {TICKET_TYPES['report']['emoji']}  **{TICKET_TYPES['report']['label']}** — Report a user breaking the rules.\n"
            f"\u2022 {TICKET_TYPES['bug']['emoji']}  **{TICKET_TYPES['bug']['label']}** — Report an issue with the bot or server.\n"
            f"\u2022 {TICKET_TYPES['appeal']['emoji']}  **{TICKET_TYPES['appeal']['label']}** — Appeal a moderation action.\n"
            f"\u2022 {TICKET_TYPES['other']['emoji']}  **{TICKET_TYPES['other']['label']}** — General inquiries and support."
        ),
        colour=COLOUR_PRIMARY,
    )
    embed.set_footer(text=f"{COG_NAME} v{COG_VERSION} • Tickets")
    return embed

# ---------------------------------------------------------------------------
# Admin Control Panel
# ---------------------------------------------------------------------------

def build_admin_panel_embed() -> discord.Embed:
    """Build the persistent Admin Control Panel embed."""
    embed = discord.Embed(
        title="\u26a0\ufe0f  Admin Control Panel",
        description=(
            "Use the buttons below to perform administrative actions on this server.\n\n"
            "**One-Click Quarantine:**\n"
            "Instantly strip all manageable roles below the bot's hierarchy from a user, "
            "apply the Quarantine role, and save a snapshot of their original roles for "
            "later restoration.\n\n"
            "**Restore User:**\n"
            "Re-apply a quarantined user's original roles and remove the Quarantine role."
        ),
        colour=COLOUR_DANGER,
    )
    embed.set_footer(text=f"{COG_NAME} v{COG_VERSION} • Admin Panel")
    return embed

# ---------------------------------------------------------------------------
# Quarantine Log Embed
# ---------------------------------------------------------------------------

def build_quarantine_log_embed(case_data: dict, action: str) -> discord.Embed:
    """Build the log embed for a quarantine or restore action.
    
    action: "quarantine" or "restore"
    """
    is_quarantine = action == "quarantine"
    
    title = f"\u26a0\ufe0f Quarantine Applied — {case_data['case_id']}" if is_quarantine else f"\u2705 Quarantine Restored — {case_data['case_id']}"
    colour = COLOUR_DANGER if is_quarantine else COLOUR_APPROVED
    
    timestamp = case_data.get("restored_at") if not is_quarantine and case_data.get("restored_at") else case_data["created_at"]
    
    embed = discord.Embed(
        title=title,
        colour=colour,
        timestamp=datetime.fromisoformat(timestamp)
    )
    
    target_id = case_data["user_id"]
    actor_id = case_data["created_by"] if is_quarantine else case_data.get("restored_by", "Unknown")
    
    embed.add_field(name="Target User", value=f"<@{target_id}> (`{target_id}`)", inline=True)
    embed.add_field(name="Action By", value=f"<@{actor_id}> (`{actor_id}`)", inline=True)
    embed.add_field(name="Reason/Notes", value=case_data.get("reason") or case_data.get("notes") or "None", inline=False)
    
    if is_quarantine:
        removed = " ".join(f"<@&{r}>" for r in case_data.get("removed_role_ids", [])) or "None"
        skipped = " ".join(f"<@&{r}>" for r in case_data.get("skipped_role_ids", [])) or "None"
        embed.add_field(name="Roles Removed", value=removed, inline=False)
        if case_data.get("skipped_role_ids"):
            embed.add_field(name="Roles Skipped (Unmanageable)", value=skipped, inline=False)
    else:
        status = case_data.get("status")
        if status == "partially_restored":
            failures = case_data.get("restore_failures", [])
            embed.add_field(name="Status", value="\u26a0\ufe0f Partially Restored", inline=False)
            if failures:
                fail_str = "\n".join(f"<@&{f['role_id']}>: {f['reason']}" for f in failures)
                embed.add_field(name="Failed Roles", value=fail_str, inline=False)
        else:
            embed.add_field(name="Status", value="\u2705 Fully Restored", inline=False)

    return embed



def build_ticket_info_embed(ticket_data: dict, guild: discord.Guild) -> discord.Embed:
    """Build the info embed posted at the top of a new ticket space."""
    ticket_type_key = ticket_data["ticket_type"]
    type_info = TICKET_TYPES.get(ticket_type_key, TICKET_TYPES["other"])
    
    status = ticket_data.get("status", "open")
    colour = COLOUR_TICKET_OPEN if status == "open" else COLOUR_TICKET_CLOSED
    
    embed = discord.Embed(
        title=f"{type_info['emoji']}  {type_info['label']} — {ticket_data['ticket_id']}",
        colour=colour,
        timestamp=datetime.fromisoformat(ticket_data["created_at"]),
    )
    embed.add_field(
        name="User",
        value=f"<@{ticket_data['user_id']}>",
        inline=True,
    )
    embed.add_field(
        name="Status",
        value=f"`{status.upper()}`",
        inline=True,
    )
    
    # Render form fields dynamically
    form_data = ticket_data.get("form_data", {})
    if form_data:
        embed.add_field(name="\u200b", value="**--- Ticket Details ---**", inline=False)
        for field_name, field_value in form_data.items():
            if field_value:
                embed.add_field(name=field_name, value=field_value, inline=False)

    if status == "closed":
        embed.add_field(name="\u200b", value="**--- Resolution ---**", inline=False)
        embed.add_field(
            name="Closed By",
            value=f"<@{ticket_data['closed_by']}>",
            inline=True,
        )
        if ticket_data.get("closed_at"):
            closed_dt = datetime.fromisoformat(ticket_data["closed_at"])
            embed.add_field(
                name="Closed At",
                value=discord.utils.format_dt(closed_dt, style="F"),
                inline=True,
            )

    embed.set_footer(text=f"{COG_NAME} • Tickets")
    return embed


def build_ticket_log_embed(ticket_data: dict, action: str, admin: discord.Member | discord.User) -> discord.Embed:
    """Build a compact log embed for ticket actions."""
    ticket_type_key = ticket_data["ticket_type"]
    type_info = TICKET_TYPES.get(ticket_type_key, TICKET_TYPES["other"])
    
    colour = COLOUR_TICKET_CLOSED if action == "closed" else COLOUR_TICKET_OPEN
    emoji = "\U0001f512" if action == "closed" else "\U0001f3ab"

    embed = discord.Embed(
        title=f"{emoji}  Ticket {action.capitalize()} — {ticket_data['ticket_id']}",
        colour=colour,
        timestamp=datetime.now(tz=timezone.utc),
    )
    embed.add_field(
        name="User",
        value=f"<@{ticket_data['user_id']}>",
        inline=True,
    )
    embed.add_field(
        name="Type",
        value=f"{type_info['label']}",
        inline=True,
    )
    embed.add_field(
        name="Admin",
        value=f"{admin.mention}",
        inline=True,
    )
    embed.set_footer(text=f"{COG_NAME} • Log")
    return embed

