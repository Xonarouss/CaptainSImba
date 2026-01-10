import os
import time
import math
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

DB_PATH = os.path.join("data", "levels.db")

def xp_needed_for_level(level: int) -> int:
    # default curve: 100 * level
    return 100 * level

class Leveling(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cooldowns = {}  # (guild_id, user_id) -> last_ts
        self.bot.loop.create_task(self._init_db())

    def _cfg(self):
        return (self.bot.xcfg.get("leveling", {}) or {}) if hasattr(self.bot, "xcfg") else {}

    async def _init_db(self):
        os.makedirs("data", exist_ok=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """CREATE TABLE IF NOT EXISTS xp (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    xp INTEGER NOT NULL DEFAULT 0,
                    level INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (guild_id, user_id)
                )"""
            )
            await db.commit()

    async def _get_row(self, guild_id: int, user_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT xp, level FROM xp WHERE guild_id=? AND user_id=?", (guild_id, user_id))
            row = await cur.fetchone()
            if not row:
                await db.execute("INSERT OR IGNORE INTO xp (guild_id, user_id, xp, level) VALUES (?,?,0,1)", (guild_id, user_id))
                await db.commit()
                return 0, 1
            return int(row[0]), int(row[1])

    async def _set_row(self, guild_id: int, user_id: int, xp: int, level: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO xp (guild_id, user_id, xp, level) VALUES (?,?,?,?) "
                             "ON CONFLICT(guild_id, user_id) DO UPDATE SET xp=excluded.xp, level=excluded.level",
                             (guild_id, user_id, xp, level))
            await db.commit()

    async def _maybe_reward_roles(self, member: discord.Member, new_level: int):
        rewards = (self._cfg().get("reward_roles") or [])
        for r in rewards:
            lvl = int(r.get("level", 0))
            role_name = r.get("role_name")
            if lvl and role_name and new_level >= lvl:
                role = discord.utils.get(member.guild.roles, name=role_name)
                if role is None:
                    try:
                        role = await member.guild.create_role(name=role_name, reason="Leveling reward role")
                    except Exception:
                        continue
                if role not in member.roles:
                    try:
                        await member.add_roles(role, reason=f"Reached level {new_level}")
                    except Exception:
                        pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        cfg = self._cfg()
        if not cfg.get("enabled", True):
            return
        if not isinstance(message.author, discord.Member):
            return

        key = (message.guild.id, message.author.id)
        now = time.time()
        cd = int(cfg.get("cooldown_seconds", 60))
        if now - self._cooldowns.get(key, 0) < cd:
            return
        self._cooldowns[key] = now

        add = int(cfg.get("xp_per_message", 10))
        xp, level = await self._get_row(message.guild.id, message.author.id)
        xp += add

        # level up loop
        leveled = False
        while xp >= xp_needed_for_level(level):
            xp -= xp_needed_for_level(level)
            level += 1
            leveled = True

        await self._set_row(message.guild.id, message.author.id, xp, level)
        if leveled:
            await self._maybe_reward_roles(message.author, level)
            try:
                await message.channel.send(f"✨ {message.author.mention} leveled up to **Level {level}**!", delete_after=8)
            except Exception:
                pass

    @app_commands.command(name="rank", description="Show your level + XP.")
    async def rank(self, interaction: discord.Interaction, member: discord.Member | None = None):
        member = member or interaction.user
        xp, level = await self._get_row(interaction.guild.id, member.id)
        need = xp_needed_for_level(level)
        embed = discord.Embed(title=f"Rank — {member.display_name}")
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="XP", value=f"{xp}/{need}", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="leaderboard", description="Top 10 levels in this server.")
    async def leaderboard(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT user_id, level, xp FROM xp WHERE guild_id=? ORDER BY level DESC, xp DESC LIMIT 10", (interaction.guild.id,))
            rows = await cur.fetchall()

        lines = []
        for i, (uid, lvl, xp) in enumerate(rows, start=1):
            m = interaction.guild.get_member(uid)
            name = m.display_name if m else str(uid)
            lines.append(f"**{i}.** {name} — Level {lvl} ({xp}xp)")
        embed = discord.Embed(title="🏆 Leaderboard", description="\n".join(lines) or "No data yet.")
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
