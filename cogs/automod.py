import re
import time
import discord
from discord.ext import commands

INVITE_RE = re.compile(r"(discord\.gg/|discord\.com/invite/)", re.IGNORECASE)

class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._recent = {}  # (guild_id, user_id) -> [timestamps]

    def _cfg(self):
        return (getattr(self.bot, "xcfg", {}) or {}).get("automod", {}) or {}

    def _is_mod(self, m: discord.Member) -> bool:
        return m.guild_permissions.administrator or m.guild_permissions.manage_messages or any(r.name == "Discord Moderator" for r in m.roles)

    async def _log(self, guild: discord.Guild, text: str):
        ch_name = (self.bot.xcfg.get("channels", {}) or {}).get("mod_log_channel_name", "mod-log")
        ch = discord.utils.get(guild.text_channels, name=ch_name)
        if ch:
            try:
                await ch.send(text)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        cfg = self._cfg()
        if not cfg.get("enabled", True):
            return
        if not isinstance(message.author, discord.Member):
            return
        if self._is_mod(message.author):
            return

        content = message.content or ""

        # 1) Invite links block
        if cfg.get("block_invite_links", True) and INVITE_RE.search(content):
            try:
                await message.delete()
            except Exception:
                pass
            await self._log(message.guild, f"🚫 Deleted invite link from {message.author.mention} in {message.channel.mention}")
            return

        # 2) Mention spam
        if len(message.mentions) >= int(cfg.get("max_mentions", 6)):
            await self._take_action(message, reason=f"mention spam ({len(message.mentions)})")
            return

        # 3) Caps spam
        letters = [c for c in content if c.isalpha()]
        if len(letters) >= int(cfg.get("min_caps_length", 12)):
            caps = sum(1 for c in letters if c.isupper())
            ratio = caps / max(len(letters), 1)
            if ratio >= float(cfg.get("max_caps_ratio", 0.75)):
                await self._take_action(message, reason=f"caps spam ({ratio:.0%})")
                return

        # 4) Flood spam (messages per window)
        key = (message.guild.id, message.author.id)
        now = time.time()
        window = int(cfg.get("spam_window_seconds", 8))
        max_msgs = int(cfg.get("spam_max_messages", 6))
        arr = self._recent.get(key, [])
        arr = [t for t in arr if now - t <= window]
        arr.append(now)
        self._recent[key] = arr
        if len(arr) >= max_msgs:
            await self._take_action(message, reason=f"flood ({len(arr)}/{window}s)")

    async def _take_action(self, message: discord.Message, reason: str):
        cfg = self._cfg()
        minutes = int(cfg.get("action_timeout_minutes", 10))
        try:
            await message.delete()
        except Exception:
            pass

        try:
            until = discord.utils.utcnow() + discord.timedelta(minutes=minutes)
            await message.author.timeout(until, reason=f"AutoMod: {reason}")
            await message.channel.send(f"🛡️ {message.author.mention} auto-timeout for **{reason}**.", delete_after=8)
        except Exception:
            pass

        await self._log(message.guild, f"🛡️ AutoMod action on {message.author} — {reason} (timeout {minutes}m)")

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
