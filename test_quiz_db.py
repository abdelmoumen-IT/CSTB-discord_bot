import asyncio
from dotenv import load_dotenv
load_dotenv()

from database.connection import init_pool, close_pool
from database.quiz_repository import (
    get_or_create_player, get_next_question, record_answer,
    get_leaderboard, get_player_rank,
)
from utils.quiz_logic import level_from_score, difficulty_for

UID = 1  # fake user id for testing


async def main():
    await init_pool()
    player = await get_or_create_player(UID, "tester")
    level = level_from_score(player["score"])

    q1 = await get_next_question(UID, difficulty_for(level))
    print("Q1:", q1["question"], q1["options"])
    print("correct ->", await record_answer(UID, q1["id"], 99 if False else await _correct(q1)))

    q2 = await get_next_question(UID, difficulty_for(level))
    print("Q2:", q2["question"])
    print("wrong ->", await record_answer(UID, q2["id"], await _wrong(q2)))

    print(await get_leaderboard())
    print("rank:", await get_player_rank(UID))
    await close_pool()


async def _correct(q):
    from database.connection import get_pool
    return await get_pool().fetchval("SELECT correct_index FROM quiz_questions WHERE id=$1", q["id"])


async def _wrong(q):
    c = await _correct(q)
    return (c + 1) % len(q["options"])


asyncio.run(main())