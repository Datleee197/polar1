import discord
from redbot.core import Config

class DatabaseWipeConfirmView(discord.ui.View):
    """View with a confirmation button to completely wipe the guild's Ops Core database."""
    def __init__(self, config: Config, author_id: int):
        super().__init__(timeout=60.0)
        self.config = config
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You cannot use these buttons.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Wipe", style=discord.ButtonStyle.danger, custom_id="opscore:core:wipe_confirm")
    async def confirm_wipe(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.config.guild(interaction.guild).clear()
        
        for item in self.children:
            item.disabled = True
            
        await interaction.response.edit_message(
            content="\u2705 **Database Wiped.** All Ops Core configurations and data for this server have been completely deleted.",
            view=self
        )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="opscore:core:wipe_cancel")
    async def cancel_wipe(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
            
        await interaction.response.edit_message(
            content="\u274c Database wipe cancelled. No data was modified.",
            view=self
        )
        self.stop()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        # Note: We don't have the message object directly here without passing it or relying on interaction,
        # but the standard Discord UI behavior handles timeout visually or we can just let it expire.
