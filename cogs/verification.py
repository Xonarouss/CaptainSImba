import os
import json
import discord
from discord.ext import commands

STATE_PATH = os.path.join("data", "verification.json")

def _load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_state(state):
    os.makedirs("data", exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

class Verification(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.state = _load_state()

    def _cfg(self):
        return (self.bot.xcfg.get("verification", {}) or {})

    def _names(self):
        c = self._cfg()
        return (
            c.get("unverified_role", "Unverified/Niet Geverifieerd"),
            c.get("verified_role", "Xonar Squad"),
            c.get("rules_channel_name", "rules"),
            c.get("verify_emoji", "✅"),
        )

    async def _ensure_roles(self, guild: discord.Guild):
        unv_name, ver_name, *_ = self._names()
        unv = discord.utils.get(guild.roles, name=unv_name)
        ver = discord.utils.get(guild.roles, name=ver_name)
        # Create if missing (permissions are handled via channel overwrites)
        if unv is None:
            try:
                unv = await guild.create_role(name=unv_name, reason="Verification role")
            except Exception:
                pass
        if ver is None:
            try:
                ver = await guild.create_role(name=ver_name, reason="Verified member role")
            except Exception:
                pass
        return unv, ver

    async def _dm_join(self, member: discord.Member):
        if not (self._cfg().get("dm_enabled", True)):
            return
        _, _, rules_name, emoji = self._names()
        try:
            msg = (
                f"Hey {member.name}! 👋\n\n"
                f"**EN:** Welcome to **XonarousLIVE**! To unlock the full server, please read the rules in **#{rules_name}** and then click the **{emoji}** reaction under the rules message.\n\n"
                f"**NL:** Welkom bij **XonarousLIVE**! Om de hele server te zien, lees de regels in **#{rules_name}** en klik daarna op de **{emoji}** reactie onder het regels-bericht.\n\n"
                f"If you can’t see #{rules_name}, message a moderator."
            )
            await member.send(msg)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not self._cfg().get("enabled", True):
            return
        unv, _ = await self._ensure_roles(member.guild)
        if unv:
            try:
                await member.add_roles(unv, reason="New member unverified")
            except Exception:
                pass
        await self._dm_join(member)

    async def _verify_member(self, guild: discord.Guild, member: discord.Member):
        unv, ver = await self._ensure_roles(guild)
        if ver and ver not in member.roles:
            try:
                await member.add_roles(ver, reason="Verified via rules reaction")
            except Exception:
                pass
        if unv and unv in member.roles:
            try:
                await member.remove_roles(unv, reason="Verified via rules reaction")
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not self._cfg().get("enabled", True):
            return
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        unv_name, ver_name, rules_name, emoji = self._names()
        if str(payload.emoji) != emoji:
            return

        channel = guild.get_channel(payload.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        if channel.name != rules_name:
            return

        member = guild.get_member(payload.user_id)
        if member is None or member.bot:
            return

        await self._verify_member(guild, member)

async def setup(bot: commands.Bot):
    await bot.add_cog(Verification(bot))
