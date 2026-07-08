# Hatfield Financial — Architecture Reference

React 18 frontend + Flask backend financial dashboard. Desktop-only, dark-themed, single-page with tabs.
Data source: Yahoo Finance (yfinance). Port 5000 (API), Port 3000 (UI).

**Detailed references:**
- API contracts → `guides/API.md`
- Strategy signal logic → `guides/FIN_STRATEGIES.md`
- Component props + CSS classes → `guides/COMPONENTS.md`
- Colors, typography, spacing → `guides/DESIGN_SYSTEM.md`
- yfinance behavior + data quirks → `guides/DATA.md`
- AWS infra, Docker, CI/CD → `guides/INFRASTRUCTURE.md`

---

## Project Structure

```
Hatfield_Financial/
├── Backend/
│   ├── app.py                          Flask entry point, registers all blueprints, rate limiter, idempotent migrations, admin seed
│   ├── auth.py                         JWT helpers, @login_required and @admin_required decorators
│   ├── models.py                       SQLAlchemy models — see "Models" below
│   ├── requirements.txt
│   ├── sp500.py                        S&P 500 ticker list (Wikipedia scrape + fallback)
│   ├── cache.py                        Thread-safe in-memory TTL cache (SimpleCache class)
│   ├── data_fetcher.py                 Shared data-fetching layer with priority queue + tiered caching
│   ├── lambda_handler.py               AWS Lambda — pre-computes S&P 500 recommendations to S3 (every 20 min)
│   ├── lambda_rebalance_handler.py     AWS Lambda — triggers Custom ETF auto-rebalance daily 9:30 ET (MON-FRI)
│   ├── Dockerfile                      ECS Fargate image (gunicorn on :8000)
│   ├── Dockerfile.lambda               Lambda container image
│   ├── instance/                       SQLite database (hatfield.db, gitignored locally; mounted on EFS in prod)
│   ├── routes/
│   │   ├── stock_data.py               GET / POST /api/stock/<ticker>
│   │   ├── stock_info.py               GET / POST /api/stock-info/<ticker>; debug endpoint
│   │   ├── backtest.py                 GET /api/backtest/<ticker>
│   │   ├── auth_routes.py              POST /api/auth/register, /login, GET/PATCH /me
│   │   ├── admin.py                    /api/admin/users CRUD, /api/admin/metrics/* (yfinance queue recording)
│   │   ├── user_data.py                Watchlist + portfolio + settings CRUD (all @login_required)
│   │   ├── recommendations.py          GET /api/recommendations + /progress — batch S&P 500 (20-min cache, S3-backed in prod)
│   │   ├── analyst_data.py             GET /api/analyst-data/<ticker>
│   │   ├── custom_etf.py               Custom ETF simulator: list/state/rankings/rebalance/reset/auto-rebalance-all/backtest
│   │   ├── markov.py                   GET /api/markov/<ticker> — Markov regime analysis for a single ticker
│   │   └── strategies/
│   │       ├── bollinger_bands.py
│   │       ├── mean_reversion.py
│   │       ├── relative_strength.py
│   │       ├── post_earnings_drift.py
│   │       ├── macd_crossover.py
│   │       ├── rsi.py
│   │       ├── volatility_squeeze.py
│   │       ├── breakout_52week.py
│   │       └── ma_confluence.py
│   ├── services/
│   │   ├── row_features.py             Price-derived rec-row features (momentum, momentum6m, realizedVol, trend, MACD, 52w) — single source shared by prewarm + backtest engine
│   │   ├── custom_etf/
│   │   │   ├── simulator.py            DB wrapper: persist trades/positions/snapshots, serialize + summarize, cost-basis tracking
│   │   │   ├── rebalance_core.py       Pure sell/mark/buy decision pass — executed verbatim by simulator AND backtest engine
│   │   │   ├── walk_forward.py         Generic walk-forward backtest engine (refuses lookahead-unsafe strategies, daily equity marks)
│   │   │   ├── custom_universe.py      Synthesizes price-feature rows for fixed-universe strategies (Sector Rotation's SPDRs)
│   │   │   ├── backtest_jobs.py        Background job queue for long-running backtests
│   │   │   ├── markov_portfolio_backtest.py   Compatibility shim → walk_forward with the markov-regime strategy
│   │   │   └── strategies/             Eight registered ETF strategies (see FIN_STRATEGIES.md)
│   │   └── markov/
│   │       └── analyze.py              Regime classification, transition matrix, stationary distribution, forecast
│   └── scripts/                        One-off CLI tools: backfill_spy_prices, audit_etf, fix_etf_snapshots, etc.
└── Frontend/
    ├── package.json
    └── src/
        ├── index.js
        ├── api.js                      apiFetch() — injects Bearer token, 401 → dispatches hf_auth_expired, FIFO response cache (50 entries, 2-min TTL)
        ├── AuthContext.js              AuthProvider + useAuth() (login, register, logout, validate-on-mount)
        ├── App.js                      Shell: auth gate, top-level tab nav, analysis sub-tab nav, shared stock-info fetch
        ├── App.css
        └── components/
            ├── AuthPage.js              Login / register form (toggle)
            ├── StockChart.js            Multi-panel chart stack (Price/Volume/MACD/ATR/Stochastic/OBV/RSI) — currently does its own internal signals table (no SIGNAL_COLUMNS / onSignals lift)
            ├── StockInfo.js             Three-row analysis cards (Valuation/Momentum/52W + Price Action/MACD/Volatility/Volume + Trend/Earnings/RelStrength/Dividend) + key metrics + fundamentals tables
            ├── AnalystPanel.js          Analyst coverage: price targets, recommendation trends, upgrades/downgrades, earnings/revenue estimates
            ├── InsiderTransactions.js   Insider buy/sell table + 90-day net summary
            ├── InstitutionalHoldings.js Institutional holders table + ownership summary
            ├── MarkovMethod.js          Markov regime analysis UI for the active ticker
            ├── EtfBacktestPanel.js      Walk-forward backtest UI for any backtest-safe ETF strategy (admin-launched job)
            ├── MarkovExplainPanel.js    Static explanation card for the Markov method
            ├── Recommendations.js       S&P 500 batch screener tab (filter bar, DataTable, Buy Score, on-demand strategy signals)
            ├── Watchlist.js             User watchlist tab (add/remove, navigate-to-stock)
            ├── CustomEtfPanel.js        Custom ETF simulator UI: strategy sidebar, holdings, trades, equity curve, rebalance button
            ├── AccountPanel.js          Profile + email update form
            ├── AdminPanel.js            Admin-only: users table, grant/revoke admin, delete user (typed-confirm modal)
            ├── ApiMonitorPanel.js       Admin-only: yfinance queue metrics recorder (5/10-minute snapshots)
            ├── AboutPage.js             Static personal-bio page
            ├── StrategyGuide.js         Static strategy documentation tab
            ├── Backtester.js / .css     ORPHANED — file exists but not imported anywhere. Still references /api/backtest. Contains the only @media query in the codebase (Backtester.css). Either delete or re-wire under Admin.
            ├── Badge.js / .css
            ├── StatCard.js / .css
            └── DataTable.js / .css
```

---

## Data Flow

```
User → React Tab → apiFetch(/api/*) → Flask route → data_fetcher (priority queue + cache) → yfinance → pandas/numpy → JSON → Chart.js
                        ↓                           ↓
                  Bearer token injected        In-memory tiered cache (see DATA.md for canonical TTLs):
                  from localStorage            - OHLCV: 5-min TTL (always fetched with 280-day warmup)
                  401 → clears token,          - Ticker info: 10-min TTL  (NOTE: code value, not 30-min)
                        dispatches             - SPY history: 10-min TTL (shared globally)
                        hf_auth_expired        - Earnings: 1-hour TTL
                                               - Analyst data: 30-min TTL
                  apiFetch FIFO cache:         - Recommendations: 20-min TTL (S3-backed in prod via Lambda)
                  - GET responses: 2-min TTL
                  - max 50 entries
                  - LocalStorage cache:
                    Recommendations also persists to LS (20-min) for instant repeat loads
```

### Auth Flow

```
Register/Login → POST /api/auth → JWT token (24h) → localStorage (hf_token, hf_user)
App mount → GET /api/auth/me → validate token → show dashboard or AuthPage
```

### Recommendations Pre-Compute (Production)

```
EventBridge (every 20 min) → Lambda (lambda_handler.handler) → _fetch_all_data() → S3 (S3_CACHE_BUCKET/recommendations/latest.json)
Flask backend on cache miss → _read_s3_cache() → in-memory cache → JSON response
```

### Custom ETF Auto-Rebalance (Production)

```
EventBridge Scheduler (9:30 ET MON-FRI) → Lambda (lambda_rebalance_handler.handler) → POST /api/custom-etf/auto-rebalance-all (X-Internal-Secret) → rebalance every registered strategy
```

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| Backend | Flask, flask-cors, flask-sqlalchemy, flask-limiter, PyJWT, yfinance, pandas, numpy, werkzeug, boto3 (S3), python-dotenv |
| Frontend | React 18, Chart.js v4, react-chartjs-2 v5, plain CSS |
| Database | SQLite via SQLAlchemy. Local dev: `Backend/instance/hatfield.db`. Prod: SQLite on EFS (`/mnt/efs/hatfield.db`) — see INFRASTRUCTURE.md. The RDS Terraform module exists but is NOT currently wired up. |
| Auth | JWT tokens (24h expiry), werkzeug password hashing, JWT secret from `SECRET_KEY` env |
| Data Source | Yahoo Finance via yfinance (curl_cffi-based; no shared session) |
| AWS | ECS Fargate (API), CloudFront + S3 (frontend), API Gateway VPC Link, EFS (SQLite mount), Lambda × 2 (precompute + rebalance) |

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
- On 401: clears `hf_token` / `hf_user` in localStorage, dispatches `hf_auth_expired` event (AuthContext listens and resets React state)
- Client-side response cache: **FIFO**, GET requests cached for 2 minutes (max 50 entries — first-inserted evicted, not LRU)

### Tab Structure

Top-level tabs (in App.js order):

| Tab Key | Label | Visibility |
|---------|-------|-----------|
| `analysis` | Stock Analysis | All |
| `recommendations` | Recommendations | All |
| `watchlist` | Watchlist | All |
| `guide` | Strategy Guide | All |
| `account` | Account | All |
| `about` | About | All |
| `administration` | Administration | Admin only |
| `custom-etf` | Custom ETF | All |
| `api-monitor` | API Monitor | Admin only |

**Stock Analysis sub-tabs** (visible once a ticker is loaded):
`overview` → StockInfo · `insider` → InsiderTransactions · `institutional` → InstitutionalHoldings · `analyst` → AnalystPanel · `charts` → StockChart + range/strategy controls · `markov` → MarkovMethod

### Stock Info Flow
- `App.js` fetches `/api/stock-info/<ticker>` once per ticker change (also drives `/api/analyst-data/<ticker>` in parallel)
- Result shared to `StockSnapshot` (internal App.js function for price/change cards), `StockInfo`, `InsiderTransactions`, `InstitutionalHoldings`, `AnalystPanel` via props — no duplicate fetches
- Refresh button POSTs to `/api/stock-info/<ticker>` to bust the server-side TTL and increments `refreshKey` to re-trigger StockChart's price-data fetch

### Signal Flow
- `StockChart` fetches strategy signals internally and renders them in its own in-component signals table (lines 1413-1442 of StockChart.js)
- The `onSignals` prop and a global `SIGNAL_COLUMNS` constant were planned (and partly wired in StockChart) but **App.js never passes `onSignals`** — the lift is a no-op today. Either remove the prop or re-wire App.js to receive signals.
- One active strategy at a time; "None" = raw chart, no signals

### Reusable Components

`Badge`, `StatCard` / `StatCardGrid`, `DataTable` — see `guides/COMPONENTS.md` for full prop API.

---

## Backend Architecture

### Route Rules
- Routes should call `data_fetcher` helpers — they may not call `yf.Ticker(...)` directly (one current violation in `routes/stock_info.py` debug endpoint)
- Services handle: input validation, caching, normalization, error mapping
- Most routes return `{ "error": "message" }` with appropriate HTTP status, but the response shape is **not** standardized via the global error handler — most routes catch their own exceptions

### Data Fetcher (`Backend/data_fetcher.py`)

Centralized layer for all yfinance access. Key public helpers:

- `get_ohlcv(ticker, start, end, priority)` — always fetches with 280-day warmup, cached 5 min
- `get_ticker_info(ticker, priority)` — `stock.info` dict, cached 10 min
- `get_spy_history(start, end, priority)` — SPY OHLCV with dedicated cache (10 min)
- `get_spy_period(period, priority)` — SPY for canned periods like `'5d'`, `'3mo'`
- `get_spy_1m_return(priority)` — cached SPY 1-month return scalar
- `get_earnings_dates(ticker, limit, priority)` — 1-hour TTL
- `get_analyst_data(ticker, priority)` — 30-min TTL (price targets, recommendations, upgrades/downgrades, estimates)
- `get_insider_transactions(ticker, priority)` — insider buy/sell history
- `get_institutional_holders(ticker, priority)` — institutional ownership
- `get_many_ohlcv(symbols, period, priority)` — bulk fetch (different cache-key prefix than `get_ohlcv` — bulk reads don't accelerate later single-ticker reads)
- `clear_cache()` / `clear_ticker_cache(symbol)` — manual eviction

All calls funnel through a single-worker priority queue (`YFinanceQueue`) with `PRIORITY_HIGH/MEDIUM/LOW`. The queue enforces a min inter-call interval (`_CALL_INTERVAL = 0.3s`) and promotes starved items after 30 s. A 5 s timeout guards individual property accesses (e.g. `stock.info`) to prevent the worker from hanging.

The queue also records per-minute metrics (success / failure / timeout / cache hit / cache miss / endpoint counts) consumed by the API Monitor admin panel.

### Database Layer
- SQLite via SQLAlchemy. Local: `Backend/instance/hatfield.db`. Prod: `/mnt/efs/hatfield.db` (EFS mount). Postgres swap is possible but the RDS module is not currently wired in.
- WAL mode + 5 s busy_timeout enabled on SQLite at startup (for EFS concurrency)
- `db.create_all()` called on app startup
- Idempotent `ALTER TABLE` migrations in app.py for: `users.is_admin`, `users.last_login_at`, `users.email`, ticker width on watchlist_items / portfolio_holdings, `watchlist_items.price_at_add`

### Models (`Backend/models.py`)

- `User`, `Watchlist`, `WatchlistItem`, `PortfolioHolding`, `UserSettings`
- `EtfPortfolio`, `EtfPosition`, `EtfTrade`, `EtfEquitySnapshot` — Custom ETF simulator state
- All models expose `to_dict()` for JSON serialization

### Auth System
- `Backend/auth.py`: `create_token()`, `decode_token()`, `@login_required`, `@admin_required`
- `@login_required` extracts Bearer token, sets `g.current_user_id`, returns 401 on failure
- Registration validation: username 3-30 chars, email format, password 8+ with upper/lower/digit
- Rate limits: login 5/min/IP, register 30/hour/IP, `auth.update_me` 10/min, `user_data.get_watchlist_data` 10/min, `admin.delete_user` 10/min, `admin.update_user_role` 10/min (all via flask-limiter)
- Admin seeding: `ADMIN_USERNAME` env var promotes that user to admin on startup; `ADMIN_PASSWORD` (if set) resets their password (intended as a one-shot — remove from task def after use)
- CORS: `ALLOWED_ORIGIN` env var (default `http://localhost:3000`) PLUS `https://hatfield-financial.com` is always allowed via set-union — local dev accepts requests from prod by design

### Backtest Engine (`routes/backtest.py`)
- `_simulate_trades()` — runs signal list through capital simulation (integer shares only; no fractional sizing)
- `_build_equity_curve()` — builds time-series equity from trades, marked-to-market each day
- `_compute_summary()` — win rate, max drawdown, profit factor, unrealized P&L. Best/worst-trade and SPY-buy-and-hold benchmark added recently.

### Custom ETF Simulator (`services/custom_etf/`)
- Five+ registered strategies score the latest Recommendations universe → top-N equal-weight portfolio with 24 h auto-rebalance cooldown
- State persisted across requests in `EtfPortfolio` / `EtfPosition` / `EtfTrade` / `EtfEquitySnapshot`
- Long-running backtests (Markov regime) run in background threads via `backtest_jobs.py` and are polled by the frontend
- Auto-rebalance triggered nightly by the rebalance Lambda hitting `/api/custom-etf/auto-rebalance-all` with the `X-Internal-Secret` header (`INTERNAL_API_SECRET` env)

### Markov Subsystem (`services/markov/`)
- `analyze.py` — 20-bar lookback, classifies bars into BULL/NEUTRAL/BEAR using `BULL_PCT` / `BEAR_PCT` thresholds, builds a 3×3 transition matrix, computes stationary distribution and N-step forecasts
- Used by `/api/markov/<ticker>`, the Markov tab in Stock Analysis, the Custom ETF Markov Regime strategy, and per-stock regime fields on the Recommendations payload

---

## Conventions

- Signals rendered as scatter points: ▲ BUY (green), ▼ SELL (red)
- MACD/RSI divergences rendered as ◆ diamond markers (green bullish, red bearish)
- MACD crossovers rendered as ▲/▼ triangles on the MACD chart
- Each chart has an expand button (⛶) to fill content area and an info button (i) with colored legend popover
- Secrets via environment variables only — never committed (see INFRASTRUCTURE.md for the full env-var table)
- `maintainAspectRatio: false` on all Chart.js charts
- Desktop-only — no responsive breakpoints, no mobile layouts (the only `@media` query in the repo is in `Backtester.css`, which violates this rule but is orphaned anyway)

---

## Maintenance Note

**Update this file when:**
- A new route file or blueprint is added → update the file tree and data flow
- A new frontend component or tab is added → update the file tree and tab structure
- The tech stack changes (new library, port change, etc.)
- Cache TTLs in `data_fetcher.py` change (also update DATA.md)
- The `onSignals`/`SIGNAL_COLUMNS` pattern is either implemented or removed

Keep this as a structural map only. API contracts → `API.md`. Strategy logic → `FIN_STRATEGIES.md`. Colors/spacing → `DESIGN_SYSTEM.md`. Component props → `COMPONENTS.md`. Infra → `INFRASTRUCTURE.md`.
