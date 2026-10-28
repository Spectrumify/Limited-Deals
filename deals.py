"""Deal and projection logic. Pure functions (no web, no database) so they are easy to test."""
import math
from statistics import median

DAY = 24 * 60 * 60

DEFAULT_SETTINGS = {
    "min_discount_pct": 35,   # listing must be at least this % below value/RAP
    "min_profit": 200,        # ...AND resell profit after fee must be at least this many R$
    "seller_keep_pct": 70,    # % of the sale price the seller receives (Roblox takes 30% on classic limiteds)
    "projection_ratio": 1.3,  # RAP jumped 30%+ but listings didn't follow -> suspected projection
    "rising_pct": 10,         # RAP and listings both up 10%+ over the history window -> rising
}


# ---------- Profit ----------

def resale_target(item):
    """What we expect to sell for: the Rolimons value if it has one, otherwise RAP."""
    return item["value"] or item["rap"] or 0


def expected_profit(buy_price, target, seller_keep_pct):
    """Robux left after reselling at `target` and paying the marketplace fee."""
    return math.floor(target * seller_keep_pct / 100) - buy_price


def buy_below_price(target, settings):
    """Highest price at which this item would count as a deal under the current thresholds.

    Both rules must hold:
      price <= target * (1 - min_discount_pct / 100)              (far enough below)
      price <= floor(target * seller_keep_pct / 100) - min_profit  (enough profit after fee)
    """
    if not target:
        return None
    by_discount = target * (1 - settings["min_discount_pct"] / 100)
    by_profit = math.floor(target * settings["seller_keep_pct"] / 100) - settings["min_profit"]
    price = math.floor(min(by_discount, by_profit))
    return price if price > 0 else None


def discount_pct(buy_price, target):
    """How far below the target the price is, in % (negative = above target)."""
    if not target:
        return 0.0
    return (target - buy_price) / target * 100


# ---------- Our own signals from saved history ----------
# history = list of (timestamp, rap, lowest_price) tuples, oldest first.

def history_days(history):
    if len(history) < 2:
        return 0.0
    return (history[-1][0] - history[0][0]) / DAY


def _medians(snapshots):
    raps = [rap for _, rap, _ in snapshots if rap]
    prices = [price for _, _, price in snapshots if price]
    return (median(raps) if raps else None, median(prices) if prices else None)


def suspected_projection(history, rap_now, price_now, ratio, now):
    """RAP jumped well above its level from over a day ago, but listings stayed low.

    A real price rise moves listings up too. A projection is usually one or two
    inflated sales pulling RAP up while sellers still list at the old price.
    """
    older = [snap for snap in history if snap[0] <= now - DAY]
    if len(older) < 6 or not rap_now or not price_now:
        return False
    old_rap, old_price = _medians(older)
    if not old_rap or not old_price:
        return False
    rap_jumped = rap_now >= old_rap * ratio
    price_followed = price_now >= old_price * ratio
    return rap_jumped and not price_followed


def own_trend_pct(history, min_days=3):
    """% change of RAP between the first and last day of history.

    Returns (rap_change_pct, price_change_pct), or (None, None) when there isn't
    at least `min_days` of history yet.
    """
    if history_days(history) < min_days:
        return None, None
    start, end = history[0][0], history[-1][0]
    first_rap, first_price = _medians([s for s in history if s[0] <= start + DAY])
    last_rap, last_price = _medians([s for s in history if s[0] >= end - DAY])
    if not (first_rap and last_rap and first_price and last_price):
        return None, None
    return (last_rap - first_rap) / first_rap * 100, (last_price - first_price) / first_price * 100


# ---------- Putting it together ----------

def evaluate(item, settings):
    """Return the extra fields the dashboard shows for one item."""
    price = item["lowest_price"]
    target = resale_target(item)

    projected = bool(item["projected"]) or bool(item.get("own_projected"))
    projected_reason = []
    if item["projected"]:
        projected_reason.append("Rolimons flag")
    if item.get("own_projected"):
        projected_reason.append("RAP jumped but listings didn't")

    rolimons_rising = item["trend"] == 3 and item["demand"] >= 2
    rap_change = item.get("rap_change_pct")
    price_change = item.get("price_change_pct")
    own_rising = (
        rap_change is not None and price_change is not None
        and rap_change >= settings["rising_pct"] and price_change >= 0
    )
    rising = (rolimons_rising or own_rising) and not projected

    result = {
        "target": target,
        "target_source": "value" if item["value"] else "RAP",
        "discount_pct": None,
        "profit": None,
        "is_deal": False,
        "projected_warning": projected,
        "projected_reason": ", ".join(projected_reason),
        "rising": rising,
        "buy_below": buy_below_price(target, settings),
    }
    if price and target:
        exact_discount = discount_pct(price, target)
        result["discount_pct"] = round(exact_discount, 1)  # rounded for display only
        result["profit"] = expected_profit(price, target, settings["seller_keep_pct"])
        result["is_deal"] = (
            not projected  # a "discount" against an inflated RAP is not a real discount
            and exact_discount >= settings["min_discount_pct"]
            and result["profit"] >= settings["min_profit"]
        )
    return result


# ---------- Filters (same rules as passesFilters in the dashboard's app.js) ----------

def passes_filters(item, f):
    price = item.get("lowest_price")
    if price is None:
        return False
    if f.get("min_price") is not None and price < f["min_price"]:
        return False
    if f.get("max_price") is not None and price > f["max_price"]:
        return False
    if f.get("min_demand") is not None and item["demand"] < f["min_demand"]:
        return False
    if f.get("trends") and item["trend"] not in f["trends"]:
        return False
    if f.get("max_copies") is not None and (item.get("total_quantity") is None or item["total_quantity"] > f["max_copies"]):
        return False
    if f.get("rare_only") and not item["rare"]:
        return False
    if f.get("hide_projected") and item["projected_warning"]:
        return False
    if f.get("deals_only") and not item["is_deal"]:
        return False
    if f.get("rising_only") and not item["rising"]:
        return False
    return True


# ---------- Suggestions (read-only: you buy manually on roblox.com) ----------

def suggestions(items, budget, limit=8):
    """Pick items worth a look. `items` must already include the fields from evaluate().

    Returns {"deals": [...], "rising": [...], "watch": [...]}. Projected items
    and anything above the budget are always left out. limit=None returns every match.
    """
    candidates = [
        item for item in items
        if item["lowest_price"] and item["lowest_price"] <= budget and not item["projected_warning"]
    ]

    deals = sorted((i for i in candidates if i["is_deal"]), key=lambda i: -i["profit"])

    rising = sorted(
        (i for i in candidates if i["rising"] and not i["is_deal"]),
        key=lambda i: -(i.get("rap_change_pct") or 0),
    )

    # Watch list: not a deal yet, but the cheapest listing is closest to the buy-below price.
    # gap = how many % the price would have to drop to become a deal.
    watch = []
    for item in candidates:
        if item["is_deal"] or item["rising"] or not item["buy_below"]:
            continue
        gap = (item["lowest_price"] - item["buy_below"]) / item["lowest_price"] * 100
        watch.append({**item, "drop_needed_pct": round(gap, 1)})
    watch.sort(key=lambda i: i["drop_needed_pct"])

    return {"deals": deals[:limit], "rising": rising[:limit], "watch": watch[:limit]}
