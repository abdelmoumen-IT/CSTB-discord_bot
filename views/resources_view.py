# views/resources_view.py
from functools import partial
import discord
from database.repositories import get_modules, get_categories, get_resources
from utils.resource_manager import fetch_stored_file
from views.common import BackButton, PagedView


# ---------- Modules ----------
async def show_modules(interaction: discord.Interaction, on_back):
    await interaction.response.defer()
    modules = await get_modules()

    async def pick(i, module):
        await show_categories(i, module, on_back)

    view = PagedView(
        modules, label_fn=lambda m: m["name"], on_pick=pick,
        placeholder="Choose a module...", on_back=on_back,
    )
    content = "📚 Choose a subject:" if modules else "No modules yet."
    await interaction.edit_original_response(content=content, embed=None, view=view)


# ---------- Categories ----------
class CategoryButton(discord.ui.Button):
    def __init__(self, category, index, on_open):
        super().__init__(label=category["name"], style=discord.ButtonStyle.primary, row=index // 5)
        self.category = category
        self.on_open = on_open

    async def callback(self, interaction: discord.Interaction):
        await self.on_open(interaction, self.category)


async def show_categories(interaction: discord.Interaction, module, on_start):
    await interaction.response.defer()
    categories = await get_categories(module["id"])

    back_to_modules = partial(show_modules, on_back=on_start)
    back_to_categories = partial(show_categories, module=module, on_start=on_start)

    async def open_category(i, category):
        await show_resources(i, category, back_to_categories)

    if len(categories) > 20:  # buttons fit 20 max, switch to a paged dropdown
        view = PagedView(
            categories, label_fn=lambda c: c["name"], on_pick=open_category,
            placeholder="Choose a category...", on_back=back_to_modules,
        )
    else:
        view = discord.ui.View(timeout=600)
        for idx, c in enumerate(categories):
            view.add_item(CategoryButton(c, idx, open_category))
        view.add_item(BackButton(back_to_modules, row=4))

    content = (f"**{module['name']}**\nWhat do you need ?" if categories
               else f"**{module['name']}**\nNo categories yet.")
    await interaction.edit_original_response(content=content, embed=None, view=view)


# ---------- Resources ----------
async def send_resource(interaction: discord.Interaction, r: dict):
    await interaction.response.defer(ephemeral=True)

    text = f"**{r['title']}**"
    if r["description"]:
        text += f"\n{r['description']}"

    if r["storage_ref"]:
        try:
            file = await fetch_stored_file(interaction.client, r["storage_ref"])
        except (discord.NotFound, discord.Forbidden, ValueError, FileNotFoundError):
            await interaction.followup.send("⚠️ File unavailable, please tell an admin.", ephemeral=True)
            return
        await interaction.followup.send(text, file=file, ephemeral=True)
    elif r["file_url"]:
        await interaction.followup.send(f"{text}\n{r['file_url']}", ephemeral=True)
    else:
        await interaction.followup.send(f"{text}\n(no file attached)", ephemeral=True)


async def show_resources(interaction: discord.Interaction, category, on_back):
    await interaction.response.defer()
    resources = await get_resources(category["id"])

    view = PagedView(
        resources, label_fn=lambda r: r["title"], description_fn=lambda r: r["description"],
        on_pick=send_resource, placeholder="Choose a resource...", on_back=on_back,
    )
    content = (f"📂 **{category['name']}**" if resources
               else f"📂 **{category['name']}**\nNo resources yet.")
    await interaction.edit_original_response(content=content, embed=None, view=view)