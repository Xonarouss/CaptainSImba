import asyncio
import sqlite3
import time
import json
from typing import Optional, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks

BRAND_GREEN = discord.Colour.from_rgb(46, 204, 113)

APPEALS_CHANNEL_NAME = "appeals"
MODLOG_NAME = "mod-log"
BANNED_CHANNEL_NAME = "banned"
DB_PATH = "bot.db"

ADMIN_ROLE_ID = 1450553389971800185

APPEAL_WINDOW_SECONDS = 30 * 24 * 60 * 60  # 30 days
MAX_APPEALS_TOTAL = 2  # 2 total attempts (2nd via website later)
PERMABAN_DELAY_SECONDS = 30  # after decline, DM then ban after ~30s


def _is_staff(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    if member.guild_permissions.moderate_members or member.guild_permissions.kick_members or member.guild_permissions.ban_members:
        return True
    return any(r.id == ADMIN_ROLE_ID for r in member.roles)


def _ensure_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS quarantine_bans(
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        roles_json TEXT NOT NULL,
        banned_by INTEGER NOT NULL,
        ban_reason TEXT,
        created_at INTEGER NOT NULL,
        appeal_count INTEGER NOT NULL DEFAULT 0,
        last_appeal_at INTEGER,
        last_appeal_text TEXT,
        last_decision TEXT,
        last_decision_by INTEGER,
        last_decision_at INTEGER,
        PRIMARY KEY (guild_id, user_id)
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS rejoin_abuse(
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        rejoin_count INTEGER NOT NULL DEFAULT 0,
        last_rejoin_at INTEGER,
        PRIMARY KEY (guild_id, user_id)
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS scheduled_permabans(
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        execute_at INTEGER NOT NULL,
        reason TEXT,
        banned_by INTEGER NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS mutes(
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        ends_at INTEGER NOT NULL,
        roles_json TEXT NOT NULL,
        reason TEXT,
        muted_by INTEGER NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    )""")

    con.commit()
    con.close()


def _get_quarantine(guild_id: int, user_id: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""SELECT guild_id,user_id,roles_json,banned_by,ban_reason,created_at,appeal_count,last_appeal_at,last_appeal_text,
                          last_decision,last_decision_by,last_decision_at
                   FROM quarantine_bans WHERE guild_id=? AND user_id=?""",
                (guild_id, user_id))
    row = cur.fetchone()
    con.close()
    return row


def _upsert_quarantine(guild_id: int, user_id: int, roles: List[int], banned_by: int, ban_reason: str):
    now = int(time.time())
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""INSERT INTO quarantine_bans(guild_id,user_id,roles_json,banned_by,ban_reason,created_at,appeal_count,last_appeal_at,last_appeal_text,last_decision,last_decision_by,last_decision_at)
                   VALUES(?,?,?,?,?,?,0,NULL,NULL,NULL,NULL,NULL)
                   ON CONFLICT(guild_id,user_id) DO UPDATE SET
                        roles_json=excluded.roles_json,
                        banned_by=excluded.banned_by,
                        ban_reason=excluded.ban_reason,
                        created_at=excluded.created_at
                """,
                (guild_id, user_id, json.dumps(roles), banned_by, ban_reason, now))
    con.commit()
    con.close()


def _set_appeal_submitted(guild_id: int, user_id: int, appeal_text: str):
    now = int(time.time())
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""UPDATE quarantine_bans
                   SET appeal_count=appeal_count+1,
                       last_appeal_at=?,
                       last_appeal_text=?,
                       last_decision=NULL,
                       last_decision_by=NULL,
                       last_decision_at=NULL
                   WHERE guild_id=? AND user_id=?""",
                (now, appeal_text, guild_id, user_id))
    con.commit()
    con.close()


def _set_decision(guild_id: int, user_id: int, decision: str, decision_by: int):
    now = int(time.time())
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""UPDATE quarantine_bans
                   SET last_decision=?, last_decision_by=?, last_decision_at=?
                   WHERE guild_id=? AND user_id=?""",
                (decision, decision_by, now, guild_id, user_id))
    con.commit()
    con.close()


def _schedule_permaban(guild_id: int, user_id: int, execute_at: int, reason: str, banned_by: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""INSERT INTO scheduled_permabans(guild_id,user_id,execute_at,reason,banned_by)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(guild_id,user_id) DO UPDATE SET
                        execute_at=excluded.execute_at,
                        reason=excluded.reason,
                        banned_by=excluded.banned_by
                """,
                (guild_id, user_id, execute_at, reason, banned_by))
    con.commit()
    con.close()


def _pop_due_permabans(now_ts: int) -> List[Tuple[int, int, int, str, int]]:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""SELECT guild_id,user_id,execute_at,COALESCE(reason,''),banned_by
                   FROM scheduled_permabans WHERE execute_at<=?""", (now_ts,))
    rows = cur.fetchall()
    cur.execute("DELETE FROM scheduled_permabans WHERE execute_at<=?", (now_ts,))
    con.commit()
    con.close()
    return rows


def _delete_quarantine(guild_id: int, user_id: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("DELETE FROM quarantine_bans WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    con.commit()
    con.close()



def _get_rejoin_count(guild_id: int, user_id: int) -> int:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT rejoin_count FROM rejoin_abuse WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    row = cur.fetchone()
    con.close()
    return int(row[0]) if row else 0


def _inc_rejoin_count(guild_id: int, user_id: int) -> int:
    now = int(time.time())
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""INSERT INTO rejoin_abuse(guild_id,user_id,rejoin_count,last_rejoin_at)
                   VALUES(?,?,1,?)
                   ON CONFLICT(guild_id,user_id) DO UPDATE SET
                        rejoin_count=rejoin_count+1,
                        last_rejoin_at=excluded.last_rejoin_at
                """, (guild_id, user_id, now))
    con.commit()
    con.close()
    return _get_rejoin_count(guild_id, user_id)


def _clear_rejoin_count(guild_id: int, user_id: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("DELETE FROM rejoin_abuse WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    con.commit()
    con.close()


def _parse_duration(s: str) -> Optional[int]:
    s = (s or "").strip().lower()
    if not s:
        return None
    num = ""
    unit = ""
    for ch in s:
        if ch.isdigit():
            num += ch
        else:
            unit += ch
    if not num:
        return None
    n = int(num)
    unit = unit.strip() or "m"
    mult = {"s": 1, "sec": 1, "secs": 1,
            "m": 60, "min": 60, "mins": 60,
            "h": 3600, "hr": 3600, "hrs": 3600,
            "d": 86400, "day": 86400, "days": 86400}.get(unit)
    if mult is None:
        return None
    return n * mult


def _insert_mute(guild_id: int, user_id: int, ends_at: int, roles: List[int], reason: str, muted_by: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""INSERT INTO mutes(guild_id,user_id,ends_at,roles_json,reason,muted_by)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(guild_id,user_id) DO UPDATE SET
                        ends_at=excluded.ends_at,
                        roles_json=excluded.roles_json,
                        reason=excluded.reason,
                        muted_by=excluded.muted_by
                """,
                (guild_id, user_id, ends_at, json.dumps(roles), reason, muted_by))
    con.commit()
    con.close()


def _remove_mute(guild_id: int, user_id: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("DELETE FROM mutes WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    con.commit()
    con.close()


class AppealModal(discord.ui.Modal, title="Ban Appeal"):
    appeal = discord.ui.TextInput(label="Your appeal", style=discord.TextStyle.paragraph, max_length=1500)

    def __init__(self, cog: "ModerationSuite", guild_id: int, user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        row = _get_quarantine(self.guild_id, self.user_id)
        if not row:
            return await interaction.response.send_message("Appeal record not found.", ephemeral=True)

        created_at = int(row[5])
        appeal_count = int(row[6] or 0)

        if int(time.time()) - created_at > APPEAL_WINDOW_SECONDS:
            return await interaction.response.send_message(
                "⛔ Your Discord appeal window has expired. If your first appeal was declined, your last chance is via the website.",
                ephemeral=True
            )

        if appeal_count >= 1:
            return await interaction.response.send_message(
                "⛔ You already used your Discord appeal. If it gets declined, your last chance is via the website after 30 days.",
                ephemeral=True
            )

        _set_appeal_submitted(self.guild_id, self.user_id, str(self.appeal).strip())

        guild = self.cog.bot.get_guild(self.guild_id)
        if not guild:
            return await interaction.response.send_message("Server not found.", ephemeral=True)

        appeals_ch = discord.utils.get(guild.text_channels, name=APPEALS_CHANNEL_NAME)
        if not appeals_ch:
            return await interaction.response.send_message("Appeals channel not found on the server.", ephemeral=True)

        banned_by_id = int(row[3])
        ban_reason = row[4] or "—"
        appeal_text = str(self.appeal).strip()

        embed = discord.Embed(
            title="📨 New Ban Appeal",
            colour=BRAND_GREEN,
            description=f"**User:** <@{self.user_id}> (`{self.user_id}`)\n"
                        f"**Quarantine-banned by:** <@{banned_by_id}> (`{banned_by_id}`)\n"
                        f"**Reason:** {ban_reason}\n\n"
                        f"**Note:** This is their **Discord appeal** (1/2 total)."
        )
        embed.add_field(name="Appeal", value=appeal_text[:1024], inline=False)

        view = AppealStaffView(self.cog, guild_id=self.guild_id, user_id=self.user_id)
        await appeals_ch.send(embed=embed, view=view)

        await interaction.response.send_message("✅ Appeal sent to staff. You’ll be notified privately when a decision is made.", ephemeral=True)


class AppealChannelView(discord.ui.View):
    def __init__(self, cog: "ModerationSuite", guild_id: int, user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id

    @discord.ui.button(label="Appeal Ban", style=discord.ButtonStyle.success)
    async def appeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This button isn’t for you.", ephemeral=True)

        row = _get_quarantine(self.guild_id, self.user_id)
        if not row:
            return await interaction.response.send_message("Appeal record not found.", ephemeral=True)

        created_at = int(row[5])
        appeal_count = int(row[6] or 0)

        if int(time.time()) - created_at > APPEAL_WINDOW_SECONDS:
            return await interaction.response.send_message("⛔ Your Discord appeal window (30 days) has expired.", ephemeral=True)
        if appeal_count >= 1:
            return await interaction.response.send_message("⛔ You already used your Discord appeal.", ephemeral=True)

        await interaction.response.send_modal(AppealModal(self.cog, self.guild_id, self.user_id))


class AppealStaffView(discord.ui.View):
    def __init__(self, cog: "ModerationSuite", guild_id: int, user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id

    async def _can_use(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False
        return _is_staff(interaction.user)

    def _modlog(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        return discord.utils.get(guild.text_channels, name=MODLOG_NAME)

    async def _log_to_modlog(self, guild: discord.Guild, decision: str, decided_by: discord.Member):
        modlog = self._modlog(guild)
        row = _get_quarantine(guild.id, self.user_id)
        if not modlog or not row:
            return

        banned_by_id = int(row[3])
        ban_reason = row[4] or "—"
        appeal_text = row[8] or "—"

        embed = discord.Embed(
            title=f"📌 Ban Appeal {decision.upper()}",
            colour=BRAND_GREEN if decision == "approved" else discord.Colour.red(),
            description=f"**User:** <@{self.user_id}> (`{self.user_id}`)\n"
                        f"**Quarantine-banned by:** <@{banned_by_id}> (`{banned_by_id}`)\n"
                        f"**Ban reason:** {ban_reason}\n"
                        f"**Decision by:** {decided_by} (`{decided_by.id}`)"
        )
        embed.add_field(name="Appeal", value=appeal_text[:1024], inline=False)
        embed.add_field(name="Policy", value="Discord appeal: 30 days window • 2 appeals max (2nd via website)", inline=False)
        await modlog.send(embed=embed)

    async def _cleanup(self, interaction: discord.Interaction):
        try:
            await interaction.message.delete()
        except Exception:
            try:
                self.disable_all_items()
                await interaction.message.edit(view=self)
            except Exception:
                pass

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._can_use(interaction):
            return await interaction.response.send_message("⛔ No permission.", ephemeral=True)

        guild = interaction.guild
        row = _get_quarantine(guild.id, self.user_id)
        if not row:
            return await interaction.response.send_message("Record not found.", ephemeral=True)

        member = guild.get_member(self.user_id)
        if not member:
            return await interaction.response.send_message("User is no longer in the server.", ephemeral=True)

        _set_decision(guild.id, self.user_id, "approved", interaction.user.id)

        banned_role = discord.utils.get(guild.roles, name="Banned")
        me = guild.me
        try:
            if banned_role and banned_role in member.roles and me and banned_role < me.top_role:
                await member.remove_roles(banned_role, reason="Appeal approved")
            roles_to_restore = json.loads(row[2] or "[]")
            roles = []
            for rid in roles_to_restore:
                r = guild.get_role(int(rid))
                if r and not r.is_default() and me and r < me.top_role and r != banned_role:
                    roles.append(r)
            if roles:
                await member.add_roles(*roles, reason="Appeal approved: restore roles")
        except Exception:
            pass

        try:
            await member.send(embed=discord.Embed(
                title="✅ Appeal approved",
                colour=BRAND_GREEN,
                description="Your appeal was **accepted**. You can now be active in the server again.\n\nPlease re-read the rules carefully."
            ), view=AppealChannelView(self, guild.id, member.id))
        except Exception:
            pass

        await self._log_to_modlog(guild, "approved", interaction.user)
        await interaction.response.send_message("✅ Approved. Roles restored; Banned role removed.", ephemeral=True)
        await self._cleanup(interaction)
        _delete_quarantine(guild.id, self.user_id)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._can_use(interaction):
            return await interaction.response.send_message("⛔ No permission.", ephemeral=True)

        guild = interaction.guild
        row = _get_quarantine(guild.id, self.user_id)
        if not row:
            return await interaction.response.send_message("Record not found.", ephemeral=True)

        member = guild.get_member(self.user_id)
        if not member:
            return await interaction.response.send_message("User is no longer in the server.", ephemeral=True)

        _set_decision(guild.id, self.user_id, "declined", interaction.user.id)

        try:
            await member.send(embed=discord.Embed(
                title="❌ Appeal declined",
                colour=discord.Colour.red(),
                description="Your appeal was **rejected**.\n\n"
                            "You will be permanently banned in ~30 seconds.\n"
                            "Last-chance appeal: wait **30 days** and use **appeals.xonarous.live**."
            ))
        except Exception:
            pass

        execute_at = int(time.time()) + PERMABAN_DELAY_SECONDS
        _schedule_permaban(guild.id, member.id, execute_at, row[4] or "No reason", interaction.user.id)

        await self._log_to_modlog(guild, "declined", interaction.user)
        await interaction.response.send_message("✅ Declined. Permanent ban scheduled (~30s).", ephemeral=True)
        await self._cleanup(interaction)


class ModerationSuite(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        _ensure_db()
        self.unmute_due.start()
        self.permaban_due.start()

    def _modlog(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        return discord.utils.get(guild.text_channels, name=MODLOG_NAME)

    async def _dm(self, user: discord.abc.User, title: str, description: str, colour: discord.Colour):
        try:
            await user.send(embed=discord.Embed(title=title, description=description, colour=colour))
        except Exception:
            pass

    async def _ensure_banned_role_and_channel_perms(self, guild: discord.Guild):
        banned_role = discord.utils.get(guild.roles, name="Banned")
        if banned_role is None:
            banned_role = await guild.create_role(name="Banned", colour=discord.Colour.dark_grey(), reason="Create Banned role for quarantine-ban")

        banned_ch = discord.utils.get(guild.text_channels, name=BANNED_CHANNEL_NAME)
        if banned_ch is None:
            banned_ch = await guild.create_text_channel(BANNED_CHANNEL_NAME, reason="Create #banned for quarantine-ban")

        # #banned hidden from everyone, visible to banned
        try:
            ow_every = banned_ch.overwrites_for(guild.default_role)
            ow_every.view_channel = False
            await banned_ch.set_permissions(guild.default_role, overwrite=ow_every, reason="Quarantine #banned perms")

            ow_banned = banned_ch.overwrites_for(banned_role)
            ow_banned.view_channel = True
            ow_banned.send_messages = False
            ow_banned.add_reactions = False
            ow_banned.send_messages_in_threads = False
            await banned_ch.set_permissions(banned_role, overwrite=ow_banned, reason="Quarantine #banned perms")
        except Exception:
            pass

        # hide all other channels from banned
        for ch in guild.text_channels:
            if ch.id == banned_ch.id:
                continue
            try:
                ow = ch.overwrites_for(banned_role)
                ow.view_channel = False
                ow.send_messages = False
                await ch.set_permissions(banned_role, overwrite=ow, reason="Quarantine: hide channels from Banned role")
            except Exception:
                pass

        return banned_role, banned_ch

    @app_commands.command(name="warn", description="Warn a member (staff only). Sends them a DM.")
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Server only.", ephemeral=True)
        if not _is_staff(interaction.user):
            return await interaction.response.send_message("⛔ No permission.", ephemeral=True)
        await self._dm(member, "⚠️ You were warned",
                       f"**Server:** {interaction.guild.name}\n**By:** {interaction.user} (`{interaction.user.id}`)\n**Reason:** {reason}",
                       BRAND_GREEN)
        await interaction.response.send_message(f"✅ Warned {member.mention}.", ephemeral=True)

    @app_commands.command(name="kick", description="Kick a member (staff only). Sends them a DM.")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Server only.", ephemeral=True)
        if not _is_staff(interaction.user):
            return await interaction.response.send_message("⛔ No permission.", ephemeral=True)
        await self._dm(member, "👢 You were kicked",
                       f"**Server:** {interaction.guild.name}\n**By:** {interaction.user} (`{interaction.user.id}`)\n**Reason:** {reason}",
                       discord.Colour.orange())
        try:
            await member.kick(reason=f"{reason} (by {interaction.user} {interaction.user.id})")
        except Exception as e:
            return await interaction.response.send_message(f"❌ Kick failed: {e}", ephemeral=True)
        await interaction.response.send_message(f"✅ Kicked {member.mention}.", ephemeral=True)

    @app_commands.command(name="ban", description="Quarantine-ban a member (staff only): removes roles, assigns Banned role, allows in-server appeal.")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Server only.", ephemeral=True)
        if not _is_staff(interaction.user):
            return await interaction.response.send_message("⛔ No permission.", ephemeral=True)

        guild = interaction.guild
        me = guild.me
        if not me or not me.guild_permissions.manage_roles:
            return await interaction.response.send_message("❌ I need **Manage Roles** to quarantine-ban.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        banned_role, banned_ch = await self._ensure_banned_role_and_channel_perms(guild)

        removable = []
        for r in member.roles:
            if r.is_default() or r.id == banned_role.id:
                continue
            if r >= me.top_role:
                continue
            removable.append(r)

        role_ids = [r.id for r in removable]
        _upsert_quarantine(guild.id, member.id, role_ids, interaction.user.id, reason)

        try:
            if removable:
                await member.remove_roles(*removable, reason=f"Quarantine-banned by {interaction.user} ({interaction.user.id}) — {reason}")
            if banned_role < me.top_role:
                await member.add_roles(banned_role, reason=f"Quarantine-banned by {interaction.user} ({interaction.user.id}) — {reason}")
        except Exception as e:
            return await interaction.followup.send(f"❌ Failed to set roles: {e}", ephemeral=True)

        try:
            await member.send(
                embed=discord.Embed(
                    title="🚫 You were banned (quarantine)",
                    colour=discord.Colour.red(),
                    description=f"You were banned in **{guild.name}**.\n\n"
                                f"**Reason:** {reason}\n"
                                f"**By:** {interaction.user} (`{interaction.user.id}`)\n\n"
                                f"You have **30 days** to appeal.\n"
                                f"Press **Appeal Ban** below to submit your Discord appeal."
                ),
                view=AppealChannelView(self, guild.id, member.id),
            )
        except Exception:
            pass

        modlog = self._modlog(guild)
        if modlog:
            emb = discord.Embed(
                title="🚫 Quarantine-ban applied",
                colour=discord.Colour.red(),
                description=f"**Member:** {member} (`{member.id}`)\n"
                            f"**By:** {interaction.user} (`{interaction.user.id}`)\n"
                            f"**Reason:** {reason}\n"
                            f"**Action:** Roles removed, Banned role applied, restricted to #{BANNED_CHANNEL_NAME}"
            )
            await modlog.send(embed=emb)

        await interaction.followup.send(f"✅ Quarantine-banned {member.mention}. They can now only see **#{BANNED_CHANNEL_NAME}**.", ephemeral=True)

    @app_commands.command(name="mute", description="Mute a member (staff only). Removes roles and applies Muted role for duration.")
    async def mute(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided"):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Server only.", ephemeral=True)
        if not _is_staff(interaction.user):
            return await interaction.response.send_message("⛔ No permission.", ephemeral=True)

        seconds = _parse_duration(duration)
        if not seconds or seconds < 10:
            return await interaction.response.send_message("❌ Invalid duration. Use like `10m`, `2h`, `1d`.", ephemeral=True)

        guild = interaction.guild
        me = guild.me
        if not me or not me.guild_permissions.manage_roles:
            return await interaction.response.send_message("❌ I need **Manage Roles** to mute.", ephemeral=True)

        muted_role = discord.utils.get(guild.roles, name="Muted")
        if muted_role is None:
            try:
                muted_role = await guild.create_role(name="Muted", reason="Create Muted role for /mute", colour=discord.Colour.dark_grey())
            except Exception:
                return await interaction.response.send_message("❌ I couldn't create the Muted role. Give me Manage Roles.", ephemeral=True)

        try:
            for ch in guild.text_channels:
                ow = ch.overwrites_for(muted_role)
                ow.send_messages = False
                ow.add_reactions = False
                ow.create_public_threads = False
                ow.create_private_threads = False
                ow.send_messages_in_threads = False
                await ch.set_permissions(muted_role, overwrite=ow, reason="Muted role permissions")
        except Exception:
            pass

        removable = []
        for r in member.roles:
            if r.is_default() or r.id == muted_role.id:
                continue
            if r >= me.top_role:
                continue
            removable.append(r)

        role_ids = [r.id for r in removable]
        ends_at = int(time.time()) + seconds

        try:
            if removable:
                await member.remove_roles(*removable, reason=f"Muted by {interaction.user} ({interaction.user.id}) — {reason}")
            if muted_role < me.top_role:
                await member.add_roles(muted_role, reason=f"Muted by {interaction.user} ({interaction.user.id}) — {reason}")
        except Exception as e:
            return await interaction.response.send_message(f"❌ Mute failed: {e}", ephemeral=True)

        _insert_mute(guild.id, member.id, ends_at, role_ids, reason, interaction.user.id)

        await self._dm(member, "🔇 You were muted",
                       f"**Server:** {guild.name}\n**By:** {interaction.user} (`{interaction.user.id}`)\n"
                       f"**Duration:** {duration}\n**Reason:** {reason}",
                       discord.Colour.orange())

        modlog = self._modlog(guild)
        if modlog:
            embed = discord.Embed(
                title="🔇 Member muted",
                colour=discord.Colour.orange(),
                description=f"**Member:** {member} (`{member.id}`)\n"
                            f"**By:** {interaction.user} (`{interaction.user.id}`)\n"
                            f"**Duration:** {duration}\n"
                            f"**Reason:** {reason}"
            )
            await modlog.send(embed=embed)

        await interaction.response.send_message(f"✅ Muted {member.mention} for **{duration}**.", ephemeral=True)


    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        row = _get_quarantine(member.guild.id, member.id)
        if row:
            _inc_rejoin_count(member.guild.id, member.id)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        row = _get_quarantine(member.guild.id, member.id)
        if not row:
            return

        guild = member.guild
        me = guild.me
        if not me or not me.guild_permissions.manage_roles:
            return

        count = _inc_rejoin_count(guild.id, member.id)
        # Strip any auto-assigned roles on join (keep only @everyone; we will enforce Banned).
        try:
            banned_role_tmp = discord.utils.get(guild.roles, name="Banned")
            to_remove = [r for r in member.roles if (not r.is_default()) and (banned_role_tmp is None or r.id != banned_role_tmp.id)]
            if to_remove:
                await member.remove_roles(*to_remove, reason="Rejoined while quarantined: strip auto roles")
        except Exception:
            pass


        if count >= 3:
            try:
                await member.send(embed=discord.Embed(
                    title="🚫 Permanent ban",
                    colour=discord.Colour.red(),
                    description="You repeatedly left and rejoined the server while quarantined.\n\n"
                                "You have been permanently banned and can no longer appeal."
                ))
            except Exception:
                pass
            try:
                await guild.ban(member, reason="Quarantine evasion: left/rejoined 3+ times", delete_message_days=0)
            except Exception:
                pass
            _delete_quarantine(guild.id, member.id)
            _clear_rejoin_count(guild.id, member.id)

            modlog = self._modlog(guild)
            if modlog:
                await modlog.send(embed=discord.Embed(
                    title="🔨 Permanent ban (quarantine evasion)",
                    colour=discord.Colour.red(),
                    description=f"**User:** {member} (`{member.id}`)\n"
                                f"**Reason:** Left/rejoined **{count}** times while quarantined."
                ))
            return

        try:
            banned_role, _ = await self._ensure_banned_role_and_channel_perms(guild)
            if banned_role < me.top_role and banned_role not in member.roles:
                await member.add_roles(banned_role, reason="Rejoined while quarantined: reapply Banned role")
        except Exception:
            pass

        try:
            await member.send(embed=discord.Embed(
                title="⚠️ You are still quarantined",
                colour=discord.Colour.orange(),
                description="You left and rejoined the server while quarantined.\n\n"
                            f"This was counted as **{count}/3**.\n"
                            "If you do this **3 times**, you will be permanently banned without appeal.\n\n"
                            f"Please read **#{BANNED_CHANNEL_NAME}** for next steps."
            ))
        except Exception:
            pass

    @tasks.loop(seconds=30)
    async def unmute_due(self):
        now_ts = int(time.time())
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT guild_id,user_id,ends_at,roles_json FROM mutes WHERE ends_at<=?", (now_ts,))
        due = cur.fetchall()
        con.close()

        for guild_id, user_id, ends_at, roles_json in due:
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                _remove_mute(int(guild_id), int(user_id))
                continue
            member = guild.get_member(int(user_id))
            if not member:
                _remove_mute(int(guild_id), int(user_id))
                continue

            me = guild.me
            muted_role = discord.utils.get(guild.roles, name="Muted")

            try:
                if muted_role and muted_role in member.roles and me and muted_role < me.top_role:
                    await member.remove_roles(muted_role, reason="Mute expired")
                role_ids = json.loads(roles_json or "[]")
                roles_to_add = []
                for rid in role_ids:
                    r = guild.get_role(int(rid))
                    if r and me and r < me.top_role:
                        roles_to_add.append(r)
                if roles_to_add:
                    await member.add_roles(*roles_to_add, reason="Mute expired: restore roles")
            except Exception:
                pass

            await self._dm(member, "🔊 You were unmuted", f"Your mute in **{guild.name}** has expired.", BRAND_GREEN)
            modlog = self._modlog(guild)
            if modlog:
                await modlog.send(embed=discord.Embed(title="🔊 Member unmuted", description=f"**Member:** {member} (`{member.id}`)\n**Reason:** Mute expired", colour=BRAND_GREEN))

            _remove_mute(int(guild_id), int(user_id))

    @tasks.loop(seconds=15)
    async def permaban_due(self):
        now_ts = int(time.time())
        due = _pop_due_permabans(now_ts)
        for guild_id, user_id, execute_at, reason, banned_by in due:
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue
            member = guild.get_member(int(user_id))
            if not member:
                continue
            try:
                await guild.ban(member, reason=f"Appeal declined — permanent ban (by {banned_by}). Original: {reason}", delete_message_days=0)
            except Exception:
                pass
            _delete_quarantine(int(guild_id), int(user_id))
            modlog = self._modlog(guild)
            if modlog:
                embed = discord.Embed(
                    title="🔨 Permanent ban executed",
                    colour=discord.Colour.red(),
                    description=f"**User:** {member} (`{member.id}`)\n"
                                f"**Reason:** Appeal declined; permanent ban executed.\n"
                                f"**Original reason:** {reason}"
                )
                await modlog.send(embed=embed)

    @unmute_due.before_loop
    async def _before_unmute(self):
        await self.bot.wait_until_ready()

    @permaban_due.before_loop
    async def _before_permaban(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    _ensure_db()
    await bot.add_cog(ModerationSuite(bot))
