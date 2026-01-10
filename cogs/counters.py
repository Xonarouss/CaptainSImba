import discord
from discord.ext import commands, tasks

class Counters(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_counters.start()

    def cog_unload(self):
        self.update_counters.cancel()

    async def _ensure_chunked(self, guild: discord.Guild):
        try:
            if guild.large and not guild.chunked:
                await guild.chunk(cache=True)
        except Exception:
            pass

    async def _find_voice_channel_by_prefix(self, guild: discord.Guild, prefix: str):
        for ch in guild.voice_channels:
            if ch.name.startswith(prefix):
                return ch
        return None

    @tasks.loop(minutes=5)
    async def update_counters(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            await self._ensure_chunked(guild)

            total = guild.member_count or 0
            bots = sum(1 for m in guild.members if m.bot) if guild.members else 0
            humans = max(total - bots, 0)

            ch_members = await self._find_voice_channel_by_prefix(guild, "👥 Members:")
            ch_bots = await self._find_voice_channel_by_prefix(guild, "🤖 Bots:")
            ch_total = await self._find_voice_channel_by_prefix(guild, "📈 Total:")

            try:
                if ch_members: await ch_members.edit(name=f"👥 Members: {humans}")
                if ch_bots: await ch_bots.edit(name=f"🤖 Bots: {bots}")
                if ch_total: await ch_total.edit(name=f"📈 Total: {total}")
            except Exception:
                pass

    @update_counters.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(Counters(bot))
