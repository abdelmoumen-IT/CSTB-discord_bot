from database.connection import get_pool
from utils.quiz_logic import level_from_score, points_for


async def get_or_create_player(user_id: int, display_name: str) -> dict:
    row = await get_pool().fetchrow(
        """
        INSERT INTO quiz_players (user_id, display_name)
        VALUES ($1, $2)
        ON CONFLICT (user_id) DO UPDATE SET display_name = EXCLUDED.display_name
        RETURNING user_id, display_name, score, answered, correct
        """,
        user_id, display_name,
    )
    return dict(row)


async def get_next_question(user_id: int, difficulty: int, module_id: int | None = None) -> dict | None:
    """Prefer the exact difficulty, fall back to easier ones.
    Skips questions this user already answered correctly."""
    row = await get_pool().fetchrow(
        """
        SELECT q.id, q.module_id, q.question, q.options, q.explanation, q.difficulty
        FROM quiz_questions q
        WHERE q.is_active
          AND q.difficulty <= $2
          AND ($3::bigint IS NULL OR q.module_id = $3)
          AND NOT EXISTS (
              SELECT 1 FROM quiz_answers a
              WHERE a.user_id = $1 AND a.question_id = q.id AND a.is_correct
          )
        ORDER BY (q.difficulty = $2) DESC, random()
        LIMIT 1
        """,
        user_id, difficulty, module_id,
    )
    return dict(row) if row else None


async def record_answer(user_id: int, question_id: int, chosen_index: int) -> dict | None:
    """Check the answer and update the score in ONE transaction.
    The correct index is read from the DB, never trusted from the client."""
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            q = await conn.fetchrow(
                "SELECT correct_index, explanation FROM quiz_questions WHERE id = $1",
                question_id,
            )
            if q is None:
                return None

            # FOR UPDATE: two fast clicks can't both read the same old score
            player = await conn.fetchrow(
                "SELECT score FROM quiz_players WHERE user_id = $1 FOR UPDATE", user_id
            )
            if player is None:
                raise RuntimeError("Player not found. Call get_or_create_player first.")

            already = await conn.fetchval(
                """
                SELECT 1 FROM quiz_answers
                WHERE user_id = $1 AND question_id = $2 AND is_correct
                LIMIT 1
                """,
                user_id, question_id,
            )
            if already:
                return {"already_answered": True}

            old_score = player["score"]
            old_level = level_from_score(old_score)
            is_correct = chosen_index == q["correct_index"]
            new_score = max(0, old_score + points_for(old_level, is_correct))
            applied = new_score - old_score  # real change (the 0 floor may reduce a loss)

            await conn.execute(
                """
                UPDATE quiz_players
                SET score = $2, answered = answered + 1, correct = correct + $3, updated_at = now()
                WHERE user_id = $1
                """,
                user_id, new_score, 1 if is_correct else 0,
            )
            await conn.execute(
                """
                INSERT INTO quiz_answers (user_id, question_id, is_correct, points, level)
                VALUES ($1, $2, $3, $4, $5)
                """,
                user_id, question_id, is_correct, applied, old_level,
            )

    return {
        "is_correct": is_correct,
        "correct_index": q["correct_index"],
        "explanation": q["explanation"],
        "points": applied,
        "new_score": new_score,
        "old_level": old_level,
        "new_level": level_from_score(new_score),
    }


async def get_leaderboard(limit: int = 10) -> list[dict]:
    rows = await get_pool().fetch(
        """
        SELECT user_id, display_name, score, correct, answered
        FROM quiz_players
        ORDER BY score DESC, correct DESC, user_id
        LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]


async def get_player_rank(user_id: int) -> int | None:
    return await get_pool().fetchval(
        """
        SELECT rank FROM (
            SELECT user_id, RANK() OVER (ORDER BY score DESC) AS rank FROM quiz_players
        ) t WHERE user_id = $1
        """,
        user_id,
    )

async def get_quiz_modules() -> list[dict]:
    """Only modules that have at least one active question."""
    rows = await get_pool().fetch(
        """
        SELECT m.id, m.name, COUNT(q.id) AS questions
        FROM modules m
        JOIN quiz_questions q ON q.module_id = m.id AND q.is_active
        GROUP BY m.id, m.name, m.position
        ORDER BY m.position, m.name
        """
    )
    return [dict(r) for r in rows]


async def add_question(module_id: int, question: str, options: list[str],
                       correct_index: int, explanation: str | None,
                       difficulty: int, created_by: int) -> int:
    return await get_pool().fetchval(
        """
        INSERT INTO quiz_questions
            (module_id, question, options, correct_index, explanation, difficulty, created_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
        """,
        module_id, question, options, correct_index, explanation, difficulty, created_by,
    )


async def get_questions(module_id: int) -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT id, question, difficulty FROM quiz_questions WHERE module_id = $1 ORDER BY difficulty, id",
        module_id,
    )
    return [dict(r) for r in rows]


async def delete_question(question_id: int) -> bool:
    row = await get_pool().fetchval(
        "DELETE FROM quiz_questions WHERE id = $1 RETURNING id", question_id
    )
    return row is not None

async def add_questions_bulk(module_id: int, items: list[dict], created_by: int) -> tuple[int, int]:
    """All-or-nothing. Returns (inserted, skipped_duplicates)."""
    inserted = skipped = 0
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            for it in items:
                row = await conn.fetchval(
                    """
                    INSERT INTO quiz_questions
                        (module_id, question, options, correct_index, explanation, difficulty, created_by)
                    SELECT $1::bigint, $2::text, $3::text[], $4::smallint, $5::text, $6::smallint, $7::bigint
                    WHERE NOT EXISTS (
                        SELECT 1 FROM quiz_questions WHERE module_id = $1::bigint AND question = $2::text
                    )
                    RETURNING id
                    """,
                    module_id, it["question"], it["options"], it["correct_index"],
                    it["explanation"], it["difficulty"], created_by,
                )
                if row is None:
                    skipped += 1
                else:
                    inserted += 1
    return inserted, skipped