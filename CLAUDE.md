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
Then open http://127.0.0.1:5000. Stop it with Ctrl+C. Run tests with `venv\Scripts\python -m pytest`.

Only one copy may run at a time (two copies double the API traffic). `app.py` refuses to start if port 5000 is already in use.

## How deals work (`deals.py`)
- Target = Rolimons value if the item is valued, otherwise RAP.
- Profit = floor(target × seller_keep_pct / 100) − lowest price.
- Deal = % below target ≥ `min_discount_pct` AND profit ≥ `min_profit`, and the item is not projected.
- Projected = Rolimons flag OR our own check: RAP jumped ≥ `projection_ratio` × its level from over a day ago while listings did not follow.
- Rising = Rolimons trend "Raising" with demand ≥ Normal, OR our own history shows RAP up ≥ `rising_pct` with listings not falling. Needs about 3 days of history.
- History: one RAP/price snapshot per item every 30 min, kept 30 days (`history` table).
- Thresholds live in the `settings` table, editable in the page's "Deal settings" panel.
- Rolimons only rates demand/trend for items it values by hand, so most cheap items have none.

## Suggestions (`deals.suggestions`, `/api/suggestions`)
- Read-only recommendations within `BUDGET`. Projected items are always excluded.
- Lists: **Deals now** (by profit), **Rising** (by RAP change), **Watch list** (smallest % drop needed to reach the buy-below price).
- Buy-below = the highest price that passes both deal thresholds (`deals.buy_below_price`), also shown as a table column.
- Each suggestion only links to the item's roblox.com page.

## Alerts (`static/app.js`)
- The page polls the local `/api/items` every 30 s and calls `checkForNewDeals()`.
- A deal alerts once per item + price (key `id:price`). The keys already alerted on and the on/off toggle are stored in the browser's localStorage.
- Alerts only fire for deals that also pass the filters currently on screen. The tab must stay open.

## Data sources
- Rolimons `api.rolimons.com/items/v2/itemdetails`: values, RAP, demand, trend, projected. Fetch at most once per 60 s (their cache is 60 s; abusers get banned).
- Roblox catalog batch details: lowest resale price and copy count, in batches of 120, spaced 6 s apart (shorter spacing caused 429s). Fetch only for items with RAP ≤ 1.5 × budget.
- Resale fee: seller keeps 70% on classic limiteds (30% Roblox fee). This is a setting, not a hard-coded constant.

## Conventions
- **All HTTP goes through `HttpClient` in `data_sources.py`.** It enforces per-host spacing, backoff on 429/5xx, and `Retry-After`. Never call `requests` directly elsewhere.
- **Zero account risk: this app never touches the owner's Roblox account.** No `.ROBLOSECURITY` cookie, no login, no purchase/trade/sell endpoints, no auto-buy. Use only public, unauthenticated read endpoints. Buying happens by hand on roblox.com. (The original auto-buy phase was deliberately replaced by Suggestions.)
- `.env` holds local settings only (e.g. `BUDGET`) and stays git-ignored.
- Keep deal/profit logic in `deals.py` as pure functions with tests.
- Prefer simple, readable code over clever code. The owner is learning Python.
- Build in phases. After each phase, run the app, verify it, then commit.
