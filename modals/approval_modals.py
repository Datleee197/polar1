"""
ops_core.modals.approval_modals
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Discord UI modals for the Approval Queue.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from ..services import approval_service
from ..utils.embeds import build_review_embed, build_dm_embed
from ..views.approval_views import ApprovalReviewView

if TYPE_CHECKING:
    from redbot.core import Config

log = logging.getLogger("red.ops_core.approval_modals")


class ApprovalRequestModal(discord.ui.Modal, title="Role Approval Request"):
    """Modal that collects the user's role request details.

    Opened when a user clicks the "Request Role" button on the
    public approval panel.
    """

    role_key = discord.ui.TextInput(
        label="Role Key",
        placeholder="e.g. member, verified, artist",
        style=discord.TextStyle.short,
        required=True,
        max_length=50,
    )
    reason = discord.ui.TextInput(
        label="Reason",
        placeholder="Why are you requesting this role?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1024,
    )
    evidence = discord.ui.TextInput(
        label="Evidence / Proof (optional)",
        placeholder="Links, screenshots, or other proof",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1024,
    )

    def __init__(self, config: "Config") -> None:
        super().__init__()
        self.config = config

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle modal submission."""
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "\u274c This can only be used in a server.", ephemeral=True
            )
            return

        # Defer — service calls may take a moment
        await interaction.response.defer(ephemeral=True, thinking=True)

        # --- Call service to create the request ---
        request_data, error = await approval_service.create_request(
            config=self.config,
            guild=guild,
            user=interaction.user,
            role_key=self.role_key.value,
            reason=self.reason.value,
            evidence=self.evidence.value,
        )

        if error:
            await interaction.followup.send(f"\u274c {error}", ephemeral=True)
            return

        # --- Post review embed in the approval review channel ---
        review_channel_id = await self.config.guild(guild).approval_review_channel_id()
        if not review_channel_id:
            await interaction.followup.send(
                "\u274c The approval review channel has not been configured.  "
                "Please ask an admin to run `[p]opscore set approvalchannel #channel`.",
                ephemeral=True,
            )
            return

        review_channel = guild.get_channel(review_channel_id)
        if review_channel is None:
            await interaction.followup.send(
                "\u274c The configured approval review channel no longer exists.  "
                "Please ask an admin to reconfigure it.",
                ephemeral=True,
            )
            return

        review_embed = build_review_embed(request_data, guild)
        review_view = ApprovalReviewView(
            config=self.config,
            request_id=request_data["request_id"],
        )

        try:
            review_msg = await review_channel.send(embed=review_embed, view=review_view)
        except discord.Forbidden:
            await interaction.followup.send(
                "\u274c Bot cannot send messages in the approval review channel.  "
                "Please check channel permissions.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            log.error("Failed to post review embed: %s", exc)
            await interaction.followup.send(
                "\u274c Failed to post the review card. Please try again later.",
                ephemeral=True,
            )
            return

        # Save the review message ID back into the request record
        await approval_service.set_review_message_id(
            self.config, guild, request_data["request_id"], review_msg.id
        )

        await interaction.followup.send(
            f"\u2705 Your request has been submitted!  "
            f"Request ID: `{request_data['request_id']}`\n"
            f"An admin will review it shortly.",
            ephemeral=True,
        )
        log.info(
            "Approval request %s submitted by %s — review posted in #%s",
            request_data["request_id"],
            interaction.user.id,
            review_channel.name,
        )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        log.exception("Unhandled error in ApprovalRequestModal: %s", error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    "\u274c An unexpected error occurred. Please try again later.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "\u274c An unexpected error occurred. Please try again later.",
                    ephemeral=True,
                )
        except discord.HTTPException:
            pass
