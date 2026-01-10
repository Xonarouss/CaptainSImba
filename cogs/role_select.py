import discord
from discord.ext import commands
from discord import app_commands

def _cfg(bot):
    return (getattr(bot, "xcfg", {}) or {}).get("role_select", {}) or {}

class RoleMultiSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot, label: str, options: list[str], custom_id: str):
        self.bot = bot
        opts = [discord.SelectOption(label=o, value=o) for o in options[:25]]
        super().__init__(
            placeholder=f"Select {label} (multi)",
            min_values=0,
            max_values=len(opts),
            options=opts,
            custom_id=custom_id,
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user
        option_names = [opt.value for opt in self.options]

        # Ensure roles exist
        roles = {}
        for name in option_names:
            r = discord.utils.get(guild.roles, name=name)
            if r is None:
                try:
                    r = await guild.create_role(name=name, reason="Role-select auto role")
                except Exception:
                    continue
            roles[name] = r

        selected = set(self.values or [])
        to_add = [roles[n] for n in selected if roles.get(n) and roles[n] not in member.roles]
        to_remove = [roles[n] for n in option_names if roles.get(n) and (n not in selected) and roles[n] in member.roles]

        try:
            if to_add:
                await member.add_roles(*to_add, reason="Role-select")
            if to_remove:
                await member.remove_roles(*to_remove, reason="Role-select")
            await interaction.response.send_message("✅ Updated your roles.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Couldn't update roles: {e}", ephemeral=True)

class RoleSelectView(discord.ui.View):
    def __init__(self, bot: commands.Bot, *, timeout=None):
        super().__init__(timeout=timeout)
        c = _cfg(bot)
        if c.get("platforms"):
            self.add_item(RoleMultiSelect(bot, "Platforms", c["platforms"], custom_id="rs_platforms"))
        if c.get("regions"):
            self.add_item(RoleMultiSelect(bot, "Regions", c["regions"], custom_id="rs_regions"))
        if c.get("languages_top10"):
            self.add_item(RoleMultiSelect(bot, "Languages", c["languages_top10"], custom_id="rs_langs"))

class RoleSelect(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # persistent view so the widget keeps working after restart
        if not getattr(self.bot, "_role_select_view_registered", False):
            self.bot.add_view(RoleSelectView(self.bot, timeout=None))
            self.bot._role_select_view_registered = True

    @app_commands.command(name="postroles", description="Admins: post the role-select widget in #role-select.")
    async def postroles(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Admins only.", ephemeral=True)

        ch_name = (self.bot.xcfg.get("channels", {}) or {}).get("role_select_channel_name", "role-select")
        ch = discord.utils.get(interaction.guild.text_channels, name=ch_name)
        if not ch:
            return await interaction.response.send_message(f"Create `#{ch_name}` first (or run /rebuild).", ephemeral=True)

        view = RoleSelectView(self.bot, timeout=None)
        embed = discord.Embed(
            title="🧩 Choose your roles",
            description="Pick your **Platform**, **Region**, and **Language** roles.\nLanguage categories unlock when you select a language role.",
        )
        msg = await ch.send(embed=embed, view=view)
        try:
            await msg.pin()
        except Exception:
            pass

        await interaction.response.send_message("Posted role selector.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(RoleSelect(bot))
