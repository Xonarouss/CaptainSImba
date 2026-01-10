import asyncio
import time
import discord
from discord.ext import commands, tasks
import feedparser

BRAND_GREEN = discord.Colour.from_rgb(46, 204, 113)

def _cfg_dict(v):
    return v if isinstance(v, dict) else {}

class TwitchLive(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.feed_url = _cfg_dict(bot.xcfg.get("feeds", {})).get("twitch_rss") or "https://twitchrss.com/feeds/?username=xonarouslive&feed=streams"
        self.channel_name = _cfg_dict(bot.xcfg.get("channels", {})).get("live_now") or "live-now"
        self.ping_role_name = _cfg_dict(bot.xcfg.get("roles", {})).get("live_ping_role")  # optional
        self._last_id = None
        self.poll.start()

    def cog_unload(self):
        self.poll.cancel()

    async def _get_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        for ch in guild.text_channels:
            if ch.name == self.channel_name:
                return ch
        return None

    async def _get_ping(self, guild: discord.Guild) -> str:
        if not self.ping_role_name:
            return ""
        role = discord.utils.get(guild.roles, name=self.ping_role_name)
        return role.mention if role else ""

    def _is_live_entry(self, entry) -> bool:
        # TwitchRSS stream feed entries are only present when live starts.
        # We'll treat any new entry as "went live".
        return True

    @tasks.loop(seconds=60)
    async def poll(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            ch = await self._get_channel(guild)
            if not ch:
                continue

            parsed = feedparser.parse(self.feed_url)
            if not parsed.entries:
                continue

            entry = parsed.entries[0]
            entry_id = entry.get("id") or entry.get("guid") or entry.get("link")
            if not entry_id:
                # fallback
                entry_id = f"{entry.get('title','')}-{int(time.time())}"

            if self._last_id is None:
                self._last_id = entry_id
                continue

            if entry_id == self._last_id:
                continue

            self._last_id = entry_id

            title = entry.get("title", "XonarousLIVE is live!")
            link = entry.get("link", "https://www.twitch.tv/xonarouslive")
            desc = entry.get("summary", "").strip()

            embed = discord.Embed(
                title="🔴 LIVE NOW on Twitch",
                description=f"**{title}**\n\n{desc[:300]}\n\nWatch here: {link}",
                colour=BRAND_GREEN,
            )
            embed.set_footer(text="XonarousLIVE • Twitch")
            ping = await self._get_ping(guild)

            try:
                await ch.send(content=ping, embed=embed)
            except Exception:
                pass

    @poll.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(TwitchLive(bot))
