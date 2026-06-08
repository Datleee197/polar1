"""
ops_core.services.ticket_service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Business logic for the Ticket System.
Handles ticket creation, thread/channel fallback, and the two-phase closure process.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord

from ..constants import TICKET_TYPES
from ..utils.embeds import build_ticket_info_embed, build_ticket_log_embed
from ..utils.ids import next_ticket_id
from ..utils.checks import (
    can_create_ticket_thread,
    can_create_ticket_channel,
    can_archive_transcript,
    can_read_ticket_history,
)
from .transcript_service import generate_transcript

if TYPE_CHECKING:
    from redbot.core import Config

log = logging.getLogger("red.ops_core.tickets")


async def get_all_open_tickets(config: "Config") -> list[tuple[int, str]]:
    """Return a list of (guild_id, ticket_id) for all currently open tickets."""
    all_guilds = await config.all_guilds()
    open_tickets = []
    for guild_id_str, guild_data in all_guilds.items():
        try:
            guild_id = int(guild_id_str)
        except ValueError:
            continue
        
        tickets = guild_data.get("active_tickets", {})
        for t_id, t_data in tickets.items():
            if t_data.get("status") == "open":
                open_tickets.append((guild_id, t_id))
    return open_tickets


async def check_duplicate_open_ticket(
    config: "Config", guild: discord.Guild, user_id: int, ticket_type: str
) -> str | None:
    """Check if the user already has an open ticket of the same type.
    
    Returns the ticket_id if duplicate exists, otherwise None.
    """
    tickets = await config.guild(guild).active_tickets()
    for t_id, t_data in tickets.items():
        if (
            t_data.get("status") == "open"
            and t_data.get("user_id") == user_id
            and t_data.get("ticket_type") == ticket_type
        ):
            return t_id
    return None


async def create_ticket(
    config: "Config",
    guild: discord.Guild,
    user: discord.Member,
    ticket_type: str,
    form_data: dict,
    support_channel: discord.TextChannel,
) -> tuple[dict | None, str | None]:
    """Create a new ticket space and save to config.

    1. Checks duplicate open tickets
    2. Tries to create a private thread
    3. Falls back to a private channel
    4. Saves to Config
    5. Posts info embed and pings staff
    """
    # 1. Duplicate check
    duplicate_id = await check_duplicate_open_ticket(config, guild, user.id, ticket_type)
    if duplicate_id:
        return None, f"You already have an open `{ticket_type}` ticket: **{duplicate_id}**."

    # Generate ID
    async with config.guild(guild).active_tickets() as tickets:
        ticket_id = next_ticket_id(tickets)
        
        # Determine staff roles
        type_info = TICKET_TYPES.get(ticket_type, TICKET_TYPES["other"])
        staff_key = type_info["staff"]
        staff_role_ids = await config.guild(guild).get_raw(staff_key, default=[])
        
        staff_roles = []
        for r_id in staff_role_ids:
            role = guild.get_role(r_id)
            if role:
                staff_roles.append(role)

        channel_name = f"ticket-{ticket_type}-{user.name}"
        channel_name = channel_name[:100]  # Discord limit

        ticket_space = None
        thread_id = None
        channel_id = None

        # 2. Try Private Thread
        ok, _ = can_create_ticket_thread(guild, support_channel)
        if ok:
            try:
                ticket_space = await support_channel.create_thread(
                    name=channel_name,
                    type=discord.ChannelType.private_thread,
                    invitable=False,
                )
                await ticket_space.add_user(user)
                thread_id = ticket_space.id
                channel_id = support_channel.id
            except discord.HTTPException as exc:
                log.warning(f"Guild {guild.id}: Failed to create private thread: {exc}. Falling back to channel.")
                ticket_space = None

        # 3. Fallback to Private Channel
        if ticket_space is None:
            ok, err = can_create_ticket_channel(guild, support_channel.category)
            if not ok:
                return None, f"Thread creation failed, and channel fallback is impossible: {err}"
            
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True),
                user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            }
            # Add staff roles to overwrites
            for r in staff_roles:
                overwrites[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
                
            try:
                ticket_space = await guild.create_text_channel(
                    name=channel_name,
                    category=support_channel.category,
                    overwrites=overwrites,
                    reason=f"OpsCore Ticket Fallback: {ticket_id}",
                )
                channel_id = ticket_space.id
            except discord.HTTPException as exc:
                return None, f"Failed to create fallback text channel: {exc}"

        # 4. Save to Config
        ticket_data = {
            "ticket_id": ticket_id,
            "guild_id": guild.id,
            "user_id": user.id,
            "ticket_type": ticket_type,
            "channel_id": channel_id,
            "thread_id": thread_id,
            "status": "open",
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "closed_at": None,
            "closed_by": None,
            "transcript_message_id": None,
            "form_data": form_data,
        }
        tickets[ticket_id] = ticket_data

    # 5. Post Embed & Ping Staff
    embed = build_ticket_info_embed(ticket_data, guild)
    
    # Import locally to avoid circular dependency
    from ..views.ticket_views import TicketCloseView
    view = TicketCloseView(config=config, ticket_id=ticket_id)

    ping_text = " ".join([r.mention for r in staff_roles])
    if not ping_text:
        ping_text = "\u26a0\ufe0f *No staff roles configured for this ticket type.*"

    try:
        await ticket_space.send(content=f"Welcome {user.mention} | Staff: {ping_text}", embed=embed, view=view)
    except discord.HTTPException as exc:
        log.error(f"Guild {guild.id}: Failed to post initial ticket embed in {ticket_space.id}: {exc}")
        # Ticket exists but UI is broken. Don't fail completely.

    return ticket_data, None


async def close_ticket(
    config: "Config",
    guild: discord.Guild,
    ticket_id: str,
    admin_user: discord.Member | discord.User,
) -> tuple[dict | None, str | None]:
    """Execute the two-phase ticket closure.

    1. Validate open state
    2. Generate transcript
    3. Send transcript to archive
    4. Update status to closed
    5. Lock/archive/delete the space
    6. Log action
    """
    tickets = await config.guild(guild).active_tickets()
    ticket_data = tickets.get(ticket_id)
    if not ticket_data:
        return None, "Ticket not found."

    if ticket_data.get("status") != "open":
        return ticket_data, "Ticket is already closed."

    archive_ch_id = await config.guild(guild).ticket_archive_channel_id()
    if not archive_ch_id:
        return None, "Archive channel not configured. Cannot close ticket without archiving."
    
    archive_channel = guild.get_channel(archive_ch_id)
    if not archive_channel:
        return None, "Configured archive channel does not exist."

    # Permission check for archive
    ok, err = can_archive_transcript(guild, archive_channel)
    if not ok:
        return None, err

    # Resolve ticket space
    thread_id = ticket_data.get("thread_id")
    channel_id = ticket_data.get("channel_id")
    
    space = None
    if thread_id:
        # It's a thread
        try:
            space = await guild.fetch_channel(thread_id)
        except discord.NotFound:
            pass
    elif channel_id:
        # It's a fallback channel
        space = guild.get_channel(channel_id)
        
    if not space:
        # The space was manually deleted. We can't generate a transcript.
        # But we must allow closing it to clear it from open status.
        log.warning(f"Guild {guild.id}: Ticket space for {ticket_id} is missing. Closing without transcript.")
        async with config.guild(guild).active_tickets() as t_dict:
            t_dict[ticket_id]["status"] = "closed"
            t_dict[ticket_id]["closed_at"] = datetime.now(tz=timezone.utc).isoformat()
            t_dict[ticket_id]["closed_by"] = admin_user.id
            ticket_data = t_dict[ticket_id]
        return ticket_data, "Ticket space was manually deleted. Marked as closed without a transcript."

    # Read history check
    ok, err = can_read_ticket_history(guild, space)
    if not ok:
        return None, err

    # 2. Generate transcript
    html_bytes, err = await generate_transcript(space, ticket_data)
    if err:
        return None, err

    # 3. Send transcript to archive
    file = discord.File(fp=io.BytesIO(html_bytes), filename=f"ticket-{ticket_id}.html")
    try:
        msg = await archive_channel.send(content=f"Transcript for **{ticket_id}** (closed by {admin_user.mention})", file=file)
        transcript_message_id = msg.id
    except discord.HTTPException as exc:
        return None, f"Failed to send transcript to archive channel: {exc}. Ticket remains open."

    # 4. Update status to closed (only after successful archive)
    async with config.guild(guild).active_tickets() as t_dict:
        t_dict[ticket_id]["status"] = "closed"
        t_dict[ticket_id]["closed_at"] = datetime.now(tz=timezone.utc).isoformat()
        t_dict[ticket_id]["closed_by"] = admin_user.id
        t_dict[ticket_id]["transcript_message_id"] = transcript_message_id
        ticket_data = t_dict[ticket_id]

    # 5. Lock/Archive/Delete
    if isinstance(space, discord.Thread):
        try:
            await space.edit(locked=True, archived=True, reason=f"Ticket {ticket_id} closed by {admin_user.name}")
        except discord.HTTPException as exc:
            log.warning(f"Guild {guild.id}: Failed to lock/archive thread {space.id}: {exc}")
    else:
        try:
            await space.delete(reason=f"Ticket {ticket_id} closed by {admin_user.name}")
        except discord.HTTPException as exc:
            log.warning(f"Guild {guild.id}: Failed to delete channel {space.id}: {exc}")

    # 6. Log action
    log_ch_id = await config.guild(guild).admin_log_channel_id()
    if log_ch_id:
        log_ch = guild.get_channel(log_ch_id)
        if log_ch:
            try:
                await log_ch.send(embed=build_ticket_log_embed(ticket_data, "closed", admin_user))
            except discord.HTTPException:
                pass

    return ticket_data, None
