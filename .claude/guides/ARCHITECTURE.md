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
│   ├── app.py                          Flask entry point, registers all blueprints
│   ├── requirements.txt
│   ├── data/
│   │   └── sp500_tickers.py            SP500_TICKERS, CRYPTO_TICKERS universe constants
│   └── routes/
│       ├── stock_data.py               GET /api/stock/<ticker>
│       ├── stock_info.py               GET /api/stock-info/<ticker>
│       ├── backtest.py                 GET /api/backtest/<ticker>
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
        ├── App.js                      Shell: tab nav, active strategy + signals state
        ├── App.css
        └── components/
            ├── StockChart.js           Price + volume + MACD + RSI charts; signal overlays; signals table
            ├── StockInfo.js            Fundamentals, RSI, MACD, 52-week analysis cards
            ├── StrategyGuide.js        Static strategy documentation tab
            ├── Badge.js / Badge.css
            ├── StatCard.js / StatCard.css
            └── DataTable.js / DataTable.css
```

---

## Data Flow

```
User → React Tab → fetch /api/* → Flask route → yfinance → pandas/numpy → JSON → Chart.js
```

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| Backend | Flask, flask-cors, yfinance, pandas, numpy (Python) |
| Frontend | React 18, Chart.js v4, react-chartjs-2 v5, plain CSS |
| Data Source | Yahoo Finance via yfinance |

---

## Frontend Architecture

### Tab Structure
- **Stock Analysis** — StockChart + StockInfo
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

### Backtest Engine (`routes/backtest.py`)
- `_simulate_trades()` — runs signal list through capital simulation
- `_build_equity_curve()` — builds time-series equity from trades
- `_compute_summary()` — win rate, max drawdown, Sharpe ratio, unrealized P&L

---

## Conventions

- Signals rendered as scatter points: ▲ BUY (green), ▼ SELL (red)
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
