"""Tests for the cloud job's safety rules, with fake data (no network)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import deals
import refresh_job


def rolimons_items(count, rap=1000):
    return [{"id": i, "name": f"Item {i}", "acronym": "", "rap": rap, "value": None, "demand": -1,
             "trend": -1, "projected": False, "hyped": False, "rare": False} for i in range(count)]


@pytest.fixture
def temp_data(tmp_path, monkeypatch):
    """Point the job at an empty temp folder instead of docs/data."""
    data = tmp_path / "data"
    monkeypatch.setattr(refresh_job, "DATA_DIR", str(data))
    monkeypatch.setattr(refresh_job, "HISTORY_DIR", str(data / "history"))
    monkeypatch.setattr(refresh_job, "ITEMS_FILE", str(data / "items.json"))
    monkeypatch.setattr(refresh_job, "ALERTED_FILE", str(data / "alerted.json"))
    monkeypatch.setattr(refresh_job, "CONFIG_FILE", str(tmp_path / "missing.json"))
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    return data


def test_rolimons_down_writes_nothing(temp_data, monkeypatch):
    def broken():
        raise ConnectionError("no internet")
    monkeypatch.setattr(refresh_job.data_sources, "fetch_rolimons_items", broken)
    with pytest.raises(refresh_job.SkipRun):
        refresh_job.run()
    assert not temp_data.exists()


def test_too_few_rolimons_items_writes_nothing(temp_data, monkeypatch):
    monkeypatch.setattr(refresh_job.data_sources, "fetch_rolimons_items", lambda: rolimons_items(10))
    with pytest.raises(refresh_job.SkipRun):
        refresh_job.run()
    assert not temp_data.exists()


def test_roblox_mostly_failing_writes_nothing(temp_data, monkeypatch):
    monkeypatch.setattr(refresh_job.data_sources, "fetch_rolimons_items", lambda: rolimons_items(1200))
    few = {i: {"lowest_price": 500, "total_quantity": 10, "collectible_item_id": None} for i in range(100)}
    monkeypatch.setattr(refresh_job.data_sources, "fetch_lowest_prices", lambda ids: few)
    with pytest.raises(refresh_job.SkipRun):
        refresh_job.run()
    assert not temp_data.exists()


def test_good_run_writes_items_and_marks_missing_prices_stale(temp_data, monkeypatch):
    monkeypatch.setattr(refresh_job.data_sources, "fetch_rolimons_items", lambda: rolimons_items(1200))
    # Item 0 is a big discount (a deal) but its price didn't refresh this run.
    prices = {i: {"lowest_price": 900, "total_quantity": 10, "collectible_item_id": None} for i in range(1, 1200)}
    monkeypatch.setattr(refresh_job.data_sources, "fetch_lowest_prices", lambda ids: prices)
    os.makedirs(temp_data)
    refresh_job.write_json(refresh_job.ITEMS_FILE, {"items": [{"id": 0, "lowest_price": 100, "total_quantity": 5}]})

    refresh_job.run()

    saved = refresh_job.load_json(refresh_job.ITEMS_FILE, {})
    item0 = next(i for i in saved["items"] if i["id"] == 0)
    assert item0["stale"] and item0["lowest_price"] == 100
    assert not item0["is_deal"]  # stale prices never count as deals
    assert saved["counts"]["priced"] == 1200
    assert len(os.listdir(temp_data / "history")) == 1


def deal_item(item_id, price, **extra):
    item = {"id": item_id, "name": f"Item {item_id}", "lowest_price": price, "rap": 2000, "value": None,
            "demand": 3, "trend": 2, "projected": False, "rare": False, "total_quantity": 10, "stale": False}
    item.update(extra)
    item.update(deals.evaluate(item, deals.DEFAULT_SETTINGS))
    return item


def test_discord_posts_once_per_listing(monkeypatch):
    posts = []
    monkeypatch.setattr(refresh_job, "post_to_discord", lambda url, payload: posts.append(payload) or True)
    items = [deal_item(1, 1000), deal_item(2, 1000, projected=True)]
    filters = {"Under 5k": {"max_price": 5000, "hide_projected": True}}

    alerted = refresh_job.send_discord_alerts(items, filters, {}, 0, "https://example.invalid/hook")
    assert len(posts) == 1 and len(posts[0]["embeds"]) == 1  # projected item is never a deal
    assert "1:1000" in alerted

    refresh_job.send_discord_alerts(items, filters, alerted, 0, "https://example.invalid/hook")
    assert len(posts) == 1  # same listing, no repeat


def test_discord_failure_is_retried_next_run(monkeypatch):
    monkeypatch.setattr(refresh_job, "post_to_discord", lambda url, payload: False)
    alerted = refresh_job.send_discord_alerts([deal_item(1, 1000)], {"all": {}}, {}, 0, "https://example.invalid/hook")
    assert alerted == {}


def test_discord_error_never_logs_webhook(caplog):
    secret = "https://discord.com/api/webhooks/123/SECRET-TOKEN"
    refresh_job.post_to_discord(secret.replace("https://", "https://does-not-exist.invalid/"), {"content": "x"})
    assert "SECRET-TOKEN" not in caplog.text
