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

## Error Responses

All endpoints return errors in this shape:

```json
{ "error": "Human-readable error message" }
```

| HTTP Status | Meaning |
|-------------|---------|
| `404` | Ticker not found or no data available |
| `400` | Invalid parameter (e.g. unknown strategy key) |
| `500` | Yahoo Finance error, rate limit, or network timeout |

Rate limit errors surface as: `"Yahoo Finance rate limit reached. Wait a moment and try again."`

---

## Maintenance Note

**Update this file when:**
- A new endpoint is added → add its full request/response contract
- An existing endpoint gains new query params or response fields
- A strategy endpoint is added or removed
- The backtest `strategy` param gains new supported values
