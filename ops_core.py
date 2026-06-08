"""
ops_core.ops_core
~~~~~~~~~~~~~~~~~

Main cog class for the Ops Core operations system.

Stage 00 — Cog skeleton, Config, debug commands.
Stage 01 — Approval Queue MVP (setup commands, persistent panel, review flow).
Stage 02 — Ticket System (support panel, private thread fallback, transcripts).
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
from .services import approval_service, ticket_service, quarantine_service
from .utils.embeds import build_approval_panel_embed, build_support_panel_embed, build_admin_panel_embed
from .views.approval_views import ApprovalPanelView, ApprovalReviewView
from .views.ticket_views import SupportPanelView, TicketCloseView
from .views.quarantine_views import AdminPanelView
from .views.core_views import DatabaseWipeConfirmView

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
        """Called when the cog is loaded. Re-register persistent views."""

        # 1. Static panel views — one registration covers all guilds
        self.bot.add_view(ApprovalPanelView(config=self.config))
        self.bot.add_view(SupportPanelView(config=self.config))
        self.bot.add_view(AdminPanelView(config=self.config, bot=self.bot))

        # 2. Re-register dynamic views for pending requests & open tickets
        all_guilds = await self.config.all_guilds()
        pending_count = 0
        ticket_count = 0
        for guild_id, guild_data in all_guilds.items():
            requests = guild_data.get("approval_requests", {})
            for request_id, req_data in requests.items():
                if req_data.get("status") == "pending":
                    view = ApprovalReviewView(
                        config=self.config, request_id=request_id
                    )
                    self.bot.add_view(view)
                    pending_count += 1
                    
            tickets = guild_data.get("active_tickets", {})
            for t_id, t_data in tickets.items():
                if t_data.get("status") == "open":
                    view = TicketCloseView(
                        config=self.config, ticket_id=t_id
                    )
                    self.bot.add_view(view)
                    ticket_count += 1

        log.info(
            "%s v%s — cog_load complete.  "
            "Re-registered %d pending review view(s) and %d open ticket view(s).",
            COG_NAME,
            COG_VERSION,
            pending_count,
            ticket_count,
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
    async def set_approval_channel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        """Set the channel where approval review embeds are posted."""
        await self.config.guild(ctx.guild).approval_review_channel_id.set(channel.id)
        await ctx.send(f"\u2705 Approval review channel set to {channel.mention}.")
        log.info("Guild %s: approval_review_channel_id set to %s", ctx.guild.id, channel.id)

    @opscore_set.command(name="logchannel")
    @commands.admin_or_permissions(administrator=True)
    async def set_log_channel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        """Set the admin log channel (optional)."""
        await self.config.guild(ctx.guild).admin_log_channel_id.set(channel.id)
        await ctx.send(f"\u2705 Admin log channel set to {channel.mention}.")
        log.info("Guild %s: admin_log_channel_id set to %s", ctx.guild.id, channel.id)

    @opscore_set.command(name="approvalrole")
    @commands.admin_or_permissions(administrator=True)
    async def set_approval_role(self, ctx: commands.Context, key: str, role: discord.Role) -> None:
        """Map a role key to a Discord role for the approval queue."""
        key = key.strip().lower()
        async with self.config.guild(ctx.guild).approval_role_options() as opts:
            opts[key] = role.id
        await ctx.send(f"\u2705 Approval role key `{key}` → {role.mention} (`{role.id}`).")
        log.info("Guild %s: approval_role_options[%s] = %s", ctx.guild.id, key, role.id)

    @opscore_set.command(name="supportchannel")
    @commands.admin_or_permissions(administrator=True)
    async def set_support_channel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        """Set the default support channel (for fallback/reference)."""
        await self.config.guild(ctx.guild).support_channel_id.set(channel.id)
        await ctx.send(f"\u2705 Support channel set to {channel.mention}.")
        log.info("Guild %s: support_channel_id set to %s", ctx.guild.id, channel.id)

    @opscore_set.command(name="archivechannel")
    @commands.admin_or_permissions(administrator=True)
    async def set_archive_channel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        """Set the channel where ticket transcripts are sent."""
        await self.config.guild(ctx.guild).ticket_archive_channel_id.set(channel.id)
        await ctx.send(f"\u2705 Ticket archive channel set to {channel.mention}.")
        log.info("Guild %s: ticket_archive_channel_id set to %s", ctx.guild.id, channel.id)

    @opscore_set.command(name="staffrole")
    @commands.admin_or_permissions(administrator=True)
    async def set_staff_role(self, ctx: commands.Context, role: discord.Role) -> None:
        """Add a role to the general staff group."""
        async with self.config.guild(ctx.guild).staff_role_ids() as roles:
            if role.id not in roles:
                roles.append(role.id)
                await ctx.send(f"\u2705 Added {role.mention} to staff roles.")
            else:
                await ctx.send(f"\u2139\ufe0f {role.mention} is already in staff roles.")

    @opscore_set.command(name="devrole")
    @commands.admin_or_permissions(administrator=True)
    async def set_dev_role(self, ctx: commands.Context, role: discord.Role) -> None:
        """Add a role to the developer group."""
        async with self.config.guild(ctx.guild).dev_role_ids() as roles:
            if role.id not in roles:
                roles.append(role.id)
                await ctx.send(f"\u2705 Added {role.mention} to developer roles.")
            else:
                await ctx.send(f"\u2139\ufe0f {role.mention} is already in developer roles.")

    @opscore_set.command(name="modrole")
    @commands.admin_or_permissions(administrator=True)
    async def set_mod_role(self, ctx: commands.Context, role: discord.Role) -> None:
        """Add a role to the moderator group."""
        async with self.config.guild(ctx.guild).mod_role_ids() as roles:
            if role.id not in roles:
                roles.append(role.id)
                await ctx.send(f"\u2705 Added {role.mention} to moderator roles.")
            else:
                await ctx.send(f"\u2139\ufe0f {role.mention} is already in moderator roles.")

    @opscore_set.command(name="quarantinerole")
    @commands.admin_or_permissions(administrator=True)
    async def set_quarantine_role(self, ctx: commands.Context, role: discord.Role) -> None:
        """Set the role to apply when a user is quarantined."""
        await self.config.guild(ctx.guild).quarantine_role_id.set(role.id)
        await ctx.send(f"\u2705 Quarantine role set to {role.mention}.")
        log.info("Guild %s: quarantine_role_id set to %s", ctx.guild.id, role.id)

    @opscore_set.command(name="quarantinecategory")
    @commands.admin_or_permissions(administrator=True)
    async def set_quarantine_category(self, ctx: commands.Context, category: discord.CategoryChannel) -> None:
        """Set the category where quarantine case channels are created."""
        await self.config.guild(ctx.guild).quarantine_category_id.set(category.id)
        await ctx.send(f"\u2705 Quarantine category set to **{category.name}**.")
        log.info("Guild %s: quarantine_category_id set to %s", ctx.guild.id, category.id)

    def _format_role_list(self, guild: discord.Guild, role_ids: list[int]) -> str:
        """Helper to format a list of role IDs."""
        if not role_ids:
            return "None"
        formatted = []
        for r in role_ids:
            role = guild.get_role(r)
            if role:
                formatted.append(role.mention)
            else:
                formatted.append(f"Deleted Role ({r})")
        return " ".join(formatted)

    # ==================================================================
    # Sub-group:  [p]opscore list
    # ==================================================================
    
    @opscore.group(name="list", invoke_without_command=True)
    @commands.admin_or_permissions(administrator=True)
    async def opscore_list(self, ctx: commands.Context) -> None:
        """List Ops Core configurations."""
        await ctx.send_help(ctx.command)
        
    @opscore_list.command(name="ticketroles")
    @commands.admin_or_permissions(administrator=True)
    async def list_ticketroles(self, ctx: commands.Context) -> None:
        """List all configured ticket staff, dev, and mod roles."""
        guild_data = await self.config.guild(ctx.guild).all()
        
        staff = self._format_role_list(ctx.guild, guild_data.get("staff_role_ids", []))
        dev = self._format_role_list(ctx.guild, guild_data.get("dev_role_ids", []))
        mod = self._format_role_list(ctx.guild, guild_data.get("mod_role_ids", []))
        
        embed = discord.Embed(title="\U0001f6e1\ufe0f Ticket Staff Roles", colour=COLOUR_PRIMARY)
        embed.add_field(name="Staff Roles", value=staff, inline=False)
        embed.add_field(name="Developer Roles", value=dev, inline=False)
        embed.add_field(name="Moderator Roles", value=mod, inline=False)
        await ctx.send(embed=embed)

    @opscore_list.command(name="staffroles")
    @commands.admin_or_permissions(administrator=True)
    async def list_staffroles(self, ctx: commands.Context) -> None:
        """List configured general staff roles."""
        role_ids = await self.config.guild(ctx.guild).staff_role_ids()
        await ctx.send(f"**Staff Roles:** {self._format_role_list(ctx.guild, role_ids)}")

    @opscore_list.command(name="devroles")
    @commands.admin_or_permissions(administrator=True)
    async def list_devroles(self, ctx: commands.Context) -> None:
        """List configured developer roles."""
        role_ids = await self.config.guild(ctx.guild).dev_role_ids()
        await ctx.send(f"**Developer Roles:** {self._format_role_list(ctx.guild, role_ids)}")

    @opscore_list.command(name="modroles")
    @commands.admin_or_permissions(administrator=True)
    async def list_modroles(self, ctx: commands.Context) -> None:
        """List configured moderator roles."""
        role_ids = await self.config.guild(ctx.guild).mod_role_ids()
        await ctx.send(f"**Moderator Roles:** {self._format_role_list(ctx.guild, role_ids)}")

    @opscore_list.command(name="quarantine")
    @commands.admin_or_permissions(administrator=True)
    async def list_quarantine(self, ctx: commands.Context) -> None:
        """List active quarantine cases."""
        cases = await self.config.guild(ctx.guild).quarantine_cases()
        active_cases = [c for c in cases.values() if c["status"] in ("active", "partially_restored")]
        if not active_cases:
            await ctx.send("\u2705 No active quarantine cases.")
            return

        lines = []
        for c in active_cases:
            quarantined_users = c.get("quarantined_users", {})
            active_users = sum(1 for u in quarantined_users.values() if u["status"] in ("active", "partially_restored", "failed"))
            lines.append(f"**{c['case_id']}** - {active_users} active user(s) ({c['status']})")
            
        await ctx.send("\u26a0\ufe0f **Active Quarantine Cases**\n" + "\n".join(lines))

    # ==================================================================
    # Sub-group:  [p]opscore remove
    # ==================================================================

    @opscore.group(name="remove", invoke_without_command=True)
    @commands.admin_or_permissions(administrator=True)
    async def opscore_remove(self, ctx: commands.Context) -> None:
        """Remove Ops Core role configurations."""
        await ctx.send_help(ctx.command)

    @opscore_remove.command(name="staffrole")
    @commands.admin_or_permissions(administrator=True)
    async def remove_staff_role(self, ctx: commands.Context, role: discord.Role | int) -> None:
        """Remove a role from the general staff group. Accepts role mention or ID."""
        r_id = role.id if isinstance(role, discord.Role) else role
        async with self.config.guild(ctx.guild).staff_role_ids() as roles:
            if r_id in roles:
                roles.remove(r_id)
                await ctx.send(f"\u2705 Removed role ID {r_id} from staff roles.\n**Current List:** {self._format_role_list(ctx.guild, roles)}")
            else:
                await ctx.send(f"\u274c Role ID {r_id} is not in the staff roles list.")

    @opscore_remove.command(name="devrole")
    @commands.admin_or_permissions(administrator=True)
    async def remove_dev_role(self, ctx: commands.Context, role: discord.Role | int) -> None:
        """Remove a role from the developer group. Accepts role mention or ID."""
        r_id = role.id if isinstance(role, discord.Role) else role
        async with self.config.guild(ctx.guild).dev_role_ids() as roles:
            if r_id in roles:
                roles.remove(r_id)
                await ctx.send(f"\u2705 Removed role ID {r_id} from developer roles.\n**Current List:** {self._format_role_list(ctx.guild, roles)}")
            else:
                await ctx.send(f"\u274c Role ID {r_id} is not in the developer roles list.")

    @opscore_remove.command(name="modrole")
    @commands.admin_or_permissions(administrator=True)
    async def remove_mod_role(self, ctx: commands.Context, role: discord.Role | int) -> None:
        """Remove a role from the moderator group. Accepts role mention or ID."""
        r_id = role.id if isinstance(role, discord.Role) else role
        async with self.config.guild(ctx.guild).mod_role_ids() as roles:
            if r_id in roles:
                roles.remove(r_id)
                await ctx.send(f"\u2705 Removed role ID {r_id} from moderator roles.\n**Current List:** {self._format_role_list(ctx.guild, roles)}")
            else:
                await ctx.send(f"\u274c Role ID {r_id} is not in the moderator roles list.")


    # ==================================================================
    # Sub-group:  [p]opscore clear
    # ==================================================================

    @opscore.group(name="clear", invoke_without_command=True)
    @commands.admin_or_permissions(administrator=True)
    async def opscore_clear(self, ctx: commands.Context) -> None:
        """Clear Ops Core configurations."""
        await ctx.send_help(ctx.command)

    @opscore_clear.command(name="database")
    @commands.admin_or_permissions(administrator=True)
    async def clear_database(self, ctx: commands.Context) -> None:
        """Completely wipe ALL Ops Core configurations and data for this server."""
        view = DatabaseWipeConfirmView(config=self.config, author_id=ctx.author.id)
        embed = discord.Embed(
            title="\u26a0\ufe0f  DANGER: Database Wipe",
            description=(
                "**WARNING:** You are about to completely delete all Ops Core data for this server. "
                "This includes all ticket records, approval requests, role mappings, and channel settings.\n\n"
                "**This action cannot be undone.**"
            ),
            colour=discord.Colour.red()
        )
        await ctx.send(embed=embed, view=view)

    @opscore_clear.command(name="staffroles")
    @commands.admin_or_permissions(administrator=True)
    async def clear_staff_roles(self, ctx: commands.Context, confirm: str = "") -> None:
        """Clear the general staff role list. Requires 'confirm' argument."""
        if confirm.lower() != "confirm":
            await ctx.send("\u26a0\ufe0f To clear all staff roles, you must run: `[p]opscore clear staffroles confirm`")
            return
        await self.config.guild(ctx.guild).staff_role_ids.set([])
        await ctx.send("\u2705 Cleared all staff roles.")

    @opscore_clear.command(name="devroles")
    @commands.admin_or_permissions(administrator=True)
    async def clear_dev_roles(self, ctx: commands.Context, confirm: str = "") -> None:
        """Clear the developer role list. Requires 'confirm' argument."""
        if confirm.lower() != "confirm":
            await ctx.send("\u26a0\ufe0f To clear all developer roles, you must run: `[p]opscore clear devroles confirm`")
            return
        await self.config.guild(ctx.guild).dev_role_ids.set([])
        await ctx.send("\u2705 Cleared all developer roles.")

    @opscore_clear.command(name="modroles")
    @commands.admin_or_permissions(administrator=True)
    async def clear_mod_roles(self, ctx: commands.Context, confirm: str = "") -> None:
        """Clear the moderator role list. Requires 'confirm' argument."""
        if confirm.lower() != "confirm":
            await ctx.send("\u26a0\ufe0f To clear all moderator roles, you must run: `[p]opscore clear modroles confirm`")
            return
        await self.config.guild(ctx.guild).mod_role_ids.set([])
        await ctx.send("\u2705 Cleared all moderator roles.")

    @opscore_clear.command(name="quarantinecases")
    @commands.admin_or_permissions(administrator=True)
    async def clear_quarantine_cases(self, ctx: commands.Context, confirm: str = "") -> None:
        """Clear all quarantine cases from the database. Requires 'confirm' argument."""
        if confirm.lower() != "confirm":
            await ctx.send("\u26a0\ufe0f To clear all quarantine cases, you must run: `[p]opscore clear quarantinecases confirm`")
            return
        await self.config.guild(ctx.guild).quarantine_cases.set({})
        await ctx.send("\u2705 Cleared all quarantine cases.")


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
        """Deploy the public Approval Queue panel in this channel."""
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

        async with self.config.guild(ctx.guild).panel_messages() as panels:
            panels["approval_panel"] = msg.id

        log.info("Guild %s: Approval panel deployed in #%s", ctx.guild.id, ctx.channel.name)
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

    @opscore_panel.command(name="ticket")
    @commands.admin_or_permissions(administrator=True)
    async def panel_ticket(self, ctx: commands.Context) -> None:
        """Deploy the public Ticket Panel in this channel."""
        embed = build_support_panel_embed()
        view = SupportPanelView(config=self.config)

        msg = await ctx.send(embed=embed, view=view)

        async with self.config.guild(ctx.guild).panel_messages() as panels:
            panels["support_panel"] = msg.id

        log.info("Guild %s: Support panel deployed in #%s", ctx.guild.id, ctx.channel.name)
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass


    @opscore_panel.command(name="quarantine")
    @commands.admin_or_permissions(administrator=True)
    async def panel_quarantine(self, ctx: commands.Context) -> None:
        """Deploy the persistent Quarantine Control Panel."""
        embed = build_admin_panel_embed()
        view = AdminPanelView(config=self.config, bot=self.bot)

        msg = await ctx.send(embed=embed, view=view)

        async with self.config.guild(ctx.guild).panel_messages() as panels:
            panels["admin_panel"] = msg.id

        log.info("Guild %s: Admin panel deployed in #%s", ctx.guild.id, ctx.channel.name)
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
        """View Ops Core operational documentation."""
        embed = discord.Embed(
            title=f"\U0001f4d6  {COG_NAME} — Documentation",
            description=(
                "Use the subcommands below to view workflow guides.\n\n"
                "**Available topics:**\n"
                "\u2022 `[p]opscore docs core` — Core configuration guide\n"
                "\u2022 `[p]opscore docs approval` — Approval Queue workflow\n"
                "\u2022 `[p]opscore docs ticket` — Ticket System workflow\n"
                "\u2022 `[p]opscore docs quarantine` — Quarantine workflow\n\n"
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
                "\u2705 **Stage 02** — Ticket System\n"
                "\u2705 **Stage 03** — Quarantine"
            ),
            inline=False,
        )
        embed.set_footer(text=f"{COG_NAME} v{COG_VERSION}")
        await ctx.send(embed=embed)

    @opscore_docs.command(name="core")
    @commands.admin_or_permissions(administrator=True)
    async def docs_core(self, ctx: commands.Context) -> None:
        """Show the Core Ops Core setup guide."""
        setup_embed = discord.Embed(
            title="\u2699\ufe0f  Ops Core — Core Setup Guide",
            description="These configurations are shared across multiple Ops Core modules (like Tickets and Quarantine).",
            colour=COLOUR_PRIMARY,
        )
        setup_embed.add_field(
            name="Step 1 — Set the global log channel (optional)",
            value="```\n[p]opscore set logchannel #admin-log\n```\nAll module actions (like approving a request or closing a ticket) are logged here.",
            inline=False,
        )
        setup_embed.add_field(
            name="Step 2 — Set global staff roles",
            value="```\n[p]opscore set staffrole @Staff\n[p]opscore set modrole @Moderator\n[p]opscore set devrole @Developer\n```\nThese roles are granted access to private tickets and future admin modules.",
            inline=False,
        )
        setup_embed.add_field(
            name="Step 3 — Manage roles",
            value="```\n[p]opscore list ticketroles\n[p]opscore remove staffrole @Staff\n[p]opscore clear modroles confirm\n```",
            inline=False,
        )
        setup_embed.add_field(
            name="Step 4 — Database Reset",
            value="```\n[p]opscore clear database\n```\nSpawns an interactive view to totally wipe all data for the server.",
            inline=False,
        )
        setup_embed.set_footer(text=f"{COG_NAME} v{COG_VERSION} • Core")
        await ctx.send(embed=setup_embed)

    @opscore_docs.command(name="approval")
    @commands.admin_or_permissions(administrator=True)
    async def docs_approval(self, ctx: commands.Context) -> None:
        """Show the Approval Queue workflow and setup guide."""
        setup_embed = discord.Embed(
            title="\U0001f4cb  Approval Queue — Setup Guide",
            description="Follow these steps to configure the Approval Queue.",
            colour=COLOUR_PRIMARY,
        )
        setup_embed.add_field(
            name="Step 1 — Set the review channel",
            value="```\n[p]opscore set approvalchannel #admin-review\n```",
            inline=False,
        )
        setup_embed.add_field(
            name="Step 2 — Add role keys",
            value="```\n[p]opscore set approvalrole member @Member\n```",
            inline=False,
        )
        setup_embed.add_field(
            name="Step 3 — Deploy the panel",
            value="```\n[p]opscore panel approval\n```",
            inline=False,
        )
        setup_embed.set_footer(text=f"{COG_NAME} v{COG_VERSION} • Approval Queue")

        flow_embed = discord.Embed(
            title="\U0001f504  Approval Queue — Workflow",
            description="How a role request flows from user to admin.",
            colour=COLOUR_PRIMARY,
        )
        flow_embed.add_field(
            name="User Side",
            value="1\ufe0f\u20e3 Request Role\n2\ufe0f\u20e3 Submit Modal\n3\ufe0f\u20e3 Receive DM",
            inline=True,
        )
        flow_embed.add_field(
            name="Admin Side",
            value="1\ufe0f\u20e3 Review embed posted\n2\ufe0f\u20e3 Accept/Deny\n3\ufe0f\u20e3 Logged",
            inline=True,
        )
        flow_embed.set_footer(text=f"{COG_NAME} v{COG_VERSION} • Approval Queue")

        await ctx.send(embeds=[setup_embed, flow_embed])

    @opscore_docs.command(name="ticket")
    @commands.admin_or_permissions(administrator=True)
    async def docs_ticket(self, ctx: commands.Context) -> None:
        """Show the Ticket System workflow and setup guide."""
        setup_embed = discord.Embed(
            title="\U0001f3ab  Ticket System — Setup Guide",
            description="Follow these steps to configure the Ticket System.",
            colour=COLOUR_PRIMARY,
        )
        setup_embed.add_field(
            name="Step 1 — Set the archive channel",
            value="```\n[p]opscore set archivechannel #transcripts\n```",
            inline=False,
        )
        setup_embed.add_field(
            name="Step 2 — Deploy the panel",
            value="```\n[p]opscore panel ticket\n```",
            inline=False,
        )
        setup_embed.add_field(
            name="Note",
            value="Make sure you have configured your staff roles first! Run `[p]opscore docs core` for instructions.",
            inline=False,
        )
        setup_embed.set_footer(text=f"{COG_NAME} v{COG_VERSION} • Tickets")

        flow_embed = discord.Embed(
            title="\U0001f504  Ticket System — Workflow",
            description="How a ticket flows from creation to closure.",
            colour=COLOUR_PRIMARY,
        )
        flow_embed.add_field(
            name="Creation",
            value="1\ufe0f\u20e3 User selects category\n2\ufe0f\u20e3 Modal opens\n3\ufe0f\u20e3 Private Thread (or Channel) created",
            inline=True,
        )
        flow_embed.add_field(
            name="Closure",
            value="1\ufe0f\u20e3 Staff clicks Close\n2\ufe0f\u20e3 HTML transcript saved\n3\ufe0f\u20e3 Space archived/deleted",
            inline=True,
        )
        flow_embed.set_footer(text=f"{COG_NAME} v{COG_VERSION} • Tickets")

        await ctx.send(embeds=[setup_embed, flow_embed])

    @opscore_docs.command(name="quarantine")
    @commands.admin_or_permissions(administrator=True)
    async def docs_quarantine(self, ctx: commands.Context) -> None:
        """Show the Quarantine workflow and setup guide."""
        setup_embed = discord.Embed(
            title="\u26a0\ufe0f  Quarantine — Setup Guide",
            description="Follow these steps to configure Case-Based Quarantine.",
            colour=COLOUR_PRIMARY,
        )
        setup_embed.add_field(
            name="Step 1 — Set the category",
            value="```\n[p]opscore set quarantinecategory \"Incident Response\"\n```",
            inline=False,
        )
        setup_embed.add_field(
            name="Step 2 — Set the quarantine role",
            value="```\n[p]opscore set quarantinerole @Quarantined\n```",
            inline=False,
        )
        setup_embed.add_field(
            name="Step 3 — Deploy the panel",
            value="```\n[p]opscore panel quarantine\n```",
            inline=False,
        )
        setup_embed.set_footer(text=f"{COG_NAME} v{COG_VERSION} • Quarantine")

        flow_embed = discord.Embed(
            title="\U0001f504  Quarantine — Workflow",
            description="How case-based isolation and restoration flows.",
            colour=COLOUR_PRIMARY,
        )
        flow_embed.add_field(
            name="Quarantine User(s)",
            value="1\ufe0f\u20e3 Staff clicks Quarantine\n2\ufe0f\u20e3 Enter user ID, reason, and an optional Case ID\n3\ufe0f\u20e3 Channel created (or reused if Case ID given)\n4\ufe0f\u20e3 Roles snapshotted & stripped",
            inline=True,
        )
        flow_embed.add_field(
            name="Restore User(s)",
            value="1\ufe0f\u20e3 Staff clicks Restore\n2\ufe0f\u20e3 Enter Case ID (restore all) or User ID (restore one)\n3\ufe0f\u20e3 Roles are perfectly restored\n4\ufe0f\u20e3 Case closed & channel locked",
            inline=True,
        )
        flow_embed.set_footer(text=f"{COG_NAME} v{COG_VERSION} • Quarantine")

        await ctx.send(embeds=[setup_embed, flow_embed])


    # ==================================================================
    # Sub-group:  [p]opscore debug
    # ==================================================================

    @opscore.group(name="debug")
    @commands.is_owner()
    async def opscore_debug(self, ctx: commands.Context) -> None:
        """Debug and low-level diagnostic commands."""
        pass

    @opscore_debug.command(name="wipe")
    async def debug_wipe(self, ctx: commands.Context) -> None:
        """Clear all Ops Core data for this server. (Owner only)"""
        await self.config.guild(ctx.guild).clear()
        await ctx.send("\u26a0\ufe0f All Ops Core data wiped for this server.")

    @opscore_debug.command(name="quarantine")
    async def debug_quarantine(self, ctx: commands.Context, case_id: str) -> None:
        """Print the raw JSON for a specific quarantine case."""
        cases = await self.config.guild(ctx.guild).quarantine_cases()
        if case_id.upper() not in cases:
            await ctx.send("\u274c Case not found.")
            return

        import json
        case_data = cases[case_id.upper()]
        dumped = json.dumps(case_data, indent=2)
        if len(dumped) > 1900:
            await ctx.send(f"```json\n{dumped[:1900]}...\n```")
        else:
            await ctx.send(f"```json\n{dumped}\n```")

    @opscore_debug.command(name="config")
    @commands.admin_or_permissions(administrator=True)
    async def debug_config(self, ctx: commands.Context) -> None:
        """Display the current guild configuration for Ops Core."""
        guild_data = await self.config.guild(ctx.guild).all()
        formatted = self._format_config(guild_data)

        embed = discord.Embed(
            title=f"\u2699\ufe0f  {COG_NAME} — Guild Config",
            description=f"```json\n{formatted}\n```",
            colour=discord.Colour.blurple(),
            timestamp=datetime.now(tz=timezone.utc),
        )
        embed.set_footer(text=f"v{COG_VERSION} • Guild {ctx.guild.id}")

        if len(formatted) > 3900:
            import io
            file = discord.File(fp=io.BytesIO(formatted.encode()), filename="ops_core_config.json")
            await ctx.send(file=file)
        else:
            await ctx.send(embed=embed)

    @opscore_debug.command(name="version")
    @commands.admin_or_permissions(administrator=True)
    async def debug_version(self, ctx: commands.Context) -> None:
        """Show the current Ops Core version."""
        await ctx.send(f"**{COG_NAME}** v{COG_VERSION}")

    # ------------------------------------------------------------------
    # Red meta methods
    # ------------------------------------------------------------------

    async def red_delete_data_for_user(self, **kwargs) -> None:
        return

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre = super().format_help_for_context(ctx)
        return f"{pre}\n\n**Version:** {COG_VERSION}"
