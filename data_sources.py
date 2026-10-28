"""Talks to Rolimons and Roblox.

Every web request goes through HttpClient, which:
  - waits a minimum time between calls to the same host (never hammer)
  - retries with exponential backoff on 429 / 5xx errors
  - honours the Retry-After header when the server sends one
"""
import logging
import random
import time
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) limited-deals-local/0.1"

# Minimum seconds between two requests to the same host.
MIN_SPACING = {
    "api.rolimons.com": 60.0,
    "catalog.roblox.com": 6.0,  # 1.5-3 s triggered 429s; 6 s spreads ~11 batches over a minute
}
DEFAULT_SPACING = 2.0
MAX_RETRIES = 4


class HttpClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.session.headers["Accept"] = "application/json"
        self.last_call = {}   # host -> time of last request
        self.csrf_token = ""  # Roblox wants this on POST requests

    def _wait_for_turn(self, host):
        spacing = MIN_SPACING.get(host, DEFAULT_SPACING)
        elapsed = time.time() - self.last_call.get(host, 0)
        if elapsed < spacing:
            time.sleep(spacing - elapsed)
        self.last_call[host] = time.time()

    def request(self, method, url, **kwargs):
        host = urlparse(url).hostname
        for attempt in range(MAX_RETRIES + 1):
            self._wait_for_turn(host)
            headers = kwargs.pop("headers", {})
            if method == "POST" and host.endswith("roblox.com") and self.csrf_token:
                headers["x-csrf-token"] = self.csrf_token
            response = self.session.request(method, url, headers=headers, timeout=30, **kwargs)

            # Roblox: first POST fails with 403 and hands us a CSRF token. Retry once with it.
            new_token = response.headers.get("x-csrf-token")
            if response.status_code == 403 and new_token and new_token != self.csrf_token:
                self.csrf_token = new_token
                continue

            if response.status_code == 429 or response.status_code >= 500:
                wait = self._backoff_seconds(response, attempt)
                log.warning("%s %s -> HTTP %s, backing off %.0f s", method, host, response.status_code, wait)
                time.sleep(wait)
                continue

            response.raise_for_status()
            return response.json()

        raise RuntimeError(f"Gave up on {host} after {MAX_RETRIES} retries")

    @staticmethod
    def _backoff_seconds(response, attempt):
        # 5 s, 10 s, 20 s, 40 s ... plus a little randomness ("jitter")
        wait = 5 * (2 ** attempt) + random.uniform(0, 2)
        # If the server says how long to wait, wait at least that long.
        retry_after = response.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            wait = max(wait, float(retry_after))
        return wait


client = HttpClient()


# ---------- Rolimons ----------

ROLIMONS_URL = "https://api.rolimons.com/items/v2/itemdetails"

# Rolimons sends each item as a list. These are the positions of each field.
# [name, acronym, rap, value(-1 = not valued), default_value, demand, trend,
#  projected, hyped, rare, limited_version]
DEMAND_NAMES = {-1: "", 0: "Terrible", 1: "Low", 2: "Normal", 3: "High", 4: "Amazing"}
TREND_NAMES = {-1: "", 0: "Lowering", 1: "Unstable", 2: "Stable", 3: "Raising", 4: "Fluctuating"}


def fetch_rolimons_items():
    """Return a list of dicts, one per limited item."""
    data = client.request("GET", ROLIMONS_URL)
    items = []
    for item_id, fields in data["items"].items():
        items.append({
            "id": int(item_id),
            "name": fields[0],
            "acronym": fields[1],
            "rap": fields[2],
            "value": fields[3] if fields[3] != -1 else None,
            "demand": fields[5],
            "trend": fields[6],
            "projected": fields[7] == 1,
            "hyped": fields[8] == 1,
            "rare": fields[9] == 1,
        })
    return items


# ---------- Roblox catalog ----------

CATALOG_DETAILS_URL = "https://catalog.roblox.com/v1/catalog/items/details"
CATALOG_BATCH_SIZE = 120


def fetch_lowest_prices(item_ids):
    """Return {item_id: {"lowest_price", "total_quantity", "collectible_item_id"}}.

    If Roblox keeps rate-limiting us, stop early and return what we have;
    the other items keep their cached prices until the next round.
    """
    results = {}
    for start in range(0, len(item_ids), CATALOG_BATCH_SIZE):
        batch = item_ids[start:start + CATALOG_BATCH_SIZE]
        body = {"items": [{"itemType": "Asset", "id": item_id} for item_id in batch]}
        try:
            data = client.request("POST", CATALOG_DETAILS_URL, json=body)
        except RuntimeError as error:
            log.warning("%s; keeping cached prices for the remaining %d items", error, len(item_ids) - start)
            break
        for entry in data.get("data", []):
            results[entry["id"]] = {
                # Roblox reports "nobody is selling" as 0; store that as no price.
                "lowest_price": entry.get("lowestResalePrice") or None,
                "total_quantity": entry.get("totalQuantity"),
                "collectible_item_id": entry.get("collectibleItemId"),
            }
    return results
