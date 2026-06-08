"""
ops_core.services.approval_service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Business logic for the Approval Queue.

All Config reads/writes for approvals go through this module.
Views and modals call these functions — they never touch Config directly.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord

from ..constants import CUSTOM_ID_PREFIX
from ..utils.checks import can_bot_manage_role, validate_approval_target
from ..utils.ids import next_approval_id

if TYPE_CHECKING:
    from redbot.core import Config

log = logging.getLogger("red.ops_core.approval_service")


# ------------------------------------------------------------------
# Create a new approval request
# ------------------------------------------------------------------

async def create_request(
    config: Config,
    guild: discord.Guild,
    user: discord.Member,
    role_key: str,
    reason: str,
    evidence: str,
) -> tuple[dict | None, str | None]:
    """Create a new approval request.

    Returns ``(request_data, None)`` on success,
    or ``(None, error_message)`` on failure.
    """
    role_key = role_key.strip().lower()

    # --- Validate role key exists in config ---
    role_options = await config.guild(guild).approval_role_options()
    if role_key not in role_options:
        available = ", ".join(f"`{k}`" for k in role_options) if role_options else "*(none configured)*"
        return None, (
            f"Unknown role key `{role_key}`.\n"
            f"Available options: {available}\n\n"
            f"Ask an admin to set up role keys with "
            f"`[p]opscore set approvalrole <key> <role>`."
        )

    role_id = role_options[role_key]

    # --- Validate role exists and bot can manage it ---
    ok, err, role = validate_approval_target(guild, role_id, user)
    if not ok:
        return None, err

    # --- Check for duplicate pending request ---
    all_requests = await config.guild(guild).approval_requests()
    for req in all_requests.values():
        if (
            req["user_id"] == user.id
            and req["role_key"] == role_key
            and req["status"] == "pending"
        ):
            return None, (
                f"You already have a pending request for `{role_key}` "
                f"(ID: `{req['request_id']}`).  Please wait for an admin to review it."
            )

    # --- Generate request ID and build record ---
    request_id = next_approval_id(all_requests)
    now = datetime.now(tz=timezone.utc).isoformat()

    request_data = {
        "request_id": request_id,
        "guild_id": guild.id,
        "user_id": user.id,
        "role_id": role_id,
        "role_key": role_key,
        "reason": reason.strip() or "No reason provided.",
        "evidence": evidence.strip() if evidence else "",
        "status": "pending",
        "review_message_id": None,  # filled after posting the review embed
        "created_at": now,
        "resolved_at": None,
        "resolved_by": None,
    }

    # --- Persist ---
    async with config.guild(guild).approval_requests() as reqs:
        reqs[request_id] = request_data

    log.info(
        "Created approval request %s for user %s (role_key=%s) in guild %s",
        request_id, user.id, role_key, guild.id,
    )
    return request_data, None


# ------------------------------------------------------------------
# Store the review message ID back into the request record
# ------------------------------------------------------------------

async def set_review_message_id(
    config: Config,
    guild: discord.Guild,
    request_id: str,
    message_id: int,
) -> None:
    """Save the review embed's message ID into the request record."""
    async with config.guild(guild).approval_requests() as reqs:
        if request_id in reqs:
            reqs[request_id]["review_message_id"] = message_id


# ------------------------------------------------------------------
# Resolve (accept / deny) an approval request
# ------------------------------------------------------------------

async def resolve_request(
    config: Config,
    guild: discord.Guild,
    request_id: str,
    action: str,
    admin: discord.Member,
) -> tuple[dict | None, str | None]:
    """Resolve a pending approval request.

    *action* must be ``"approved"`` or ``"denied"``.

    Returns ``(updated_request_data, None)`` on success,
    or ``(None, error_message)`` on failure.
    """
    all_requests = await config.guild(guild).approval_requests()
    request_data = all_requests.get(request_id)

    if request_data is None:
        return None, f"Request `{request_id}` not found."

    if request_data["status"] != "pending":
        return None, (
            f"Request `{request_id}` has already been "
            f"**{request_data['status']}** and cannot be changed."
        )

    now = datetime.now(tz=timezone.utc).isoformat()

    # --- If approving, grant the role ---
    if action == "approved":
        role_id = request_data["role_id"]
        role = guild.get_role(role_id)
        if role is None:
            return None, (
                f"Role ID `{role_id}` no longer exists.  "
                f"Cannot approve request `{request_id}`."
            )

        ok, err = can_bot_manage_role(guild, role)
        if not ok:
            return None, err

        member = guild.get_member(request_data["user_id"])
        if member is None:
            # User left the server
            return None, (
                f"User <@{request_data['user_id']}> is no longer in this server.  "
                f"Cannot grant role."
            )

        if role in member.roles:
            # User already has the role (maybe granted manually)
            log.info(
                "User %s already has role %s — marking %s as approved without re-granting.",
                member.id, role.id, request_id,
            )
        else:
            try:
                await member.add_roles(role, reason=f"Approval request {request_id} accepted by {admin}")
            except discord.Forbidden:
                return None, "Bot does not have permission to assign this role."
            except discord.HTTPException as exc:
                return None, f"Failed to assign role: {exc}"

    # --- Update the record ---
    async with config.guild(guild).approval_requests() as reqs:
        reqs[request_id]["status"] = action
        reqs[request_id]["resolved_at"] = now
        reqs[request_id]["resolved_by"] = admin.id
        request_data = dict(reqs[request_id])

    log.info(
        "Resolved approval request %s as %s by admin %s in guild %s",
        request_id, action, admin.id, guild.id,
    )
    return request_data, None


# ------------------------------------------------------------------
# DM the requesting user
# ------------------------------------------------------------------

async def notify_user(
    guild: discord.Guild,
    request_data: dict,
    action: str,
    dm_embed: discord.Embed,
) -> bool:
    """Attempt to DM the requesting user.

    Returns ``True`` if the DM was sent, ``False`` if it failed
    (e.g. DMs closed, user not found).
    """
    user_id = request_data["user_id"]
    member = guild.get_member(user_id)
    if member is None:
        log.warning(
            "Cannot DM user %s for request %s — not in guild.",
            user_id, request_data["request_id"],
        )
        return False

    try:
        await member.send(embed=dm_embed)
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        log.warning(
            "Cannot DM user %s for request %s — %s",
            user_id, request_data["request_id"], exc,
        )
        return False


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def get_all_pending_requests(
    config: Config,
    guild_id: int,
) -> dict[str, dict]:
    """Return all pending approval requests for a guild.

    Used during cog_load to re-register review views.
    """
    # Config.guild requires a guild-like object with an `id` attribute.
    # We use a simple namespace since we may not have the guild object yet.
    class _GuildRef:
        def __init__(self, gid: int):
            self.id = gid

    all_requests = await config.guild(_GuildRef(guild_id)).approval_requests()
    return {
        rid: data
        for rid, data in all_requests.items()
        if data.get("status") == "pending"
    }
