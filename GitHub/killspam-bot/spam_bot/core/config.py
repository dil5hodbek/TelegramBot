import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_TELEGRAM_IDS = [x.strip() for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip()]
KEY_ENCRYPTION_SECRET = os.getenv("KEY_ENCRYPTION_SECRET")
BASE_URL = os.getenv("BASE_URL")
PORT = int(os.getenv("PORT", "8080"))

# Gemini pricing ($ per 1M tokens) for cost estimates in /tokens + the daily report.
# Defaults are gemini-2.5-flash public rates; override per environment if they change.
GEMINI_PRICE_IN = float(os.getenv("GEMINI_PRICE_IN", "0.30"))
GEMINI_PRICE_OUT = float(os.getenv("GEMINI_PRICE_OUT", "2.50"))
# Local hour (Asia/Tashkent, UTC+5, no DST) to DM the daily usage report.
REPORT_HOUR = int(os.getenv("REPORT_HOUR", "9"))
# Abuse guard: max groups one non-operator admin may /enable. Operators are exempt.
MAX_GROUPS_PER_OWNER = int(os.getenv("MAX_GROUPS_PER_OWNER", "20"))