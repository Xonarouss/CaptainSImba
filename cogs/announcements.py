import discord
from discord import app_commands
from discord.ext import commands

# XonarousLIVE brand color (green)
BRAND_GREEN = discord.Colour.from_rgb(46, 204, 113)

class Announcements(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="announcement", description="Admins: post a branded announcement (embed) pinging a role.")
    @app_commands.describe(role="Role to ping", channel="Channel to post in", title="Embed title", message="Announcement text")
    async def announcement(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        channel: discord.TextChannel,
        title: str,
        message: str,
    ):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Admins only.", ephemeral=True)

        if role.is_default():
            return await interaction.response.send_message("Pick a specific role (not @everyone).", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title=f"📣 {title}".strip(),
            description=message,
            colour=BRAND_GREEN,
        )
        embed.set_footer(text="XonarousLIVE • Official Announcement")

        try:
            await channel.send(content=role.mention, embed=embed)
            await interaction.followup.send(f"✅ Posted in {channel.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed to post: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Announcements(bot))
