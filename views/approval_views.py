"""
ops_core.views.approval_views
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Persistent Discord UI views for the Approval Queue.

Two view classes:

* **ApprovalPanelView** — public panel with a "Request Role" button.
  Static ``custom_id``; registered once in ``cog_load``.

* **ApprovalReviewView** — admin review card with Accept / Deny buttons.
  Dynamic ``custom_id`` per request; re-registered for each pending
  request during ``cog_load``.

.. note::
   TODO: Consider ``discord.ui.DynamicItem`` in a future stage if the
   number of concurrent pending requests becomes large enough to make
   per-request view registration expensive.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from ..services import approval_service
from ..utils.embeds import (
    build_approval_log_embed,
    build_dm_embed,
    build_review_embed,
)

if TYPE_CHECKING:
    from redbot.core import Config

log = logging.getLogger("red.ops_core.approval_views")


# ======================================================================
# Public Approval Panel View
# ======================================================================

class ApprovalPanelView(discord.ui.View):
    """Persistent public panel — contains the "Request Role" button.

    Uses a static ``custom_id`` so a single ``bot.add_view(...)`` call
    in ``cog_load`` is enough to keep it working across restarts.
    """

    def __init__(self, config: "Config") -> None:
        super().__init__(timeout=None)
        self.config = config

    @discord.ui.button(
        label="\U0001f4dd Request Role",
        style=discord.ButtonStyle.primary,
        custom_id="ops_core:approval:open_modal",
    )
    async def open_modal_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Open the approval request modal."""
        # Import here to avoid circular import at module level
        from ..modals.approval_modals import ApprovalRequestModal

        modal = ApprovalRequestModal(config=self.config)
        await interaction.response.send_modal(modal)


# ======================================================================
# Admin Review View  (Accept / Deny)
# ======================================================================

class ApprovalReviewView(discord.ui.View):
    """Persistent admin review card — Accept and Deny buttons.

    Each instance is tied to a specific ``request_id``.  The
    ``custom_id`` values embed the request ID so that the correct
    handler fires after a bot restart.

    During ``cog_load``, one instance is registered per pending
    request via ``bot.add_view(ApprovalReviewView(...))``.
    """

    def __init__(self, config: "Config", request_id: str) -> None:
        super().__init__(timeout=None)
        self.config = config
        self.request_id = request_id

        # Dynamically create buttons with the request_id baked into custom_id.
        # We cannot use the @discord.ui.button decorator for dynamic IDs,
        # so we build the buttons manually.
        accept_btn = discord.ui.Button(
            label="\u2705 Accept",
            style=discord.ButtonStyle.success,
            custom_id=f"ops_core:approval:accept:{request_id}",
        )
        deny_btn = discord.ui.Button(
            label="\u274c Deny",
            style=discord.ButtonStyle.danger,
            custom_id=f"ops_core:approval:deny:{request_id}",
        )

        accept_btn.callback = self._accept_callback
        deny_btn.callback = self._deny_callback

        self.add_item(accept_btn)
        self.add_item(deny_btn)

    # ------------------------------------------------------------------
    # Accept
    # ------------------------------------------------------------------

    async def _accept_callback(self, interaction: discord.Interaction) -> None:
        await self._resolve(interaction, "approved")

    # ------------------------------------------------------------------
    # Deny
    # ------------------------------------------------------------------

    async def _deny_callback(self, interaction: discord.Interaction) -> None:
        await self._resolve(interaction, "denied")

    # ------------------------------------------------------------------
    # Shared resolve logic
    # ------------------------------------------------------------------

    async def _resolve(self, interaction: discord.Interaction, action: str) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "\u274c This can only be used in a server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        # --- Resolve the request ---
        request_data, error = await approval_service.resolve_request(
            config=self.config,
            guild=guild,
            request_id=self.request_id,
            action=action,
            admin=interaction.user,
        )

        if error:
            await interaction.followup.send(f"\u274c {error}", ephemeral=True)
            return

        # --- Update the review embed (disable buttons, show resolved state) ---
        try:
            updated_embed = build_review_embed(request_data, guild)
            # Disable all buttons on the view
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(embed=updated_embed, view=self)
        except discord.HTTPException as exc:
            log.warning(
                "Could not update review embed for %s: %s",
                self.request_id, exc,
            )

        # --- DM the requesting user ---
        dm_embed = build_dm_embed(request_data, action, guild.name)
        dm_sent = await approval_service.notify_user(
            guild, request_data, action, dm_embed
        )
        dm_note = "" if dm_sent else "\n\u26a0\ufe0f Could not DM the user (DMs may be closed)."

        # --- Log to admin log channel (if configured) ---
        log_channel_id = await self.config.guild(guild).admin_log_channel_id()
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel is not None:
                try:
                    log_embed = build_approval_log_embed(
                        request_data, action, interaction.user
                    )
                    await log_channel.send(embed=log_embed)
                except discord.HTTPException as exc:
                    log.warning("Could not send to log channel: %s", exc)

        # --- Respond to admin ---
        emoji = "\u2705" if action == "approved" else "\u274c"
        await interaction.followup.send(
            f"{emoji} Request `{self.request_id}` has been **{action}**.{dm_note}",
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # Error handler
    # ------------------------------------------------------------------

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item
    ) -> None:
        log.exception(
            "Unhandled error in ApprovalReviewView for %s: %s",
            self.request_id, error,
        )
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    "\u274c An unexpected error occurred.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "\u274c An unexpected error occurred.", ephemeral=True
                )
        except discord.HTTPException:
            pass
