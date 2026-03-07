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
| POST | `/api/backtest` | `routes/backtest.py` | `run_backtest` — single-stock or S&P 500 portfolio sim |
| POST | `/api/screener` | `routes/screener.py` | `run_screener` — S&P 500 or crypto universe scan |
| GET | `/api/strategy/bollinger-bands/<ticker>` | `routes/strategies/bollinger_bands.py` | `bollinger_bands` — BUY/SELL signals |
| GET | `/api/strategy/mean-reversion/<ticker>` | `routes/strategies/mean_reversion.py` | `mean_reversion` — BUY/SELL signals |
| GET | `/api/strategy/post-earnings-drift/<ticker>` | `routes/strategies/post_earnings_drift.py` | `post_earnings_drift` — BUY/SELL signals |
| GET | `/api/strategy/relative-strength/<ticker>` | `routes/strategies/relative_strength.py` | `relative_strength` — BUY/SELL signals vs SPY |

### Key Backend Functions

**`routes/stock_info.py`**
- `compute_rsi()` — 14-period RSI
- `compute_consolidation()` — price range tightness

**`routes/backtest.py`**
- `signals_bollinger / _relative_strength / _mean_reversion / _pead()` — signal generators (vectorized with pandas boolean masking; 7–9x faster than loop-based)
- `run_simulation()` — single-stock backtest engine
- `_run_portfolio_sim()` — portfolio backtest engine
- `_precompute_*_signals()` — vectorized precompute (bb, rs, mr, pead)
- `_handle_portfolio_backtest()` — portfolio mode handler

**`routes/screener.py`**
- `score_bollinger / score_relative_strength / score_mean_reversion / score_pead()` — strategy scorers

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
| `components/Backtest.js` | `Backtest` | Single-stock and portfolio backtesting UI |
| `components/Screener.js` | `Screener` | Stock/crypto screener with progress bar |
| `components/StrategyGuide.js` | `StrategyGuide` | Educational strategy reference |

### Sub-components & Helpers

**`StockChart.js`** — `buildSignalArray()` maps signal dates to price points

**`StockInfo.js`** — `MetricRow`, `StatusBadge`; color helpers: `valuationColor / rsiColor / consolidationColor / recColor()`

**`Backtest.js`** — `SummaryCard`, `PortfolioSummaryCard`, `PnlCell`; formatters: `fmt$()`, `fmtPct()`, `fmtShares()`

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

## Conventions
- Signals: ▲ BUY (green), ▼ SELL (red) as scatter points on price chart
- One active strategy at a time; "None" = raw chart
- Routes call helpers only — no provider logic in route handlers
- Secrets via environment variables only
