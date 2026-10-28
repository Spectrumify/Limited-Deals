"""Hourly data refresh, run by GitHub Actions (also works locally: python refresh_job.py).

1. Fetch Rolimons values + Roblox lowest prices (same rate limits as the local app).
2. Check the data looks sane. If not, write NOTHING and exit quietly.
3. Save docs/data/items.json for the GitHub Pages dashboard and append price history.
4. Post new deals matching docs/alerts.json to Discord (webhook comes from an env var / GitHub secret).
"""
import argparse
import csv
import io
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

import data_sources
import deals

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "docs", "data")
HISTORY_DIR = os.path.join(DATA_DIR, "history")
ITEMS_FILE = os.path.join(DATA_DIR, "items.json")
ALERTED_FILE = os.path.join(DATA_DIR, "alerted.json")
CONFIG_FILE = os.path.join(ROOT, "docs", "alerts.json")

MIN_ROLIMONS_ITEMS = 1000      # Rolimons normally lists ~2,580; far fewer means something broke
MIN_FRESH_PRICE_SHARE = 0.5    # need fresh prices for at least half the items, or skip the run
HISTORY_KEEP_DAYS = 30
ALERT_MEMORY_DAYS = 7
DISCORD_MAX_EMBEDS = 10        # Discord's limit per message

log = logging.getLogger("refresh_job")


class SkipRun(Exception):
    """A source is down or the data looks broken: write nothing this run."""


# ---------- Small file helpers ----------

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_text_safely(path, text):
    """Write to a temp file, then swap it in, so a crash never leaves a half-written file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def write_json(path, data):
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    json.loads(text)  # make sure it reads back before replacing the old file
    write_text_safely(path, text)


# ---------- Fetching ----------

def fetch_items(budget, previous_items, now):
    try:
        rolimons = data_sources.fetch_rolimons_items()
    except Exception as error:
        raise SkipRun(f"Rolimons unavailable ({type(error).__name__}: {str(error)[:200]})")
    if len(rolimons) < MIN_ROLIMONS_ITEMS:
        raise SkipRun(f"Rolimons returned only {len(rolimons)} items")

    rap_limit = int(budget * 1.5)
    candidates = [item for item in rolimons if item["rap"] is not None and item["rap"] <= rap_limit]
    prices = data_sources.fetch_lowest_prices([item["id"] for item in candidates])
    if len(prices) < MIN_FRESH_PRICE_SHARE * len(candidates):
        raise SkipRun(f"Roblox prices only loaded for {len(prices)} of {len(candidates)} items")

    previous = {item["id"]: item for item in previous_items}
    for item in candidates:
        fresh = prices.get(item["id"])
        if fresh is not None:
            item.update(lowest_price=fresh["lowest_price"], total_quantity=fresh["total_quantity"],
                        price_updated_at=int(now), stale=False)
        else:
            # Not refreshed this time: keep the old price, but mark it so it can't be a "deal".
            old = previous.get(item["id"], {})
            item.update(lowest_price=old.get("lowest_price"), total_quantity=old.get("total_quantity"),
                        price_updated_at=old.get("price_updated_at"), stale=True)
    return candidates


# ---------- History (one CSV per UTC day) ----------

def history_path(day):
    return os.path.join(HISTORY_DIR, f"{day:%Y-%m-%d}.csv")


def append_history(items, now):
    path = history_path(datetime.fromtimestamp(now, timezone.utc))
    try:
        with open(path, encoding="utf-8", newline="") as f:
            existing = f.read()
    except FileNotFoundError:
        existing = "item_id,ts,rap,lowest_price\n"
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    for item in items:
        if not item["stale"] and item["lowest_price"]:
            writer.writerow([item["id"], int(now), item["rap"], item["lowest_price"]])
    write_text_safely(path, existing + out.getvalue())


def prune_history(now):
    cutoff = datetime.fromtimestamp(now, timezone.utc).date() - timedelta(days=HISTORY_KEEP_DAYS)
    for name in os.listdir(HISTORY_DIR):
        try:
            day = datetime.strptime(name, "%Y-%m-%d.csv").date()
        except ValueError:
            continue
        if day < cutoff:
            os.remove(os.path.join(HISTORY_DIR, name))


def load_history(since):
    """{item_id: [(ts, rap, lowest_price), ...]} oldest first, from the daily CSVs."""
    history = {}
    if not os.path.isdir(HISTORY_DIR):
        return history
    first_day = datetime.fromtimestamp(since, timezone.utc).date()
    for name in sorted(os.listdir(HISTORY_DIR)):
        try:
            day = datetime.strptime(name, "%Y-%m-%d.csv").date()
        except ValueError:
            continue
        if day < first_day:
            continue
        with open(os.path.join(HISTORY_DIR, name), encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                ts = float(row["ts"])
                if ts >= since:
                    history.setdefault(int(row["item_id"]), []).append(
                        (ts, int(row["rap"]), int(row["lowest_price"])))
    for snapshots in history.values():
        snapshots.sort()
    return history


# ---------- Signals, deals, suggestions ----------

def add_signals(items, settings, now):
    history = load_history(since=now - 7 * deals.DAY)
    for item in items:
        snapshots = history.get(item["id"], [])
        rap_change, price_change = deals.own_trend_pct(snapshots)
        item["rap_change_pct"] = None if rap_change is None else round(rap_change, 1)
        item["price_change_pct"] = None if price_change is None else round(price_change, 1)
        item["own_projected"] = deals.suspected_projection(
            snapshots, item["rap"], item["lowest_price"], settings["projection_ratio"], now)
        item["history_days"] = round(deals.history_days(snapshots), 2) if snapshots else None


def evaluate_all(items, settings, budget):
    for item in items:
        item["demand_name"] = data_sources.DEMAND_NAMES.get(item["demand"], "")
        item["trend_name"] = data_sources.TREND_NAMES.get(item["trend"], "")
        item.update(deals.evaluate(item, settings))
        if item["stale"]:
            item["is_deal"] = False  # an old price may already be sold
        item.update(suggestion=None, suggestion_rank=None, drop_needed_pct=None)

    by_id = {item["id"]: item for item in items}
    lists = deals.suggestions([i for i in items if not i["stale"]], budget, limit=None)
    for list_name, entries in lists.items():
        for rank, entry in enumerate(entries):
            item = by_id[entry["id"]]
            item["suggestion"] = list_name
            item["suggestion_rank"] = rank
            item["drop_needed_pct"] = entry.get("drop_needed_pct")


# ---------- Discord ----------

def post_to_discord(webhook_url, payload):
    """Returns True on success. Never logs the webhook URL (it's a secret)."""
    for attempt in range(2):
        try:
            response = requests.post(webhook_url, json=payload, timeout=15)
        except requests.RequestException as error:
            log.warning("Discord post failed (%s)", type(error).__name__)  # no message: it can contain the URL
            return False
        if response.status_code == 429 and attempt == 0:
            try:
                wait = float(response.json().get("retry_after", 2))
            except (ValueError, AttributeError):
                wait = 2
            time.sleep(min(wait, 30))
            continue
        if response.status_code >= 300:
            log.warning("Discord post failed (HTTP %s)", response.status_code)
            return False
        return True
    return False


def deal_embed(item):
    return {
        "title": item["name"][:250],
        "url": f"https://www.roblox.com/catalog/{item['id']}",
        "color": 0x16A34A,
        "description": (
            f"**{item['lowest_price']:,} R$**, {item['discount_pct']}% below {item['target_source']} "
            f"({item['target']:,})\n~**{item['profit']:,} R$** profit after fee"
        ),
    }


def send_discord_alerts(items, filters_by_name, alerted, now, webhook_url):
    """Post deals that match any saved filter and weren't posted before. Returns the updated alerted dict."""
    new_deals = [
        item for item in items
        if item["is_deal"]
        and any(deals.passes_filters(item, f) for f in filters_by_name.values())
        and f"{item['id']}:{item['lowest_price']}" not in alerted
    ]
    if not new_deals:
        log.info("No new deals for Discord")
        return alerted
    if not webhook_url:
        log.info("%d new deal(s), but DISCORD_WEBHOOK_URL is not set; skipping Discord", len(new_deals))
        return alerted

    new_deals.sort(key=lambda i: -i["profit"])
    shown = new_deals[:DISCORD_MAX_EMBEDS]
    payload = {
        "content": f"💰 {len(new_deals)} new deal(s)" + (f" (top {len(shown)} shown)" if len(new_deals) > len(shown) else ""),
        "embeds": [deal_embed(item) for item in shown],
        "allowed_mentions": {"parse": []},
    }
    if post_to_discord(webhook_url, payload):
        log.info("Posted %d deal(s) to Discord", len(shown))
        alerted = dict(alerted)
        for item in new_deals:
            alerted[f"{item['id']}:{item['lowest_price']}"] = int(now)
    return alerted  # on failure, they stay un-alerted and are retried next run


# ---------- Main ----------

KEEP_FIELDS = [
    "id", "name", "acronym", "rap", "value", "demand", "trend", "demand_name", "trend_name",
    "projected", "hyped", "rare", "lowest_price", "total_quantity", "stale", "price_updated_at",
    "target", "target_source", "discount_pct", "profit", "is_deal", "projected_warning",
    "projected_reason", "rising", "buy_below", "rap_change_pct", "price_change_pct", "history_days",
    "suggestion", "suggestion_rank", "drop_needed_pct",
]


def run(discord_test=False):
    now = time.time()
    config = load_json(CONFIG_FILE, {})
    budget = config.get("budget", 5000)
    settings = {**deals.DEFAULT_SETTINGS, **config.get("deal_settings", {})}
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

    if discord_test:
        if not webhook_url:
            log.warning("Discord test requested, but DISCORD_WEBHOOK_URL is not set")
        elif post_to_discord(webhook_url, {"content": "✅ Limited Deals test message: Discord alerts are connected.",
                                           "allowed_mentions": {"parse": []}}):
            log.info("Discord test message sent")

    previous = load_json(ITEMS_FILE, {}).get("items", [])
    items = fetch_items(budget, previous, now)  # raises SkipRun before anything is written

    os.makedirs(HISTORY_DIR, exist_ok=True)
    append_history(items, now)
    prune_history(now)
    add_signals(items, settings, now)
    evaluate_all(items, settings, budget)

    alerted = load_json(ALERTED_FILE, {})
    alerted = {key: ts for key, ts in alerted.items() if ts > now - ALERT_MEMORY_DAYS * deals.DAY}
    alerted = send_discord_alerts(items, config.get("discord_filters", {}), alerted, now, webhook_url)

    priced = [i for i in items if i["lowest_price"]]
    write_json(ITEMS_FILE, {
        "generated_at": int(now),
        "budget": budget,
        "settings": settings,
        "counts": {
            "items": len(items),
            "priced": len(priced),
            "stale": sum(i["stale"] for i in items),
            "deals": sum(i["is_deal"] for i in items),
        },
        "items": [{key: item.get(key) for key in KEEP_FIELDS} for item in priced],
    })
    write_json(ALERTED_FILE, alerted)
    log.info("Saved %d items (%d stale, %d deals)", len(priced),
             sum(i["stale"] for i in priced), sum(i["is_deal"] for i in priced))


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser()
    parser.add_argument("--discord-test", action="store_true", help="also send a Discord test message")
    args = parser.parse_args()
    discord_test = args.discord_test or os.environ.get("DISCORD_TEST", "").lower() == "true"
    try:
        run(discord_test)
    except SkipRun as reason:
        # Not a crash: nothing was written, so the workflow has nothing to commit.
        print(f"::warning::Skipped this run, no data written: {reason}")
        log.warning("Skipped: %s", reason)


if __name__ == "__main__":
    main()
