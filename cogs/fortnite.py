import os
import urllib.parse
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

API_BASE = "https://fortnite-api.com"

def _auth_headers() -> dict:
    key = os.getenv("FORTNITE_API_KEY", "").strip()
    return {"Authorization": key} if key else {}

async def _get_json(url: str) -> tuple[int, dict | None]:
    headers = {"User-Agent": "XonarousLIVE-DiscordBot/1.0"}
    headers.update(_auth_headers())
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers, timeout=25) as r:
            try:
                data = await r.json()
            except Exception:
                data = None
            return r.status, data

def _ok(status: int, data: dict | None) -> bool:
    if status != 200 or not isinstance(data, dict):
        return False
    # fortnite-api.com typically uses {"status": 200, "data": {...}}
    if data.get("status") and int(data["status"]) != 200:
        return False
    return True

class Fortnite(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    fn = app_commands.Group(name="fn", description="Fortnite commands")

    @fn.command(name="shop", description="Show the current Item Shop.")
    async def shop(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        # Most wrappers reference /v2/shop (shop br is sometimes /v2/shop/br)
        urls = [
            f"{API_BASE}/v2/shop?language=en",
            f"{API_BASE}/v2/shop/br?language=en",
        ]
        status = 0
        data = None
        for u in urls:
            status, data = await _get_json(u)
            if _ok(status, data):
                break

        if not _ok(status, data):
            return await interaction.followup.send(f"❌ Shop lookup failed (HTTP {status}).")

        payload = data.get("data") or {}
        # Try both shapes
        entries = payload.get("entries") or payload.get("shop") or []
        if not entries:
            # some responses have featured/daily
            entries = (payload.get("featured", {}).get("entries") or []) + (payload.get("daily", {}).get("entries") or [])

        # Pull some item names
        names = []
        for e in entries[:12]:
            items = e.get("items") or []
            for it in items[:2]:
                name = it.get("name")
                if name:
                    names.append(name)
            if len(names) >= 12:
                break

        embed = discord.Embed(title="🛒 Fortnite Item Shop", description="Here are some items currently in the shop:")
        if names:
            embed.add_field(name="Highlights", value="\n".join(f"• {n}" for n in names[:12]), inline=False)
        else:
            embed.description = "Shop is online, but I couldn't parse item names from the response."

        # Try to attach a shop image if present
        img = (payload.get("image") or payload.get("imageUrl") or payload.get("shopImage")) 
        if isinstance(img, str) and img.startswith("http"):
            embed.set_image(url=img)

        await interaction.followup.send(embed=embed)

    @fn.command(name="news", description="Show Fortnite news (BR/STW/Creative).")
    async def news(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        status, data = await _get_json(f"{API_BASE}/v2/news?language=en")
        if not _ok(status, data):
            return await interaction.followup.send(f"❌ News lookup failed (HTTP {status}).")

        d = data.get("data") or {}
        # likely keys: br, stw, creative
        def pick(section_key: str):
            sec = d.get(section_key) or {}
            motds = sec.get("motds") or sec.get("messages") or []
            if motds:
                m = motds[0]
                return (m.get("title") or section_key.upper(), m.get("body") or "")
            return (section_key.upper(), "No items.")
        br_t, br_b = pick("br")
        stw_t, stw_b = pick("stw")
        cr_t, cr_b = pick("creative")

        embed = discord.Embed(title="📰 Fortnite News")
        embed.add_field(name=br_t, value=(br_b[:900] + "…") if len(br_b) > 900 else (br_b or "—"), inline=False)
        embed.add_field(name=stw_t, value=(stw_b[:900] + "…") if len(stw_b) > 900 else (stw_b or "—"), inline=False)
        embed.add_field(name=cr_t, value=(cr_b[:900] + "…") if len(cr_b) > 900 else (cr_b or "—"), inline=False)

        await interaction.followup.send(embed=embed)

    @fn.command(name="map", description="Show the current BR map.")
    async def map(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        status, data = await _get_json(f"{API_BASE}/v1/map?language=en")
        if not _ok(status, data):
            return await interaction.followup.send(f"❌ Map lookup failed (HTTP {status}).")

        payload = data.get("data") or {}
        embed = discord.Embed(title="🗺️ Fortnite BR Map")
        img = None
        # common shapes: images: {pois, blank}, or image
        images = payload.get("images") or {}
        for key in ("pois", "blank"):
            if isinstance(images, dict) and isinstance(images.get(key), str):
                img = images.get(key)
                break
        if not img:
            img = payload.get("image") if isinstance(payload.get("image"), str) else None

        if img:
            embed.set_image(url=img)

        await interaction.followup.send(embed=embed)

    @fn.command(name="cosmetic", description="Search a cosmetic by name.")
    async def cosmetic(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(thinking=True)
        q = urllib.parse.quote(name)
        status, data = await _get_json(f"{API_BASE}/v2/cosmetics/br/search?name={q}&language=en")
        if not _ok(status, data):
            return await interaction.followup.send(f"❌ Cosmetic search failed (HTTP {status}). Try a different spelling.")

        c = (data.get("data") or {})
        embed = discord.Embed(title=f"✨ {c.get('name','Cosmetic')}")
        desc = []
        if c.get("type"):
            desc.append(f"Type: **{(c['type'] or {}).get('displayValue','')}**")
        if c.get("rarity"):
            desc.append(f"Rarity: **{(c['rarity'] or {}).get('displayValue','')}**")
        if c.get("introduction"):
            intro = (c["introduction"] or {}).get("text")
            if intro:
                desc.append(intro)
        if desc:
            embed.description = "\n".join(desc)

        icon = None
        images = c.get("images") or {}
        for key in ("icon", "featured", "smallIcon"):
            if isinstance(images, dict) and isinstance(images.get(key), str):
                icon = images.get(key)
                break
        if icon:
            embed.set_thumbnail(url=icon)

        await interaction.followup.send(embed=embed)

    @fn.command(name="upcoming", description="Show newly added cosmetics (good proxy for upcoming).")
    async def upcoming(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        # docs/wrappers mention "Cosmetics New V2"
        status, data = await _get_json(f"{API_BASE}/v2/cosmetics/br/new?language=en")
        if not _ok(status, data):
            return await interaction.followup.send(f"❌ Upcoming lookup failed (HTTP {status}).")

        items = (data.get("data") or {}).get("items") or (data.get("data") or {}).get("data") or []
        names = []
        for it in items[:15]:
            n = it.get("name")
            if n:
                names.append(n)
        embed = discord.Embed(title="🧪 New / Upcoming Cosmetics", description="Recent additions (often includes upcoming/leaked items):")
        embed.add_field(name="Items", value="\n".join(f"• {n}" for n in (names[:15] or ['(none parsed)'])), inline=False)
        await interaction.followup.send(embed=embed)

    @fn.command(name="stats", description="Get Battle Royale stats for a player.")
    async def stats(self, interaction: discord.Interaction, player: str, platform: str = "epic"):
        await interaction.response.defer(thinking=True)
        # FortNite-API v2 stats endpoint used by several wrappers:
        q_player = urllib.parse.quote(player)
        q_platform = urllib.parse.quote(platform.lower())
        url = f"{API_BASE}/v2/stats/br/v2?name={q_player}&accountType={q_platform}"
        status, data = await _get_json(url)
        if not _ok(status, data):
            return await interaction.followup.send(f"❌ Stats lookup failed (HTTP {status}). Try platform: epic, psn, xbl.")

        d = data.get("data") or {}
        acc = d.get("account") or {}
        stats = d.get("stats") or {}
        alltime = stats.get("all") or {}

        def get(path, default=None):
            cur = alltime
            for k in path:
                if not isinstance(cur, dict): 
                    return default
                cur = cur.get(k)
            return cur if cur is not None else default

        wins = get(["overall","wins"]) or get(["wins"]) 
        kd = get(["overall","kd"]) or get(["kd"])
        matches = get(["overall","matches"]) or get(["matches"])
        kills = get(["overall","kills"]) or get(["kills"])

        embed = discord.Embed(title="📊 Fortnite Stats")
        embed.add_field(name="Player", value=acc.get("name", player), inline=True)
        embed.add_field(name="Platform", value=platform.upper(), inline=True)
        embed.add_field(name="Matches", value=str(matches) if matches is not None else "—", inline=True)
        embed.add_field(name="Wins", value=str(wins) if wins is not None else "—", inline=True)
        embed.add_field(name="Kills", value=str(kills) if kills is not None else "—", inline=True)
        embed.add_field(name="K/D", value=str(kd) if kd is not None else "—", inline=True)

        img = d.get("image") if isinstance(d.get("image"), str) else None
        if img:
            embed.set_thumbnail(url=img)

        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Fortnite(bot))
