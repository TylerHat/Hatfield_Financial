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
  "rsi":         [58.3, ...]
}
```

All arrays are the same length and index-aligned to `dates`. Null where indicators lack enough history.

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
      "entry_date": "2024-01-10",
      "entry_price": 180.00,
      "exit_date": "2024-02-05",
      "exit_price": 192.50,
      "pnl": 125.00,
      "pnl_pct": 6.94
    }
  ],
  "equityCurve": [
    { "date": "2024-01-02", "equity": 10000.00 }
  ],
  "summary": {
    "totalReturn": 12.5,
    "totalReturnPct": 12.5,
    "winRate": 66.7,
    "totalTrades": 6,
    "maxDrawdown": -4.2,
    "sharpeRatio": 1.35,
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

**Rate limit:** 3 requests/hour per IP.

**Request body**

```json
{
  "username": "string (3-30 chars)",
  "email": "string (valid email)",
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
    "email": "tyler@example.com",
    "created_at": "2026-03-18T12:00:00"
  }
}
```

**Errors:** `400` validation failure, `409` email/username already exists.

---

### POST `/api/auth/login`

Authenticate and receive a JWT token. No auth required.

**Rate limit:** 5 requests/minute per IP.

**Request body**

```json
{
  "email": "string",
  "password": "string"
}
```

**Response (200)**

```json
{
  "token": "eyJhbGciOi...",
  "user": { "id": 1, "username": "tyler", "email": "tyler@example.com", "created_at": "..." }
}
```

**Errors:** `401` invalid credentials.

---

### GET `/api/auth/me`

Validate stored token and return current user. Requires `Authorization: Bearer <token>`.

**Response (200)**

```json
{
  "user": { "id": 1, "username": "tyler", "email": "tyler@example.com", "created_at": "..." }
}
```

**Errors:** `401` missing/invalid/expired token.

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

## Maintenance Note

**Update this file when:**
- A new endpoint is added → add its full request/response contract
- An existing endpoint gains new query params or response fields
- A strategy endpoint is added or removed
- The backtest `strategy` param gains new supported values
