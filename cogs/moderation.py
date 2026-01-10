import discord
from discord import app_commands
from discord.ext import commands

def is_mod(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    if member.guild_permissions.moderate_members or member.guild_permissions.kick_members or member.guild_permissions.ban_members:
        return True
    return any(r.name in {"Discord Moderator", "XonarousLIVE | Owner"} for r in member.roles)

class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    mod = app_commands.Group(name="mod", description="Moderation commands (mods only).")

    async def _log(self, guild: discord.Guild, text: str):
        ch_name = (self.bot.xcfg.get("channels", {}) or {}).get("mod_log_channel_name", "mod-log")
        ch = discord.utils.get(guild.text_channels, name=ch_name)
        if ch:
            try:
                await ch.send(text)
            except Exception:
                pass

    @mod.command(name="clear", description="Delete up to 100 messages in a channel.")
    async def clear(self, interaction: discord.Interaction, amount: int):
        if not is_mod(interaction.user):
            return await interaction.response.send_message("Mods only.", ephemeral=True)
        amount = max(1, min(100, amount))
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)
        await self._log(interaction.guild, f"🧹 {interaction.user} cleared {len(deleted)} messages in {interaction.channel.mention}")

    @mod.command(name="timeout", description="Timeout a member.")
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str | None = None):
        if not is_mod(interaction.user) or not interaction.user.guild_permissions.moderate_members:
            return await interaction.response.send_message("You need Moderate Members permission.", ephemeral=True)
        minutes = max(1, min(10080, minutes))
        await interaction.response.defer(ephemeral=True)
        until = discord.utils.utcnow() + discord.timedelta(minutes=minutes)
        try:
            await member.timeout(until, reason=reason)
            await interaction.followup.send(f"⏳ Timed out {member.mention} for {minutes} min.", ephemeral=True)
            await self._log(interaction.guild, f"⏳ {interaction.user} timed out {member} for {minutes} min. Reason: {reason or '—'}")
        except Exception as e:
            await interaction.followup.send(f"Failed: {e}", ephemeral=True)

    @mod.command(name="kick", description="Kick a member.")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None):
        if not is_mod(interaction.user) or not interaction.user.guild_permissions.kick_members:
            return await interaction.response.send_message("You need Kick Members permission.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            await member.kick(reason=reason)
            await interaction.followup.send(f"👢 Kicked {member}.", ephemeral=True)
            await self._log(interaction.guild, f"👢 {interaction.user} kicked {member}. Reason: {reason or '—'}")
        except Exception as e:
            await interaction.followup.send(f"Failed: {e}", ephemeral=True)

    @mod.command(name="ban", description="Ban a member.")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None):
        if not is_mod(interaction.user) or not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message("You need Ban Members permission.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            await member.ban(reason=reason, delete_message_days=0)
            await interaction.followup.send(f"🔨 Banned {member}.", ephemeral=True)
            await self._log(interaction.guild, f"🔨 {interaction.user} banned {member}. Reason: {reason or '—'}")
        except Exception as e:
            await interaction.followup.send(f"Failed: {e}", ephemeral=True)

    @mod.command(name="warn", description="Warn a member (logs only).")
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if not is_mod(interaction.user):
            return await interaction.response.send_message("Mods only.", ephemeral=True)
        await interaction.response.send_message(f"⚠️ Warned {member.mention}: {reason}", ephemeral=True)
        await self._log(interaction.guild, f"⚠️ {interaction.user} warned {member}: {reason}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
