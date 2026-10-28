import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import deals
from deals import DAY, DEFAULT_SETTINGS


def make_item(**overrides):
    item = {
        "lowest_price": 1000, "rap": 2000, "value": None, "demand": -1, "trend": -1,
        "projected": False, "own_projected": False, "rap_change_pct": None, "price_change_pct": None,
    }
    item.update(overrides)
    return item


# ---------- Profit math ----------

def test_profit_after_30_percent_fee():
    # Sell at 2000, keep 70% = 1400, minus 1000 paid = 400
    assert deals.expected_profit(1000, 2000, 70) == 400


def test_profit_rounds_down():
    # 70% of 1001 = 700.7 -> Roblox pays whole Robux, so 700
    assert deals.expected_profit(0, 1001, 70) == 700


def test_discount_pct():
    assert deals.discount_pct(600, 1000) == 40
    assert deals.discount_pct(1200, 1000) == -20


def test_target_prefers_value_over_rap():
    assert deals.resale_target(make_item(value=3000)) == 3000
    assert deals.resale_target(make_item(value=None)) == 2000


# ---------- Deal rule: BOTH thresholds must pass ----------

def test_deal_when_both_thresholds_pass():
    result = deals.evaluate(make_item(lowest_price=1000, rap=2000), DEFAULT_SETTINGS)
    assert result["discount_pct"] == 50
    assert result["profit"] == 400
    assert result["is_deal"]


def test_not_deal_when_profit_too_small():
    # 50% off, but cheap item: keep 70% of 200 = 140 - 100 = 40 profit < 200
    result = deals.evaluate(make_item(lowest_price=100, rap=200), DEFAULT_SETTINGS)
    assert result["discount_pct"] == 50
    assert not result["is_deal"]


def test_not_deal_when_discount_too_small():
    # Profit 2100 is big, but only 30% off (< 35%)
    result = deals.evaluate(make_item(lowest_price=7000, rap=10000), DEFAULT_SETTINGS)
    assert result["profit"] == 0
    assert not result["is_deal"]


def test_projected_item_is_never_a_deal():
    result = deals.evaluate(make_item(lowest_price=1000, rap=2000, projected=True), DEFAULT_SETTINGS)
    assert result["projected_warning"]
    assert not result["is_deal"]


# ---------- Buy-below price ----------

def test_buy_below_uses_the_stricter_rule():
    # target 2000: 35% below -> 1300; profit rule -> 1400 - 200 = 1200. Stricter = 1200.
    assert deals.buy_below_price(2000, DEFAULT_SETTINGS) == 1200


def test_buy_below_matches_deal_rule_for_many_targets():
    for target in [300, 999, 2000, 4385, 7373, 12000]:
        limit = deals.buy_below_price(target, DEFAULT_SETTINGS)
        if limit is None:
            continue
        assert deals.evaluate(make_item(lowest_price=limit, rap=target), DEFAULT_SETTINGS)["is_deal"]
        assert not deals.evaluate(make_item(lowest_price=limit + 1, rap=target), DEFAULT_SETTINGS)["is_deal"]


def test_buy_below_none_for_cheap_items():
    # 70% of 250 = 175, minus 200 profit -> impossible
    assert deals.buy_below_price(250, DEFAULT_SETTINGS) is None


# ---------- Suggestions ----------

def evaluated(**overrides):
    item = make_item(**overrides)
    item.update(deals.evaluate(item, DEFAULT_SETTINGS))
    return item


def test_suggestions_sort_items_into_lists():
    items = [
        evaluated(id=1, lowest_price=1000, rap=2000),                          # deal
        evaluated(id=2, lowest_price=1500, rap=2000),                          # near: buy below 1200
        evaluated(id=3, lowest_price=1900, rap=2000),                          # further away
        evaluated(id=4, lowest_price=1500, rap=2000, rap_change_pct=20, price_change_pct=5),  # rising
    ]
    result = deals.suggestions(items, budget=5000)
    assert [i["id"] for i in result["deals"]] == [1]
    assert [i["id"] for i in result["rising"]] == [4]
    assert [i["id"] for i in result["watch"]] == [2, 3]
    assert result["watch"][0]["drop_needed_pct"] == 20


def test_suggestions_skip_projected_and_over_budget():
    items = [
        evaluated(id=1, lowest_price=1000, rap=2000, projected=True),
        evaluated(id=2, lowest_price=6000, rap=12000),
    ]
    result = deals.suggestions(items, budget=5000)
    assert result == {"deals": [], "rising": [], "watch": []}


# ---------- Own projection detection ----------

NOW = 10 * DAY


def flat_history(days, rap, price):
    """One snapshot every 2 hours for `days` days, ending at NOW."""
    return [(NOW - h * 3600, rap, price) for h in range(days * 24, -1, -2)]


def test_projection_when_rap_jumps_but_listings_stay():
    history = flat_history(5, rap=1000, price=1000)
    assert deals.suspected_projection(history, rap_now=1600, price_now=1050, ratio=1.3, now=NOW)


def test_no_projection_when_listings_rise_too():
    history = flat_history(5, rap=1000, price=1000)
    assert not deals.suspected_projection(history, rap_now=1600, price_now=1500, ratio=1.3, now=NOW)


def test_no_projection_without_enough_history():
    history = flat_history(5, rap=1000, price=1000)[-3:]
    assert not deals.suspected_projection(history, rap_now=1600, price_now=1050, ratio=1.3, now=NOW)


# ---------- Own trend ----------

def test_trend_needs_three_days():
    assert deals.own_trend_pct(flat_history(2, 1000, 1000)) == (None, None)


def test_trend_detects_rise():
    history = flat_history(4, 1000, 1000)
    history = [(ts, 1000 if ts < NOW - 2 * DAY else 1200, 900 if ts < NOW - 2 * DAY else 1000)
               for ts, _, _ in history]
    rap_change, price_change = deals.own_trend_pct(history)
    assert rap_change == 20
    assert price_change > 0


def test_rising_badge_from_own_trend():
    item = make_item(rap_change_pct=15, price_change_pct=5)
    assert deals.evaluate(item, DEFAULT_SETTINGS)["rising"]


def test_rising_badge_hidden_when_projected():
    item = make_item(rap_change_pct=15, price_change_pct=5, projected=True)
    assert not deals.evaluate(item, DEFAULT_SETTINGS)["rising"]
