import discord
from discord import app_commands
from discord.ext import commands

class Misc(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Bot latency.")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🏓 Pong `{round(self.bot.latency*1000)}ms`")

    @app_commands.command(name="helpme", description="Quick command list.")
    async def helpme(self, interaction: discord.Interaction):
        txt = (
            "**XonarousLIVE Bot Commands**\n"
            "• `/rebuild` (mods)\n"
            "• `/mod clear|timeout|kick|ban` (mods)\n"
            "• `/giveaway start|end|reroll` (admins)\n"
            "• `/rank`, `/leaderboard`\n"
            "• `/askai`\n"
            "• `/weather`, `/metar`, `/vatsimatis`\n"
            "• `/feeds add|remove|list` (admins)\n"
        )
        await interaction.response.send_message(txt, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Misc(bot))
