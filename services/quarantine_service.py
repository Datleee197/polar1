import discord
from redbot.core import Config
import logging
from datetime import datetime, timezone

from ..utils.embeds import build_quarantine_log_embed
from ..utils.ids import next_quarantine_id

log = logging.getLogger("red.ops_core.quarantine_service")

async def _log_action(config: Config, guild: discord.Guild, case_data: dict, action: str):
    log_channel_id = await config.guild(guild).admin_log_channel_id()
    if log_channel_id:
        channel = guild.get_channel(log_channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            embed = build_quarantine_log_embed(case_data, action)
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

async def _is_admin_or_staff(config: Config, member: discord.Member) -> bool:
    """Check if user has permissions to run quarantine operations."""
    if member.guild_permissions.administrator:
        return True
    
    guild_conf = await config.guild(member.guild).all()
    allowed_roles = set(
        guild_conf.get("staff_role_ids", []) +
        guild_conf.get("mod_role_ids", [])
    )
    
    for r in member.roles:
        if r.id in allowed_roles:
            return True
    return False

async def handle_quarantine_modal(config: Config, interaction: discord.Interaction, target_id: int, case_id: str | None, reason: str, notes: str):
    guild = interaction.guild
    me = guild.me

    if not await _is_admin_or_staff(config, interaction.user):
        await interaction.followup.send("\u274c You do not have permission to quarantine users.", ephemeral=True)
        return

    quar_role_id = await config.guild(guild).quarantine_role_id()
    if not quar_role_id:
        await interaction.followup.send("\u274c Quarantine role is not configured. Run `[p]opscore set quarantinerole <role>`.", ephemeral=True)
        return

    quar_role = guild.get_role(quar_role_id)
    if not quar_role:
        await interaction.followup.send("\u274c The configured Quarantine role no longer exists.", ephemeral=True)
        return

    quar_category_id = await config.guild(guild).quarantine_category_id()
    if not quar_category_id:
        await interaction.followup.send("\u274c Quarantine category is not configured. Run `[p]opscore set quarantinecategory <category>`.", ephemeral=True)
        return

    quar_category = guild.get_channel(quar_category_id)
    if not quar_category or not isinstance(quar_category, discord.CategoryChannel):
        await interaction.followup.send("\u274c The configured Quarantine category no longer exists.", ephemeral=True)
        return

    if not me.guild_permissions.manage_roles or not me.guild_permissions.manage_channels:
        await interaction.followup.send("\u274c Bot is missing **Manage Roles** or **Manage Channels** permission.", ephemeral=True)
        return

    if me.top_role <= quar_role:
        await interaction.followup.send(f"\u274c Bot's top role is not high enough to assign {quar_role.mention}.", ephemeral=True)
        return

    target = guild.get_member(target_id)
    if not target:
        await interaction.followup.send(f"\u274c User with ID `{target_id}` is not currently in the server.", ephemeral=True)
        return

    # Safety checks
    if target.id == guild.owner_id:
        await interaction.followup.send("\u274c Cannot quarantine the server owner.", ephemeral=True)
        return
    if target.id == me.id or target.bot:
        await interaction.followup.send("\u274c Cannot quarantine a bot.", ephemeral=True)
        return
    if target.id == interaction.user.id:
        await interaction.followup.send("\u274c You cannot quarantine yourself.", ephemeral=True)
        return
    if target.top_role >= me.top_role:
        await interaction.followup.send(f"\u274c Cannot quarantine {target.mention} because their top role is equal to or higher than the bot's.", ephemeral=True)
        return

    # Check existing active cases for this user
    async with config.guild(guild).quarantine_cases() as cases:
        for cid, case_obj in cases.items():
            if case_obj["status"] in ("active", "partially_restored"):
                user_record = case_obj.get("quarantined_users", {}).get(str(target.id))
                if user_record and user_record["status"] in ("active", "partially_restored", "failed"):
                    await interaction.followup.send(f"\u274c User is already active in quarantine case: `{cid}`.", ephemeral=True)
                    return

        # If existing case ID provided, validate it
        if case_id:
            if case_id not in cases:
                await interaction.followup.send(f"\u274c Provided Case ID `{case_id}` does not exist.", ephemeral=True)
                return
            if cases[case_id]["status"] not in ("active", "partially_restored"):
                await interaction.followup.send(f"\u274c Provided Case `{case_id}` is already {cases[case_id]['status']}.", ephemeral=True)
                return
            
            target_case = cases[case_id]
            channel_id = target_case.get("case_channel_id")
            case_channel = guild.get_channel(channel_id) if channel_id else None
            
            if not case_channel:
                await interaction.followup.send(f"\u274c The channel for case `{case_id}` no longer exists.", ephemeral=True)
                return

        else:
            # Create new case
            case_id = next_quarantine_id(cases)
            target_case = {
                "case_id": case_id,
                "guild_id": guild.id,
                "status": "active",
                "case_channel_id": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": interaction.user.id,
                "reason": reason,
                "notes": notes,
                "quarantined_users": {}
            }
            cases[case_id] = target_case
            
            # Setup channel permissions
            guild_conf = await config.guild(guild).all()
            staff_roles_ids = set(
                guild_conf.get("staff_role_ids", []) +
                guild_conf.get("mod_role_ids", [])
            )
            
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True)
            }
            for sr_id in staff_roles_ids:
                r = guild.get_role(sr_id)
                if r:
                    overwrites[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

            try:
                case_channel = await guild.create_text_channel(
                    name=f"quarantine-{case_id.lower()}",
                    category=quar_category,
                    overwrites=overwrites,
                    reason=f"Quarantine Case {case_id}"
                )
                target_case["case_channel_id"] = case_channel.id
            except discord.HTTPException as e:
                log.error(f"Failed to create quarantine channel: {e}")
                del cases[case_id]
                await interaction.followup.send("\u274c Failed to create case channel. Discord API Error.", ephemeral=True)
                return

        # Role policy
        original_roles = [r.id for r in target.roles if r.id != guild.default_role.id]
        removed_roles = []
        skipped_roles = []

        for r in target.roles:
            if r.id == guild.default_role.id:
                continue
            if r.id == quar_role.id:
                continue
            
            # Policy: remove all manageable roles below bot's top role
            if r.is_integration() or r.is_bot_managed() or r.is_premium_subscriber():
                skipped_roles.append(r.id)
                continue
            if r >= me.top_role:
                skipped_roles.append(r.id)
                continue
            
            removed_roles.append(r.id)

        user_data = {
            "user_id": target.id,
            "original_role_ids": original_roles,
            "removed_role_ids": removed_roles,
            "skipped_role_ids": skipped_roles,
            "added_quarantine_role_ids": [quar_role.id],
            "status": "active",
            "added_at": datetime.now(timezone.utc).isoformat(),
            "added_by": interaction.user.id,
            "restored_at": None,
            "restored_by": None,
            "restore_failures": []
        }
        
        target_case["quarantined_users"][str(target.id)] = user_data

    # Execute changes
    try:
        roles_to_remove = [guild.get_role(r) for r in removed_roles if guild.get_role(r)]
        await target.remove_roles(*roles_to_remove, reason=f"Quarantine Case {case_id}")
        await target.add_roles(quar_role, reason=f"Quarantine Case {case_id}")
        
        # Add permission overwrite to channel
        await case_channel.set_permissions(target, view_channel=True, send_messages=True, read_message_history=True)
        await case_channel.send(f"\u26a0\ufe0f {target.mention} has been added to this quarantine case.")
    except discord.HTTPException as e:
        log.error(f"Failed to modify roles/channel for quarantine {case_id}: {e}")
        await interaction.followup.send(f"\u26a0\ufe0f Case `{case_id}` created, but Discord API rejected some role/permission changes.", ephemeral=True)
    else:
        await interaction.followup.send(f"\u2705 User {target.mention} quarantined successfully in case `{case_id}`.", ephemeral=True)
    
    cases = await config.guild(guild).quarantine_cases()
    await _log_action(config, guild, cases[case_id], "quarantine")

async def _restore_user(config: Config, guild: discord.Guild, target_case: dict, user_record: dict, interaction: discord.Interaction):
    me = guild.me
    failures = []
    roles_to_add = []
    
    target = guild.get_member(user_record["user_id"])
    if not target:
        failures.append({"role_id": 0, "reason": "User is no longer in the server."})
        return failures

    for r_id in user_record["removed_role_ids"]:
        role = guild.get_role(r_id)
        if not role:
            failures.append({"role_id": r_id, "reason": "Role was deleted from the server."})
            continue
        if role >= me.top_role:
            failures.append({"role_id": r_id, "reason": "Role is now equal to or higher than bot's top role."})
            continue
        roles_to_add.append(role)

    try:
        for qr_id in user_record["added_quarantine_role_ids"]:
            quar_role = guild.get_role(qr_id)
            if quar_role and quar_role in target.roles:
                if me.top_role > quar_role:
                    await target.remove_roles(quar_role, reason=f"Restore Case {target_case['case_id']}")
                else:
                    failures.append({"role_id": qr_id, "reason": "Cannot remove Quarantine role: hierarchy too low."})
        
        if roles_to_add:
            await target.add_roles(*roles_to_add, reason=f"Restore Case {target_case['case_id']}")
            
        # Remove channel overwrite
        channel_id = target_case.get("case_channel_id")
        case_channel = guild.get_channel(channel_id) if channel_id else None
        if case_channel:
            await case_channel.set_permissions(target, overwrite=None)
            
    except discord.HTTPException as e:
        log.error(f"Failed to restore roles for user {user_record['user_id']} in case {target_case['case_id']}: {e}")
        failures.append({"role_id": 0, "reason": "Discord API rejected the role modification."})

    return failures

async def handle_restore_modal(config: Config, interaction: discord.Interaction, target_val, notes: str):
    guild = interaction.guild
    me = guild.me

    if not await _is_admin_or_staff(config, interaction.user):
        await interaction.followup.send("\u274c You do not have permission to restore users.", ephemeral=True)
        return

    if not me.guild_permissions.manage_roles:
        await interaction.followup.send("\u274c Bot is missing the **Manage Roles** permission.", ephemeral=True)
        return

    async with config.guild(guild).quarantine_cases() as cases:
        target_case = None
        restore_user_id = None
        
        # Determine if target_val is a Case ID or User ID
        if isinstance(target_val, str) and target_val.startswith("QUAR-"):
            target_case = cases.get(target_val)
            if not target_case:
                await interaction.followup.send(f"\u274c Case `{target_val}` not found.", ephemeral=True)
                return
        else:
            restore_user_id = target_val
            for cid, case in cases.items():
                if case["status"] in ("active", "partially_restored"):
                    u_rec = case.get("quarantined_users", {}).get(str(restore_user_id))
                    if u_rec and u_rec["status"] in ("active", "partially_restored", "failed"):
                        target_case = case
                        break
            if not target_case:
                await interaction.followup.send("\u274c Could not find an active quarantine case for that user.", ephemeral=True)
                return

        if target_case["status"] not in ("active", "partially_restored"):
            await interaction.followup.send(f"\u274c Case `{target_case['case_id']}` is already closed or fully restored.", ephemeral=True)
            return

        users_to_restore = []
        if restore_user_id:
            users_to_restore = [target_case["quarantined_users"][str(restore_user_id)]]
        else:
            for u_rec in target_case["quarantined_users"].values():
                if u_rec["status"] in ("active", "partially_restored", "failed"):
                    users_to_restore.append(u_rec)
                    
        if not users_to_restore:
            await interaction.followup.send(f"\u274c No active users found in case `{target_case['case_id']}`.", ephemeral=True)
            return

        all_failures = []
        for user_record in users_to_restore:
            failures = await _restore_user(config, guild, target_case, user_record, interaction)
            user_record["restored_at"] = datetime.now(timezone.utc).isoformat()
            user_record["restored_by"] = interaction.user.id
            if failures:
                user_record["status"] = "partially_restored"
                user_record["restore_failures"] = failures
                all_failures.extend(failures)
            else:
                user_record["status"] = "restored"

        # Check case status
        active_users_remaining = 0
        for u_rec in target_case["quarantined_users"].values():
            if u_rec["status"] in ("active", "partially_restored", "failed"):
                active_users_remaining += 1
                
        if active_users_remaining == 0:
            target_case["status"] = "closed"
            # Lock the channel
            channel_id = target_case.get("case_channel_id")
            case_channel = guild.get_channel(channel_id) if channel_id else None
            if case_channel:
                try:
                    await case_channel.send("\u26a0\ufe0f All users restored. Case closed and locked.")
                except discord.HTTPException:
                    pass

        if notes:
            target_case["notes"] = (target_case.get("notes", "") + f"\nRestore notes: {notes}").strip()

        if all_failures:
            await interaction.followup.send(f"\u26a0\ufe0f Partial restoration in `{target_case['case_id']}`. Some operations failed.", ephemeral=True)
        else:
            await interaction.followup.send(f"\u2705 Restoration complete for `{target_case['case_id']}`.", ephemeral=True)

    cases = await config.guild(guild).quarantine_cases()
    await _log_action(config, guild, cases[target_case["case_id"]], "restore")
