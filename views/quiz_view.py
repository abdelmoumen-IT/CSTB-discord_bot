from functools import partial

import discord

from database.repositories import get_modules
from database.quiz_repository import (
    get_or_create_player, get_next_question, record_answer,
    get_leaderboard, get_player_rank, get_quiz_modules,
)
from utils.quiz_logic import level_from_score, difficulty_for, points_for, progress_bar
from views.common import BackButton, PagedView

LETTERS = "ABCD"
QUESTION_TIMEOUT = 90
MEDALS = ["🥇", "🥈", "🥉"]


# ---------- Leaderboard ----------
async def build_leaderboard_embed(user_id: int | None = None) -> discord.Embed:
    rows = await get_leaderboard(10)
    embed = discord.Embed(title="🏆 CSTB Leaderboard", color=discord.Color.gold())
    if not rows:
        embed.description = "No players yet. Be the first!"
        return embed

    lines = []
    for i, r in enumerate(rows):
        badge = MEDALS[i] if i < 3 else f"`{i + 1}.`"
        name = discord.utils.escape_markdown(r["display_name"])
        lines.append(f"{badge} **{name}** — {r['score']} pts • Lv {level_from_score(r['score'])}")
    embed.description = "\n".join(lines)

    if user_id is not None:
        rank = await get_player_rank(user_id)
        if rank:
            embed.set_footer(text=f"Your rank: #{rank}")
    return embed


async def show_leaderboard(interaction: discord.Interaction, back):
    await interaction.response.defer()
    embed = await build_leaderboard_embed(interaction.user.id)
    view = discord.ui.View(timeout=600)
    view.add_item(BackButton(back, row=0))
    await interaction.edit_original_response(content=None, embed=embed, view=view)


# ---------- Quiz menu ----------
async def show_quiz_menu(interaction: discord.Interaction, on_back):
    await interaction.response.defer()
    user = interaction.user
    player = await get_or_create_player(user.id, user.display_name)
    rank = await get_player_rank(user.id)
    score = player["score"]
    level = level_from_score(score)

    embed = discord.Embed(
        title="💡 Quizzes",
        description="Answer questions, earn points, climb the leaderboard.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Level", value=str(level))
    embed.add_field(name="Score", value=str(score))
    embed.add_field(name="Rank", value=f"#{rank}" if rank else "—")
    embed.add_field(name="Progress to next level", value=progress_bar(score), inline=False)
    embed.set_footer(text=f"Correct: +{points_for(level, True)}  •  Wrong: {points_for(level, False)}")
    await interaction.edit_original_response(content=None, embed=embed, view=QuizMenuView(on_back))


class QuizMenuView(discord.ui.View):
    def __init__(self, on_back):
        super().__init__(timeout=600)
        self.on_back = on_back
        self.menu = partial(show_quiz_menu, on_back=on_back)

    @discord.ui.button(label="Play", emoji="▶️", style=discord.ButtonStyle.success, row=0)
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        await pick_module(interaction, self.menu)

    @discord.ui.button(label="Leaderboard", emoji="🏆", style=discord.ButtonStyle.primary, row=0)
    async def leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_leaderboard(interaction, back=self.menu)

    @discord.ui.button(label="🔙 رجوع", style=discord.ButtonStyle.danger, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.on_back(interaction)


# ---------- Module choice ----------
async def pick_module(interaction: discord.Interaction, menu):
    await interaction.response.defer()
    modules = await get_quiz_modules()

    if not modules:
        view = discord.ui.View(timeout=600)
        view.add_item(BackButton(menu, row=0))
        await interaction.edit_original_response(
            content="No quiz questions yet. Check back soon!", embed=None, view=view
        )
        return

    items = [{"id": m["id"], "name": f"{m['name']} ({m['questions']})"} for m in modules]
    if len(modules) > 1:  # "Mixed" only makes sense with 2+ modules
        items.insert(0, {"id": 0, "name": "🎲 Mixed (all modules)"})

    async def on_pick(i: discord.Interaction, item: dict):
        await send_question(i, item["id"] or None, menu)

    view = PagedView(
        items, label_fn=lambda m: m["name"], on_pick=on_pick,
        placeholder="Choose a module...", on_back=menu,
    )
    await interaction.edit_original_response(
        content="💡 What do you want to practice?", embed=None, view=view
    )


# ---------- Question ----------
async def send_question(interaction: discord.Interaction, module_id: int | None, menu):
    await interaction.response.defer()
    user = interaction.user
    player = await get_or_create_player(user.id, user.display_name)
    level = level_from_score(player["score"])
    question = await get_next_question(user.id, difficulty_for(level), module_id)

    if question is None:
        view = discord.ui.View(timeout=600)
        view.add_item(BackButton(menu, row=0))
        await interaction.edit_original_response(
            content="🎉 No more questions here for now. Try another module or come back later.",
            embed=None, view=view,
        )
        return

    view = QuestionView(question, user.id, module_id, menu, level, player["score"], interaction)
    await interaction.edit_original_response(content=None, embed=view.question_embed(), view=view)


class AnswerButton(discord.ui.Button):
    def __init__(self, index: int):
        super().__init__(label=LETTERS[index], style=discord.ButtonStyle.primary, row=0)
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        await self.view.answer(interaction, self.index)


class QuestionView(discord.ui.View):
    def __init__(self, question, author_id, module_id, menu, level, score, origin):
        super().__init__(timeout=QUESTION_TIMEOUT)
        self.question = question
        self.author_id = author_id
        self.module_id = module_id
        self.menu = menu
        self.level = level
        self.score = score
        self.origin = origin
        self.answered = False
        for i in range(len(question["options"])):
            self.add_item(AnswerButton(i))

    def question_embed(self) -> discord.Embed:
        q = self.question
        options = "\n".join(f"**{LETTERS[i]}.** {text}" for i, text in enumerate(q["options"]))
        embed = discord.Embed(
            title=f"Level {self.level}  •  {'⭐' * q['difficulty']}",
            description=f"**{q['question']}**\n\n{options}",
            color=discord.Color.blurple(),
        )
        embed.set_footer(
            text=f"✅ +{points_for(self.level, True)}   ❌ {points_for(self.level, False)}   •   {self.score} pts"
        )
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This question isn't yours.", ephemeral=True)
            return False
        return True

    async def answer(self, interaction: discord.Interaction, index: int):
        if self.answered:
            await interaction.response.send_message("Already answered.", ephemeral=True)
            return
        self.answered = True  # set before any await: blocks double clicks
        await interaction.response.defer()

        try:
            result = await record_answer(interaction.user.id, self.question["id"], index)
        except Exception:
            self.answered = False
            await interaction.followup.send("⚠️ Something went wrong, try again.", ephemeral=True)
            raise
        self.stop()

        await interaction.edit_original_response(
            content=None,
            embed=result_embed(self.question, index, result),
            view=NextView(self.module_id, self.menu),
        )

    @discord.ui.button(label="🔙 رجوع", style=discord.ButtonStyle.danger, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.answered = True
        self.stop()  # otherwise on_timeout would overwrite the menu later
        await self.menu(interaction)

    async def on_timeout(self):
        if self.answered:
            return
        try:
            await self.origin.edit_original_response(
                content="⏰ Time's up, no points changed.",
                embed=self.question_embed(),
                view=NextView(self.module_id, self.menu),
            )
        except discord.HTTPException:
            pass


def result_embed(question: dict, chosen: int, r: dict | None) -> discord.Embed:
    options = question["options"]
    if r is None:
        return discord.Embed(description="⚠️ This question no longer exists.", color=discord.Color.orange())
    if r.get("already_answered"):
        return discord.Embed(
            description="ℹ️ You already answered this one correctly, no points this time.",
            color=discord.Color.orange(),
        )

    ok = r["is_correct"]
    embed = discord.Embed(
        title="✅ Correct!" if ok else "❌ Wrong",
        description=f"**{question['question']}**",
        color=discord.Color.green() if ok else discord.Color.red(),
    )
    embed.add_field(name="Your answer", value=f"{LETTERS[chosen]}. {options[chosen]}", inline=False)
    if not ok:
        c = r["correct_index"]
        embed.add_field(name="Correct answer", value=f"{LETTERS[c]}. {options[c]}", inline=False)
    if r["explanation"]:
        embed.add_field(name="💡 Explanation", value=r["explanation"], inline=False)

    sign = "+" if r["points"] >= 0 else ""
    embed.add_field(name="Points", value=f"{sign}{r['points']}")
    embed.add_field(name="Score", value=str(r["new_score"]))
    embed.add_field(name="Level", value=str(r["new_level"]))

    if r["new_level"] > r["old_level"]:
        embed.description += f"\n\n🎉 **Level up!** You reached level {r['new_level']}."
    elif r["new_level"] < r["old_level"]:
        embed.description += f"\n\n⬇️ Level down to {r['new_level']}. Keep going!"

    embed.set_footer(text=progress_bar(r["new_score"]))
    return embed


class NextView(discord.ui.View):
    def __init__(self, module_id, menu):
        super().__init__(timeout=600)
        self.module_id = module_id
        self.menu = menu

    @discord.ui.button(label="Next", emoji="➡️", style=discord.ButtonStyle.success, row=0)
    async def next_question(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_question(interaction, self.module_id, self.menu)

    @discord.ui.button(label="Leaderboard", emoji="🏆", style=discord.ButtonStyle.primary, row=0)
    async def leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_leaderboard(interaction, back=self.menu)

    @discord.ui.button(label="🔙 رجوع", style=discord.ButtonStyle.danger, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.menu(interaction)