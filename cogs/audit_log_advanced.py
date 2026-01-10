import discord
from discord.ext import commands

BRAND_GREEN = discord.Colour.from_rgb(46, 204, 113)

MODLOG_NAME = "mod-log"

class AuditLogAdvanced(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _modlog_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        name = (self.bot.xcfg.get("channels", {}) or {}).get("mod_log_channel_name", MODLOG_NAME)
        for ch in guild.text_channels:
            if ch.name == name:
                return ch
        # fallback: #mod-log
        for ch in guild.text_channels:
            if ch.name == MODLOG_NAME:
                return ch
        return None

    async def _send(self, guild: discord.Guild, embed: discord.Embed):
        ch = self._modlog_channel(guild)
        if not ch:
            return
        try:
            await ch.send(embed=embed)
        except Exception:
            pass

    async def _find_executor(self, guild: discord.Guild, action: discord.AuditLogAction, target_id: int | None = None):
        try:
            async for entry in guild.audit_logs(limit=6, action=action):
                if target_id is None:
                    return entry.user, entry.reason
                t = entry.target
                if hasattr(t, "id") and t.id == target_id:
                    return entry.user, entry.reason
        except Exception:
            return None, None
        return None, None

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        embed = discord.Embed(
            title="🗑️ Message deleted",
            colour=BRAND_GREEN,
            description=f"**Author:** {message.author} (ID {message.author.id})\n"
                        f"**Channel:** {message.channel.mention}"
        )
        content = (message.content or "").strip()
        if content:
            embed.add_field(name="Content", value=content[:1024], inline=False)
        if message.attachments:
            att_lines = [f"[{a.filename}]({a.url})" for a in message.attachments[:10]]
            embed.add_field(name="Attachments", value="\n".join(att_lines), inline=False)

        executor, reason = await self._find_executor(message.guild, discord.AuditLogAction.message_delete)
        if executor:
            embed.set_footer(text=f"Deleted by: {executor} • Reason: {reason or '—'}")
        await self._send(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not after.guild or after.author.bot:
            return
        if (before.content or "") == (after.content or ""):
            return
        embed = discord.Embed(
            title="✏️ Message edited",
            colour=BRAND_GREEN,
            description=f"**Author:** {after.author} (ID {after.author.id})\n"
                        f"**Channel:** {after.channel.mention}\n"
                        f"[Jump to message]({after.jump_url})"
        )
        if before.content:
            embed.add_field(name="Before", value=before.content[:1024], inline=False)
        if after.content:
            embed.add_field(name="After", value=after.content[:1024], inline=False)
        await self._send(after.guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not after.guild:
            return

        # Role changes
        before_roles = set(r.id for r in before.roles)
        after_roles = set(r.id for r in after.roles)
        if before_roles != after_roles:
            added = [r for r in after.roles if r.id not in before_roles and r.name != "@everyone"]
            removed = [r for r in before.roles if r.id not in after_roles and r.name != "@everyone"]
            if added or removed:
                embed = discord.Embed(
                    title="🎭 Roles updated",
                    colour=BRAND_GREEN,
                    description=f"**Member:** {after} (ID {after.id})"
                )
                if added:
                    embed.add_field(name="Added", value="\n".join(r.mention for r in added)[:1024], inline=False)
                if removed:
                    embed.add_field(name="Removed", value="\n".join(r.mention for r in removed)[:1024], inline=False)

                executor, reason = await self._find_executor(after.guild, discord.AuditLogAction.member_role_update, after.id)
                if executor:
                    embed.set_footer(text=f"By: {executor} • Reason: {reason or '—'}")
                await self._send(after.guild, embed)

        # Timeout changes
        if before.timed_out_until != after.timed_out_until:
            embed = discord.Embed(
                title="⏱️ Timeout updated",
                colour=BRAND_GREEN,
                description=f"**Member:** {after} (ID {after.id})"
            )
            embed.add_field(name="Before", value=str(before.timed_out_until), inline=True)
            embed.add_field(name="After", value=str(after.timed_out_until), inline=True)
            executor, reason = await self._find_executor(after.guild, discord.AuditLogAction.member_update, after.id)
            if executor:
                embed.set_footer(text=f"By: {executor} • Reason: {reason or '—'}")
            await self._send(after.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        embed = discord.Embed(title="📁 Channel created", colour=BRAND_GREEN, description=f"{channel.mention} (`{channel.name}`)")
        executor, reason = await self._find_executor(guild, discord.AuditLogAction.channel_create)
        if executor:
            embed.set_footer(text=f"By: {executor} • Reason: {reason or '—'}")
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        embed = discord.Embed(title="🗑️ Channel deleted", colour=BRAND_GREEN, description=f"`{channel.name}` (ID {channel.id})")
        executor, reason = await self._find_executor(guild, discord.AuditLogAction.channel_delete)
        if executor:
            embed.set_footer(text=f"By: {executor} • Reason: {reason or '—'}")
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        if before.name == after.name:
            return
        guild = after.guild
        embed = discord.Embed(
            title="✏️ Channel updated",
            colour=BRAND_GREEN,
            description=f"**Before:** `{before.name}`\n**After:** `{after.name}`"
        )
        executor, reason = await self._find_executor(guild, discord.AuditLogAction.channel_update)
        if executor:
            embed.set_footer(text=f"By: {executor} • Reason: {reason or '—'}")
        await self._send(guild, embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(AuditLogAdvanced(bot))
