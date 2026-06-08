"""
ops_core.modals.ticket_modals
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Discord modals for the Ticket System.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Type

import discord

if TYPE_CHECKING:
    from redbot.core import Config

log = logging.getLogger("red.ops_core.ticket_modals")


class BaseTicketModal(discord.ui.Modal):
    """Base class for all ticket modals."""

    def __init__(self, config: "Config", ticket_type: str, title: str) -> None:
        super().__init__(title=title[:45])  # Discord modal title limit
        self.config = config
        self.ticket_type = ticket_type

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from ..services.ticket_service import create_ticket
        
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("\u274c This can only be used in a server.", ephemeral=True)
            return

        # Build form data dict from modal fields
        form_data = {}
        for child in self.children:
            if isinstance(child, discord.ui.TextInput):
                form_data[child.label] = child.value

        await interaction.response.defer(ephemeral=True, thinking=True)

        ticket_data, error = await create_ticket(
            config=self.config,
            guild=guild,
            user=interaction.user,
            ticket_type=self.ticket_type,
            form_data=form_data,
            support_channel=interaction.channel,
        )

        if error:
            await interaction.followup.send(f"\u274c {error}", ephemeral=True)
            return

        ticket_id = ticket_data["ticket_id"]
        channel_id = ticket_data.get("thread_id") or ticket_data.get("channel_id")
        
        # Give a link if we successfully made the channel/thread
        if channel_id:
            link = f"<#{channel_id}>"
            await interaction.followup.send(f"\u2705 Ticket created: **{ticket_id}**.\nPlease proceed to {link}.", ephemeral=True)
        else:
            await interaction.followup.send(f"\u2705 Ticket created: **{ticket_id}**.", ephemeral=True)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        log.exception("Unhandled error in ticket modal submit: %s", error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send("\u274c An unexpected error occurred.", ephemeral=True)
            else:
                await interaction.response.send_message("\u274c An unexpected error occurred.", ephemeral=True)
        except discord.HTTPException:
            pass


class ReportTicketModal(BaseTicketModal):
    def __init__(self, config: "Config", ticket_type: str) -> None:
        super().__init__(config, ticket_type, title="Report Violation")
        
        self.add_item(discord.ui.TextInput(
            label="Accused User / User ID",
            style=discord.TextStyle.short,
            required=True,
            max_length=100,
            placeholder="e.g. JohnDoe#1234 or 123456789",
        ))
        self.add_item(discord.ui.TextInput(
            label="What happened?",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000,
            placeholder="Describe the violation...",
        ))
        self.add_item(discord.ui.TextInput(
            label="Evidence / Links",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000,
            placeholder="Message links, screenshots (upload in the ticket later if needed)",
        ))


class BugTicketModal(BaseTicketModal):
    def __init__(self, config: "Config", ticket_type: str) -> None:
        super().__init__(config, ticket_type, title="Report System Bug")
        
        self.add_item(discord.ui.TextInput(
            label="Bug Summary",
            style=discord.TextStyle.short,
            required=True,
            max_length=100,
            placeholder="Brief description of the bug",
        ))
        self.add_item(discord.ui.TextInput(
            label="Steps to Reproduce",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000,
            placeholder="1. Go to...\n2. Click...",
        ))
        self.add_item(discord.ui.TextInput(
            label="Evidence / Logs",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000,
            placeholder="Any extra info or links",
        ))


class AppealTicketModal(BaseTicketModal):
    def __init__(self, config: "Config", ticket_type: str) -> None:
        super().__init__(config, ticket_type, title="Appeal Action")
        
        self.add_item(discord.ui.TextInput(
            label="What are you appealing?",
            style=discord.TextStyle.short,
            required=True,
            max_length=100,
            placeholder="e.g. Warn, Mute, Ban",
        ))
        self.add_item(discord.ui.TextInput(
            label="Why should it be reconsidered?",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000,
            placeholder="Explain your reasoning...",
        ))
        self.add_item(discord.ui.TextInput(
            label="Evidence / Context",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000,
        ))


class OtherTicketModal(BaseTicketModal):
    def __init__(self, config: "Config", ticket_type: str) -> None:
        super().__init__(config, ticket_type, title="General Support")
        
        self.add_item(discord.ui.TextInput(
            label="Subject",
            style=discord.TextStyle.short,
            required=True,
            max_length=100,
            placeholder="What is this regarding?",
        ))
        self.add_item(discord.ui.TextInput(
            label="Description",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1500,
        ))
        self.add_item(discord.ui.TextInput(
            label="Extra Information",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=500,
        ))


def get_ticket_modal(ticket_type: str) -> Type[BaseTicketModal] | None:
    """Return the correct modal class for the ticket type."""
    modals = {
        "report": ReportTicketModal,
        "bug": BugTicketModal,
        "appeal": AppealTicketModal,
        "other": OtherTicketModal,
    }
    return modals.get(ticket_type)
