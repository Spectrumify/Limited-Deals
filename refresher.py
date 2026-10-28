"""Background thread that keeps the database up to date."""
import logging
import threading
import time

import data_sources
import db
import deals
from config import PRICE_FETCH_RAP_LIMIT, REFRESH_SECONDS

log = logging.getLogger(__name__)


def refresh_once():
    started = time.time()

    items = data_sources.fetch_rolimons_items()
    db.save_rolimons_items(items)

    ids = db.item_ids_with_rap_at_most(PRICE_FETCH_RAP_LIMIT)
    prices = data_sources.fetch_lowest_prices(ids)
    db.save_prices(prices)

    # Our own trend/projection signals only change when a new snapshot is saved (every 30 min).
    if db.record_history() > 0:
        update_signals()

    db.set_meta("last_refresh", time.time())
    db.set_meta("last_error", "")
    log.info("Refreshed %d items, %d prices in %.0f s", len(items), len(prices), time.time() - started)


def update_signals():
    now = time.time()
    ratio = db.get_settings(deals.DEFAULT_SETTINGS)["projection_ratio"]
    current = {item["id"]: item for item in db.all_items()}
    signals = {}
    for item_id, history in db.history_by_item(since=now - 7 * deals.DAY).items():
        item = current.get(item_id)
        if not item:
            continue
        rap_change, price_change = deals.own_trend_pct(history)
        signals[item_id] = {
            "rap_change_pct": rap_change,
            "price_change_pct": price_change,
            "own_projected": deals.suspected_projection(history, item["rap"], item["lowest_price"], ratio, now),
            "history_days": round(deals.history_days(history), 2),
        }
    db.save_signals(signals)
    log.info("Updated trend signals for %d items", len(signals))


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
