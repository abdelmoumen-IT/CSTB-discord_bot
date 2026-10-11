import os
from dotenv import load_dotenv

load_dotenv()

ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}
ARCHIVE_CHANNEL_ID = int(os.getenv("ARCHIVE_CHANNEL_ID", "0"))


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS