import discord
from discord import app_commands
from discord.ext import commands

# Admin role that can use /lock and /unlock (plus anyone with Administrator perm)
ADMIN_ROLE_ID = 1450553389971800185

# Owners who can use server-wide lockdown
OWNER_IDS = {289409320318402560, 369632653374390274}

BRAND_GREEN = discord.Colour.from_rgb(46, 204, 113)


def _has_admin(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    if interaction.user.guild_permissions.administrator:
        return True
    return any(r.id == ADMIN_ROLE_ID for r in interaction.user.roles)


def _bot_can_manage_channel(interaction: discord.Interaction) -> bool:
    if not interaction.guild or not interaction.guild.me:
        return False
    me = interaction.guild.me
    ch = interaction.channel
    if not isinstance(ch, discord.abc.GuildChannel):
        return False
    perms = ch.permissions_for(me)
    return perms.manage_channels


def _locked_overwrite(base: discord.PermissionOverwrite, locked: bool) -> discord.PermissionOverwrite:
    # Deny messaging + reactions + thread posting when locked.
    # Important: explicit DENY beats any role allow (unless the member has Administrator).
    if locked:
        base.send_messages = False
        base.add_reactions = False
        base.create_public_threads = False
        base.create_private_threads = False
        base.send_messages_in_threads = False
    else:
        base.send_messages = None
        base.add_reactions = None
        base.create_public_threads = None
        base.create_private_threads = None
        base.send_messages_in_threads = None
    return base


async def _apply_lock(channel: discord.TextChannel, locked: bool, reason: str):
    guild = channel.guild

    # Apply deny to @everyone
    ow_everyone = channel.overwrites_for(guild.default_role)
    ow_everyone = _locked_overwrite(ow_everyone, locked)
    await channel.set_permissions(guild.default_role, overwrite=ow_everyone, reason=reason)

    # Also apply deny to common member roles if configured (extra safety for servers with complex perms)
    roles_cfg = (getattr(guild, "bot", None) and {})  # placeholder; not used
    # We'll just try a few known role names if they exist
    common_role_names = {"Xonar Squad", "Unverified", "Niet Geverifieerd"}
    for r in guild.roles:
        if r.name in common_role_names:
            ow_r = channel.overwrites_for(r)
            ow_r = _locked_overwrite(ow_r, locked)
            await channel.set_permissions(r, overwrite=ow_r, reason=reason)

    # Lock active threads too (optional best-effort)
    try:
        for th in channel.threads:
            try:
                await th.edit(locked=locked, reason=reason)
            except Exception:
                pass
    except Exception:
        pass


class Locks(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _embed(self, title: str, desc: str = "") -> discord.Embed:
        return discord.Embed(title=title, description=desc, colour=BRAND_GREEN)

    @app_commands.command(name="lock", description="Lock the current channel (admins only).")
    async def lock(self, interaction: discord.Interaction):
        if not interaction.guild or not _has_admin(interaction):
            return await interaction.response.send_message("⛔ You don't have permission to do that.", ephemeral=True)
        if not _bot_can_manage_channel(interaction):
            return await interaction.response.send_message("⛔ I need **Manage Channels** permission in this channel to lock it.", ephemeral=True)

        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message("This can only be used in a text channel.", ephemeral=True)

        try:
            await _apply_lock(ch, True, reason=f"Locked by {interaction.user} ({interaction.user.id})")
        except discord.Forbidden:
            return await interaction.response.send_message("⛔ I don't have permission to change channel overwrites here.", ephemeral=True)

        await interaction.response.send_message(embed=self._embed("🔒 Channel locked", f"{ch.mention} is now locked."))

    @app_commands.command(name="unlock", description="Unlock the current channel (admins only).")
    async def unlock(self, interaction: discord.Interaction):
        if not interaction.guild or not _has_admin(interaction):
            return await interaction.response.send_message("⛔ You don't have permission to do that.", ephemeral=True)
        if not _bot_can_manage_channel(interaction):
            return await interaction.response.send_message("⛔ I need **Manage Channels** permission in this channel to unlock it.", ephemeral=True)

        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message("This can only be used in a text channel.", ephemeral=True)

        try:
            await _apply_lock(ch, False, reason=f"Unlocked by {interaction.user} ({interaction.user.id})")
        except discord.Forbidden:
            return await interaction.response.send_message("⛔ I don't have permission to change channel overwrites here.", ephemeral=True)

        await interaction.response.send_message(embed=self._embed("🔓 Channel unlocked", f"{ch.mention} is now unlocked."))

    @app_commands.command(name="lockdown", description="Lock down the full server (Chris/Bromeo only).")
    async def lockdown(self, interaction: discord.Interaction):
        if not interaction.guild or interaction.user.id not in OWNER_IDS:
            return await interaction.response.send_message("⛔ You don't have permission to do that.", ephemeral=True)
        if not interaction.guild.me or not interaction.guild.me.guild_permissions.manage_channels:
            return await interaction.response.send_message("⛔ I need **Manage Channels** server permission to run lockdown.", ephemeral=True)

        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)

        locked = 0
        failed = 0
        for ch in guild.text_channels:
            if ch.name == "rules":
                continue
            try:
                await _apply_lock(ch, True, reason=f"Lockdown by {interaction.user} ({interaction.user.id})")
                locked += 1
            except Exception:
                failed += 1

        msg = f"✅ Lockdown enabled. Locked **{locked}** channels."
        if failed:
            msg += f" (Failed: **{failed}**) — check bot permissions on those channels."
        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(name="unlockdown", description="Lift full server lockdown (Chris/Bromeo only).")
    async def unlockdown(self, interaction: discord.Interaction):
        if not interaction.guild or interaction.user.id not in OWNER_IDS:
            return await interaction.response.send_message("⛔ You don't have permission to do that.", ephemeral=True)
        if not interaction.guild.me or not interaction.guild.me.guild_permissions.manage_channels:
            return await interaction.response.send_message("⛔ I need **Manage Channels** server permission to lift lockdown.", ephemeral=True)

        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)

        unlocked = 0
        failed = 0
        for ch in guild.text_channels:
            if ch.name == "rules":
                continue
            try:
                await _apply_lock(ch, False, reason=f"Unlockdown by {interaction.user} ({interaction.user.id})")
                unlocked += 1
            except Exception:
                failed += 1

        msg = f"✅ Lockdown lifted. Unlocked **{unlocked}** channels."
        if failed:
            msg += f" (Failed: **{failed}**) — check bot permissions on those channels."
        await interaction.followup.send(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Locks(bot))
