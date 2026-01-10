import discord
from discord.ext import commands

class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _cfg(self):
        return (self.bot.xcfg.get("welcome", {}) or {})

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = self._cfg()
        if not cfg.get("enabled", True):
            return
        ch_name = (self.bot.xcfg.get("channels", {}) or {}).get("welcome_channel_name", "welcome")
        ch = discord.utils.get(member.guild.text_channels, name=ch_name)
        if not ch:
            return
        rules_name = self.bot.xcfg.get("rebuild", {}).get("keep_rules_channel_name", "rules")
        rules = discord.utils.get(member.guild.text_channels, name=rules_name)
        general = discord.utils.get(member.guild.text_channels, name="general-chat") or ch
        msg_tpl = cfg.get("message", "Welcome {member_mention}!")
        msg = msg_tpl.format(
            member_mention=member.mention,
            rules_channel_mention=(rules.mention if rules else "#rules"),
            general_channel_mention=(general.mention if general else "#general"),
        )
        try:
            await ch.send(msg)
        except Exception:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
