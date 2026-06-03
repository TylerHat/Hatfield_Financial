# Hatfield Financial — Project Instructions

**Hatfield Investments** is a React + Flask financial dashboard: market data, portfolio views, screening/ranking, backtesting.

> Goal: fast iteration, clean architecture, safe handling of secrets, predictable local dev.

**Reference guides (in `.claude/guides/`):**
- `ARCHITECTURE.md` — project structure, data flow, tech stack, component map
- `API.md` — all endpoint contracts, query params, response shapes (chart, auth, recommendations, admin, custom ETF, markov)
- `FIN_STRATEGIES.md` — signal logic, indicators, scoring for the 9 chart strategies AND the 6 Custom ETF strategies
- `COMPONENTS.md` — full prop API for all React components (Badge, StatCard, DataTable, StockChart, StockInfo, Watchlist, CustomEtfPanel, Markov*, admin panels, etc.)
- `DESIGN_SYSTEM.md` — colors, typography, spacing, CSS class naming
- `DATA.md` — yfinance behaviors, known quirks, timezone handling, rate limits, priority queue, S3-backed prewarm
- `INFRASTRUCTURE.md` — Terraform, Docker, CI/CD, AWS deployment (SQLite-on-EFS, Lambda × 2, API Gateway)

**Major subsystems beyond the analysis tab:**
- **Custom ETF simulator** — universe-wide portfolio strategies (Buy Score, Momentum, Low Vol, Analyst Conviction, Undervalued, Markov Regime). State persisted in DB; auto-rebalances daily via Lambda.
- **Markov regime model** — per-ticker Bull/Sideways/Bear classification with transition matrix forecast. Used in Stock Analysis sub-tab, Custom ETF strategy, and pre-computed onto every Recommendations row.
- **Admin tooling** — user management + yfinance queue metrics recorder; gated by `is_admin` flag on the `users` table.

---

## Backend Rules (Flask)

- No provider logic inside routes — routes call `data_fetcher` helpers only.
- All yfinance access goes through `data_fetcher.py` (priority queue + tiered cache). Do not call `yf.Ticker(...)` from a route.
- Services handle: input validation, caching, normalization, error mapping
- Cache TTLs are tuned per data type (see DATA.md). Add new helpers there, not in routes.
- Most routes catch their own exceptions and return `{"error": "..."}`; the global 500 handler is a backstop, not the primary path. Add new endpoints in the same style for consistency.
- Long-running work (Custom ETF backtests, S&P-500-wide jobs) should use the `backtest_jobs` background-thread pattern with job-id polling — NOT block the request.

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

## Environment Variables

Backend reads (see INFRASTRUCTURE.md for the full table):
- `SECRET_KEY` — JWT signing
- `DATABASE_URL` — defaults to local SQLite; prod hardcoded to `sqlite:////mnt/efs/hatfield.db` in the ECS task def
- `ALLOWED_ORIGIN` — CORS origin (defaults to `http://localhost:3000`; prod also always allows `https://hatfield-financial.com`)
- `ADMIN_USERNAME` — promotes the named user to admin on startup
- `ADMIN_PASSWORD` — optional one-shot password reset for the admin user (REMOVE from task def after use)
- `INTERNAL_API_SECRET` — shared secret for Lambda → backend auto-rebalance calls (`X-Internal-Secret` header)
- `S3_CACHE_BUCKET` — bucket holding the precomputed `recommendations/latest.json` (prod only)

Frontend reads:
- `REACT_APP_API_URL` — backend base URL at build time (defaults to `http://localhost:5000`)

---

## Setup

```bash
# Backend (activate venv first)
cd Backend && ..\.venv\Scripts\activate && pip install -r requirements.txt && python app.py

# Frontend
cd Frontend && npm install && npm start
```
