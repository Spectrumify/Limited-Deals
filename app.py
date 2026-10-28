"""Start the dashboard:  venv\\Scripts\\python app.py  then open http://127.0.0.1:5000"""
import logging
import os

from flask import Flask, jsonify, render_template

import db
import refresher
from config import BUDGET, LOG_DIR
from data_sources import DEMAND_NAMES, TREND_NAMES

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html", budget=BUDGET)


@app.route("/api/items")
def api_items():
    items = db.all_items()
    for item in items:
        item["demand_name"] = DEMAND_NAMES.get(item["demand"], "")
        item["trend_name"] = TREND_NAMES.get(item["trend"], "")
    return jsonify(items)


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


if __name__ == "__main__":
    setup_logging()
    db.init_db()
    refresher.start()
    # 127.0.0.1 = only reachable from this PC. use_reloader=False so the refresher starts once.
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
