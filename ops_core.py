"""
ops_core.ops_core
~~~~~~~~~~~~~~~~~

Main cog class for the Ops Core operations system.

Stage 00 — Cog skeleton, Config, debug commands.
Stage 01 — Approval Queue MVP (setup commands, persistent panel, review flow).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

from .constants import COG_IDENTIFIER, COG_NAME, COG_VERSION, COLOUR_PRIMARY, DEFAULT_GUILD
from .services import approval_service
from .utils.embeds import build_approval_panel_embed
from .views.approval_views import ApprovalPanelView, ApprovalReviewView

if TYPE_CHECKING:
    pass

log = logging.getLogger("red.ops_core")


class OpsCore(commands.Cog):
    """Discord operations system — Approval Queue, Tickets, and Quarantine."""

    __author__ = "datvt"
    __version__ = COG_VERSION

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=COG_IDENTIFIER,
            force_registration=True,
        )
        self.config.register_guild(**DEFAULT_GUILD)
        log.info(
            "%s v%s — cog instance created, Config schema registered.",
            COG_NAME,
            COG_VERSION,
        )

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    async def cog_load(self) -> None:
        """Called when the cog is loaded.  Re-register persistent views."""

        # 1. Static panel view — one registration covers all guilds
        self.bot.add_view(ApprovalPanelView(config=self.config))

        # 2. Re-register review views for every pending approval request
        #    across all guilds that have data.
        #    TODO: Consider DynamicItem if the number of pending requests
        #    becomes large enough to make per-request registration expensive.
        all_guilds = await self.config.all_guilds()
        pending_count = 0
        for guild_id, guild_data in all_guilds.items():
            requests = guild_data.get("approval_requests", {})
            for request_id, req_data in requests.items():
                if req_data.get("status") == "pending":
                    view = ApprovalReviewView(
                        config=self.config, request_id=request_id
                    )
                    self.bot.add_view(view)
                    pending_count += 1

        log.info(
            "%s v%s — cog_load complete.  "
            "Re-registered %d pending review view(s).",
            COG_NAME,
            COG_VERSION,
            pending_count,
        )

    async def cog_unload(self) -> None:
        """Called when the cog is unloaded.  Clean up tasks/views if needed."""
        log.info("%s v%s — cog_unload complete.", COG_NAME, COG_VERSION)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_config(data: dict) -> str:
        """Return a pretty-printed JSON representation of a config dict."""
        return json.dumps(data, indent=2, default=str)

    # ==================================================================
    # Command group:  [p]opscore
    # ==================================================================

    @commands.group(name="opscore", invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def opscore(self, ctx: commands.Context) -> None:
        """Ops Core — Discord operations system."""
        await ctx.send_help(ctx.command)

    # ==================================================================
    # Sub-group:  [p]opscore set
    # ==================================================================

    @opscore.group(name="set", invoke_without_command=True)
    @commands.admin_or_permissions(administrator=True)
    async def opscore_set(self, ctx: commands.Context) -> None:
        """Configure Ops Core settings."""
        await ctx.send_help(ctx.command)

    @opscore_set.command(name="approvalchannel")
    @commands.admin_or_permissions(administrator=True)
    async def set_approval_channel(
        self, ctx: commands.Context, channel: discord.TextChannel
    ) -> None:
        """Set the channel where approval review embeds are posted."""
        await self.config.guild(ctx.guild).approval_review_channel_id.set(channel.id)
        await ctx.send(
            f"\u2705 Approval review channel set to {channel.mention}."
        )
        log.info(
            "Guild %s: approval_review_channel_id set to %s by %s",
            ctx.guild.id, channel.id, ctx.author.id,
        )

    @opscore_set.command(name="logchannel")
    @commands.admin_or_permissions(administrator=True)
    async def set_log_channel(
        self, ctx: commands.Context, channel: discord.TextChannel
    ) -> None:
        """Set the admin log channel (optional)."""
        await self.config.guild(ctx.guild).admin_log_channel_id.set(channel.id)
        await ctx.send(f"\u2705 Admin log channel set to {channel.mention}.")
        log.info(
            "Guild %s: admin_log_channel_id set to %s by %s",
            ctx.guild.id, channel.id, ctx.author.id,
        )

    @opscore_set.command(name="approvalrole")
    @commands.admin_or_permissions(administrator=True)
    async def set_approval_role(
        self, ctx: commands.Context, key: str, role: discord.Role
    ) -> None:
        """Map a role key to a Discord role for the approval queue.

        Example: ``[p]opscore set approvalrole member @Member``
        Users will type this key in the approval modal.
        """
        key = key.strip().lower()
        async with self.config.guild(ctx.guild).approval_role_options() as opts:
            opts[key] = role.id
        await ctx.send(
            f"\u2705 Approval role key `{key}` → {role.mention} (`{role.id}`)."
        )
        log.info(
            "Guild %s: approval_role_options[%s] = %s by %s",
            ctx.guild.id, key, role.id, ctx.author.id,
        )

    # ==================================================================
    # Sub-group:  [p]opscore panel
    # ==================================================================

    @opscore.group(name="panel", invoke_without_command=True)
    @commands.admin_or_permissions(administrator=True)
    async def opscore_panel(self, ctx: commands.Context) -> None:
        """Deploy operational panels."""
        await ctx.send_help(ctx.command)

    @opscore_panel.command(name="approval")
    @commands.admin_or_permissions(administrator=True)
    async def panel_approval(self, ctx: commands.Context) -> None:
        """Deploy the public Approval Queue panel in this channel.

        Users click the button on this panel to request roles.
        """
        # Check that the approval review channel is configured
        review_ch_id = await self.config.guild(ctx.guild).approval_review_channel_id()
        if not review_ch_id:
            await ctx.send(
                "\u274c You must set the approval review channel first.\n"
                "Run: `[p]opscore set approvalchannel #channel`"
            )
            return

        embed = build_approval_panel_embed()
        view = ApprovalPanelView(config=self.config)

        msg = await ctx.send(embed=embed, view=view)

        # Save the panel message ID so we can reference it later
        async with self.config.guild(ctx.guild).panel_messages() as panels:
            panels["approval_panel"] = msg.id

        log.info(
            "Guild %s: Approval panel deployed in #%s (msg %s) by %s",
            ctx.guild.id, ctx.channel.name, msg.id, ctx.author.id,
        )

        # Clean up the invoking command message if possible
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

    # ==================================================================
    # Sub-group:  [p]opscore docs
    # ==================================================================

    @opscore.group(name="docs", invoke_without_command=True)
    @commands.admin_or_permissions(administrator=True)
    async def opscore_docs(self, ctx: commands.Context) -> None:
        """View Ops Core operational documentation.

        Shows workflow guides and setup instructions as embeds.
        For command syntax, use ``[p]help opscore`` instead.
        """
        embed = discord.Embed(
            title=f"\U0001f4d6  {COG_NAME} — Documentation",
            description=(
                "Use the subcommands below to view workflow guides.\n\n"
                "**Available topics:**\n"
                "\u2022 `[p]opscore docs approval` — Approval Queue workflow\n\n"
                "**Other commands:**\n"
                "\u2022 `[p]help opscore` — Full command syntax reference\n"
                "\u2022 `[p]opscore debug version` — Current version\n"
                "\u2022 `[p]opscore debug config` — View guild configuration"
            ),
            colour=COLOUR_PRIMARY,
        )
        embed.add_field(
            name="Stage Status",
            value=(
                "\u2705 **Stage 00** — Cog Skeleton\n"
                "\u2705 **Stage 01** — Approval Queue\n"
                "\u23f3 **Stage 02** — Ticket System *(planned)*\n"
                "\u23f3 **Stage 03** — Quarantine *(planned)*"
            ),
            inline=False,
        )
        embed.set_footer(text=f"{COG_NAME} v{COG_VERSION}")
        await ctx.send(embed=embed)

    @opscore_docs.command(name="approval")
    @commands.admin_or_permissions(administrator=True)
    async def docs_approval(self, ctx: commands.Context) -> None:
        """Show the Approval Queue workflow and setup guide."""
        # --- Page 1: Setup ---
        setup_embed = discord.Embed(
            title="\U0001f4cb  Approval Queue — Setup Guide",
            description="Follow these steps to configure the Approval Queue.",
            colour=COLOUR_PRIMARY,
        )
        setup_embed.add_field(
            name="Step 1 — Set the review channel",
            value=(
                "```\n[p]opscore set approvalchannel #admin-review\n```\n"
                "This is where admin review cards are posted."
            ),
            inline=False,
        )
        setup_embed.add_field(
            name="Step 2 — Set the log channel (optional)",
            value=(
                "```\n[p]opscore set logchannel #admin-log\n```\n"
                "Approval/denial actions are logged here."
            ),
            inline=False,
        )
        setup_embed.add_field(
            name="Step 3 — Add role keys",
            value=(
                "```\n[p]opscore set approvalrole member @Member\n"
                "[p]opscore set approvalrole artist @Artist\n```\n"
                "Users type these keys in the request modal."
            ),
            inline=False,
        )
        setup_embed.add_field(
            name="Step 4 — Deploy the panel",
            value=(
                "```\n[p]opscore panel approval\n```\n"
                "Run this in the public channel where users should "
                "see the request button."
            ),
            inline=False,
        )
        setup_embed.set_footer(text=f"{COG_NAME} v{COG_VERSION} • Approval Queue")

        # --- Page 2: Workflow ---
        flow_embed = discord.Embed(
            title="\U0001f504  Approval Queue — Workflow",
            description="How a role request flows from user to admin.",
            colour=COLOUR_PRIMARY,
        )
        flow_embed.add_field(
            name="User Side",
            value=(
                "1\ufe0f\u20e3 User clicks **\U0001f4dd Request Role** on the panel\n"
                "2\ufe0f\u20e3 Modal opens — user enters role key, reason, evidence\n"
                "3\ufe0f\u20e3 Bot confirms submission (ephemeral)\n"
                "4\ufe0f\u20e3 User receives a DM when approved or denied"
            ),
            inline=False,
        )
        flow_embed.add_field(
            name="Admin Side",
            value=(
                "1\ufe0f\u20e3 Review embed appears in the review channel\n"
                "2\ufe0f\u20e3 Admin clicks **\u2705 Accept** or **\u274c Deny**\n"
                "3\ufe0f\u20e3 Bot grants/skips the role and updates the embed\n"
                "4\ufe0f\u20e3 Action is logged to the log channel (if set)"
            ),
            inline=False,
        )
        flow_embed.add_field(
            name="Error Handling",
            value=(
                "\u2022 Invalid role key → ephemeral error to user\n"
                "\u2022 Duplicate pending request → blocked\n"
                "\u2022 User already has role → blocked\n"
                "\u2022 User left server → admin notified\n"
                "\u2022 User DMs closed → admin warned, action proceeds\n"
                "\u2022 Bot role too low → clear error message\n"
                "\u2022 Already-resolved request → admin notified"
            ),
            inline=False,
        )
        flow_embed.set_footer(text=f"{COG_NAME} v{COG_VERSION} • Approval Queue")

        await ctx.send(embeds=[setup_embed, flow_embed])

    # ==================================================================
    # Sub-group:  [p]opscore debug   (preserved from Stage 00)
    # ==================================================================

    @opscore.group(name="debug", invoke_without_command=True)
    @commands.admin_or_permissions(administrator=True)
    async def opscore_debug(self, ctx: commands.Context) -> None:
        """Debugging utilities for Ops Core."""
        await ctx.send_help(ctx.command)

    @opscore_debug.command(name="config")
    @commands.admin_or_permissions(administrator=True)
    async def debug_config(self, ctx: commands.Context) -> None:
        """Display the current guild configuration for Ops Core."""
        guild_data = await self.config.guild(ctx.guild).all()
        formatted = self._format_config(guild_data)

        # Discord message limit is 2 000 chars; embed description limit is 4 096.
        # Use an embed for cleaner output.
        embed = discord.Embed(
            title=f"\u2699\ufe0f  {COG_NAME} — Guild Config",
            description=f"```json\n{formatted}\n```",
            colour=discord.Colour.blurple(),
            timestamp=datetime.now(tz=timezone.utc),
        )
        embed.set_footer(text=f"v{COG_VERSION} • Guild {ctx.guild.id}")

        if len(formatted) > 3900:
            # Fallback: send as a file attachment if the config is too large.
            import io

            file = discord.File(
                fp=io.BytesIO(formatted.encode()),
                filename="ops_core_config.json",
            )
            await ctx.send(file=file)
        else:
            await ctx.send(embed=embed)

    @opscore_debug.command(name="version")
    @commands.admin_or_permissions(administrator=True)
    async def debug_version(self, ctx: commands.Context) -> None:
        """Show the current Ops Core version."""
        await ctx.send(f"**{COG_NAME}** v{COG_VERSION}")

    # ------------------------------------------------------------------
    # Red meta methods  (optional but good practice)
    # ------------------------------------------------------------------

    async def red_delete_data_for_user(self, **kwargs) -> None:
        """Required by Red — handle user data deletion requests."""
        # ops_core stores guild-scoped operational data only.
        # Per-user data deletion will be handled when user-level
        # data is introduced in future stages.
        return

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """Append version info to the cog help text."""
        pre = super().format_help_for_context(ctx)
        return f"{pre}\n\n**Version:** {COG_VERSION}"
