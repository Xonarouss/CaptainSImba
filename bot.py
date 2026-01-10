import os
import asyncio
from dotenv import load_dotenv

import discord
from discord.ext import commands

load_dotenv()

INTENTS = discord.Intents.default()
INTENTS.guilds = True
INTENTS.members = True
INTENTS.message_content = True
INTENTS.voice_states = True  # needed for voice state tracking (even if you don't use voice right now)

EXTENSIONS = [
    "cogs.config",
    "cogs.sync_cmds",
    "cogs.rebuild_server",
    "cogs.verification",
    "cogs.welcome",
    "cogs.role_select",
    "cogs.status_rotation",
    "cogs.announcements",
    "cogs.supabase_files",
    "cogs.moderation",
    "cogs.automod",
    "cogs.audit_log_advanced",
    "cogs.locks",
    "cogs.appeals_moderation",
    # optional / existing:
    "cogs.feeds",
    "cogs.twitch_live",
    "cogs.giveaways",
    "cogs.leveling",
    "cogs.metar",
    "cogs.vatsim",
    "cogs.weather",
    "cogs.search_ddg",
    "cogs.fortnite",
    "cogs.askai_gemini",
    "cogs.music",
    "cogs.misc",
]

class XonarousBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS, help_command=None)

    async def setup_hook(self):
        # load YAML config if your project uses it
        self.xcfg = {}
        try:
            import yaml
            if os.path.exists("config.yaml"):
                with open("config.yaml", "r", encoding="utf-8") as f:
                    self.xcfg = yaml.safe_load(f) or {}
        except Exception:
            self.xcfg = {}

        for ext in EXTENSIONS:
            try:
                await self.load_extension(ext)
                print(f"✅ Loaded {ext}")
            except Exception as e:
                print(f"❌ Failed to load {ext}: {e}")

        # Sync slash commands (global sync can take time; we also provide /sync)
        try:
            await self.tree.sync()
            print("✅ Slash commands synced.")
        except Exception as e:
            print(f"⚠️ Slash command sync failed: {e}")

bot = XonarousBot()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN missing. Set it in Railway Variables or .env")
    bot.run(token)

if __name__ == "__main__":
    main()
