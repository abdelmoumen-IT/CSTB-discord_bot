import asyncio
import re
import secrets
import unicodedata
from functools import partial

import asyncpg
import discord
import json
from database.quiz_repository import add_question, get_questions, delete_question, add_questions_bulk
from utils.config import is_admin, ARCHIVE_CHANNEL_ID
from utils.resource_manager import delete_stored_file
from views.common import BackButton, PagedView
from database.quiz_repository import add_question, get_questions, delete_question
from database.repositories import (
    get_modules, get_categories, get_resources,
    add_resource, delete_resource, add_module, add_category,
    rename_module, rename_category, delete_module, delete_category,
)
class AdminView(discord.ui.View):
    """Base view: every click is checked against ADMIN_IDS."""
    def __init__(self):
        super().__init__(timeout=600)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_admin(interaction.user.id):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return False
        return True

def picker(items, placeholder, label_key, on_pick, on_back):
    return PagedView(
        items, label_fn=lambda i: i[label_key], on_pick=on_pick,
        placeholder=placeholder, on_back=on_back, admin_only=True,
    )

# ---------- Add resource flow ----------
class ResourceModal(discord.ui.Modal, title="New resource"):
    name_input = discord.ui.TextInput(label="Title", max_length=100)
    desc_input = discord.ui.TextInput(
        label="Description (optional)", style=discord.TextStyle.paragraph,
        required=False, max_length=300,
    )

    def __init__(self, category: dict):
        super().__init__()
        self.category = category

    async def on_submit(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return

        await interaction.response.send_message(
            "📎 Now send the file in this channel (you have 2 minutes).", ephemeral=True
        )

        def check(m: discord.Message):
            return (m.author.id == interaction.user.id
                    and m.channel.id == interaction.channel_id
                    and m.attachments)

        try:
            msg = await interaction.client.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Cancelled, no file received.", ephemeral=True)
            return

        att = msg.attachments[0]
        try:
            archive = interaction.client.get_channel(ARCHIVE_CHANNEL_ID) \
                or await interaction.client.fetch_channel(ARCHIVE_CHANNEL_ID)
            archived = await archive.send(
                content=f"{self.category['name']} — {self.name_input.value}",
                file=await att.to_file(),
            )
        except (discord.HTTPException, discord.Forbidden) as e:
            await interaction.followup.send(f"❌ Upload to archive failed: {e}", ephemeral=True)
            return

        resource_id = await add_resource(
            category_id=self.category["id"],
            title=self.name_input.value.strip(),
            description=self.desc_input.value.strip() or None,
            storage_ref=f"discord:{archive.id}:{archived.id}",
            file_name=att.filename,
            created_by=interaction.user.id,
        )

        try:
            await msg.delete()  # needs Manage Messages, optional
        except discord.HTTPException:
            pass

        await interaction.followup.send(
            f"✅ Added **{self.name_input.value}** (id {resource_id}) to {self.category['name']}.",
            ephemeral=True,
        )

async def start_add_resource(interaction: discord.Interaction, on_back):
    await interaction.response.defer()
    modules = await get_modules()

    async def pick_module(i, module):
        await i.response.defer()
        categories = await get_categories(module["id"])

        async def back_to_modules(i2):
            await start_add_resource(i2, on_back)

        async def pick_category(i2, category):
            # a modal must be the first response, so no defer here
            await i2.response.send_modal(ResourceModal(category))

        view = picker(categories, "Choose a category...", "name", pick_category, back_to_modules)
        text = (f"➕ **{module['name']}**: choose the category" if categories
                else f"**{module['name']}** has no categories yet.")
        await i.edit_original_response(content=text, view=view)

    view = picker(modules, "Choose a module...", "name", pick_module, on_back)
    await interaction.edit_original_response(
        content="➕ Choose the module:" if modules else "No modules yet.", view=view
    )

# ---------- Delete resource flow ----------

class DeleteConfirmView(AdminView):
    def __init__(self, resource, on_cancel, on_done):
        super().__init__()
        self.resource = resource
        self.on_cancel = on_cancel
        self.on_done = on_done

    @discord.ui.button(label="Yes, delete", emoji="🗑", style=discord.ButtonStyle.danger, row=0)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        deleted = await delete_resource(self.resource["id"])
        if deleted and deleted["storage_ref"]:
            await delete_stored_file(interaction.client, deleted["storage_ref"])

        view = AdminView()
        view.add_item(BackButton(self.on_done, row=0))
        text = f"✅ Deleted **{self.resource['title']}**." if deleted else "Already deleted."
        await interaction.edit_original_response(content=text, view=view)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=0)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.on_cancel(interaction)


async def start_delete(interaction: discord.Interaction, on_back):
    await interaction.response.defer()
    modules = await get_modules()

    async def pick_module(i, module):
        await delete_pick_category(i, module, on_back)

    view = AdminView()
    view = picker(modules, "Choose a module...", "name", pick_module, on_back)
    view.add_item(BackButton(on_back, row=1))
    await interaction.edit_original_response(
        content="🗑 Choose the module:" if modules else "No modules yet.", view=view
    )


async def delete_pick_category(interaction, module, on_back):
    await interaction.response.defer()
    categories = await get_categories(module["id"])

    async def back_to_modules(i):
        await start_delete(i, on_back)

    async def pick_category(i, category):
        await delete_pick_resource(i, module, category, on_back)

    view = AdminView()
    view = picker(categories, "Choose a category...", "name", pick_category, back_to_modules)
    view.add_item(BackButton(back_to_modules, row=1))
    await interaction.edit_original_response(
        content=f"🗑 **{module['name']}**: choose the category" if categories
        else f"**{module['name']}** has no categories.",
        view=view,
    )


async def delete_pick_resource(interaction, module, category, on_back):
    await interaction.response.defer()
    resources = await get_resources(category["id"])

    async def back_to_categories(i):
        await delete_pick_category(i, module, on_back)

    async def pick_resource(i, resource):
        await i.response.edit_message(
            content=f"⚠️ Delete **{resource['title']}** from {module['name']} / {category['name']}?\n"
                    f"This also deletes the file and cannot be undone.",
            view=DeleteConfirmView(
                resource,
                on_cancel=partial(delete_pick_resource, module=module, category=category, on_back=on_back),
                on_done=on_back,
            ),
        )

    view = AdminView()
    view = picker(resources, "Choose a resource...", "title", pick_resource, back_to_categories)
    view.add_item(BackButton(back_to_categories, row=1))
    await interaction.edit_original_response(
        content=f"🗑 **{category['name']}**: choose the resource" if resources
        else f"**{category['name']}** has no resources.",
        view=view,
    )

# ---------- manage module / category flow ----------
def make_slug(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or f"item-{secrets.token_hex(2)}"  # e.g. Arabic-only names


class NameModal(discord.ui.Modal):
    def __init__(self, title: str, on_name, default: str = ""):
        super().__init__(title=title)
        self.on_name = on_name
        self.name_input = discord.ui.TextInput(label="Name", max_length=50, default=default or None)
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        await self.on_name(interaction, self.name_input.value.strip())

async def create_module(interaction: discord.Interaction, name: str):
    try:
        await add_module(name, make_slug(name))
    except asyncpg.UniqueViolationError:
        await interaction.response.send_message("⚠️ This module already exists.", ephemeral=True)
        return
    await interaction.response.send_message(
        f"✅ Module **{name}** created. Now add its categories.", ephemeral=True
    )

async def start_add_category(interaction: discord.Interaction, on_back):
    await interaction.response.defer()
    modules = await get_modules()

    async def pick_module(i: discord.Interaction, module: dict):
        async def create_category(i2: discord.Interaction, name: str):
            try:
                await add_category(module["id"], name, make_slug(name))
            except asyncpg.UniqueViolationError:
                await i2.response.send_message("⚠️ This category already exists here.", ephemeral=True)
                return
            await i2.response.send_message(
                f"✅ Category **{name}** added to {module['name']}.", ephemeral=True
            )

        # a modal must be the first response, so no defer here
        await i.response.send_modal(NameModal(f"New category in {module['name']}"[:45], create_category))

    view = AdminView()
    view = picker(modules, "Choose a module...", "name", pick_module, on_back)
    view.add_item(BackButton(on_back, row=1))
    await interaction.edit_original_response(
        content="📂 Choose the module for the new category:" if modules else "No modules yet.",
        view=view,
    )

# ---------- Rename / delete module & category ----------
async def pick_module_screen(interaction, text, on_pick, on_back):
    await interaction.response.defer()
    modules = await get_modules()
    view = AdminView()
    view = picker(modules, "Choose a module...", "name", on_pick, on_back)
    view.add_item(BackButton(on_back, row=1))
    await interaction.edit_original_response(content=text if modules else "No modules yet.", view=view)


async def pick_category_screen(interaction, module, text, on_pick, on_back):
    await interaction.response.defer()
    categories = await get_categories(module["id"])
    view = AdminView()
    view = picker(categories, "Choose a category...", "name", on_pick, on_back)
    view.add_item(BackButton(on_back, row=1))
    await interaction.edit_original_response(
        content=text if categories else f"**{module['name']}** has no categories.", view=view
    )


class ConfirmView(AdminView):
    """action: async callable returning the result message."""
    def __init__(self, action, on_cancel, on_done):
        super().__init__()
        self.action = action
        self.on_cancel = on_cancel
        self.on_done = on_done

    @discord.ui.button(label="Yes, delete", emoji="🗑", style=discord.ButtonStyle.danger, row=0)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        text = await self.action()
        view = AdminView()
        view.add_item(BackButton(self.on_done, row=0))
        await interaction.edit_original_response(content=text, view=view)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=0)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.on_cancel(interaction)


# --- rename module ---
async def start_rename_module(interaction, on_back):
    async def pick(i, module):
        async def save(i2, name):
            await rename_module(module["id"], name)
            await i2.response.send_message(f"✅ **{module['name']}** → **{name}**", ephemeral=True)
        await i.response.send_modal(NameModal("Rename module", save, default=module["name"]))

    await pick_module_screen(interaction, "✏️ Choose the module to rename:", pick, on_back)


# --- rename category ---
async def start_rename_category(interaction, on_back):
    async def pick_module(i, module):
        async def back_to_modules(i2):
            await start_rename_category(i2, on_back)

        async def pick_cat(i2, category):
            async def save(i3, name):
                await rename_category(category["id"], name)
                await i3.response.send_message(f"✅ **{category['name']}** → **{name}**", ephemeral=True)
            await i2.response.send_modal(NameModal("Rename category", save, default=category["name"]))

        await pick_category_screen(i, module, f"✏️ **{module['name']}**: choose the category", pick_cat, back_to_modules)

    await pick_module_screen(interaction, "✏️ Choose the module:", pick_module, on_back)


# --- delete module ---
async def start_delete_module(interaction, on_back):
    async def pick(i, module):
        async def action():
            try:
                ok = await delete_module(module["id"])
            except (asyncpg.RestrictViolationError, asyncpg.ForeignKeyViolationError):
                return f"⛔ **{module['name']}** still has categories. Delete them first."
            return f"✅ Deleted module **{module['name']}**." if ok else "Already deleted."

        async def cancel(i2):
            await start_delete_module(i2, on_back)

        await i.response.edit_message(
            content=f"⚠️ Delete module **{module['name']}**? Only works if it has no categories.",
            view=ConfirmView(action, cancel, on_back),
        )

    await pick_module_screen(interaction, "🗑 Choose the module to delete:", pick, on_back)


# --- delete category ---
async def start_delete_category(interaction, on_back):
    async def pick_module(i, module):
        async def back_to_modules(i2):
            await start_delete_category(i2, on_back)

        async def pick_cat(i2, category):
            async def action():
                try:
                    ok = await delete_category(category["id"])
                except (asyncpg.RestrictViolationError, asyncpg.ForeignKeyViolationError):
                    return f"⛔ **{category['name']}** still has resources. Delete them first."
                return f"✅ Deleted category **{category['name']}**." if ok else "Already deleted."

            async def cancel(i3):
                await start_delete_category(i3, on_back)

            await i2.response.edit_message(
                content=f"⚠️ Delete category **{category['name']}** from {module['name']}? "
                        f"Only works if it has no resources.",
                view=ConfirmView(action, cancel, on_back),
            )

        await pick_category_screen(i, module, f"🗑 **{module['name']}**: choose the category", pick_cat, back_to_modules)

    await pick_module_screen(interaction, "🗑 Choose the module:", pick_module, on_back)

class StructureView(AdminView):
    def __init__(self, on_back):
        super().__init__()
        self.on_back = on_back

    async def to_structure(self, interaction: discord.Interaction):
        await show_structure(interaction, self.on_back)

    @discord.ui.button(label="New module", emoji="🆕", style=discord.ButtonStyle.success, row=0)
    async def new_module(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NameModal("New module", create_module))

    @discord.ui.button(label="New category", emoji="📂", style=discord.ButtonStyle.success, row=0)
    async def new_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_add_category(interaction, on_back=self.to_structure)

    @discord.ui.button(label="Rename module", emoji="✏️", style=discord.ButtonStyle.primary, row=1)
    async def rename_mod(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_rename_module(interaction, on_back=self.to_structure)

    @discord.ui.button(label="Rename category", emoji="✏️", style=discord.ButtonStyle.primary, row=1)
    async def rename_cat(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_rename_category(interaction, on_back=self.to_structure)

    @discord.ui.button(label="Delete module", emoji="🗑", style=discord.ButtonStyle.danger, row=2)
    async def delete_mod(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_delete_module(interaction, on_back=self.to_structure)

    @discord.ui.button(label="Delete category", emoji="🗑", style=discord.ButtonStyle.danger, row=2)
    async def delete_cat(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_delete_category(interaction, on_back=self.to_structure)

    @discord.ui.button(label="🔙 رجوع", style=discord.ButtonStyle.secondary, row=3)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.on_back(interaction)

async def show_structure(interaction: discord.Interaction, on_back):
    await interaction.response.edit_message(
        content="📁 **Modules & categories**", embed=None, view=StructureView(on_back)
    )

# ---------- Quiz questions ----------
LETTERS = "ABCD"


def parse_question_form(options_text: str, correct_text: str, difficulty_text: str):
    options = [line.strip() for line in options_text.splitlines() if line.strip()]
    if not 2 <= len(options) <= 4:
        raise ValueError("Write between 2 and 4 options, one per line.")

    idx = LETTERS.find(correct_text.strip().upper()) if correct_text.strip() else -1
    if idx == -1 or idx >= len(options):
        raise ValueError(f"Correct answer must be a letter between A and {LETTERS[len(options) - 1]}.")

    try:
        difficulty = int(difficulty_text.strip() or 1)
    except ValueError:
        raise ValueError("Difficulty must be a number from 1 to 5.")
    if not 1 <= difficulty <= 5:
        raise ValueError("Difficulty must be a number from 1 to 5.")

    return options, idx, difficulty


class QuestionModal(discord.ui.Modal, title="New quiz question"):
    q_input = discord.ui.TextInput(label="Question", style=discord.TextStyle.paragraph, max_length=400)
    options_input = discord.ui.TextInput(
        label="Options (one per line, 2 to 4)", style=discord.TextStyle.paragraph,
        max_length=400, placeholder="O(n)\nO(log n)\nO(n²)\nO(1)",
    )
    correct_input = discord.ui.TextInput(label="Correct answer (A, B, C or D)", max_length=1)
    difficulty_input = discord.ui.TextInput(label="Difficulty (1 to 5)", max_length=1, default="1")
    explanation_input = discord.ui.TextInput(
        label="Explanation (optional)", style=discord.TextStyle.paragraph,
        required=False, max_length=300,
    )

    def __init__(self, module: dict):
        super().__init__()
        self.module = module

    async def on_submit(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        try:
            options, correct_index, difficulty = parse_question_form(
                self.options_input.value, self.correct_input.value, self.difficulty_input.value
            )
        except ValueError as e:
            await interaction.response.send_message(f"❌ {e} Try again.", ephemeral=True)
            return

        qid = await add_question(
            module_id=self.module["id"],
            question=self.q_input.value.strip(),
            options=options,
            correct_index=correct_index,
            explanation=self.explanation_input.value.strip() or None,
            difficulty=difficulty,
            created_by=interaction.user.id,
        )
        await interaction.response.send_message(
            f"✅ Question #{qid} added to **{self.module['name']}** "
            f"({'⭐' * difficulty}, correct: {LETTERS[correct_index]}).",
            ephemeral=True,
        )


async def start_add_question(interaction: discord.Interaction, on_back):
    await interaction.response.defer()
    modules = await get_modules()

    async def pick(i, module):
        # a modal must be the first response, so no defer here
        await i.response.send_modal(QuestionModal(module))

    view = picker(modules, "Choose a module...", "name", pick, on_back)
    await interaction.edit_original_response(
        content="❓ Choose the module for the new question:" if modules else "No modules yet.",
        view=view,
    )


async def start_delete_question(interaction: discord.Interaction, on_back):
    async def pick_module(i, module):
        await delete_pick_question(i, module, on_back)

    await pick_module_screen(interaction, "🧹 Choose the module:", pick_module, on_back)


async def delete_pick_question(interaction, module, on_back):
    await interaction.response.defer()
    questions = await get_questions(module["id"])

    async def back_to_modules(i):
        await start_delete_question(i, on_back)

    async def pick_question(i, q):
        async def action():
            ok = await delete_question(q["id"])
            return "✅ Question deleted." if ok else "Already deleted."

        async def cancel(i2):
            await delete_pick_question(i2, module, on_back)

        await i.response.edit_message(
            content=f"⚠️ Delete this question?\n**{q['question'][:300]}**\n"
                    f"Scores stay as they are, only its answer history is removed.",
            view=ConfirmView(action, cancel, on_back),
        )

    view = PagedView(
        questions, label_fn=lambda q: f"{'⭐' * q['difficulty']} {q['question']}",
        on_pick=pick_question, placeholder="Choose a question...",
        on_back=back_to_modules, admin_only=True,
    )
    await interaction.edit_original_response(
        content=f"🧹 **{module['name']}**: choose the question" if questions
        else f"**{module['name']}** has no questions.",
        view=view,
    )

# ---------- Import questions from JSON ----------
MAX_IMPORT_BYTES = 500_000
MAX_IMPORT_QUESTIONS = 200


def validate_item(item: dict) -> dict:
    q = str(item.get("question", "")).strip()
    if not q or len(q) > 400:
        raise ValueError("question must be 1 to 400 characters")

    options = item.get("options")
    if not isinstance(options, list) or not 2 <= len(options) <= 4:
        raise ValueError("options must be a list of 2 to 4 items")
    options = [str(o).strip() for o in options]
    if any(not o or len(o) > 100 for o in options):
        raise ValueError("each option must be 1 to 100 characters")
    if len({o.lower() for o in options}) != len(options):
        raise ValueError("two options are identical")

    correct = str(item.get("correct", "")).strip().upper()
    idx = LETTERS.find(correct) if len(correct) == 1 else -1
    if idx == -1 or idx >= len(options):
        raise ValueError("correct must be a letter that matches one option")

    try:
        difficulty = int(item.get("difficulty", 1))
    except (TypeError, ValueError):
        raise ValueError("difficulty must be a number from 1 to 5")
    if not 1 <= difficulty <= 5:
        raise ValueError("difficulty must be a number from 1 to 5")

    explanation = str(item.get("explanation") or "").strip()
    if len(explanation) > 500:
        raise ValueError("explanation is longer than 500 characters")

    return {
        "question": q, "options": options, "correct_index": idx,
        "difficulty": difficulty, "explanation": explanation or None,
    }


def parse_import(raw: bytes) -> tuple[list[dict], list[str]]:
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except UnicodeDecodeError:
        raise ValueError("The file must be UTF-8 text.")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e.msg} (line {e.lineno}, column {e.colno}).")

    if isinstance(data, dict):
        data = data.get("questions")
    if not isinstance(data, list) or not data:
        raise ValueError("Expected a non-empty JSON array of questions.")
    if len(data) > MAX_IMPORT_QUESTIONS:
        raise ValueError(f"Too many questions in one file (max {MAX_IMPORT_QUESTIONS}).")

    clean, errors = [], []
    for n, item in enumerate(data, start=1):
        try:
            if not isinstance(item, dict):
                raise ValueError("must be an object")
            clean.append(validate_item(item))
        except ValueError as e:
            errors.append(f"#{n}: {e}")
    return clean, errors


async def start_import_questions(interaction: discord.Interaction, on_back):
    await interaction.response.defer()
    modules = await get_modules()

    async def pick(i: discord.Interaction, module: dict):
        await i.response.send_message(
            f"📎 Send the **.json** file for **{module['name']}** in this channel (2 minutes).",
            ephemeral=True,
        )

        def check(m: discord.Message):
            return (m.author.id == i.user.id
                    and m.channel.id == i.channel_id
                    and m.attachments)

        try:
            msg = await i.client.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            await i.followup.send("⏰ Cancelled, no file received.", ephemeral=True)
            return

        att = msg.attachments[0]
        error, items, errors = None, [], []
        try:
            if not att.filename.lower().endswith(".json"):
                raise ValueError("The file must be a .json file.")
            if att.size > MAX_IMPORT_BYTES:
                raise ValueError("File too large (500 KB max).")
            items, errors = parse_import(await att.read())
        except ValueError as e:
            error = str(e)
        except discord.HTTPException:
            error = "Could not download the file."

        try:
            await msg.delete()  # needs Manage Messages, optional
        except discord.HTTPException:
            pass

        if error:
            await i.followup.send(f"❌ {error}", ephemeral=True)
            return
        if errors:
            shown = "\n".join(errors[:10])
            more = f"\n…and {len(errors) - 10} more." if len(errors) > 10 else ""
            await i.followup.send(
                f"❌ Nothing imported. Fix these and try again:\n{shown}{more}", ephemeral=True
            )
            return

        inserted, skipped = await add_questions_bulk(module["id"], items, i.user.id)
        text = f"✅ Imported **{inserted}** question(s) into **{module['name']}**."
        if skipped:
            text += f" Skipped {skipped} duplicate(s)."
        await i.followup.send(text, ephemeral=True)

    view = picker(modules, "Choose a module...", "name", pick, on_back)
    await interaction.edit_original_response(
        content="📥 Choose the module to import into:" if modules else "No modules yet.",
        view=view,
    )

# ---------- Panel ----------
class AdminPanel(AdminView):
    def __init__(self, on_back):
        super().__init__()
        self.on_back = on_back

    async def to_panel(self, interaction: discord.Interaction):
        await show_admin_panel(interaction, self.on_back)

    @discord.ui.button(label="Add resource", emoji="➕", style=discord.ButtonStyle.success, row=0)
    async def add_resource_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_add_resource(interaction, on_back=self.to_panel)

    @discord.ui.button(label="Delete resource", emoji="🗑", style=discord.ButtonStyle.danger, row=0)
    async def delete_resource_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_delete(interaction, on_back=self.to_panel)

    @discord.ui.button(label="Manage modules / categories", emoji="📁", style=discord.ButtonStyle.primary, row=1)
    async def add_structure_button(self, interaction: discord.Interaction, button: discord.ui.Button):
       await show_structure(interaction, on_back=self.to_panel)
    @discord.ui.button(label="Add question", emoji="❓", style=discord.ButtonStyle.success, row=2)
    async def add_question_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_add_question(interaction, on_back=self.to_panel)
   
    @discord.ui.button(label="Delete question", emoji="🧹", style=discord.ButtonStyle.danger, row=2)
    async def delete_question_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_delete_question(interaction, on_back=self.to_panel)
    @discord.ui.button(label="Import questions", emoji="📥", style=discord.ButtonStyle.primary, row=2)
    async def import_questions_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_import_questions(interaction, on_back=self.to_panel)

    @discord.ui.button(label="🔙 رجوع", style=discord.ButtonStyle.secondary, row=3)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.on_back(interaction)
    @discord.ui.button(label="🔙 رجوع", style=discord.ButtonStyle.secondary, row=3)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.on_back(interaction)


async def show_admin_panel(interaction: discord.Interaction, on_back):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
        return
    await interaction.response.edit_message(
        content="🛠 **Admin panel**", embed=None, view=AdminPanel(on_back)
    )