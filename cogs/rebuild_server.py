import os
import asyncio
import yaml
import discord
from discord import app_commands
from discord.ext import commands

CONFIG_PATH = os.getenv("BRAND_CONFIG", "config.yaml")

RULES_TEXT = """## XonarousLIVE Community Rules (EN)

Welcome to **XonarousLIVE**. Keep it friendly, clean, and fun.

1) **Respect others**
No harassment, hate, discrimination, slurs, or personal attacks.

2) **No spam / scams**
No spam, phishing, malicious links, or unsolicited ads.

3) **Keep it appropriate**
No NSFW content. No gore. No shock content.

4) **No doxxing**
Don’t share personal info (yours or anyone else’s).

5) **Use the right channels**
Help keep the server readable. Mods may move/delete posts.

6) **Follow Discord ToS**
If Discord doesn’t allow it, neither do we.

7) **Mods keep the vibe**
If you disagree with a mod action, DM politely — don’t start public drama.

Thanks for being here. ⚡
"""

INFO_TEXT = """Hey! I’m **Chris**, a 20-year-old creator from the Netherlands. I was born in **Hellevoetsluis** and now live in **Kerkrade**.

My life pretty much revolves around three things: **flight simulation**, **PvP games**, and **Minecraft**. Whether I’m flying a long-haul at FL380, sweating in PvP, or creating absolute chaos with blocks — I love doing it all with the same energy and passion.

When I’m not streaming, I work as a **web developer**, but on Twitch I’m here to play games, hang out, and bring good vibes to the community. I stream in both **Dutch** and **English**, depending on who’s in chat and how the vibe feels.

I’m also a huge **Feyenoord** fan (so if you occasionally hear “I Will Survive,” now you know why). My content is all about positive energy, learning together, improving, and just having fun with people who enjoy the same stuff.

And then there’s **Captain Simba** — my cat, my sidekick, and the unofficial moderator of the channel. He came to us as a rehomed kitten and was cuddling with everyone from day one. He’s a huge cuddle monster and completely attached to me, so when I moved out, he moved with me. He often shows up during streams… usually at the worst possible moment.

Whether you’re here for PvP, Minecraft, aviation, or simply the good vibes: **welcome aboard.** ✈️💚

More: https://xonarous.live
"""

FAQ_TEXT = """**FAQ**

**Q: Where can I donate/support?**  
A: https://donate.xonarous.live

**Q: How can I contact you?**  
A: Email: **media@xonarous.live**  
Or use the contact form on https://xonarous.live

**Q: Do you stream in Dutch or English?**  
A: Both — it depends on the vibe and who’s in chat.

**Q: What do you stream?**  
A: Flight simulation, PvP games, and Minecraft (plus whatever is fun at the time).

**Q: Who is Captain Simba?**  
A: My cat and the unofficial moderator — he appears on stream at the worst possible moment 😼
"""

SOCIALS_TEXT = """Everything in one place: **Linktree**

Use the button below to find all socials, donations, and links."""


class LinktreeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Open Linktree", style=discord.ButtonStyle.link, url="https://linktree.xonarous.live/"))
def load_cfg():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def has_mod_power(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or any(r.name in {"Discord Moderator","Discord Admin"} for r in member.roles)

def role_can_be_deleted(guild: discord.Guild, role: discord.Role) -> bool:
    if role.is_default() or role.managed:
        return False
    me = guild.me
    if not me:
        return False
    return role < me.top_role

async def throttle(sec: float = 0.35):
    await asyncio.sleep(sec)

def _slug(lang: str) -> str:
    s = "".join(ch.lower() if ch.isalnum() else "-" for ch in lang).strip("-")
    s = "-".join([p for p in s.split("-") if p])
    return s[:40].rstrip("-")

class ConfirmRebuildView(discord.ui.View):
    def __init__(self, cog, interaction: discord.Interaction):
        super().__init__(timeout=75)
        self.cog = cog
        self.interaction = interaction

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.interaction.user.id

    @discord.ui.button(label="CONFIRM FULL REBUILD", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="🧨 Full rebuild started…", view=self)
        await self.cog._do_rebuild(self.interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Cancelled.", view=self)
        self.stop()

class RebuildServer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rebuild", description="Full wipe + rebuild (keeps #rules).")
    async def rebuild(self, interaction: discord.Interaction):
        # Owner-only safety: rebuild wipes channels/roles
        if interaction.user.id != 289409320318402560:
            return await interaction.response.send_message('⛔ Only Chris can run this command.', ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message("Run this in a server.", ephemeral=True)
        if not has_mod_power(interaction.user):
            return await interaction.response.send_message("Admin / Mod only.", ephemeral=True)

        view = ConfirmRebuildView(self, interaction)
        await interaction.response.send_message(
            "⚠️ **FULL REBUILD**\n"
            "• Deletes **ALL channels** except `#rules`\n"
            "• Deletes **ALL deletable roles**\n"
            "• Rebuilds everything + permissions + verification gate\n\n"
            "Press **CONFIRM FULL REBUILD** to continue.",
            ephemeral=True,
            view=view,
        )

    async def _do_rebuild(self, interaction: discord.Interaction):
        cfg = getattr(self.bot, "xcfg", None) or load_cfg()
        guild = interaction.guild

        keep_rules_name = cfg["rebuild"]["keep_rules_channel_name"]
        info_cat_name = cfg["rebuild"]["information_category_name"]

        rules_channel = discord.utils.get(guild.text_channels, name=keep_rules_name)
        if rules_channel is None:
            return await interaction.followup.send(f"Create `#{keep_rules_name}` first, then rerun.", ephemeral=True)

        try:
            await rules_channel.edit(category=None, reason="Full rebuild prep")
        except Exception:
            pass

        # 1) Delete channels
        await interaction.followup.send("Step 1/6: Deleting channels…", ephemeral=True)
        others = [c for c in guild.channels if c.id != rules_channel.id]
        non_cats = [c for c in others if not isinstance(c, discord.CategoryChannel)]
        cats = [c for c in others if isinstance(c, discord.CategoryChannel)]

        async def safe_delete(ch):
            try:
                await ch.delete(reason="XonarousLIVE rebuild")
            except Exception:
                pass
            await throttle()

        for ch in non_cats:
            await safe_delete(ch)
        for cat in cats:
            await safe_delete(cat)

        # 2) Delete roles
        await interaction.followup.send("Step 2/6: Deleting roles…", ephemeral=True)
        roles = sorted(guild.roles, key=lambda r: r.position, reverse=True)
        for role in roles:
            if not role_can_be_deleted(guild, role):
                continue
            try:
                await role.delete(reason="XonarousLIVE rebuild")
            except Exception:
                pass
            await asyncio.sleep(0.20)

        # 3) Create roles (including verification roles)
        await interaction.followup.send("Step 3/6: Creating roles…", ephemeral=True)
        role_map = {r.name: r for r in guild.roles}

        async def ensure_role(name: str, color=(120,120,120), perms: dict | None = None):
            r = role_map.get(name)
            if r:
                return r
            p = discord.Permissions.none()
            for k, v in (perms or {}).items():
                try:
                    setattr(p, k, bool(v))
                except Exception:
                    pass
            try:
                r = await guild.create_role(name=name, colour=discord.Colour.from_rgb(*color), permissions=p, reason="Rebuild role")
                role_map[name] = r
                await asyncio.sleep(0.20)
                return r
            except Exception:
                return None

        for r in cfg.get("roles", []):
            await ensure_role(r["name"], color=tuple(r.get("color",[120,120,120])), perms=r.get("perms") or {})

        rs = cfg.get("role_select", {}) or {}
        languages = rs.get("languages_top10") or []
        for name in (rs.get("platforms") or []) + (rs.get("regions") or []) + languages:
            await ensure_role(name, color=(160,160,160), perms={})

        vcfg = cfg.get("verification", {}) or {}
        unv_name = vcfg.get("unverified_role", "Unverified/Niet Geverifieerd")
        ver_name = vcfg.get("verified_role", "Xonar Squad")
        unverified = await ensure_role(unv_name, color=(120,120,120), perms={})
        verified = await ensure_role(ver_name, color=(120,255,160), perms={"send_messages": True, "read_message_history": True, "view_channel": True})

        # Refresh handles
        role_map = {r.name: r for r in guild.roles}
        everyone = guild.default_role
        r_owner = role_map.get("XonarousLIVE | Owner")
        r_admin = role_map.get("Discord Admin")
        r_mod = role_map.get("Discord Moderator")
        r_bromeo = role_map.get("BromeoLIVE")
        verified = role_map.get(ver_name)
        unverified = role_map.get(unv_name)

        # 4) Permissions model:
        # - Default (@everyone): sees NOTHING
        # - Unverified: sees only rules + welcome (read-only) + announcements (read-only)
        # - Verified (Xonar Squad): sees everything (except mod-only)
        await interaction.followup.send("Step 4/6: Creating categories/channels…", ephemeral=True)

        def ow_admins(base: dict):
            for rr in [r_mod, r_admin, r_owner, r_bromeo]:
                if rr:
                    base[rr] = discord.PermissionOverwrite(
                        view_channel=True, send_messages=True,
                        manage_messages=True, manage_channels=True,
                        manage_roles=True, moderate_members=True
                    )
            return base

        def ow_hidden_by_default():
            ow = {everyone: discord.PermissionOverwrite(view_channel=False)}
            if verified:
                ow[verified] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            return ow_admins(ow)

        def ow_info_category():
            # Hidden for everyone; Unverified + Verified can view.
            ow = {everyone: discord.PermissionOverwrite(view_channel=False)}
            if unverified:
                ow[unverified] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True, add_reactions=True)
            if verified:
                ow[verified] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            return ow_admins(ow)

        def ow_readonly_channel():
            ow = {everyone: discord.PermissionOverwrite(view_channel=False)}
            if unverified:
                ow[unverified] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True, add_reactions=True)
            if verified:
                ow[verified] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True, add_reactions=True)
            return ow_admins(ow)

        def ow_rules_channel():
            # Unverified must be able to react ✅
            ow = {everyone: discord.PermissionOverwrite(view_channel=False)}
            if unverified:
                ow[unverified] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True, add_reactions=True)
            if verified:
                ow[verified] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True, add_reactions=True)
            return ow_admins(ow)

        def ow_chat_channel():
            ow = {everyone: discord.PermissionOverwrite(view_channel=False)}
            if verified:
                ow[verified] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            return ow_admins(ow)

        def ow_mod_only():
            ow = {everyone: discord.PermissionOverwrite(view_channel=False)}
            for rr in [r_mod, r_admin, r_owner, r_bromeo]:
                if rr:
                    ow[rr] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
            return ow

        def ow_language(lang_role: discord.Role | None):
            ow = {everyone: discord.PermissionOverwrite(view_channel=False)}
            # Verified still needs access if they also have the language role
            if lang_role:
                ow[lang_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            # Staff can see
            return ow_admins(ow)

        created = {}

        info_cat = await guild.create_category(info_cat_name, overwrites=ow_info_category(), reason="Rebuild")
        await throttle()

        # Put rules into info cat
        try:
            await rules_channel.edit(category=info_cat, reason="Rebuild")
            await rules_channel.edit(overwrites=ow_rules_channel())
        except Exception:
            pass

        # Create configured structure
        for block in (cfg.get("structure") or []):
            cat_name = block.get("category")
            private_to_mods = bool(block.get("private_to_mods"))

            if cat_name == info_cat_name:
                category = info_cat
                cat_ow = ow_info_category()
            else:
                cat_ow = ow_mod_only() if private_to_mods else ow_hidden_by_default()
                try:
                    category = await guild.create_category(cat_name, overwrites=cat_ow, reason="Rebuild")
                except Exception:
                    continue
                await throttle()

            for ch in (block.get("channels") or []):
                name = ch["name"]
                ch_type = ch.get("type", "text")
                if ch_type == "text" and name == keep_rules_name:
                    continue

                try:
                    if ch_type == "voice":
                        created[name] = await guild.create_voice_channel(name, category=category, reason="Rebuild")
                    else:
                        readonly = name in {"announcements","info","faq","welcome","live-now","socials","role-select","polls"}
                        mod_only = name in {"mod-log","mod-notes","staff-chat"}
                        if name == "rules":
                            overwrites = ow_rules_channel()
                        elif mod_only:
                            overwrites = ow_mod_only()
                        elif readonly:
                            overwrites = ow_readonly_channel()
                        else:
                            overwrites = ow_chat_channel()
                        created[name] = await guild.create_text_channel(name, category=category, overwrites=overwrites, reason="Rebuild")
                    await throttle()
                except Exception:
                    await throttle()
                    continue

        # 5) Language categories: ONLY chat channel, unlocked by language role
        await interaction.followup.send("Step 5/6: Creating language categories…", ephemeral=True)
        lang_cats_created = 0
        for lang in languages:
            if lang.strip().lower() in {"english","dutch"}:
                continue
            lang_role = role_map.get(lang)
            if not lang_role:
                continue
            cat_title = f"💬 {lang.upper()}"
            try:
                cat = await guild.create_category(cat_title, overwrites=ow_language(lang_role), reason="Language category")
                await throttle()
                await guild.create_text_channel(f"{_slug(lang)}-chat", category=cat, reason="Language chat")
                await throttle()
                lang_cats_created += 1
            except Exception:
                continue

        # 6) Post messages + react ✅ on rules; assign invoker verified + owner
        await interaction.followup.send("Step 6/6: Posting setup messages…", ephemeral=True)

        async def post_embed(chan_name: str, title: str, body: str, socials: bool = False):
            ch = created.get(chan_name) or discord.utils.get(guild.text_channels, name=chan_name)
            if not ch:
                return None
            try:
                emb = discord.Embed(title=title, description=body)
                msg = await ch.send(embed=emb, view=(LinktreeView() if socials else None))
                try:
                    await msg.pin()
                except Exception:
                    pass
                return msg
            except Exception:
                return None

        # Rules message in rules channel
        rules_msg = None
        try:
            emb = discord.Embed(title="📜 Server Rules", description=RULES_TEXT.strip())
            rules_msg = await rules_channel.send(embed=emb)
            try:
                await rules_msg.pin()
            except Exception:
                pass
            emoji = (cfg.get("verification", {}) or {}).get("verify_emoji", "✅")
            try:
                await rules_msg.add_reaction(emoji)
            except Exception:
                pass
        except Exception:
            pass

        await post_embed("info", "ℹ️ About XonarousLIVE", INFO_TEXT.strip())
        await post_embed("faq", "❓ FAQ", FAQ_TEXT.strip())
        await post_embed("socials", "🔗 Socials", SOCIALS_TEXT.strip(), socials=True)

        # Role selector widget (only visible after verified can see category, but info category is visible to unverified too; still ok)
        try:
            rs_name = (cfg.get("channels", {}) or {}).get("role_select_channel_name", "role-select")
            rs_ch = created.get(rs_name) or discord.utils.get(guild.text_channels, name=rs_name)
            if rs_ch:
                from cogs.role_select import RoleSelectView
                view = RoleSelectView(self.bot, timeout=None)
                embed = discord.Embed(
                    title="🧩 Choose your roles",
                    description="Pick your **Platform**, **Region**, and **Language** roles.\n"
                                "Language categories unlock when you select a language role.",
                )
                msg = await rs_ch.send(embed=embed, view=view)
                try:
                    await msg.pin()
                except Exception:
                    pass
        except Exception:
            pass

        # Auto-assign the invoker as Owner + Verified (so you don't lock yourself out)
        try:
            inv = interaction.user
            to_add = []
            if r_owner and r_owner not in inv.roles:
                to_add.append(r_owner)
            if verified and verified not in inv.roles:
                to_add.append(verified)
            if to_add:
                await inv.add_roles(*to_add, reason="Rebuild: ensure invoker access")
            if unverified and unverified in inv.roles:
                await inv.remove_roles(unverified, reason="Rebuild: ensure invoker access")
        except Exception:
            pass

        await interaction.followup.send(
            f"✅ Rebuild finished. Language categories created: {lang_cats_created}.\n"
            f"New members will start as **{unv_name}** and must react **✅** in #{keep_rules_name} to get **{ver_name}**.",
            ephemeral=True,
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(RebuildServer(bot))
