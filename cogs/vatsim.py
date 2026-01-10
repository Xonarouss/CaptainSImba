import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

VATSIM_DATA = "https://data.vatsim.net/v3/vatsim-data.json"
VATSIM_AFV_ATIS_LIST = "https://data.vatsim.net/v3/afv-atis-data.json"

def _extract_text_atis(obj) -> str:
    lines = obj.get("text_atis") or obj.get("atis") or []
    if isinstance(lines, list):
        return " ".join(str(x) for x in lines).strip()
    return str(lines).strip()

def _find_atis_in_network(net: dict, icao: str):
    want = {f"{icao}_ATIS", f"{icao}_A_ATIS", f"{icao}_D_ATIS"}
    for key in ("atis", "controllers"):
        arr = net.get(key) or []
        if isinstance(arr, list):
            for x in arr:
                cs = (x.get("callsign") or "").upper()
                if cs in want:
                    text = _extract_text_atis(x)
                    if text:
                        return {
                            "callsign": cs,
                            "letter": (x.get("atis_code") or "").upper(),
                            "text": text,
                            "frequency": x.get("frequency"),
                        }
    return None

class Vatsim(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="vatsimatis", description="Show VATSIM ATIS (if online) for an ICAO. Includes freq when available.")
    async def vatsimatis(self, interaction: discord.Interaction, icao: str):
        icao = icao.strip().upper()
        if len(icao) != 4:
            return await interaction.response.send_message("Use a 4-letter ICAO like `EHAM`.", ephemeral=True)
        await interaction.response.defer()
        async with aiohttp.ClientSession() as session:
            async with session.get(VATSIM_AFV_ATIS_LIST, timeout=15) as r:
                if r.status != 200:
                    return await interaction.followup.send(f"ATIS lookup failed (HTTP {r.status}).")
                atis_list = await r.json()
            online = False
            if isinstance(atis_list, list):
                online = any((x.get("callsign","").upper() in {f"{icao}_ATIS", f"{icao}_A_ATIS", f"{icao}_D_ATIS"}) for x in atis_list)
            if not online:
                return await interaction.followup.send(f"No VATSIM ATIS online for `{icao}` right now.")
            async with session.get(VATSIM_DATA, timeout=15) as r2:
                if r2.status != 200:
                    return await interaction.followup.send(f"ATIS online, but main feed failed (HTTP {r2.status}).")
                net = await r2.json()
        found = _find_atis_in_network(net, icao)
        if not found:
            return await interaction.followup.send("ATIS online, but text not available right now.")
        letter = f" {found['letter']}" if found.get("letter") else ""
        freq = found.get("frequency") or "unknown"
        text = found["text"].replace("\n", " ").strip()
        embed = discord.Embed(title=f"VATSIM ATIS — {icao}{letter}")
        embed.add_field(name="Callsign", value=found.get("callsign","—"), inline=True)
        embed.add_field(name="Frequency", value=str(freq), inline=True)
        embed.add_field(name="ATIS", value=f"```{text[:3900]}```", inline=False)
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Vatsim(bot))
