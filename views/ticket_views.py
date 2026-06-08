"""
ops_core.views.ticket_views
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Persistent Discord UI views for the Ticket System.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from ..constants import TICKET_TYPES

if TYPE_CHECKING:
    from redbot.core import Config

log = logging.getLogger("red.ops_core.ticket_views")


class TicketTypeSelect(discord.ui.Select):
    """Dropdown for selecting the ticket type."""

    def __init__(self, config: "Config") -> None:
        self.config = config
        options = [
            discord.SelectOption(
                label=data["label"],
                value=key,
                emoji=data["emoji"],
            )
            for key, data in TICKET_TYPES.items()
        ]
        super().__init__(
            placeholder="Select a ticket type...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ops_core:ticket:select_type_dropdown",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        # Import modal here to avoid circular imports
        from ..modals.ticket_modals import get_ticket_modal
        
        ticket_type = self.values[0]
        modal_class = get_ticket_modal(ticket_type)
        if not modal_class:
            await interaction.response.send_message("\u274c Invalid ticket type.", ephemeral=True)
            return
            
        modal = modal_class(config=self.config, ticket_type=ticket_type)
        await interaction.response.send_modal(modal)


class SupportPanelView(discord.ui.View):
    """Persistent support panel with a ticket type dropdown.
    
    Static custom_ids.
    """

    def __init__(self, config: "Config") -> None:
        super().__init__(timeout=None)
        self.config = config
        self.add_item(TicketTypeSelect(config))


class TicketCloseView(discord.ui.View):
    """Persistent ticket close view, posted inside the ticket space."""

    def __init__(self, config: "Config", ticket_id: str) -> None:
        super().__init__(timeout=None)
        self.config = config
        self.ticket_id = ticket_id

        close_btn = discord.ui.Button(
            label="\U0001f512 Close Ticket",
            style=discord.ButtonStyle.danger,
            custom_id=f"ops_core:ticket:close:{ticket_id}",
        )
        close_btn.callback = self._close_callback
        self.add_item(close_btn)

    async def _close_callback(self, interaction: discord.Interaction) -> None:
        from ..services.ticket_service import close_ticket
        
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("\u274c Must be used in a server.", ephemeral=True)
            return

        # Defer immediately since generation/uploading transcript might take a moment
        await interaction.response.defer(ephemeral=False, thinking=True)

        ticket_data, err = await close_ticket(
            config=self.config,
            guild=guild,
            ticket_id=self.ticket_id,
            admin_user=interaction.user,
        )

        if err:
            await interaction.followup.send(f"\u274c Failed to close ticket: {err}", ephemeral=False)
            return

        # If the space was locked/archived, the followup might fail if we don't have perms to send
        # in an archived thread, but usually the bot can send or we just pass.
        try:
            # Disable buttons
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)
            
            # Send confirmation
            await interaction.followup.send(f"\u2705 Ticket **{self.ticket_id}** has been closed and archived.", ephemeral=False)
        except discord.HTTPException:
            pass

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item
    ) -> None:
        log.exception(f"Unhandled error in TicketCloseView for {self.ticket_id}: {error}")
        try:
            if interaction.response.is_done():
                await interaction.followup.send("\u274c An unexpected error occurred.", ephemeral=True)
            else:
                await interaction.response.send_message("\u274c An unexpected error occurred.", ephemeral=True)
        except discord.HTTPException:
            pass
