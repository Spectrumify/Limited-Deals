"""Background thread that keeps the database up to date."""
import logging
import threading
import time

import data_sources
import db
from config import PRICE_FETCH_RAP_LIMIT, REFRESH_SECONDS

log = logging.getLogger(__name__)


def refresh_once():
    started = time.time()

    items = data_sources.fetch_rolimons_items()
    db.save_rolimons_items(items)

    ids = db.item_ids_with_rap_at_most(PRICE_FETCH_RAP_LIMIT)
    prices = data_sources.fetch_lowest_prices(ids)
    db.save_prices(prices)

    db.set_meta("last_refresh", time.time())
    db.set_meta("last_error", "")
    log.info("Refreshed %d items, %d prices in %.0f s", len(items), len(prices), time.time() - started)


def run_forever():
    while True:
        try:
            refresh_once()
        except Exception as error:
            # Keep serving the cached data; try again next round.
            log.exception("Refresh failed")
            db.set_meta("last_error", f"{type(error).__name__}: {error}")
        time.sleep(REFRESH_SECONDS)


def start():
    thread = threading.Thread(target=run_forever, daemon=True)
    thread.start()
