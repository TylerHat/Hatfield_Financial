
This repository contains **Hatfield Investments**, a React-based financial app with a **Flask API** backend used to fetch, normalize, and serve market/portfolio data.

> Goal: fast iteration, clean architecture, safe handling of secrets, and predictable environments for local dev + CI.

---

## What to Build (Product Summary) **

Hatfield Investments is a web app that:
- Displays market data (prices, OHLCV, fundamentals where applicable)
- Provides portfolio views (holdings, performance, allocations)
- Supports screening/ranking (momentum, trend, volatility, etc.)
- Offers alerts/notifications (optional)
- Emphasizes reliability, clear error states, and auditability of calculations

**High-level requirements**
- React frontend consumes a versioned Flask REST API
- API returns normalized JSON with explicit timestamps + timezones
- Compute-heavy work should be batchable/cached
- All secrets are stored in environment variables (never committed)
- Observable: structured logs + request IDs + basic metrics

---
**Backend Implementation Guidance (Flask)**
Rules:
No provider logic inside routes; routes call services
Providers implement a common interface:
get_quotes(symbols)
get_bars(symbol, tf, start, end)
Services handle:
input validation
caching
normalization
error mapping to API error codes

**Caching**
Cache on:
- (provider, endpoint, params hash)
- Short TTL for quotes (e.g., 5–30 seconds)
- Longer TTL for historical bars (minutes-hours depending on size)
- Observability
- Generate a request_id per request
- Log structured JSON:
   * method, path, status
   * latency_ms
   * user agent
   * request_id
Add a global error handler that returns standardized errors