import asyncio
import random
import time
import discord
from discord import app_commands
from discord.ext import commands

class GiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.entries: set[int] = set()
        self.message_id: int | None = None  # set after send

    def count(self) -> int:
        return len(self.entries)

    async def _update_footer(self, interaction: discord.Interaction):
        # Update the embed footer with entry count (best-effort)
        try:
            msg = interaction.message
            if not msg or not msg.embeds:
                return
            emb = msg.embeds[0]
            emb.set_footer(text=f"Entries: {self.count()} • Use buttons to join/leave")
            await msg.edit(embed=emb, view=self)
        except Exception:
            pass

    @discord.ui.button(label="🎉 Enter", style=discord.ButtonStyle.success, custom_id="gw_enter")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        if uid in self.entries:
            await interaction.response.send_message("You’re already entered ✅", ephemeral=True)
            return
        self.entries.add(uid)
        await interaction.response.send_message("Entered! ✅", ephemeral=True)
        await self._update_footer(interaction)

    @discord.ui.button(label="🚪 Leave", style=discord.ButtonStyle.secondary, custom_id="gw_leave")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        if uid not in self.entries:
            await interaction.response.send_message("You weren’t entered.", ephemeral=True)
            return
        self.entries.remove(uid)
        await interaction.response.send_message("Removed you from the giveaway. ✅", ephemeral=True)
        await self._update_footer(interaction)

class Giveaways(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active = {}  # guild_id -> dict

    giveaway = app_commands.Group(name="giveaway", description="Giveaway commands (admins only).")

    def _enabled(self):
        return (self.bot.xcfg.get("giveaways", {}) or {}).get("enabled", True)

    def _is_admin(self, m: discord.Member) -> bool:
        return m.guild_permissions.administrator

    @giveaway.command(name="start", description="Start a giveaway.")
    async def start(
        self,
        interaction: discord.Interaction,
        minutes: int,
        winners: int,
        prize: str,
        channel: discord.TextChannel | None = None,
    ):
        if not self._enabled():
            return await interaction.response.send_message("Giveaways disabled.", ephemeral=True)
        if not self._is_admin(interaction.user):
            return await interaction.response.send_message("Admins only.", ephemeral=True)

        minutes = max(1, min(10080, minutes))
        winners = max(1, min(10, winners))
        channel = channel or interaction.channel

        view = GiveawayView()
        end_ts = time.time() + minutes * 60

        embed = discord.Embed(
            title="🎁 GIVEAWAY",
            description=f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends in:** {minutes} minutes",
        )
        embed.set_footer(text="Entries: 0 • Use buttons to join/leave")
        msg = await channel.send(embed=embed, view=view)
        view.message_id = msg.id

        self.active[interaction.guild.id] = {
            "message_id": msg.id,
            "channel_id": channel.id,
            "view": view,
            "winners": winners,
            "prize": prize,
            "end_ts": end_ts,
        }

        await interaction.response.send_message(f"Giveaway started in {channel.mention}.", ephemeral=True)
        self.bot.loop.create_task(self._finish(interaction.guild, msg))

    async def _finish(self, guild: discord.Guild, msg: discord.Message):
        g = self.active.get(guild.id)
        if not g:
            return
        remaining = max(0, g["end_ts"] - time.time())
        await asyncio.sleep(remaining)

        g = self.active.get(guild.id)
        if not g:
            return

        entries = list(g["view"].entries)
        if len(entries) == 0:
            await msg.reply("No one entered 😭")
            self.active.pop(guild.id, None)
            return

        winners_n = min(g["winners"], len(entries))
        picked = random.sample(entries, winners_n)
        mentions = [guild.get_member(uid).mention if guild.get_member(uid) else f"<@{uid}>" for uid in picked]

        await msg.reply(f"🎉 Winner(s): {', '.join(mentions)}\n**Prize:** {g['prize']}\nEntries: {len(entries)}")
        self.active.pop(guild.id, None)

    @giveaway.command(name="end", description="End the active giveaway now.")
    async def end(self, interaction: discord.Interaction):
        if not self._is_admin(interaction.user):
            return await interaction.response.send_message("Admins only.", ephemeral=True)
        g = self.active.get(interaction.guild.id)
        if not g:
            return await interaction.response.send_message("No active giveaway.", ephemeral=True)

        ch = interaction.guild.get_channel(g["channel_id"])
        msg = await ch.fetch_message(g["message_id"])
        g["end_ts"] = time.time()

        await interaction.response.send_message("Ending giveaway…", ephemeral=True)
        self.bot.loop.create_task(self._finish(interaction.guild, msg))

async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaways(bot))
