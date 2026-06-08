import discord
from redbot.core import Config
import re

class QuarantineModal(discord.ui.Modal, title="Quarantine User"):
    """Modal to capture user ID and reason for quarantine."""
    
    target_input = discord.ui.TextInput(
        label="Target User ID or Mention",
        style=discord.TextStyle.short,
        placeholder="e.g. 123456789012345678 or @User",
        required=True,
        max_length=100,
    )
    
    case_id_input = discord.ui.TextInput(
        label="Existing Case ID (Optional)",
        style=discord.TextStyle.short,
        placeholder="e.g. QUAR-000001 (leave blank for new)",
        required=False,
        max_length=50,
    )
    
    reason_input = discord.ui.TextInput(
        label="Reason for Quarantine",
        style=discord.TextStyle.short,
        placeholder="Why is this user being quarantined?",
        required=True,
        max_length=200,
    )
    
    notes_input = discord.ui.TextInput(
        label="Internal Notes (Optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Additional context for staff...",
        required=False,
        max_length=1000,
    )

    def __init__(self, config: Config, service_callback):
        super().__init__()
        self.config = config
        self.service_callback = service_callback

    async def on_submit(self, interaction: discord.Interaction):
        # Defers so the service has time to execute role operations
        await interaction.response.defer(ephemeral=True)
        
        # Extract ID from mention if present
        target_str = self.target_input.value.strip()
        match = re.search(r'\d+', target_str)
        if not match:
            await interaction.followup.send("\u274c Invalid user ID or mention format.", ephemeral=True)
            return
            
        target_id = int(match.group(0))
        case_id = self.case_id_input.value.strip().upper() if self.case_id_input.value.strip() else None
        reason = self.reason_input.value.strip()
        notes = self.notes_input.value.strip()
        
        await self.service_callback(self.config, interaction, target_id, case_id, reason, notes)


class RestoreModal(discord.ui.Modal, title="Restore User"):
    """Modal to capture target ID/Case ID for restoration."""
    
    target_input = discord.ui.TextInput(
        label="Target User ID or Case ID",
        style=discord.TextStyle.short,
        placeholder="e.g. 123456789012345678 or QUAR-000001",
        required=True,
        max_length=100,
    )
    
    notes_input = discord.ui.TextInput(
        label="Internal Notes (Optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Reason for restoration...",
        required=False,
        max_length=1000,
    )

    def __init__(self, config: Config, service_callback):
        super().__init__()
        self.config = config
        self.service_callback = service_callback

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        target_str = self.target_input.value.strip()
        notes = self.notes_input.value.strip()
        
        # Could be QUAR-000001 or 123456789012345678
        # If it's a mention, extract numbers
        match = re.search(r'\d+', target_str)
        if match and not target_str.upper().startswith("QUAR"):
            target_val = int(match.group(0))
        else:
            target_val = target_str.upper()
            
        await self.service_callback(self.config, interaction, target_val, notes)
