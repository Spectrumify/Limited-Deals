"""Settings loaded from .env (with safe defaults)."""
import os

from dotenv import load_dotenv

load_dotenv()

BUDGET = int(os.getenv("BUDGET", "5000"))

# We only fetch live prices for items whose RAP is at most this much,
# so we don't waste Roblox API calls on items we could never afford.
PRICE_FETCH_RAP_LIMIT = int(BUDGET * 1.5)

# How often the background refresher runs (seconds).
# Rolimons caches for 60 s, so anything faster is pointless.
REFRESH_SECONDS = 120

DB_PATH = os.path.join(os.path.dirname(__file__), "limited_deals.db")
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
