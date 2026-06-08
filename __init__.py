"""
ops_core
~~~~~~~~

Red-DiscordBot custom cog — Discord operations system.

Modules:
  • Approval Queue   (Stage 01)
  • Ticket System    (Stage 02)
  • One-Click Quarantine  (Stage 03)
"""

from .ops_core import OpsCore

__red_end_user_data_statement__ = (
    "This cog stores guild-level operational data (channel IDs, role IDs, "
    "tickets, approval requests, and quarantine cases).  Per-user data is "
    "limited to user IDs associated with operational records and can be "
    "deleted upon request."
)


async def setup(bot) -> None:
    """Red Bot entry point — load the OpsCore cog."""
    cog = OpsCore(bot)
    await bot.add_cog(cog)
