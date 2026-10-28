"""SQLite storage. One file (limited_deals.db), created automatically."""
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
        """)


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
