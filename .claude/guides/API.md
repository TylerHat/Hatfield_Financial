# Hatfield Financial — API Reference

Base URL: `http://localhost:5000`

All endpoints return JSON. Errors return `{ "error": "message" }` with an appropriate HTTP status.

---

## GET `/api/stock/<ticker>`

Price, volume, moving averages, MACD, and RSI for a ticker.

**Query params**

| Param | Default | Description |
|-------|---------|-------------|
| `start` | 182 days ago | `YYYY-MM-DD` |
| `end` | today | `YYYY-MM-DD` |

**Response**

```json
{
  "dates":       ["2024-01-02", ...],
  "close":       [185.20, ...],
  "volume":      [55000000, ...],
  "ma20":        [183.10, ...],
  "ma50":        [180.55, ...],
  "macd":        [0.4821, ...],
  "macd_signal": [0.3912, ...],
  "macd_hist":   [0.0909, ...],
  "rsi":         [58.3, ...],
  "bb_upper":    [190.50, ...],
  "bb_lower":    [175.90, ...],
  "vol_ma20":    [48000000, ...],
  "atr":         [3.25, ...],
  "stoch_k":     [65.2, ...],
  "stoch_d":     [60.1, ...],
  "obv":         [120000000, ...],
  "obv_signal":  [115000000, ...],
  "fifty_two_week_high": 641.81,
  "fifty_two_week_low":  442.80,
  "earnings_dates": ["2024-01-25", "2024-04-25", ...]
}
```

All time-series arrays are the same length and index-aligned to `dates`. Null where indicators lack enough history.

| Field | Type | Description |
|-------|------|-------------|
| `bb_upper` / `bb_lower` | array | Bollinger Bands (20-period, 2 std dev) |
| `vol_ma20` | array | 20-day volume moving average |
| `atr` | array | Average True Range (14-period, Wilder's smoothing) |
| `stoch_k` / `stoch_d` | array | Stochastic Oscillator (9,3,3) — %K and %D |
| `obv` | array | On-Balance Volume (cumulative) |
| `obv_signal` | array | 20-day moving average of OBV |
| `fifty_two_week_high` / `fifty_two_week_low` | number \| null | 52-week extremes from yfinance info |
| `earnings_dates` | string[] | Up to 20 recent earnings dates (`YYYY-MM-DD`) |

---

## GET `/api/stock-info/<ticker>`

Fundamentals, technicals, and analyst data. Always uses 1 year of history regardless of chart date range.

**Response fields**

| Field | Type | Description |
|-------|------|-------------|
| `ticker` | string | Uppercase ticker |
| `name` | string | Company name |
| `sector` / `industry` | string | From yfinance |
| `currentPrice` | number | Latest price |
| `dayChange` | number | % change open → current |
| `marketCap` | string | Formatted (e.g. `$2.85T`) |
| `trailingPE` / `forwardPE` | number | P/E ratios |
| `priceToBook` / `priceToSales` | number | Valuation multiples |
| `beta` | number | Market beta |
| `dividendYield` | number | Annual yield (raw decimal) |
| `eps` | number | Trailing EPS |
| `fiftyTwoWeekHigh` / `fiftyTwoWeekLow` | number | 52-week range |
| `pctFromHigh` / `pctFromLow` | number | % from 52-week extremes |
| `positionInRange` | number | 0–100, position within 52-week range |
| `rsi` | number | 14-period RSI |
| `rsiSignal` | string | `Overbought` / `Oversold` / `Neutral` |
| `consolidationStatus` | string | `Strong Consolidation` / `Consolidating` / `Expanding / Trending` / `Neutral` |
| `consolidationDetail` | string | Human-readable explanation |
| `valuation` | string | `Potentially Undervalued` / `Fairly Valued` / `Slightly Overvalued` / `Potentially Overvalued` / `Not Profitable` / `N/A` |
| `valuationDetail` | string | P/E-based explanation |
| `analystRecommendation` | string | e.g. `Strong Buy` |
| `targetMeanPrice` | number | Analyst price target |
| `macdValue` / `macdSignalValue` | number | Current MACD values |
| `macdStatus` | string | `BULLISH CROSSOVER` / `BEARISH CROSSOVER` / `BULLISH` / `BEARISH` |
| `macdMomentum` | string | `STRONG MOMENTUM` / `WEAK MOMENTUM` |
| `volatilityStatus` | string | `HIGH Volatility` / `LOW Volatility` / `Normal Volatility` |
| `atrRatio` | number | ATR vs 1-year ATR average |
| `volumeStatus` | string | `HIGH Volume` / `LOW Volume` / `Normal Volume` |
| `volumeRelative` | number | Current volume as % of 20-day avg |
| `volumeTrend` | string | `↗ Increasing` / `↘ Decreasing` |
| `revenueGrowth` / `earningsGrowth` | number | YoY growth (raw decimal, optional) |
| `grossMargins` / `operatingMargins` / `profitMargins` | number | Margin ratios (optional) |
| `returnOnEquity` / `returnOnAssets` | number | Profitability ratios (optional) |
| `debtToEquity` / `currentRatio` | number | Financial health (optional) |
| `freeCashflow` | string | Formatted (e.g. `$12.50B`, optional) |
| `shortPercentOfFloat` | number | Short interest (optional) |
| `evToEbitda` | number | Enterprise Value / EBITDA (optional) |
| `pegRatio` | number | P/E to Growth ratio (optional) |
| `dividendRate` | number | Annual dividend rate in dollars (optional) |
| `exDividendDate` | string | Ex-dividend date `YYYY-MM-DD` (optional) |
| `earningsDate` | string | Next earnings date `YYYY-MM-DD` (optional) |
| `fiftyDayAverage` | number | 50-day moving average price (optional) |
| `twoHundredDayAverage` | number | 200-day moving average price (optional) |
| `trendAlignment` | string | `Strong Uptrend` / `Strong Downtrend` / `Bullish (Mixed)` / `Bearish (Mixed)` / `Bullish (Short-term)` / `Bearish (Short-term)` (optional) |
| `trendDetail` | string | Human-readable MA alignment explanation (optional) |
| `earningsProximity` | string | e.g. `14 days away`, `Earnings TODAY`, `Reported 3 days ago` (optional) |
| `earningsProximityDays` | number | Signed days until earnings (negative = past) (optional) |
| `earningsWarning` | boolean | True if earnings within 14 days (optional) |
| `relStrength1M` / `relStrength3M` | number | Relative return vs SPY over 1M/3M (optional) |
| `stock1MReturn` / `spy1MReturn` | number | Raw 1-month returns for stock and SPY (optional) |
| `stock3MReturn` / `spy3MReturn` | number | Raw 3-month returns for stock and SPY (optional) |
| `payoutRatio` | number | Dividend payout ratio (raw decimal, optional) |
| `dividendHealth` | string | `Very Healthy` / `Healthy` / `Moderate` / `Stretched` / `Unsustainable` / `No Dividend` / `Unknown` (optional) |
| `dividendHealthDetail` | string | Human-readable payout ratio explanation (optional) |
| `quickRatio` | number | Quick ratio (optional) |
| `totalCash` | string | Formatted total cash (e.g. `$48.30B`, optional) |
| `totalDebt` | string | Formatted total debt (optional) |
| `operatingCashflow` | string | Formatted operating cash flow (optional) |
| `ebitda` | string | Formatted EBITDA (optional) |
| `revenueTTM` | string | Formatted trailing twelve month revenue (optional) |
| `insiderPctHeld` | number | Insider ownership (raw decimal, optional) |
| `institutionalPctHeld` | number | Institutional ownership (raw decimal, optional) |

---

## GET `/api/strategy/<strategy-key>/<ticker>`

Returns BUY/SELL signals for the given strategy. See `FIN_STRATEGIES.md` for signal logic details.

**Available strategy keys**

| Key | Endpoint |
|-----|----------|
| `bollinger-bands` | `/api/strategy/bollinger-bands/<ticker>` |
| `mean-reversion` | `/api/strategy/mean-reversion/<ticker>` |
| `relative-strength` | `/api/strategy/relative-strength/<ticker>` |
| `post-earnings-drift` | `/api/strategy/post-earnings-drift/<ticker>` |
| `macd-crossover` | `/api/strategy/macd-crossover/<ticker>` |
| `rsi` | `/api/strategy/rsi/<ticker>` |
| `volatility-squeeze` | `/api/strategy/volatility-squeeze/<ticker>` |
| `52-week-breakout` | `/api/strategy/52-week-breakout/<ticker>` |
| `ma-confluence` | `/api/strategy/ma-confluence/<ticker>` |

**Query params** (all strategy endpoints)

| Param | Default | Description |
|-------|---------|-------------|
| `start` | 182 days ago | `YYYY-MM-DD` — start of user-visible window |
| `end` | today | `YYYY-MM-DD` |

**Response**

```json
{
  "signals": [
    {
      "date":       "2024-03-15",
      "price":      185.20,
      "type":       "BUY",
      "score":      72,
      "conviction": "HIGH",
      "reason":     "Human-readable explanation of why this signal fired"
    }
  ]
}
```

**Signal object fields**

| Field | Type | Values |
|-------|------|--------|
| `date` | string | `YYYY-MM-DD` |
| `price` | number | Close price on signal date |
| `type` | string | `BUY` or `SELL` |
| `score` | number | 0–100, signal strength |
| `conviction` | string | `HIGH` (≥60) / `MEDIUM` (≥30) / `LOW` (<30) |
| `reason` | string | Explanation with indicator values |

---

## GET `/api/recommendations`

Batch S&P 500 stock recommendations with technical + fundamental signals. Data is cached in-memory for 20 minutes. Frontend also caches in localStorage for instant repeat loads.

**Query params**: None

**Response (200)**

```json
{
  "stocks": [
    {
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "currentPrice": 185.20,
      "dayChangePct": 1.25,
      "analystRecommendation": "Strong Buy",
      "recommendationKey": "strong_buy",
      "priceAction": "Bullish",
      "macdStatus": "BULLISH CROSSOVER",
      "volatilityStatus": "Normal Volatility",
      "trendAlignment": "Strong Uptrend",
      "momentum": "STRONG MOMENTUM"
    }
  ],
  "lastUpdated": "2026-03-19T14:30:00",
  "count": 485,
  "failedCount": 18,
  "totalTickers": 503
}
```

**Response (202)** — returned while data is still being fetched on first request or after cache expiry:

```json
{ "status": "loading", "message": "S&P 500 data is currently being fetched. Please try again in a moment." }
```

| Field | Type | Description |
|-------|------|-------------|
| `stocks[].ticker` | string | Uppercase ticker symbol |
| `stocks[].name` | string | Company name |
| `stocks[].currentPrice` | number | Latest price |
| `stocks[].dayChangePct` | number | Intraday % change |
| `stocks[].analystRecommendation` | string | e.g. `Strong Buy`, `Buy`, `Hold` |
| `stocks[].recommendationKey` | string | Machine-readable key e.g. `strong_buy` |
| `stocks[].priceAction` | string | Price action status |
| `stocks[].macdStatus` | string | MACD status string |
| `stocks[].volatilityStatus` | string | Volatility status string |
| `stocks[].volRatio` | number\|null | ATR ratio (recent ATR / mean ATR); used by Buy Score risk-adjustment bucket |
| `stocks[].trendAlignment` | string | Trend alignment label |
| `stocks[].momentum` | number\|null | 1-month return relative to SPY (percent) |
| `stocks[].overallRisk` | number\|null | yfinance ISS overall risk (1–10, lower=better) |
| `stocks[].rsiValue` | number\|null | Wilder 14-day RSI |
| `stocks[].numberOfAnalysts` | number\|null | Count of analyst opinions |
| `stocks[].epsGrowth` | number\|null | Forward earnings growth rate (decimal, e.g. 0.12 = 12%) |
| `stocks[].revenueGrowth` | number\|null | Forward revenue growth rate (decimal) |
| `stocks[].forwardPE` | number\|null | Forward P/E ratio (falls back to trailing P/E when forward unavailable) |
| `stocks[].returnOnEquity` | number\|null | ROE (decimal) |
| `stocks[].debtToEquity` | number\|null | Debt-to-equity, reported by yfinance as percent (e.g. 50 = 50%) |
| `stocks[].grossMargins` | number\|null | Gross margin (decimal) |
| `stocks[].fcfYield` | number\|null | Free cash flow / market cap (decimal) |
| `stocks[].fiftyTwoWeekHigh` | number\|null | 52-week high price |
| `stocks[].fiftyTwoWeekLow` | number\|null | 52-week low price |
| `stocks[].fiftyTwoWeekPosition` | number\|null | 0–100 — where current price sits in the 52w range |
| `lastUpdated` | string | ISO timestamp of last cache refresh |
| `count` | number | Number of stocks successfully fetched |
| `failedCount` | number | Number of tickers that failed to fetch |
| `totalTickers` | number | Total S&P 500 tickers attempted |

---

## GET `/api/backtest/<ticker>`

Simulates trades for a strategy over a date range and returns performance metrics.

**Query params**

| Param | Default | Description |
|-------|---------|-------------|
| `strategy` | `bollinger-bands` | Any strategy key from the list above |
| `start` | 182 days ago | `YYYY-MM-DD` |
| `end` | today | `YYYY-MM-DD` |
| `capital` | `10000` | Starting capital in dollars |

**Supported strategies for backtest**: `bollinger-bands`, `rsi`, `macd-crossover`, `mean-reversion`, `relative-strength`

**Response**

```json
{
  "trades": [
    {
      "date": "2024-02-05",
      "type": "SELL",
      "entryDate": "2024-01-10",
      "entryPrice": 180.00,
      "price": 192.50,
      "shares": 55,
      "value": 10587.50,
      "pnl": 687.50,
      "pnlPct": 6.94,
      "status": "CLOSED"
    }
  ],
  "equityCurve": [
    { "date": "2024-01-02", "value": 10000.00 }
  ],
  "summary": {
    "startingCapital": 10000.00,
    "finalValue": 10687.50,
    "totalReturn": 6.88,
    "totalReturnDollar": 687.50,
    "winRate": 66.7,
    "numTrades": 6,
    "numWins": 4,
    "numLosses": 2,
    "avgWinPct": 5.2,
    "avgLossPct": -2.1,
    "profitFactor": 3.5,
    "bestTrade": 8.3,
    "worstTrade": -3.1,
    "maxDrawdown": -4.2,
    "unrealizedPnl": 85.00,
    "unrealizedPnlPct": 3.4,
    "hasUnrealized": true
  }
}
```

---

## Authentication Endpoints

### POST `/api/auth/register`

Create a new user account. No auth required.

**Rate limit:** 30 requests/hour per IP.

**Request body**

```json
{
  "username": "string (3-30 chars)",
  "password": "string (8+ chars, uppercase, lowercase, digit)"
}
```

**Response (201)**

```json
{
  "token": "eyJhbGciOi...",
  "user": {
    "id": 1,
    "username": "tyler",
    "created_at": "2026-03-18T12:00:00"
  }
}
```

**Errors:** `400` validation failure, `409` username already exists.

---

### POST `/api/auth/login`

Authenticate and receive a JWT token. No auth required.

**Rate limit:** 5 requests/minute per IP.

**Request body**

```json
{
  "username": "string",
  "password": "string"
}
```

**Response (200)**

```json
{
  "token": "eyJhbGciOi...",
  "user": { "id": 1, "username": "tyler", "created_at": "..." }
}
```

**Errors:** `401` invalid credentials.

---

### GET `/api/auth/me`

Validate stored token and return current user. Requires `Authorization: Bearer <token>`.

**Response (200)**

```json
{
  "user": { "id": 1, "username": "tyler", "created_at": "..." }
}
```

**Errors:** `401` missing/invalid/expired token.

---

## GET `/api/analyst-data/<ticker>`

Analyst coverage data including price targets, recommendation trends, upgrades/downgrades, and earnings/revenue estimates.

**Response (200)**

```json
{
  "ticker": "AAPL",
  "priceTargets": {
    "current": 185.20,
    "low": 150.00,
    "high": 250.00,
    "mean": 210.50,
    "median": 215.00
  },
  "numberOfAnalysts": 35,
  "recommendationTrend": [...],
  "recommendationCounts": {
    "strongBuy": 15,
    "buy": 10,
    "hold": 8,
    "sell": 1,
    "strongSell": 1,
    "total": 35
  },
  "consensusRecommendation": "Buy",
  "upgradesDowngrades": [...],
  "earningsEstimate": {...},
  "revenueEstimate": {...}
}
```

**Errors:** `404` ticker not found, `500` data fetch failure.

---

## GET `/api/recommendations/progress`

Returns progress updates during the batch S&P 500 data fetch.

**Response (200)**

```json
{
  "status": "fetching",
  "progress": 250,
  "stocks": 232,
  "total": 503
}
```

**Note:** field names are `progress` / `stocks` / `total` (not `fetched` / `pct` as in earlier docs).

---

## User Data Endpoints

All user data endpoints require `Authorization: Bearer <token>`. Returns `401` if missing or invalid.

### GET `/api/user/watchlists`

List all watchlists with their ticker items.

**Response (200)**

```json
{
  "watchlists": [
    {
      "id": 1,
      "name": "Tech Stocks",
      "created_at": "...",
      "items": [
        { "id": 1, "ticker": "AAPL", "added_at": "..." }
      ]
    }
  ]
}
```

### POST `/api/user/watchlists`

Create a new watchlist.

**Request body:** `{ "name": "string (required)" }`

**Response (201):** `{ "watchlist": { ... } }`

### POST `/api/user/watchlists/<id>/items`

Add a ticker to a watchlist.

**Request body:** `{ "ticker": "AAPL" }`

**Response (201):** `{ "item": { ... } }`

**Errors:** `404` watchlist not found or not owned, `409` ticker already in watchlist.

### DELETE `/api/user/watchlists/<id>/items/<ticker>`

Remove a ticker from a watchlist.

**Response (200):** `{ "message": "Removed" }`

---

### GET `/api/user/portfolio`

List all portfolio holdings.

**Response (200)**

```json
{
  "holdings": [
    {
      "id": 1,
      "ticker": "AAPL",
      "shares": 10.0,
      "cost_basis": 150.00,
      "acquired_at": "2024-01-15",
      "notes": "Long-term hold",
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

### POST `/api/user/portfolio`

Add a new holding.

**Request body:** `{ "ticker": "AAPL", "shares": 10, "cost_basis": 150.00, "acquired_at": "2024-01-15", "notes": "optional" }`

**Response (201):** `{ "holding": { ... } }`

### PUT `/api/user/portfolio/<id>`

Update an existing holding. Accepts any subset of: `ticker`, `shares`, `cost_basis`, `acquired_at`, `notes`.

**Response (200):** `{ "holding": { ... } }`

### DELETE `/api/user/portfolio/<id>`

Remove a holding.

**Response (200):** `{ "message": "Deleted" }`

---

### GET `/api/user/settings`

Get user settings (auto-creates defaults on first call).

**Response (200)**

```json
{
  "settings": {
    "default_strategy": "none",
    "default_date_range_months": 6,
    "updated_at": "..."
  }
}
```

### PUT `/api/user/settings`

Update settings. Accepts any subset of: `default_strategy`, `default_date_range_months`.

**Response (200):** `{ "settings": { ... } }`

---

## Error Responses

All endpoints return errors in this shape:

```json
{ "error": "Human-readable error message" }
```

| HTTP Status | Meaning |
|-------------|---------|
| `400` | Invalid parameter (e.g. unknown strategy key, validation failure) |
| `401` | Missing, invalid, or expired auth token |
| `404` | Ticker not found or no data available |
| `409` | Conflict (e.g. duplicate email/username, ticker already in watchlist) |
| `429` | Rate limit exceeded (`Too many requests. Please try again later.`) |
| `500` | Yahoo Finance error, rate limit, or network timeout |

Rate limit errors surface as: `"Yahoo Finance rate limit reached. Wait a moment and try again."`

---

## GET `/health`

Health check endpoint. No auth required.

**Response (200)**

```json
{ "status": "ok" }
```

---

## Admin Endpoints

All admin endpoints require `Authorization: Bearer <token>` with `is_admin = true` on the user. Wrong-role returns `403`.

### GET `/api/admin/users`
List all users (sorted by creation date ascending).
**Response (200):** `{ "users": [ { id, username, email, is_admin, created_at, last_login_at }, ... ] }`

### DELETE `/api/admin/users/<id>`
Delete a user and cascade their watchlists, portfolio holdings, settings. Cannot delete yourself (`400`) or another admin (`403`). Rate-limited 10/min.

### PATCH `/api/admin/users/<id>/role`
Grant or revoke admin. Body `{ "is_admin": bool }`. Cannot change your own role. Rate-limited 10/min.

### POST `/api/admin/metrics/start/<minutes>`
Start a yfinance-queue metrics recording. `minutes` must be `5` or `10`. Captures per-minute snapshots of call/success/failure/timeout/cache-hit counts + per-endpoint counts.
**Response:** `{ "status": "started" | "already_recording", "starts_at": <epoch> }`

### GET `/api/admin/metrics/status`
Return the in-progress recording state and any captured snapshots so far.

### POST `/api/admin/metrics/clear`
Wipe recorded data. Returns `{ "status": "cleared" }`.

---

## Custom ETF Endpoints

Reads available to any logged-in user; writes are admin-only or use the internal-secret header. Auto-rebalance has a 24h cooldown unless `force=true` is set.

### GET `/api/custom-etf/strategies`
List all registered strategies (id, name, description, buy/sell thresholds, max positions, starting capital).

### GET `/api/custom-etf/summary`
Headline stats for every strategy — drives the multi-ETF comparison sidebar.

### GET `/api/custom-etf/<strategy_id>/state`
Full portfolio state: positions, trades, equity series, summary metrics.

### GET `/api/custom-etf/<strategy_id>/rankings`
Score every Recommendations row against the strategy, return ranked list.

### POST `/api/custom-etf/<strategy_id>/rebalance` (admin)
Run a single rebalance pass. Body `{ "force": true }` bypasses the 24h cooldown.

### POST `/api/custom-etf/<strategy_id>/reset` (admin)
Wipe portfolio state and restart from `starting_capital`.

### POST `/api/custom-etf/auto-rebalance-all`
Rebalance every registered strategy. Called by the ETF Rebalance Lambda. Requires `X-Internal-Secret` header matching `INTERNAL_API_SECRET` env, OR admin auth.

### POST `/api/custom-etf/markov-regime/backtest` (admin)
Submit a long-running Markov-regime portfolio backtest job. Returns `{ "job_id": "..." }`.

### GET `/api/custom-etf/backtest/<job_id>`
Poll job status. Response: `{ "status": "running" | "complete" | "failed", "progress": 0-100, "result": {...} | null, "error": str | null }`.

---

## Markov Endpoint

### GET `/api/markov/<ticker>`
Per-ticker Markov regime analysis. Query params: `start`, `end` (defaults to last 365 days). Returns current regime label, 3×3 transition matrix, stationary distribution, and N-step forecasts (1, 3, 5, 10 bars).

**Errors:** `404` no data, `422` insufficient history (need at least `LOOKBACK + 1` bars).

---

## User Watchlist Data (Bulk)

### GET `/api/user/watchlists/<id>/data`
Returns the watchlist with each item enriched with current price, percent change, ATR, and other live fields. Rate-limited 10/min. Used by the Watchlist tab to render the table without per-row fetches.

### GET `/api/user/watchlists/<id>/data/<ticker>`
Single-ticker enriched view of a watchlist row. Useful for refresh-one-row UX.

---

## PATCH `/api/auth/me`

Update the current user's email and/or password. Requires `Authorization: Bearer <token>`. Rate-limited 10/min.
**Body** (any subset): `{ "email": str, "current_password": str, "new_password": str }`

---

## Debug Endpoint (no auth)

### GET `/api/debug/yfinance/<ticker>`

Returns raw yfinance dump (info dict, history columns/dtypes, sample rows) for diagnostic purposes. **No auth required — information disclosure surface, should be gated or removed in production.**

---

## Out-of-band Notes

- The Recommendations response includes Markov fields not yet listed in the spec above: `markovRegime` (`Bull` | `Sideways` | `Bear`), `markovBull3d`, `markovBull5d`, `markovBear5d`. All `number | null`.
- The `/api/stock-info` response returns many more fields than this spec enumerates — including company overview (`longBusinessSummary`, `fullTimeEmployees`, `website`, `city`, `state`, `country`), share/float counts (`sharesOutstanding`, `floatShares`), ISS governance risks (`auditRisk`, `boardRisk`, `compensationRisk`, `shareHolderRightsRisk`, `overallRisk`), split history (`lastSplitFactor`, `lastSplitDate`), and the insider/institutional payloads (`insiderTransactions`, `insiderNet90d`, `insiderNet90dValue`, `institutionalHolders`, `institutionalMajor`, `institutionalCount`). When adding new analysis cards, treat all of these as optional / nullable.

---

## Maintenance Note

**Update this file when:**
- A new endpoint is added → add its full request/response contract
- An existing endpoint gains new query params or response fields
- A strategy endpoint is added or removed
- The backtest `strategy` param gains new supported values
