import discord
from redbot.core import Config
import logging

from ..modals.quarantine_modals import QuarantineModal, RestoreModal
from ..services import quarantine_service

log = logging.getLogger("red.ops_core.quarantine_views")

class AdminPanelView(discord.ui.View):
    """Persistent Admin Control Panel view for Quarantine and Restore."""

    def __init__(self, config: Config, bot):
        super().__init__(timeout=None)
        self.config = config
        self.bot = bot



    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Extra safety check, but actual admin validation is handled in the service
        return True

    @discord.ui.button(
        label="Quarantine User",
        style=discord.ButtonStyle.danger,
        custom_id="ops_core:quarantine:open_modal",
        emoji="\u26a0\ufe0f"
    )
    async def quarantine_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = QuarantineModal(self.config, quarantine_service.handle_quarantine_modal)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Restore User",
        style=discord.ButtonStyle.success,
        custom_id="ops_core:quarantine:restore_modal",
        emoji="\u2705"
    )
    async def restore_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RestoreModal(self.config, quarantine_service.handle_restore_modal)
        await interaction.response.send_modal(modal)
