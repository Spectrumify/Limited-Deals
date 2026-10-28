"""Start the dashboard:  venv\\Scripts\\python app.py  then open http://127.0.0.1:5000"""
import logging
import os
import socket
import sys

from flask import Flask, jsonify, render_template, request

import db
import deals
import refresher
from config import BUDGET, LOG_DIR
from data_sources import DEMAND_NAMES, TREND_NAMES

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html", budget=BUDGET)


@app.route("/api/items")
def api_items():
    settings = db.get_settings(deals.DEFAULT_SETTINGS)
    items = db.all_items()
    for item in items:
        item["demand_name"] = DEMAND_NAMES.get(item["demand"], "")
        item["trend_name"] = TREND_NAMES.get(item["trend"], "")
        item.update(deals.evaluate(item, settings))
    return jsonify(items)


@app.route("/api/settings", methods=["GET"])
def api_settings():
    return jsonify(db.get_settings(deals.DEFAULT_SETTINGS))


@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    body = request.get_json()
    values = {}
    for key in deals.DEFAULT_SETTINGS:
        if key in body:
            try:
                values[key] = float(body[key])
            except (TypeError, ValueError):
                return jsonify({"error": f"{key} must be a number"}), 400
    if not 0 < values.get("seller_keep_pct", 70) <= 100:
        return jsonify({"error": "seller_keep_pct must be between 0 and 100"}), 400
    db.save_settings(values)
    return jsonify(db.get_settings(deals.DEFAULT_SETTINGS))


@app.route("/api/presets", methods=["GET"])
def api_presets():
    return jsonify(db.all_presets())


@app.route("/api/presets", methods=["POST"])
def api_save_preset():
    body = request.get_json()
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Preset needs a name"}), 400
    db.save_preset(name, body.get("filters", {}))
    return jsonify({"ok": True})


@app.route("/api/presets/<name>", methods=["DELETE"])
def api_delete_preset(name):
    db.delete_preset(name)
    return jsonify({"ok": True})


@app.route("/api/status")
def api_status():
    return jsonify({
        "last_refresh": float(db.get_meta("last_refresh", 0) or 0),
        "last_error": db.get_meta("last_error", ""),
    })


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(LOG_DIR, "app.log"))],
    )


def already_running(port):
    """True if something is already answering on this port (e.g. a forgotten copy of the app).

    On Windows a second copy can start on the same port without an error, which would
    double our API traffic, so we check first.
    """
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


if __name__ == "__main__":
    if already_running(5000):
        sys.exit("The dashboard is already running at http://127.0.0.1:5000 (close the other window first).")
    setup_logging()
    db.init_db()
    refresher.start()
    # 127.0.0.1 = only reachable from this PC. use_reloader=False so the refresher starts once.
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
