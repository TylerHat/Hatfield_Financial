# Hatfield Financial — Architecture Reference

React frontend + Flask backend financial app. Dark-themed, single-page with tabs.
Data source: Yahoo Finance (yfinance). Port 5000 (API), Port 3000 (UI).

---

## Backend — Flask (`Backend/`)

### Entry Point
- `app.py` — registers all blueprints, starts server

### Routes

| Method | Endpoint | File | Function |
|--------|----------|------|----------|
| GET | `/api/stock/<ticker>` | `routes/stock_data.py` | `get_stock_data` — OHLCV + MA20/MA50 |
| GET | `/api/stock-info/<ticker>` | `routes/stock_info.py` | `get_stock_info` — fundamentals, RSI, consolidation |
| GET | `/api/strategy/bollinger-bands/<ticker>` | `routes/strategies/bollinger_bands.py` | `bollinger_bands` — BUY/SELL signals |
| GET | `/api/strategy/mean-reversion/<ticker>` | `routes/strategies/mean_reversion.py` | `mean_reversion` — BUY/SELL signals |
| GET | `/api/strategy/post-earnings-drift/<ticker>` | `routes/strategies/post_earnings_drift.py` | `post_earnings_drift` — BUY/SELL signals |
| GET | `/api/strategy/relative-strength/<ticker>` | `routes/strategies/relative_strength.py` | `relative_strength` — BUY/SELL signals vs SPY |

### Key Functions

**`routes/stock_info.py`**
- `compute_rsi()` — 14-period RSI
- `compute_consolidation()` — price range tightness

**`data/sp500_tickers.py`**
- `SP500_TICKERS`, `CRYPTO_TICKERS` — universe constants

---

## Frontend — React (`Frontend/src/`)

### Components

| File | Component | Purpose |
|------|-----------|---------|
| `App.js` | `App` | Shell with tab navigation |
| `components/StockChart.js` | `StockChart` | Price + volume chart with signal overlays |
| `components/StockInfo.js` | `StockInfo` | Fundamentals, RSI, 52-week range |
| `components/StrategyGuide.js` | `StrategyGuide` | Educational strategy reference |

### Sub-components & Helpers

**`StockChart.js`** — `buildSignalArray()` maps signal dates to price points

**`StockInfo.js`** — `MetricRow`, `StatusBadge`; color helpers: `valuationColor / rsiColor / consolidationColor`

---

## Strategies (4 total)

| Key | Name | Signal Logic |
|-----|------|-------------|
| `bollinger-bands` | Bollinger Bands | Price vs 2-std bands |
| `relative-strength` | Relative Strength | Performance vs SPY benchmark |
| `mean-reversion` | Mean Reversion | Drawdown from rolling high |
| `post-earnings-drift` | PEAD | Price move post-earnings |

---

## Data Flow

```
User → React Tab → fetch /api/* → Flask → yfinance → pandas/numpy → JSON → Chart.js
```

## Tech Stack

- **Backend**: Flask + flask-cors + yfinance + pandas + numpy
- **Frontend**: React 18, Chart.js v4, react-chartjs-2 v5, plain CSS
- **Data Source**: Yahoo Finance (yfinance)

## Conventions

- Signals: ▲ BUY (green), ▼ SELL (red) as scatter points on price chart
- One active strategy at a time; "None" = raw chart
- Routes call helpers only — no provider logic in route handlers
- Secrets via environment variables only
- Dark theme: #0d1117 (GitHub-style)

---

## Maintenance Note

**Claude.md has permission to update this file** as new features/endpoints are added. Keep this file as a high-level map only—no session logs, bug histories, or implementation details. Focus on endpoint signatures, tool descriptions, and data flow.

**Ideal size**: under 200 lines for token efficiency.
