import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data_sources import HttpClient


class FakeResponse:
    def __init__(self, headers):
        self.headers = headers


def test_backoff_grows_each_attempt():
    waits = [HttpClient._backoff_seconds(FakeResponse({}), attempt) for attempt in range(4)]
    assert 5 <= waits[0] < 7
    assert 40 <= waits[3] < 42
    assert waits == sorted(waits)


def test_backoff_respects_long_retry_after():
    assert HttpClient._backoff_seconds(FakeResponse({"Retry-After": "120"}), 0) == 120


def test_short_retry_after_does_not_stop_backoff_growing():
    # Roblox sent Retry-After: 5 every time, which kept us retrying too fast.
    assert HttpClient._backoff_seconds(FakeResponse({"Retry-After": "5"}), 3) >= 40
