import random
import asyncio
import discord
from discord.ext import commands

TWITCH_URL = "https://twitch.tv/xonarouslive"

class StatusRotation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cycle = []
        self._task = self.bot.loop.create_task(self._runner())

    def cog_unload(self):
        if self._task:
            self._task.cancel()

    def _cfg(self):
        return (self.bot.xcfg.get("status_rotation", {}) or {})

    def _build_pool(self):
        cfg = self._cfg()
        customs = list(cfg.get("custom_statuses") or [])
        facts = list(cfg.get("aviation_facts") or [])
        pool = customs + [f"✈️ Fact: {f}" for f in facts]
        return [p.strip() for p in pool if isinstance(p, str) and p.strip()]

    async def _set_status(self, text: str):
        # Streaming activity shows the purple "streaming" icon in Discord.
        try:
            await self.bot.change_presence(activity=discord.Streaming(name=text, url=TWITCH_URL))
        except Exception:
            pass

    async def _next_status(self):
        pool = self._build_pool()
        if not pool:
            return
        if not self._cycle:
            self._cycle = pool[:]
            random.shuffle(self._cycle)
        await self._set_status(self._cycle.pop())

    async def _runner(self):
        await self.bot.wait_until_ready()
        await self._next_status()

        while not self.bot.is_closed():
            cfg = self._cfg()
            if not cfg.get("enabled", True):
                await asyncio.sleep(10)
                continue
            interval = int(cfg.get("interval_seconds", 15))
            await asyncio.sleep(max(5, interval))
            await self._next_status()

async def setup(bot: commands.Bot):
    await bot.add_cog(StatusRotation(bot))
