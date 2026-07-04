import os

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("TELEGRAM_ADMIN_ID", "0"))
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
MAX_CHUNK_SIZE_MB = 45
