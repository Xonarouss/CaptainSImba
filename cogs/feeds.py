import os
import json
import re
import aiohttp
import feedparser
import discord
from discord import app_commands
from discord.ext import commands, tasks

STATE_PATH = os.path.join("data", "feeds.json")

YOUTUBE_HANDLE_RE = re.compile(r"youtube\.com/@([A-Za-z0-9_\-\.]+)", re.IGNORECASE)
YOUTUBE_RSS_RE = re.compile(r"youtube\.com/feeds/videos\.xml\?channel_id=UC", re.IGNORECASE)

def _load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"feeds": [], "last_seen": {}}

def _save_state(state):
    os.makedirs("data", exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

async def _fetch_text(url: str):
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=25, headers={"User-Agent": "XonarousLIVE-DiscordBot/1.0"}) as r:
            return r.status, await r.text()

async def _youtube_handle_to_rss(url: str) -> str | None:
    # Convert https://www.youtube.com/@handle to channel_id RSS, best-effort.
    if not YOUTUBE_HANDLE_RE.search(url):
        return None
    status, html = await _fetch_text(url)
    if status != 200 or not html:
        return None
    m = re.search(r'"channelId"\s*:\s*"(UC[0-9A-Za-z_-]{20,})"', html)
    if not m:
        m = re.search(r"channel_id=(UC[0-9A-Za-z_-]{20,})", html)
    if not m:
        return None
    cid = m.group(1)
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"

class Feeds(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.state = _load_state()
        # ensure youtube handles are converted at startup (async)
        self.bot.loop.create_task(self._maybe_convert_youtube_handles())
        self.poll.start()

    def cog_unload(self):
        self.poll.cancel()

    async def _maybe_convert_youtube_handles(self):
        # This fixes the AttributeError you saw: the method now always exists.
        try:
            changed = False
            for f in self.state.get("feeds", []):
                url = (f.get("url") or "")
                if "youtube.com/@" in url.lower() and not YOUTUBE_RSS_RE.search(url):
                    rss = await _youtube_handle_to_rss(url)
                    if rss:
                        f["url"] = rss
                        changed = True
            if changed:
                _save_state(self.state)
        except Exception:
            # do not crash bot on conversion issues
            pass

    def _is_admin(self, m: discord.Member) -> bool:
        return m.guild_permissions.administrator

    feeds = app_commands.Group(name="feeds", description="Social notifications via RSS/Atom (admins only).")

    @feeds.command(name="add", description="Add an RSS/Atom feed (posts into #announcements).")
    async def add(self, interaction: discord.Interaction, url: str, name: str):
        if not self._is_admin(interaction.user):
            return await interaction.response.send_message("Admins only.", ephemeral=True)

        if "youtube.com/@" in url.lower() and not YOUTUBE_RSS_RE.search(url):
            rss = await _youtube_handle_to_rss(url)
            if rss:
                url = rss

        self.state["feeds"] = [f for f in self.state["feeds"] if f.get("name") != name]
        self.state["feeds"].append({"name": name, "url": url})
        _save_state(self.state)
        await interaction.response.send_message(f"Added feed **{name}**.", ephemeral=True)

    @feeds.command(name="remove", description="Remove a feed by name.")
    async def remove(self, interaction: discord.Interaction, name: str):
        if not self._is_admin(interaction.user):
            return await interaction.response.send_message("Admins only.", ephemeral=True)
        self.state["feeds"] = [f for f in self.state["feeds"] if f.get("name") != name]
        self.state["last_seen"].pop(name, None)
        _save_state(self.state)
        await interaction.response.send_message(f"Removed `{name}`.", ephemeral=True)

    @feeds.command(name="list", description="List configured feeds.")
    async def list(self, interaction: discord.Interaction):
        if not self._is_admin(interaction.user):
            return await interaction.response.send_message("Admins only.", ephemeral=True)
        if not self.state["feeds"]:
            return await interaction.response.send_message("No feeds configured.", ephemeral=True)
        lines = [f"• **{f.get('name')}** — {f.get('url')}" for f in self.state["feeds"]]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    async def _post(self, guild: discord.Guild, title: str, link: str, source: str):
        ch_name = (self.bot.xcfg.get("channels", {}) or {}).get("announcements_channel_name", "announcements")
        ch = discord.utils.get(guild.text_channels, name=ch_name)
        if not ch:
            return
        msg = f"📰 **{source}** — {title}\n{link}"
        try:
            await ch.send(msg)
        except Exception:
            pass

    @tasks.loop(minutes=3)
    async def poll(self):
        await self.bot.wait_until_ready()
        if not self.state.get("feeds"):
            return

        for feed in self.state["feeds"]:
            name = feed.get("name")
            url = feed.get("url")
            if not name or not url:
                continue

            status, xml = await _fetch_text(url)
            if status != 200 or not xml:
                continue

            parsed = feedparser.parse(xml)
            entries = parsed.entries or []
            if not entries:
                continue

            newest = entries[0]
            sig = getattr(newest, "id", None) or getattr(newest, "link", None) or getattr(newest, "title", None)
            if not sig:
                continue

            last = self.state["last_seen"].get(name)
            if last == sig:
                continue

            # First time: store without notifying (prevents instant spam on fresh install)
            if last is None:
                self.state["last_seen"][name] = sig
                _save_state(self.state)
                continue

            self.state["last_seen"][name] = sig
            _save_state(self.state)

            title = getattr(newest, "title", "New post")
            link = getattr(newest, "link", url)

            for guild in self.bot.guilds:
                await self._post(guild, title, link, name)

    @poll.before_loop
    async def before(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(Feeds(bot))
