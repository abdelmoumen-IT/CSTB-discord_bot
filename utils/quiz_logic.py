BASE_GAIN = 10
BASE_LOSS = 5
MAX_DIFFICULTY = 5


def level_from_score(score: int) -> int:
    """Level n starts at 50 * n * (n - 1) points."""
    level = 1
    while score >= 50 * (level + 1) * level:
        level += 1
    return level


def difficulty_for(level: int) -> int:
    return min(level, MAX_DIFFICULTY)


def points_for(level: int, correct: bool) -> int:
    return BASE_GAIN * level if correct else -BASE_LOSS * level

def level_bounds(level: int) -> tuple[int, int]:
    """(score where this level starts, score where the next one starts)"""
    return 50 * level * (level - 1), 50 * (level + 1) * level


def progress_bar(score: int, length: int = 10) -> str:
    low, high = level_bounds(level_from_score(score))
    filled = round((score - low) / (high - low) * length)
    return "▰" * filled + "▱" * (length - filled) + f"  {score - low}/{high - low}"