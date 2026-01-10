import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

AVIATIONWEATHER_BASE = "https://aviationweather.gov/api/data/metar"

class Metar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="metar", description="Get METAR for an ICAO (e.g. EHAM, EGLL).")
    async def metar(self, interaction: discord.Interaction, icao: str):
        icao = icao.strip().upper()
        if len(icao) != 4 or not icao.isalnum():
            return await interaction.response.send_message("Give me a valid 4-letter ICAO like `EHAM`.", ephemeral=True)
        await interaction.response.defer()
        async with aiohttp.ClientSession() as session:
            async with session.get(AVIATIONWEATHER_BASE, params={"ids": icao, "format": "json"}, timeout=15) as r:
                if r.status != 200:
                    return await interaction.followup.send(f"METAR fetch failed (HTTP {r.status}).")
                data = await r.json()
        if not data:
            return await interaction.followup.send(f"No METAR found for `{icao}`.")
        raw = (data[0].get("rawOb") or data[0].get("raw") or "No raw METAR returned.")
        await interaction.followup.send(embed=discord.Embed(title=f"METAR {icao}", description=f"```{raw}```"))

async def setup(bot: commands.Bot):
    await bot.add_cog(Metar(bot))
