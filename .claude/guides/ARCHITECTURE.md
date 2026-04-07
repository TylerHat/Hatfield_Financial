# Hatfield Financial — Architecture Reference

React 18 frontend + Flask backend financial dashboard. Desktop-only, dark-themed, single-page with tabs.
Data source: Yahoo Finance (yfinance). Port 5000 (API), Port 3000 (UI).

**Detailed references:**
- API contracts → `guides/API.md`
- Strategy signal logic → `guides/FIN_STRATEGIES.md`
- Component props + CSS classes → `guides/COMPONENTS.md`
- Colors, typography, spacing → `guides/DESIGN_SYSTEM.md`
- yfinance behavior + data quirks → `guides/DATA.md`

---

## Project Structure

```
Hatfield_Financial/
├── Backend/
│   ├── app.py                          Flask entry point, registers all blueprints, rate limiter
│   ├── auth.py                         JWT helpers (create/decode token), @login_required decorator
│   ├── models.py                       SQLAlchemy models (User, Watchlist, Portfolio, Settings)
│   ├── requirements.txt
│   ├── sp500.py                        Static S&P 500 ticker list
│   ├── cache.py                        Thread-safe in-memory cache with TTL (used by recommendations)
│   ├── data_fetcher.py                 Shared data-fetching layer with caching (OHLCV, info, SPY, earnings, analyst)
│   ├── instance/                       SQLite database (hatfield.db, gitignored)
│   └── routes/
│       ├── stock_data.py               GET /api/stock/<ticker>
│       ├── stock_info.py               GET /api/stock-info/<ticker> (also fetches SPY for relative strength)
│       ├── backtest.py                 GET /api/backtest/<ticker>
│       ├── auth_routes.py              POST /api/auth/register, /login, GET /me
│       ├── user_data.py                Watchlist, portfolio, settings CRUD (all @login_required)
│       ├── recommendations.py          GET /api/recommendations — batch S&P 500 recommendations (20-min cache)
│       ├── analyst_data.py             GET /api/analyst-data/<ticker> — price targets, recommendations, earnings estimates
│       └── strategies/
│           ├── bollinger_bands.py
│           ├── mean_reversion.py
│           ├── relative_strength.py
│           ├── post_earnings_drift.py
│           ├── macd_crossover.py
│           ├── rsi.py
│           ├── volatility_squeeze.py
│           ├── breakout_52week.py
│           └── ma_confluence.py
└── Frontend/
    ├── package.json
    └── src/
        ├── api.js                      apiFetch() wrapper — injects Bearer token, handles 401
        ├── AuthContext.js              AuthProvider + useAuth() hook (login, register, logout)
        ├── App.js                      Shell: auth gate, tab nav, strategy + signals state
        ├── App.css
        └── components/
            ├── AuthPage.js / AuthPage.css   Login / register form with toggle
            ├── StockChart.js           Price + Volume + MACD + ATR + Stochastic + OBV + RSI charts; expand/info UI; signal overlays
            ├── StockInfo.js            Three-row analysis cards: (Valuation, Momentum, 52-Week) + (Price Action, MACD, Volatility, Volume) + (Trend Alignment, Earnings Proximity, Rel Strength vs SPY, Dividend Health)
            ├── AnalystPanel.js / AnalystPanel.css   Analyst coverage: price targets, recommendation trends, upgrades/downgrades, earnings estimates
            ├── Backtester.js / Backtester.css       Strategy backtesting: equity curve charts, trade tables, performance metrics
            ├── StrategyGuide.js        Static strategy documentation tab
            ├── Recommendations.js / Recommendations.css   Recommendations tab (filter bar, DataTable, on-demand strategy signals)
            ├── Badge.js / Badge.css
            ├── StatCard.js / StatCard.css
            └── DataTable.js / DataTable.css
```

---

## Data Flow

```
User → React Tab → apiFetch(/api/*) → Flask route → data_fetcher (cached) → yfinance → pandas/numpy → JSON → Chart.js
                        ↓                           ↓
                  Bearer token injected        In-memory cache layer:
                  from localStorage            - OHLCV: 5-min TTL (280-day warmup)
                  401 → clears token           - Ticker info: 30-min TTL
                                               - SPY: 10-min TTL (shared globally)
                                               - Earnings: 1-hour TTL
                                               - Analyst data: 30-min TTL
                  apiFetch client-side cache:
                  - GET responses: 2-min TTL (max 50 entries)
```

### Auth Flow

```
Register/Login → POST /api/auth → JWT token (24h) → localStorage (hf_token, hf_user)
App mount → GET /api/auth/me → validate token → show dashboard or AuthPage
```

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| Backend | Flask, flask-cors, flask-sqlalchemy, flask-migrate, flask-limiter, PyJWT, yfinance, pandas, numpy, werkzeug (Python) |
| Frontend | React 18, Chart.js v4, react-chartjs-2 v5, plain CSS |
| Database | SQLite via SQLAlchemy (swappable to Postgres) |
| Auth | JWT tokens (24h expiry), werkzeug password hashing |
| Data Source | Yahoo Finance via yfinance |

---

## Frontend Architecture

### Auth Gate
- `AuthProvider` wraps `<App />` in `index.js`
- On mount: validates stored JWT via `GET /api/auth/me`
- Not logged in → `AuthPage` (login/register toggle)
- Logged in → dashboard with username + logout in header

### API Layer
- All fetch calls use `apiFetch()` from `src/api.js`
- Automatically injects `Authorization: Bearer <token>` header
- On 401: clears localStorage, dispatches `hf_auth_expired` custom event
- Client-side response cache: GET requests cached for 2 minutes (max 50 entries)

### Tab Structure
- **Stock Analysis** — StockChart + StockInfo + AnalystPanel
- **Recommendations** — Recommendations (S&P 500 batch screener with filter bar, strategy signals)
- **Components** — Badge, StatCard, DataTable showcase
- **Strategy Guide** — StrategyGuide (static docs)

### Stock Info Flow
- `App.js` fetches `/api/stock-info/<ticker>` once per ticker change
- Result shared to `StockSnapshot` (internal App.js function for price/change cards) and `StockInfo` (analysis cards) via props
- Eliminates the prior duplicate fetch from both components

### Signal Flow
- `StockChart` fetches strategy signals, lifts them to `App.js` via `onSignals` prop
- `SIGNAL_COLUMNS` defined at module scope in App.js (stable reference)
- One active strategy at a time; "None" = raw chart, no signals

### Reusable Components

`Badge`, `StatCard` / `StatCardGrid`, `DataTable` — see `guides/COMPONENTS.md` for full prop API.

---

## Backend Architecture

### Route Rules
- No provider logic inside routes — routes call helpers only
- All yfinance data fetched via `data_fetcher.py` (not called directly from routes)
- Services handle: input validation, caching, normalization, error mapping
- All errors return `{ "error": "message" }` with appropriate HTTP status code

### Data Fetcher (`Backend/data_fetcher.py`)
- Centralized caching layer; all routes use `get_ohlcv()`, `get_ticker_info()`, `get_spy_history()`, `get_spy_period()`, `get_earnings_dates()`, `get_analyst_data()`
- `get_ohlcv()` always fetches with 280-day warmup (max any strategy needs), cached 5 min
- SPY data cached globally (10-min TTL), shared across stock_info, relative_strength, backtest
- Recommendations cache pre-warmed on server start via background thread

### Database Layer
- SQLite stored in `Backend/instance/hatfield.db` (gitignored)
- Models in `Backend/models.py`: User, Watchlist, WatchlistItem, PortfolioHolding, UserSettings
- `db.create_all()` called on app startup
- All models have `to_dict()` for JSON serialization

### Auth System
- `Backend/auth.py`: `create_token()`, `decode_token()`, `@login_required` decorator
- `@login_required` extracts Bearer token, sets `g.current_user_id`, returns 401 on failure
- Registration validation: username 3-30 chars, email format, password 8+ with upper/lower/digit
- Rate limits: login 5/min/IP, register 30/hour/IP (via flask-limiter)
- CORS restricted to `http://localhost:3000`

### Backtest Engine (`routes/backtest.py`)
- `_simulate_trades()` — runs signal list through capital simulation
- `_build_equity_curve()` — builds time-series equity from trades
- `_compute_summary()` — win rate, max drawdown, profit factor, unrealized P&L

---

## Conventions

- Signals rendered as scatter points: ▲ BUY (green), ▼ SELL (red)
- MACD/RSI divergences rendered as ◆ diamond markers (green bullish, red bearish)
- MACD crossovers rendered as ▲/▼ triangles on the MACD chart
- Each chart has an expand button (⛶) to fill content area and an info button (i) with colored legend popover
- Secrets via environment variables only — never committed
- `maintainAspectRatio: false` on all Chart.js charts
- Desktop-only — no responsive breakpoints, no mobile layouts

---

## Maintenance Note

**Update this file when:**
- A new route file or blueprint is added → update the file tree and data flow
- A new frontend component or tab is added → update the component list and tab structure
- The tech stack changes (new library, port change, etc.)

Keep this as a structural map only. API contracts → `API.md`. Strategy logic → `FIN_STRATEGIES.md`. Colors/spacing → `DESIGN_SYSTEM.md`. Component props → `COMPONENTS.md`.
