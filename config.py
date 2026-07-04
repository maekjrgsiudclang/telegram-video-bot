import os

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
MAX_CHUNK_SIZE_MB = 45
QUALITY_PRESETS = {
    "best": None,
    "720p": 720,
    "480p": 480,
    "360p": 360,
}
