import os
import uuid
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

ALLOWED_USER_IDS = {289409320318402560, 369632653374390274}

def _deny(interaction: discord.Interaction):
    return interaction.response.send_message("⛔ You don't have permission to use this.", ephemeral=True)

class SupabaseFiles(commands.Cog):
    """Owner-only Supabase Storage uploader/deleter with DM flow."""

    files = app_commands.Group(name="files", description="Owner-only file hosting")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.bucket = os.getenv("SUPABASE_BUCKET", "uploads")
        # Your custom public base (your reverse proxy) e.g. https://files.xonarous.live/f/
        self.public_base = os.getenv("SUPABASE_PUBLIC_BASE", "https://files.xonarous.live/f/").rstrip("/") + "/"

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.service_key}",
            "apikey": self.service_key,
        }

    async def _upload_bytes(self, object_key: str, data: bytes, content_type: str | None):
        # PUT /storage/v1/object/<bucket>/<object_key>
        url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{object_key}"
        headers = self._headers()
        if content_type:
            headers["Content-Type"] = content_type
        async with aiohttp.ClientSession() as session:
            async with session.put(url, headers=headers, data=data) as resp:
                txt = await resp.text()
                if resp.status >= 300:
                    raise RuntimeError(f"Supabase upload failed ({resp.status}): {txt[:300]}")

    async def _delete_object(self, object_key: str):
        # DELETE uses JSON array body to /storage/v1/object/<bucket>
        url = f"{self.supabase_url}/storage/v1/object/{self.bucket}"
        headers = self._headers()
        async with aiohttp.ClientSession() as session:
            async with session.delete(url, headers=headers, json=[object_key]) as resp:
                txt = await resp.text()
                if resp.status >= 300:
                    raise RuntimeError(f"Supabase delete failed ({resp.status}): {txt[:300]}")

    @files.command(name="upload", description="Upload a file to files.xonarous.live (owner-only).")
    async def upload(self, interaction: discord.Interaction):
        if interaction.user.id not in ALLOWED_USER_IDS:
            return await _deny(interaction)

        await interaction.response.send_message("✅ Check your DMs.", ephemeral=True)

        try:
            dm = await interaction.user.create_dm()
        except Exception:
            return

        await dm.send("📤 **Upload the file** you want me to host (send it as an attachment here).\n"
                      "Tip: you can send multiple files in one message.")

        def check(m: discord.Message):
            return m.author.id == interaction.user.id and isinstance(m.channel, discord.DMChannel) and len(m.attachments) > 0

        try:
            msg: discord.Message = await self.bot.wait_for("message", check=check, timeout=300)
        except Exception:
            try:
                await dm.send("⏳ Timed out. Run `/files upload` again when you're ready.")
            except Exception:
                pass
            return

        links = []
        for a in msg.attachments:
            try:
                data = await a.read()
                object_key = str(uuid.uuid4())  # IMPORTANT: key is UUID only (matches /f/<uuid>)
                await self._upload_bytes(object_key, data, a.content_type)
                links.append(self.public_base + object_key)
            except Exception as e:
                links.append(f"❌ Failed for **{a.filename}**: {e}")

        await dm.send("✅ Done! Here are your links:\n" + "\n".join(links))

    @files.command(name="delete", description="Delete a hosted file (owner-only). Use URL or UUID.")
    @app_commands.describe(url_or_key="Full link like https://files.xonarous.live/f/<uuid> or just the <uuid>")
    async def delete(self, interaction: discord.Interaction, url_or_key: str):
        if interaction.user.id not in ALLOWED_USER_IDS:
            return await _deny(interaction)

        key = url_or_key.strip()
        # Accept full /f/<uuid>
        if "/f/" in key:
            key = key.split("/f/", 1)[1]
        key = key.strip("/")

        await interaction.response.defer(ephemeral=True)
        try:
            await self._delete_object(key)
        except Exception as e:
            return await interaction.followup.send(f"❌ Delete failed: {e}", ephemeral=True)

        await interaction.followup.send(f"🗑️ Deleted: `{key}`", ephemeral=True)

async def setup(bot: commands.Bot):
    cog = SupabaseFiles(bot)
    await bot.add_cog(cog)
    try:
        bot.tree.add_command(SupabaseFiles.files)
    except discord.app_commands.CommandAlreadyRegistered:
        pass
