import discord
from discord.ext import commands
import os
import logging
import asyncio
from dotenv import load_dotenv
from database.connection import init_pool, close_pool
from views.resources_view import show_modules
from utils.adkar_api import get_morning_evening_adkar,get_sleeping_adkar,build_pages
from utils.config import is_admin
from views.admin_view import show_admin_panel
from views.quiz_view import show_quiz_menu, build_leaderboard_embed
from discord import app_commands
from database.repositories import mark_welcomed
load_dotenv()
TOKEN=os.getenv('MY_TOKEN')

handler = logging.FileHandler(filename='discord.log',encoding='utf-8',mode='w')
intents = discord.Intents.default()
intents.message_content = True


class CSTBBot(commands.Bot):
    async def setup_hook(self):
        await init_pool()
        await self.tree.sync()
        print("✅ Database pool ready, commands synced")

    async def close(self):
        await close_pool()
        await super().close()

bot = CSTBBot(command_prefix='!', intents=intents)

async def show_start(interaction: discord.Interaction):
    await interaction.response.edit_message(
        content=f"I'm CSTB, nice to meet you {interaction.user.mention}",
        embed=None,
        view=StartView(show_admin=is_admin(interaction.user.id)),
    )
class StartView(discord.ui.View):

    def __init__(self, show_admin: bool = False):
        super().__init__()
        if show_admin:
            btn = discord.ui.Button(label="Admin", emoji="🛠", style=discord.ButtonStyle.secondary, row=3)
            btn.callback = self.admin_callback
            self.add_item(btn)

    async def admin_callback(self, interaction: discord.Interaction):
        await show_admin_panel(interaction, on_back=show_start)
    
    @discord.ui.button(label="Modules Resources", emoji="📚", style=discord.ButtonStyle.primary,row=0)
    async def resources_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_modules(interaction, on_back=show_start)

    @discord.ui.button(label="الاذكار اليومية", style=discord.ButtonStyle.primary,row=1)
    async def adkar_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="choose an option :",
            view=AdkarView()
        )
    @discord.ui.button(label="Quizzes", emoji='💡', style=discord.ButtonStyle.primary, row=2)
    async def Quizzes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_quiz_menu(interaction, on_back=show_start)




class AdkarView(discord.ui.View):
    @discord.ui.button(label="اذكار الصباح والمساء", style=discord.ButtonStyle.primary, row=0)
    async def morning_evening_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        adkar = await asyncio.to_thread(get_morning_evening_adkar)
        pages = build_pages(adkar)
        view = AdkarPaginator(pages, interaction.user.id, "أذكار الصباح والمساء")
        await interaction.edit_original_response(content=None, embed=view.make_embed(), view=view)

    @discord.ui.button(label="اذكار النوم", style=discord.ButtonStyle.primary, row=1)
    async def sleeping_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        adkar = await asyncio.to_thread(get_sleeping_adkar)
        pages = build_pages(adkar)
        view = AdkarPaginator(pages, interaction.user.id, "أذكار النوم")
        await interaction.edit_original_response(content=None, embed=view.make_embed(), view=view)
    @discord.ui.button(label="🔙 رجوع", style=discord.ButtonStyle.danger, row=3)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
        content=f"I'm CSTB, nice to meet you {interaction.user.mention}",
        embed=None,
        view=StartView(show_admin=is_admin(interaction.user.id))
    )
        
class AdkarPaginator(discord.ui.View):
    def __init__(self, pages, author_id, title):
        super().__init__(timeout=600)
        self.pages = pages
        self.index = 0
        self.author_id = author_id
        self.title = title
        self.update_buttons()

    def make_embed(self):
        embed = discord.Embed(
            title=self.title,
            description=self.pages[self.index],
            color=discord.Color.green(),
        )
        embed.set_footer(text=f"{self.index + 1}/{len(self.pages)}")
        return embed

    def update_buttons(self):
        self.prev_button.disabled = self.index <= 0
        self.next_button.disabled = self.index >= len(self.pages) - 1

    async def refresh(self, interaction: discord.Interaction):
        self.update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "هاذي مش ليك، اكتب الأمر بنفسك.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=0)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = max(0, self.index - 1)
        await self.refresh(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = min(len(self.pages) - 1, self.index + 1)
        await self.refresh(interaction)

    @discord.ui.button(label="🔙 رجوع", style=discord.ButtonStyle.danger, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="choose an option :",
            embed=None,
            view=AdkarView()
        )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
    
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if "CSTB" in message.content.upper():
     await message.channel.send(f'{message.author.mention} use /start to start using the bot')
    await bot.process_commands(message)

start_interactions: dict[int, discord.Interaction] = {}

@bot.tree.command(name="start", description="Start using the CSTB bot")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def start(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"I'm CSTB, nice to meet you {interaction.user.mention}",
        view=StartView(show_admin=is_admin(interaction.user.id)),
        ephemeral=True,
    )

    # first-time welcome: DM first, ephemeral message as a fallback
    if await mark_welcomed(interaction.user.id):
        embed = make_welcome_embed("👋 Welcome to CSTB!")
        try:
            await interaction.user.send(embed=embed)
        except discord.HTTPException:
            await interaction.followup.send(embed=embed, ephemeral=True)

    old = start_interactions.get(interaction.user.id)
    if old is not None:
        try:
            await old.delete_original_response()
        except discord.HTTPException:
            pass

    start_interactions[interaction.user.id] = interaction

@bot.tree.command(name="leaderboard", description="Top CSTB quiz players")
async def leaderboard(interaction: discord.Interaction):
    embed = await build_leaderboard_embed(interaction.user.id)
    await interaction.response.send_message(embed=embed)

def make_welcome_embed(title: str) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=(
            "Thanks for using **CSTB** (Computer Science Toolbox)! 🎉\n\n"
            "📚 Courses, TDs, TPs and exams by module\n"
            "💡 Quizzes with levels and a leaderboard\n"
            " Daily adkar\n\n"
            "Type **/start** anytime to open the menu."
        ),
        color=discord.Color.green(),
    )

async def find_inviter(guild: discord.Guild) -> discord.abc.User | None:
    await asyncio.sleep(2)  # the audit-log entry can take a moment to appear
    if guild.me.guild_permissions.view_audit_log:
        try:
            async for entry in guild.audit_logs(limit=10, action=discord.AuditLogAction.bot_add):
                if entry.target and entry.target.id == bot.user.id:
                    return entry.user
        except discord.HTTPException:
            pass
    try:
        return await bot.fetch_user(guild.owner_id)  # fallback: the server owner
    except discord.HTTPException:
        return None


@bot.event
async def on_guild_join(guild: discord.Guild):
    embed = make_welcome_embed(f"👋 Hello from CSTB, {guild.name}!")

    user = await find_inviter(guild)
    if user is not None:
        try:
            await user.send(embed=embed)
            await mark_welcomed(user.id)  # no second welcome on their first /start
            return
        except discord.HTTPException:
            pass  # DMs closed: fall back to the server

    channel = guild.system_channel
    if channel and channel.permissions_for(guild.me).send_messages:
        await channel.send(embed=embed)

bot.run(token=TOKEN,log_handler=handler)