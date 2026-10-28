"""SQLite storage. One file (limited_deals.db), created automatically."""
import json
import sqlite3
import time

from config import DB_PATH


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    return conn


def init_db():
    with connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS items (
                id                  INTEGER PRIMARY KEY,
                name                TEXT,
                acronym             TEXT,
                rap                 INTEGER,
                value               INTEGER,
                demand              INTEGER,
                trend               INTEGER,
                projected           INTEGER,
                hyped               INTEGER,
                rare                INTEGER,
                lowest_price        INTEGER,
                total_quantity      INTEGER,
                collectible_item_id TEXT,
                price_updated_at    REAL
            );
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS presets (
                name    TEXT PRIMARY KEY,
                filters TEXT  -- JSON, e.g. {"max_price": 5000, "min_demand": 3}
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value REAL
            );
            -- RAP + lowest price snapshots (at most one per item every 30 min) for our own trend
            CREATE TABLE IF NOT EXISTS history (
                item_id      INTEGER,
                ts           REAL,
                rap          INTEGER,
                lowest_price INTEGER
            );
            CREATE INDEX IF NOT EXISTS history_item_ts ON history (item_id, ts);
        """)
        # Columns added in Phase 3 (older databases won't have them yet).
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
        for column, sql_type in [("rap_change_pct", "REAL"), ("price_change_pct", "REAL"),
                                 ("own_projected", "INTEGER"), ("history_days", "REAL")]:
            if column not in existing:
                conn.execute(f"ALTER TABLE items ADD COLUMN {column} {sql_type}")
        # A starter preset, added only the first time.
        conn.execute(
            "INSERT OR IGNORE INTO presets (name, filters) VALUES (?, ?)",
            ("Under 5k, high demand", json.dumps({"max_price": 5000, "min_demand": 3, "hide_projected": True})),
        )


def save_rolimons_items(items):
    with connect() as conn:
        conn.executemany("""
            INSERT INTO items (id, name, acronym, rap, value, demand, trend, projected, hyped, rare)
            VALUES (:id, :name, :acronym, :rap, :value, :demand, :trend, :projected, :hyped, :rare)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, acronym=excluded.acronym, rap=excluded.rap,
                value=excluded.value, demand=excluded.demand, trend=excluded.trend,
                projected=excluded.projected, hyped=excluded.hyped, rare=excluded.rare
        """, items)


def save_prices(prices):
    now = time.time()
    with connect() as conn:
        for item_id, info in prices.items():
            conn.execute("""
                UPDATE items SET lowest_price=?, total_quantity=?, collectible_item_id=?, price_updated_at=?
                WHERE id=?
            """, (info["lowest_price"], info["total_quantity"], info["collectible_item_id"], now, item_id))


def item_ids_with_rap_at_most(limit):
    with connect() as conn:
        rows = conn.execute("SELECT id FROM items WHERE rap <= ? ORDER BY id", (limit,)).fetchall()
    return [row["id"] for row in rows]


def all_items():
    with connect() as conn:
        rows = conn.execute("SELECT * FROM items").fetchall()
    return [dict(row) for row in rows]


def set_meta(key, value):
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(value)))


def get_meta(key, default=None):
    with connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def get_settings(defaults):
    """Saved settings, falling back to `defaults` for anything not saved yet."""
    with connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    settings = dict(defaults)
    settings.update({row["key"]: row["value"] for row in rows if row["key"] in defaults})
    return settings


def save_settings(values):
    with connect() as conn:
        conn.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", values.items())


def record_history(min_gap_seconds=30 * 60, keep_days=30):
    """Snapshot RAP + lowest price for priced items. Returns how many rows were added."""
    now = time.time()
    with connect() as conn:
        added = conn.execute("""
            INSERT INTO history (item_id, ts, rap, lowest_price)
            SELECT id, ?, rap, lowest_price FROM items
            WHERE lowest_price IS NOT NULL
              AND id NOT IN (SELECT item_id FROM history WHERE ts > ?)
        """, (now, now - min_gap_seconds)).rowcount
        conn.execute("DELETE FROM history WHERE ts < ?", (now - keep_days * 86400,))
    return added


def history_by_item(since):
    """{item_id: [(ts, rap, lowest_price), ...]} oldest first."""
    result = {}
    with connect() as conn:
        rows = conn.execute(
            "SELECT item_id, ts, rap, lowest_price FROM history WHERE ts >= ? ORDER BY item_id, ts", (since,)
        )
        for item_id, ts, rap, price in rows:
            result.setdefault(item_id, []).append((ts, rap, price))
    return result


def save_signals(signals):
    """signals: {item_id: {rap_change_pct, price_change_pct, own_projected, history_days}}"""
    with connect() as conn:
        conn.executemany("""
            UPDATE items SET rap_change_pct=:rap_change_pct, price_change_pct=:price_change_pct,
                             own_projected=:own_projected, history_days=:history_days
            WHERE id=:id
        """, [{"id": item_id, **values} for item_id, values in signals.items()])


def all_presets():
    with connect() as conn:
        rows = conn.execute("SELECT name, filters FROM presets ORDER BY name").fetchall()
    return [{"name": row["name"], "filters": json.loads(row["filters"])} for row in rows]


def save_preset(name, filters):
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO presets (name, filters) VALUES (?, ?)", (name, json.dumps(filters)))


def delete_preset(name):
    with connect() as conn:
        conn.execute("DELETE FROM presets WHERE name=?", (name,))
