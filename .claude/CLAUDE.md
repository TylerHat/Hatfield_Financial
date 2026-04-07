# Hatfield Financial — Project Instructions

**Hatfield Investments** is a React + Flask financial dashboard: market data, portfolio views, screening/ranking, backtesting.

> Goal: fast iteration, clean architecture, safe handling of secrets, predictable local dev.

**Reference guides (in `.claude/guides/`):**
- `ARCHITECTURE.md` — project structure, data flow, tech stack, component map
- `API.md` — all endpoint contracts, query params, response shapes
- `FIN_STRATEGIES.md` — signal logic, indicators, scoring for all 9 strategies
- `COMPONENTS.md` — full prop API for Badge, StatCard, DataTable, StockChart, AnalystPanel, Backtester
- `DESIGN_SYSTEM.md` — colors, typography, spacing, CSS class naming
- `DATA.md` — yfinance behaviors, known quirks, timezone handling, rate limits
- `INFRASTRUCTURE.md` — Terraform, Docker, CI/CD, AWS deployment

---

## Backend Rules (Flask)

- No provider logic inside routes — routes call services/helpers only
- Providers implement a common interface: `get_quotes(symbols)`, `get_bars(symbol, tf, start, end)`
- Services handle: input validation, caching, normalization, error mapping
- Cache key: `(provider, endpoint, params_hash)` — short TTL for quotes, longer for bars
- Generate a `request_id` per request; log structured JSON
- Global error handler returns standardized error responses

---

## Frontend Rules (React)

- Desktop-only — do not add mobile layouts, responsive breakpoints, or touch patterns
- Plain CSS only — no Tailwind, Bootstrap, or Material UI
- All API requests go through the Flask backend at `http://localhost:5000`
- Dark GitHub-style theme — see DESIGN_SYSTEM.md for color palette

---

## Guide Maintenance

When adding features that change API contracts, components, strategies, design tokens, or infrastructure, update the relevant guide in `.claude/guides/`.

---

## Setup

```bash
# Backend (activate venv first)
cd Backend && ..\.venv\Scripts\activate && pip install -r requirements.txt && python app.py

# Frontend
cd Frontend && npm install && npm start
```
