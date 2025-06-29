import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import os
import re
import datetime

ALLOWED_ROLE_IDS = [1329910265264869387, 1329910241835352064]
ACTION_LOG_PATH = os.path.join("logs", "archive_action_log.txt")
DOC_CHANNEL_ID = 1343686645815181382

def has_allowed_role(ctx):
    return any(role.id in ALLOWED_ROLE_IDS for role in getattr(ctx.author, "roles", []))

def has_allowed_role_appcmd(interaction: discord.Interaction):
    return any(role.id in ALLOWED_ROLE_IDS for role in getattr(interaction.user, "roles", []))

def log_action(user, action, details):
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(ACTION_LOG_PATH), exist_ok=True)
    with open(ACTION_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{now}] {user} | {action} | {details}\n")

class NameSelect(discord.ui.Select):
    def __init__(self, date, names, messages):
        options = [discord.SelectOption(label=name, value=str(i)) for i, name in enumerate(names)]
        super().__init__(placeholder="Select a name...", min_values=1, max_values=1, options=options)
        self.date = date
        self.names = names
        self.messages = messages

    async def callback(self, interaction: discord.Interaction):
        idx = int(self.values[0])
        name = self.names[idx]
        message = self.messages[idx]
        embed = discord.Embed(
            title=f"Archive for {self.date} - {name}",
            description=message
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        log_action(interaction.user, "Viewed Archive Entry", f"{self.date} - {name}")

class NameSelectView(discord.ui.View):
    def __init__(self, date, names, messages):
        super().__init__(timeout=60)
        self.add_item(NameSelect(date, names, messages))

class DateModal(discord.ui.Modal, title="Enter Date"):
    date = discord.ui.TextInput(label="Date", placeholder="YYYY-MM-DD", required=True)

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        date_value = self.date.value
        if not re.match(r"^[\w\-]+$", date_value):
            await interaction.response.send_message(
                "Invalid date format. Use only letters, numbers, dashes, or underscores.",
                ephemeral=True
            )
            return

        db_path = os.path.join(os.getcwd(), "data", "Archive.db")
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT Name, Message FROM Archive WHERE Date = ?", (date_value,)
            ) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await interaction.response.send_message("No entries found for that date.", ephemeral=True)
            return

        names = [row[0] for row in rows]
        messages = [row[1] for row in rows]
        await interaction.response.send_message(
            f"Select a name for `{date_value}`:",
            view=NameSelectView(date_value, names, messages),
            ephemeral=True
        )
        log_action(interaction.user, "Viewed Archive List", f"Date: {date_value}")

class ArchiveView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="View a Archive", style=discord.ButtonStyle.success, custom_id="view_archive")
    async def view_archive(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DateModal(interaction.client))

class LogMessage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="archive")
    async def archive(self, ctx):
        embed = discord.Embed(
            title="HRM ARCHIVE",
            description="Welcome to the HRM archives."
        )
        await ctx.send(embed=embed, view=ArchiveView())
        log_action(ctx.author, "Used !archive", f"Channel: {ctx.channel}")

    @commands.command(name="sendtoarchive")
    async def sendtoarchive(self, ctx, date: str, name: str, *, message: str):
        if not has_allowed_role(ctx):
            await ctx.send("You do not have permission to use this command. Only users with <@&911072161349918720> or <@&1329910241835352064> can save to the archive.")
            return
        # Validate date and name
        if not re.match(r"^[\w\-]+$", date):
            await ctx.send("Invalid date format. Use only letters, numbers, dashes, or underscores.")
            return
        if not re.match(r"^[\w\-]+$", name):
            await ctx.send("Invalid name format. Use only letters, numbers, dashes, or underscores.")
            return

        db_path = os.path.join(os.getcwd(), "data", "Archive.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        try:
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "CREATE TABLE IF NOT EXISTS Archive (Date TEXT, Name TEXT, Message TEXT)"
                )
                await db.execute(
                    "INSERT INTO Archive (Date, Name, Message) VALUES (?, ?, ?)",
                    (date, name, message)
                )
                await db.commit()
            await ctx.send(f"Archive saved for `{date}` and `{name}`.")
            log_action(ctx.author, "Saved Archive", f"Date: {date} | Name: {name}")
        except Exception:
            await ctx.send("Failed to save the archive.")

    @commands.command(name="viewallarchives")
    async def viewallarchives(self, ctx):
        """View all archive entries (date and name)."""
        db_path = os.path.join(os.getcwd(), "data", "Archive.db")
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT Date, Name FROM Archive ORDER BY Date DESC"
            ) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await ctx.send("No archive entries found.")
            return
        msg = "\n".join([f"**Date:** `{row[0]}` | **Name:** `{row[1]}`" for row in rows])
        await ctx.send(f"**All Archive Entries:**\n{msg}")
        log_action(ctx.author, "Viewed All Archives", f"Total: {len(rows)}")

    @app_commands.command(name="archive", description="Open the HRM archive interface (interactive).")
    async def archive_slash(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="HRM ARCHIVE",
            description="Welcome to the HRM archives."
        )
        await interaction.response.send_message(embed=embed, view=ArchiveView(), ephemeral=True)
        log_action(interaction.user, "Used /archive", f"Channel: {interaction.channel}")

    @app_commands.command(name="archive-viewall", description="View all archive entries (date and name).")
    async def archive_viewall_slash(self, interaction: discord.Interaction):
        db_path = os.path.join(os.getcwd(), "data", "Archive.db")
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT Date, Name FROM Archive ORDER BY Date DESC"
            ) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await interaction.response.send_message("No archive entries found.", ephemeral=True)
            return
        msg = "\n".join([f"**Date:** `{row[0]}` | **Name:** `{row[1]}`" for row in rows])
        await interaction.response.send_message(f"**All Archive Entries:**\n{msg}", ephemeral=True)
        log_action(interaction.user, "Viewed All Archives (slash)", f"Total: {len(rows)}")

    @app_commands.command(name="sendtoarchive", description="Save a new archive entry. Only allowed roles can use this.")
    @app_commands.describe(
        date="Date for the archive entry (YYYY-MM-DD)",
        name="Name for the archive entry",
        message="Text to archive"
    )
    async def sendtoarchive_slash(self, interaction: discord.Interaction, date: str, name: str, message: str):
        if not has_allowed_role_appcmd(interaction):
            await interaction.response.send_message(
                "You do not have permission to use this command. Only users with <@&911072161349918720> or <@&1329910241835352064> can save to the archive.",
                ephemeral=True
            )
            return
        # Validate date and name
        if not re.match(r"^[\w\-]+$", date):
            await interaction.response.send_message(
                "Invalid date format. Use only letters, numbers, dashes, or underscores.",
                ephemeral=True
            ) # test test 
            return
        if not re.match(r"^[\w\-]+$", name):
            await interaction.response.send_message(
                "Invalid name format. Use only letters, numbers, dashes, or underscores.",
                ephemeral=True
            )
            return

        db_path = os.path.join(os.getcwd(), "data", "Archive.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        try:
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "CREATE TABLE IF NOT EXISTS Archive (Date TEXT, Name TEXT, Message TEXT)"
                )
                await db.execute(
                    "INSERT INTO Archive (Date, Name, Message) VALUES (?, ?, ?)",
                    (date, name, message)
                )
                await db.commit()
            await interaction.response.send_message(
                f"Archive saved for `{date}` and `{name}`.",
                ephemeral=True
            )
            log_action(interaction.user, "Saved Archive (slash)", f"Date: {date} | Name: {name}")
        except Exception:
            await interaction.response.send_message(
                "Failed to save the archive.",
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_ready(self):
        # Send documentation embed to the log channel on startup
        channel = self.bot.get_channel(DOC_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="🟩 Archive Management Documentation 🟩",
                color=discord.Color.green(),
                description=(
                    "**Commands:**\n"
                    "> `!archive` or `/archive` — Open the archive interface\n"
                    "> `!sendtoarchive <YEAR>-<MONTH>-<DAY> <NAME> <TEXT TO ARCHIVE>` — Save to the archive (roles: <@&911072161349918720> <@&1329910241835352064>)\n"
                    "> `!viewallarchives` or `/archive-viewall` — View all archive entries\n\n"
                    "**Who can save to the archive:**\n"
                    "> Only users with <@&911072161349918720> or <@&1329910241835352064>\n\n"
                    "**All actions are logged in `logs/archive_action_log.txt`**"
                )
            )
            await channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(LogMessage(bot))