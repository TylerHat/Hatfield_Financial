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
│   ├── cache.py                        Thread-safe in-memory cache with TTL
│   ├── instance/                       SQLite database (hatfield.db, gitignored)
│   ├── data/
│   │   └── sp500_tickers.py            SP500_TICKERS, CRYPTO_TICKERS universe constants
│   └── routes/
│       ├── stock_data.py               GET /api/stock/<ticker>
│       ├── stock_info.py               GET /api/stock-info/<ticker> (also fetches SPY for relative strength)
│       ├── backtest.py                 GET /api/backtest/<ticker>
│       ├── auth_routes.py              POST /api/auth/register, /login, GET /me
│       ├── user_data.py                Watchlist, portfolio, settings CRUD (all @login_required)
│       ├── recommendations.py          GET /api/recommendations — batch S&P 500 recommendations (30-min cache)
│       ├── batch_signals.py            GET /api/strategy/<name>/batch — batch strategy signals for all S&P 500 (30-min cache)
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
            ├── StrategyGuide.js        Static strategy documentation tab
            ├── Recommendations.js / Recommendations.css   Recommendations tab (filter bar, DataTable, batch strategy signals)
            ├── Badge.js / Badge.css
            ├── StatCard.js / StatCard.css
            └── DataTable.js / DataTable.css
```

---

## Data Flow

```
User → React Tab → apiFetch(/api/*) → Flask route → yfinance → pandas/numpy → JSON → Chart.js
                        ↓
                  Bearer token injected from localStorage
                  401 → clears token, dispatches hf_auth_expired → AuthPage
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
| Backend | Flask, flask-cors, flask-sqlalchemy, flask-limiter, PyJWT, yfinance, pandas, numpy (Python) |
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

### Tab Structure
- **Stock Analysis** — StockChart + StockInfo
- **Recommendations** — Recommendations (S&P 500 batch screener with filter bar, strategy signals)
- **Components** — Badge, StatCard, DataTable showcase
- **Strategy Guide** — StrategyGuide (static docs)

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
- Services handle: input validation, caching, normalization, error mapping
- All errors return `{ "error": "message" }` with appropriate HTTP status code

### Database Layer
- SQLite stored in `Backend/instance/hatfield.db` (gitignored)
- Models in `Backend/models.py`: User, Watchlist, WatchlistItem, PortfolioHolding, UserSettings
- `db.create_all()` called on app startup
- All models have `to_dict()` for JSON serialization

### Auth System
- `Backend/auth.py`: `create_token()`, `decode_token()`, `@login_required` decorator
- `@login_required` extracts Bearer token, sets `g.current_user_id`, returns 401 on failure
- Registration validation: username 3-30 chars, email format, password 8+ with upper/lower/digit
- Rate limits: login 5/min/IP, register 3/hour/IP (via flask-limiter)
- CORS restricted to `http://localhost:3000`

### Backtest Engine (`routes/backtest.py`)
- `_simulate_trades()` — runs signal list through capital simulation
- `_build_equity_curve()` — builds time-series equity from trades
- `_compute_summary()` — win rate, max drawdown, Sharpe ratio, unrealized P&L

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
