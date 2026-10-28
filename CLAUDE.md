# Limited Deals — local Roblox limiteds deal finder

A web dashboard that runs only on this PC (http://127.0.0.1:5000). It browses classic Roblox limiteds, filters them, and flags deals after Roblox's resale fee.

## Stack
- Python 3.13, Flask (web server), SQLite (single file `limited_deals.db`), `requests`, `python-dotenv`
- Front end: one HTML page + vanilla JS (`templates/`, `static/`). No build step.
- Tests: pytest (`tests/`)

## Run it
```
python -m venv venv
venv\Scripts\pip install -r requirements.txt
copy .env.example .env        (then edit .env)
venv\Scripts\python app.py
```
Then open http://127.0.0.1:5000. Run tests with `venv\Scripts\pytest`.

## Data sources
- Rolimons `api.rolimons.com/items/v2/itemdetails`: values, RAP, demand, trend, projected. Fetch at most once per 60 s (their cache is 60 s; abusers get banned).
- Roblox catalog batch details: lowest resale price. Fetch only for items within budget.
- Resale fee: seller keeps 70% on classic limiteds (30% Roblox fee). This is a setting, not a hard-coded constant.

## Conventions
- **All HTTP goes through `HttpClient` in `data_sources.py`.** It enforces per-host spacing, backoff on 429/5xx, and `Retry-After`. Never call `requests` directly elsewhere.
- **Secrets live only in `.env`.** Never log, print, or commit the `ROBLOSECURITY` cookie. Send it only to `*.roblox.com` hosts.
- **Buying is off by default, and test mode is on by default.** Every purchase needs a click in a confirm dialog, and every attempt is written to `purchase_log`.
- Keep deal/profit logic in `deals.py` as pure functions with tests.
- Prefer simple, readable code over clever code. The owner is learning Python.
- Build in phases. After each phase, run the app, verify it, then commit.
