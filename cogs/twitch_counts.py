import os
import aiohttp
import discord
from discord.ext import commands, tasks

TWITCH_OAUTH = "https://id.twitch.tv/oauth2/token"
HELIX = "https://api.twitch.tv/helix"

class TwitchCounts(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._app_token = None
        self._broadcaster_id = None
        self.update_twitch_counters.start()

    def cog_unload(self):
        self.update_twitch_counters.cancel()

    async def _get_app_token(self):
        if self._app_token:
            return self._app_token
        client_id = os.getenv("TWITCH_CLIENT_ID")
        client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        if not client_id or not client_secret:
            return None
        async with aiohttp.ClientSession() as s:
            async with s.post(
                TWITCH_OAUTH,
                params={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
                timeout=20,
            ) as r:
                data = await r.json()
                if r.status != 200:
                    return None
                self._app_token = data.get("access_token")
                return self._app_token

    async def _helix_get(self, path: str, params: dict, token: str):
        client_id = os.getenv("TWITCH_CLIENT_ID")
        headers = {"Client-Id": client_id, "Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{HELIX}{path}", headers=headers, params=params, timeout=20) as r:
                return r.status, await r.json()

    async def _get_broadcaster_id(self):
        if self._broadcaster_id:
            return self._broadcaster_id
        login = os.getenv("TWITCH_BROADCASTER_LOGIN", "xonarouslive").strip().lower()
        token = await self._get_app_token()
        if not token:
            return None
        status, data = await self._helix_get("/users", {"login": login}, token)
        if status != 200:
            return None
        users = data.get("data") or []
        if not users:
            return None
        self._broadcaster_id = users[0].get("id")
        return self._broadcaster_id

    async def _find_voice_channel_by_prefix(self, guild: discord.Guild, prefix: str):
        for ch in guild.voice_channels:
            if ch.name.startswith(prefix):
                return ch
        return None

    async def _get_follower_count(self, broadcaster_id: str):
        token = await self._get_app_token()
        if not token:
            return None
        status, data = await self._helix_get("/channels/followers", {"broadcaster_id": broadcaster_id, "first": 1}, token)
        if status != 200:
            return None
        return data.get("total")

    async def _get_sub_count(self, broadcaster_id: str):
        user_token = os.getenv("TWITCH_USER_TOKEN")
        if not user_token:
            return None
        status, data = await self._helix_get("/subscriptions", {"broadcaster_id": broadcaster_id, "first": 1}, user_token)
        if status != 200:
            return None
        return data.get("total")

    @tasks.loop(minutes=5)
    async def update_twitch_counters(self):
        await self.bot.wait_until_ready()
        broadcaster_id = await self._get_broadcaster_id()
        if not broadcaster_id:
            return
        followers = await self._get_follower_count(broadcaster_id)
        subs = await self._get_sub_count(broadcaster_id)

        for guild in self.bot.guilds:
            ch_follow = await self._find_voice_channel_by_prefix(guild, "💚 Followers:")
            ch_subs = await self._find_voice_channel_by_prefix(guild, "⭐ Subs:")
            try:
                if ch_follow and followers is not None:
                    await ch_follow.edit(name=f"💚 Followers: {followers}")
                if ch_subs:
                    await ch_subs.edit(name=f"⭐ Subs: {subs if subs is not None else 'N/A'}")
            except Exception:
                pass

    @update_twitch_counters.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(TwitchCounts(bot))
