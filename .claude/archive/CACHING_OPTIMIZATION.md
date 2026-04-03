# Caching & Data Retrieval Optimization

> Decision document for optimizing yfinance data fetching, caching, and computation in Hatfield Financial.

---

## Current State Analysis

### How Data Flows Today

All market data is fetched **live from yfinance on every request**. The only caching exists on the two heaviest endpoints (recommendations and batch signals) via an in-memory `SimpleCache` with 30-minute TTL. Single-ticker routes — which power the main Stock Analysis tab — have **zero caching**.

The existing SQLite database (`Backend/instance/hatfield.db`) stores only user data: authentication, watchlists, portfolio holdings, and settings. No market data touches the database.

### Current Request Costs

| User Action | yfinance API Calls | Approx Latency |
|---|---|---|
| Load a stock (no strategy) | 3 requests (2 are duplicate `/stock-info`) | 2–4s |
| Load a stock + strategy | 4 requests | 3–5s |
| Switch strategy (same ticker) | 1 fresh OHLCV fetch (re-downloads same data) | 1–2s |
| Load Recommendations tab (cold) | 1 batch download + ~500 `.info` calls (20 threads) | 30–60s |
| Load Recommendations tab (cached) | 0 | <1s |
| Run backtest | 1–2 requests (+ SPY if relative strength) | 1–2s |
| Switch batch strategy on Recommendations | 0 if OHLCV cached, else full reload | 0–60s |

### Key Bottlenecks

1. **No single-ticker caching** — Every chart load, strategy switch, or stock-info request hits yfinance fresh. Switching between 3 strategies on the same ticker = 3 redundant OHLCV downloads.

2. **Duplicate `/api/stock-info` calls** — `App.js` (StockSnapshot) and `StockInfo.js` both call the same endpoint simultaneously when a ticker is submitted. 33% wasted overhead on every stock load.

3. **SPY fetched redundantly** — Three separate code paths fetch SPY data independently:
   - `stock_info.py` (relative strength card)
   - `relative_strength.py` (strategy signals)
   - `backtest.py` (RS backtest)

   Each is a fresh yfinance call with no sharing.

4. **Recommendations first-load cost** — 500+ concurrent `yf.Ticker().info` calls take 30–60s. Users see a loading spinner for nearly a minute on first visit.

5. **Variable warmup periods wasted** — Each strategy fetches its own lookback window (40–280 extra days). Switching strategies re-downloads overlapping date ranges instead of fetching once and trimming.

6. **Earnings dates fetched inconsistently** — Four different code paths fetch earnings data using different yfinance methods (`get_earnings_dates()`, `.calendar`, `.earnings_dates`), none cached.

### Files Involved

| File | Role | Caching |
|---|---|---|
| `Backend/cache.py` | SimpleCache class (in-memory, TTL, thread-safe) | — |
| `Backend/routes/stock_data.py` | Single-ticker OHLCV + earnings | None |
| `Backend/routes/stock_info.py` | Fundamentals + 1Y history + SPY | None |
| `Backend/routes/strategies/*.py` | 9 strategy signal generators | None |
| `Backend/routes/backtest.py` | Backtest engine + optional SPY | None |
| `Backend/routes/recommendations.py` | Batch S&P 500 fetch | 30-min SimpleCache |
| `Backend/routes/batch_signals.py` | Batch strategy signals | 30-min SimpleCache |
| `Backend/models.py` | User/Watchlist/Portfolio models | SQLite |
| `Frontend/src/App.js` | Duplicate stock-info fetch | None |
| `Frontend/src/components/StockChart.js` | Chart + strategy data fetching | None |

---

## Approach 1: Database-First (Store All yfinance Data in DB)

### Description
Fetch yfinance data on a schedule (or on first request), store OHLCV bars, fundamentals, and earnings in SQLite (or PostgreSQL), and have all routes/calculations query the database instead of yfinance directly.

### How It Would Work
- New DB tables: `ohlcv_daily`, `stock_fundamentals`, `earnings_dates`, `spy_daily`
- Background job (APScheduler or Celery) refreshes data periodically (e.g., every 15–30 min during market hours, nightly for fundamentals)
- All strategy, chart, and info endpoints read from DB instead of yfinance
- First request for a new ticker triggers a fetch-and-store, subsequent requests read from DB

### Pros
- **Eliminates redundant fetches entirely** — One canonical data source for all endpoints
- **Sub-100ms query latency** — SQLite reads are nearly instant vs 0.5–2s per yfinance call
- **Offline resilience** — App works even if yfinance is temporarily down or rate-limited
- **Consistent data** — All endpoints see the same snapshot; no race conditions between parallel fetches
- **Enables historical analysis** — Can store and query data beyond what yfinance provides in a single call
- **Simplifies strategy code** — Strategies receive DataFrames from DB queries instead of managing their own fetches
- **Scalable** — Adding new strategies or endpoints doesn't add yfinance calls

### Cons
- **Significant implementation effort** — New DB schema, migration scripts, data ingestion pipeline, refresh scheduling
- **Data freshness trade-off** — DB data is only as fresh as the last refresh cycle; intraday traders may notice lag
- **Storage growth** — S&P 500 daily OHLCV for 2 years ≈ 250K rows (small); fundamentals for 500 tickers adds more. Manageable for SQLite but needs monitoring
- **Schema maintenance** — yfinance response shapes change without warning; ingestion must handle missing/renamed fields gracefully
- **New dependency** — Needs APScheduler or Celery for background refresh; adds operational complexity
- **Cold start problem** — First launch requires bulk data load (could take 5–10 min for full S&P 500 history)
- **Stale data risk** — If refresh job fails silently, users see outdated data without knowing

### Implementation Complexity: **High**
- New DB models and migrations
- Background job infrastructure (APScheduler recommended for simplicity)
- Data ingestion service with error handling and retry logic
- Refactor all routes to query DB instead of yfinance
- Monitoring for refresh job health

---

## Approach 2: Pre-Computation on Login

### Description
When a user logs in, immediately kick off background fetches for their likely data needs (watchlist tickers, last-viewed stocks, S&P 500 recommendations) so the data is warm by the time they navigate.

### How It Would Work
- On successful `/api/auth/login`, trigger async pre-fetch jobs:
  - Fetch OHLCV + fundamentals for watchlist tickers
  - Pre-compute recommendations if cache is stale
  - Pre-fetch SPY data
- Store results in the existing `SimpleCache` (or an enhanced version)
- When user navigates to a stock/tab, data is already cached → instant response

### Pros
- **Perceived performance boost** — User sees fast load times because data was fetched during login
- **Minimal architecture change** — Uses existing cache infrastructure; no new DB tables needed
- **Leverages user context** — Can prioritize fetching data the user is most likely to need (watchlist, recent tickers)
- **Low risk** — If pre-fetch fails, falls back to normal on-demand fetching

### Cons
- **Doesn't eliminate redundancy** — Still fetching from yfinance (just earlier); doesn't solve the underlying duplication
- **Login latency** — If pre-fetch runs synchronously, login feels slow. If async, needs background thread/task management
- **Wasted work** — Pre-fetched data for tickers the user never views is wasted API calls and memory
- **Cache invalidation** — Pre-fetched data may go stale if user stays logged in for hours
- **Doesn't help first-time/anonymous users** — No login = no pre-computation
- **Doesn't help Recommendations tab** — The 500-ticker batch is too heavy to pre-fetch on every login
- **Memory pressure** — Pre-fetching many tickers bloats in-memory cache; no eviction strategy in current SimpleCache

### Implementation Complexity: **Medium**
- Background thread pool for async pre-fetching on login
- Logic to determine what to pre-fetch (watchlist, recent tickers)
- Enhanced cache with size limits and eviction
- Fallback handling if pre-fetch didn't complete before user navigates

---

## Approach 3: Tiered Caching + Request Deduplication (Recommended)

### Description
A layered approach that adds intelligent caching at multiple levels without requiring a full database migration or background job infrastructure. Focuses on eliminating the specific redundancies identified in the current codebase.

### How It Would Work

**Layer 1 — Backend request-level cache (SimpleCache enhancement)**
- Cache single-ticker OHLCV with 5-min TTL (covers strategy switching)
- Cache SPY data globally with 10-min TTL (shared across all RS calculations)
- Cache fundamentals/info with 15-min TTL
- Cache earnings dates with 1-hour TTL (rarely changes)
- Key format: `(endpoint, ticker, params_hash)`

**Layer 2 — Unified OHLCV fetch**
- New helper: `get_ohlcv(ticker, start, end)` that all routes call
- Fetches the maximum lookback needed (280 days warmup) once, trims per strategy
- Returns from cache on subsequent calls within TTL

**Layer 3 — Frontend deduplication**
- Eliminate duplicate `/api/stock-info` call (lift state to App.js)
- Add simple client-side response cache (Map with 2-min TTL) in `api.js`

**Layer 4 — Batch optimization**
- Stagger the 500 `.info` calls in recommendations (10 workers instead of 20, with retry)
- Add progress reporting via polling status endpoint
- Pre-warm recommendations cache on server start (background thread)

### Pros
- **Highest ROI** — Fixes the biggest pain points with the least architectural change
- **Incremental** — Each layer can be implemented and tested independently
- **No new infrastructure** — Uses existing SimpleCache pattern; no Redis, no Celery, no new DB tables
- **Backwards compatible** — All existing endpoints keep their contracts; only internal fetching changes
- **Measurable** — Each layer provides a clear before/after latency improvement
- **Low memory footprint** — TTL-based eviction prevents unbounded growth
- **Works for all users** — Not dependent on login or user context

### Cons
- **Data still comes from yfinance** — Subject to yfinance rate limits and downtime
- **In-memory only** — Cache lost on server restart (cold start penalty remains)
- **Doesn't enable historical queries** — No persistent storage of market data
- **TTL tuning needed** — Too short = cache misses; too long = stale data; requires experimentation
- **Not a long-term scaling solution** — If the app grows significantly, a database-backed approach will eventually be needed

### Implementation Complexity: **Low to Medium**
- Enhance `cache.py` with key-based TTL and size limits
- Create shared `get_ohlcv()` helper
- Refactor strategy routes to use shared helper (mechanical change)
- Frontend: lift stock-info state, add api-level cache
- Optional: background thread for recommendations pre-warm on startup

---

## Quick Wins — IMPLEMENTED

All 5 quick wins have been implemented as of 2026-03-21.

### 1. Deduplicate Frontend `/api/stock-info` Call — DONE
- `App.js` now fetches stock-info once, passes data to both `StockSnapshot` and `StockInfo` via props
- `StockInfo.js` no longer fetches internally

### 2. Cache SPY Data Globally — DONE
- `data_fetcher.py`: `get_spy_history()` and `get_spy_period()` with 10-min TTL
- Used by `stock_info.py`, `relative_strength.py`, and `backtest.py`

### 3. Cache Single-Ticker OHLCV (5-min TTL) — DONE
- `data_fetcher.py`: `get_ohlcv()` caches per (ticker, start, end) with 5-min TTL
- All 9 strategy routes, `stock_data.py`, `stock_info.py`, and `backtest.py` use it

### 4. Fetch Maximum Lookback Once — DONE
- `get_ohlcv()` always fetches with 280-day warmup; strategies trim to their window
- Switching strategies on the same ticker hits cache instead of yfinance

### 5. Pre-warm Recommendations on Server Start — DONE
- `app.py` launches `prewarm_cache()` in a daemon thread after init
- First user to hit Recommendations tab gets cached data

### 6. Client-Side Response Cache — DONE (bonus)
- `api.js` caches GET responses for 2 minutes (max 50 entries)
- Tab switching and re-renders don't trigger redundant backend calls

---

## Recommendation

### Short Term: Approach 3 (Tiered Caching) + Quick Wins

Start with the 5 quick wins listed above — they're independent, testable, and collectively cut perceived latency by 50–70% for the most common user flows. Then implement the remaining layers of Approach 3 (client-side cache, batch optimization).

**Expected improvements after full Approach 3 implementation:**

| User Action | Current Latency | After Optimization |
|---|---|---|
| Load a stock (no strategy) | 2–4s | 1–2s (first), <0.5s (cached) |
| Switch strategy (same ticker) | 1–2s | <0.1s (cached OHLCV) |
| Load Recommendations (cold) | 30–60s | 30–60s (but pre-warmed on start) |
| Load Recommendations (warm) | <1s | <1s (unchanged) |
| Run backtest | 1–2s | 0.5–1s (cached OHLCV + SPY) |

### Long Term: Approach 1 (Database-First)

Once the app matures and user count grows, migrate to a database-backed data layer. The shared `get_ohlcv()` helper created in Approach 3 becomes the natural insertion point — swap its implementation from "cache → yfinance" to "cache → DB → yfinance fallback" without changing any route code.

This two-phase strategy gives you **immediate performance gains** without heavy infrastructure investment, while **setting up clean abstractions** that make the database migration straightforward when the time comes.

---

## Maintenance Note

Update this document when:
- A caching layer is implemented or changed
- Cache TTL values are tuned based on production observation
- The data layer migrates from in-memory to database-backed
- New data sources are added beyond yfinance
