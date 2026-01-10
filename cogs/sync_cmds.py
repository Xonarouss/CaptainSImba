import discord
from discord import app_commands
from discord.ext import commands

class SyncCmds(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="sync", description="Admins: force-sync slash commands to this server (instant).")
    async def sync(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Admins only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync(guild=interaction.guild)
            await interaction.followup.send(f"✅ Synced {len(synced)} commands to this server.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Sync failed: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SyncCmds(bot))
