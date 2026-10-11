# views/common.py
import math
import discord
from utils.config import is_admin

PAGE_SIZE = 25  # Discord's hard limit for options in one Select


class BackButton(discord.ui.Button):
    def __init__(self, on_back, row=4):
        super().__init__(label="🔙 رجوع", style=discord.ButtonStyle.danger, row=row)
        self.on_back = on_back

    async def callback(self, interaction: discord.Interaction):
        await self.on_back(interaction)


class _PageSelect(discord.ui.Select):
    def __init__(self, placeholder, options):
        super().__init__(placeholder=placeholder, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_pick(interaction, self.values[0])


class PagedView(discord.ui.View):
    """Dropdown with ◀ ▶ buttons. Items are dicts with an 'id' key."""

    def __init__(self, items, *, label_fn, on_pick, placeholder, on_back,
                 description_fn=None, admin_only=False, page_size=PAGE_SIZE):
        super().__init__(timeout=600)
        self.items = items
        self.label_fn = label_fn
        self.description_fn = description_fn
        self.on_pick = on_pick
        self.placeholder = placeholder
        self.on_back = on_back
        self.admin_only = admin_only
        self.page_size = page_size
        self.page = 0
        self.total_pages = max(1, math.ceil(len(items) / page_size))
        self._by_id = {str(i["id"]): i for i in items}
        self._render()

    def _render(self):
        self.clear_items()
        start = self.page * self.page_size
        chunk = self.items[start:start + self.page_size]

        if chunk:
            options = []
            for it in chunk:
                desc = self.description_fn(it) if self.description_fn else None
                options.append(discord.SelectOption(
                    label=str(self.label_fn(it))[:100],
                    value=str(it["id"]),
                    description=desc[:100] if desc else None,
                ))
            self.add_item(_PageSelect(self.placeholder, options))

        if self.total_pages > 1:
            prev = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary,
                                     row=1, disabled=self.page == 0)
            prev.callback = self._prev
            info = discord.ui.Button(label=f"{self.page + 1}/{self.total_pages}",
                                     style=discord.ButtonStyle.secondary, row=1, disabled=True)
            nxt = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary,
                                    row=1, disabled=self.page >= self.total_pages - 1)
            nxt.callback = self._next
            for b in (prev, info, nxt):
                self.add_item(b)

        self.add_item(BackButton(self.on_back, row=2 if self.total_pages > 1 else 1))

    async def _prev(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self._render()
        await interaction.response.edit_message(view=self)

    async def _next(self, interaction: discord.Interaction):
        self.page = min(self.total_pages - 1, self.page + 1)
        self._render()
        await interaction.response.edit_message(view=self)

    async def handle_pick(self, interaction: discord.Interaction, value: str):
        await self.on_pick(interaction, self._by_id[value])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.admin_only and not is_admin(interaction.user.id):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return False
        return True