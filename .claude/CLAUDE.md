# Hatfield Financial — Project Instructions

**Hatfield Investments** is a React-based financial dashboard with a Flask API backend used to fetch, normalize, and serve market and portfolio data.

> Goal: fast iteration, clean architecture, safe handling of secrets, and predictable local dev environments.

**Reference guides (in `.claude/guides/`):**
- `ARCHITECTURE.md` — project structure, data flow, tech stack, component map
- `API.md` — all endpoint contracts, query params, and response shapes
- `FIN_STRATEGIES.md` — signal logic, indicators, and scoring for all 9 strategies
- `COMPONENTS.md` — full prop API for Badge, StatCard, DataTable, StockChart
- `DESIGN_SYSTEM.md` — colors, typography, spacing, CSS class naming conventions
- `DATA.md` — yfinance behaviors, known quirks, timezone handling, rate limits

---

## Product Summary

Hatfield Investments is a desktop-only web app that:
- Displays market data (prices, OHLCV, fundamentals)
- Provides portfolio views (holdings, performance, allocations)
- Supports screening and ranking (momentum, trend, volatility)
- Runs backtests on trading strategies
- Emphasizes reliability, clear error states, and auditability of calculations

**High-level requirements**
- React frontend consumes a versioned Flask REST API
- API returns normalized JSON with explicit timestamps and timezones
- Compute-heavy work should be batchable and cached
- All secrets stored in environment variables — never committed
- Observable: structured logs + request IDs + basic metrics

---

## Backend Rules (Flask)

- No provider logic inside routes — routes call services/helpers only
- Providers implement a common interface: `get_quotes(symbols)`, `get_bars(symbol, tf, start, end)`
- Services handle: input validation, caching, normalization, error mapping

**Caching**
- Cache key: `(provider, endpoint, params_hash)`
- Short TTL for quotes (5–30 seconds)
- Longer TTL for historical bars (minutes to hours)

**Observability**
- Generate a `request_id` per request
- Log structured JSON: `method`, `path`, `status`, `latency_ms`, `user_agent`, `request_id`
- Global error handler returns standardized error responses

---

## Frontend Rules (React)

- Desktop-only — do not add mobile layouts, responsive breakpoints, or touch patterns
- Plain CSS only — no Tailwind, Bootstrap, or Material UI
- All API requests go through the Flask backend at `http://localhost:5000`
- Dark GitHub-style theme — see arch doc for color palette

---

## Maintenance Note

**Update the relevant guide file whenever a feature is added or changed.** Each guide has a "Maintenance Note" section listing exactly what triggers an update. Do not let guides go stale — outdated docs are worse than none.

**Auto-update rule:** After completing any feature addition, endpoint change, new component, or chart enhancement, immediately update the affected guide files (`ARCHITECTURE.md`, `API.md`, `COMPONENTS.md`, `DESIGN_SYSTEM.md`, `FIN_STRATEGIES.md`, `DATA.md`) before reporting the work as done. This includes:
- New backend response fields → update `API.md`
- New chart panels or UI features → update `COMPONENTS.md` and `ARCHITECTURE.md`
- New routes or blueprints → update `ARCHITECTURE.md` and `API.md`
- New strategies or signal logic → update `FIN_STRATEGIES.md`
- New CSS classes, colors, or design tokens → update `DESIGN_SYSTEM.md` and `COMPONENTS.md`
- New data quirks or yfinance changes → update `DATA.md`

---

## Setup

```bash
# Backend (activate venv first)
cd Backend && ..\.venv\Scripts\activate && pip install -r requirements.txt && python app.py

# Frontend
cd Frontend && npm install && npm start
```
