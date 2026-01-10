import os
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

MODELS_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

PREFERRED_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]

class AskAIGemini(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _list_models(self, api_key: str) -> list[str]:
        async with aiohttp.ClientSession() as session:
            async with session.get(MODELS_BASE, params={"key": api_key}, timeout=20) as r:
                data = await r.json()
                if r.status != 200:
                    return []
        out = []
        for m in (data.get("models") or []):
            name = m.get("name")
            if not name:
                continue
            short = name.split("/", 1)[-1]
            methods = m.get("supportedGenerationMethods") or []
            if methods and "generateContent" not in methods:
                continue
            out.append(short)
        return out

    async def _generate(self, api_key: str, model: str, prompt: str):
        url = f"{MODELS_BASE}/{model}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 512},
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, params={"key": api_key}, json=payload, timeout=30) as r:
                return r.status, await r.json()

    @app_commands.command(name="askai", description="Chat with Gemini AI.")
    async def askai(self, interaction: discord.Interaction, prompt: str):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return await interaction.response.send_message("GEMINI_API_KEY is not set.", ephemeral=True)

        await interaction.response.defer()
        status, data = 0, {}
        tried = []

        for m in PREFERRED_MODELS:
            tried.append(m)
            status, data = await self._generate(api_key, m, prompt)
            if status == 200:
                break

        if status == 404:
            avail = await self._list_models(api_key)
            for m in avail[:8]:
                if m in tried:
                    continue
                status, data = await self._generate(api_key, m, prompt)
                if status == 200:
                    break

        if status != 200:
            return await interaction.followup.send(f"Gemini error (HTTP {status}). If this persists, rotate your key and ensure the API is enabled.")

        text = ""
        try:
            cand = (data.get("candidates") or [])[0]
            parts = ((cand.get("content") or {}).get("parts") or [])
            text = "".join(p.get("text", "") for p in parts).strip()
        except Exception:
            pass

        if not text:
            return await interaction.followup.send("Gemini returned no text.")
        await interaction.followup.send(text[:1900] + ("…" if len(text) > 1900 else ""))

async def setup(bot: commands.Bot):
    await bot.add_cog(AskAIGemini(bot))
