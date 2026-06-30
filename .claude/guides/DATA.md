# Hatfield Financial — Data Reference

Documents yfinance behavior, known quirks, and defensive patterns already established in the codebase.

---

## Data Source

All market data comes from **Yahoo Finance via the `yfinance` Python library**. No API key required.
Market data is cached in-memory via `data_fetcher.py` with tiered TTLs (OHLCV 5-min, info **10-min**, SPY 10-min, earnings 1-hr, analyst 30-min, insider/institutional/news 1-hr). All yfinance HTTP calls funnel through a single-worker priority queue (`YFinanceQueue`) with min inter-call interval `0.3 s` and starvation promotion after 30 s. User data is stored in SQLite (local + prod-on-EFS; the RDS Postgres module exists but is not wired up).

---

## yfinance Key Behaviors

### Ticker Object

```python
stock = yf.Ticker("AAPL")
hist  = stock.history(start=..., end=...)
info  = stock.info
```

### `stock.history()` — OHLCV DataFrame

- Returns a pandas DataFrame with a DatetimeIndex
- Columns: `Open`, `High`, `Low`, `Close`, `Volume`, `Dividends`, `Stock Splits`
- Index is timezone-aware (UTC) for most tickers — check `hist.index.tz` before comparing with `pd.Timestamp`

**Timezone handling pattern** used throughout all strategy files:

```python
cutoff = pd.Timestamp(user_start).tz_localize('UTC')
if hist.index.tz is None:
    cutoff = cutoff.tz_localize(None)
hist = hist[hist.index >= cutoff]
```

Always do this when trimming `hist` to a user date window. Do not assume UTC or naive.

### `stock.info` — Fundamentals Dict

- Returns a flat dict of ~100+ fields sourced from Yahoo Finance
- **Many fields can be `None`, missing, or `'N/A'`** — always use `safe_float()` pattern:

```python
def safe_float(key, decimals=2):
    val = info.get(key)
    if val is None or val == 'N/A':
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, decimals)
    except Exception:
        return None
```

- **NaN/Inf guard**: yfinance can return `float('nan')` or `float('inf')` for fields like P/E ratios (near-zero earnings). These serialize as invalid JSON (`NaN`/`Infinity`) and break browser JSON parsing. The `math.isnan()`/`math.isinf()` check converts them to `None` → JSON `null`.
- `currentPrice` is sometimes `None` — fall back to `regularMarketPrice`
- `marketCap` can be very large — format with `fmt_large()` helper
- `recommendationKey` uses underscores (e.g. `'strong_buy'`) — replace with spaces and title-case for display

### `stock.get_earnings_dates()` — Earnings Calendar (primary)

- Returns a DataFrame of upcoming and recent earnings dates
- **Unreliable**: can raise exceptions, return `None`, or return an empty DataFrame
- Always wrap in `try/except` and check `if earnings is not None and not earnings.empty`
- Timezone of `earnings.index` may differ from `hist.index` — align before comparison (see `post_earnings_drift.py`)
- Accessed via `data_fetcher.get_earnings_dates(ticker, limit, priority)` with a 1-hour TTL. **Cache key currently ignores `limit`** — first caller wins; mixing `limit=4` and `limit=20` across callers will share a single cached DataFrame.

### `stock.news` — Recent Headlines

- Accessed via `data_fetcher.get_news(ticker, limit=10, priority)` with a **1-hour TTL** (`_NEWS_TTL`).
- Normalizes each item to a stable shape `{title, publisher, link, publishTime (ISO str), summary}`, drops items without a title, sorts newest-first, and truncates to `limit`.
- **Format varies across yfinance versions** — `_normalize_news_item()` tolerates both the legacy flat dict (`title`/`publisher`/`link`/`providerPublishTime` epoch/`summary`) and the newer nested `content` dict (`provider.displayName`, `canonicalUrl`/`clickThroughUrl`, `pubDate`/`displayTime` ISO). Returns `None` on failure (no news, or none had a title).
- `summary` is frequently sparse or absent — treat it as optional.
- Consumed by the Ollama report generator (`sandbox_ollama.py`); no Flask route exposes it yet.

### `stock.calendar` (not used)

The previous design also fell back to `stock.calendar`, but the current code path uses only `get_earnings_dates()`. The `stock.calendar` field format varies across yfinance versions and is fragile; if you need to re-add it, wrap in `try/except` and verify the format.

---

## Warmup Periods

Each strategy fetches extra history before `start` so rolling indicators are stable before the user's window. The route trims `hist` to the user window after computing. Per-strategy warmup values are listed in `FIN_STRATEGIES.md`. The `/api/backtest` endpoint mirrors these in its own `warmup_map` dict.

---

## RSI Implementation

Two slightly different RSI implementations exist in the codebase:

**`stock_data.py` and `stock_info.py`** — uses `ewm(com=period-1)`:
```python
avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
```

**`rsi.py` strategy** — uses `ewm(alpha=1/period)` (Wilder's formula):
```python
avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
```

Both approximate Wilder's smoothing. The `alpha=1/period` version in `rsi.py` is more precise.
RSI values will differ slightly between the `/api/stock` endpoint and the `/api/strategy/rsi` endpoint.

---

## Rate Limits

Yahoo Finance enforces undocumented rate limits. Heavy or rapid requests will return HTTP 429 or connection errors.

All route handlers catch this pattern:

```python
except Exception as e:
    msg = str(e)
    if 'rate' in msg.lower() or '429' in msg:
        msg = 'Yahoo Finance rate limit reached. Wait a moment and try again.'
    elif 'connection' in msg.lower() or 'timeout' in msg.lower():
        msg = 'Could not reach Yahoo Finance. Check your network connection.'
    return jsonify({'error': msg}), 500
```

This pattern must be used in any new route handler.

---

## Relative Strength — Dual Fetch

The `relative-strength` strategy fetches **two tickers simultaneously**: the target ticker and SPY:

```python
stock = yf.Ticker(ticker.upper())
spy   = yf.Ticker('SPY')
hist     = stock.history(...)
spy_hist = spy.history(...)
```

Then aligns on common dates via `pd.DataFrame({'stock': ..., 'spy': ...}).dropna()`.
This `dropna()` drops any dates where one of the two had no data (market holidays, new listings, etc.).

---

## Null / NaN Handling

All numeric output to JSON uses a `safe_list()` or `safe_float()` pattern to convert `NaN` to `null`:

```python
def safe_list(series):
    return [None if pd.isna(v) else round(float(v), 4) for v in series]
```

Frontend Chart.js handles `null` values by leaving gaps in lines — this is intentional and correct behavior for indicators that lack enough history at the start of the date range.

---

## Large Number Formatting

The `fmt_large()` helper in `stock_info.py` formats market cap and free cash flow:

| Value | Output |
|-------|--------|
| ≥ 1T | `$2.85T` |
| ≥ 1B | `$1.20B` |
| ≥ 1M | `$450.00M` |
| < 1M | `$123,456` |

---

## Known Limitations

- **No real-time data**: yfinance returns delayed/end-of-day prices for most tickers
- **Crypto tickers**: yfinance accepts `BTC-USD`-style symbols and the watchlist / portfolio columns now accommodate 20-char tickers (per the prod migration), but earnings/analyst data is unavailable for crypto. `sp500.py` only contains the S&P 500 list plus a fallback list — there is no `CRYPTO_TICKERS` constant.
- **International tickers**: may work with exchange suffixes (e.g. `ASML.AS`) but timezone handling becomes more complex
- **Earnings dates**: only reliable for ~2 years of history; far-future dates may be estimates
- **`info` dict instability**: yfinance occasionally changes field names across library versions — if a field goes missing, `safe_float()` returns `None` gracefully
- **Negative caching**: `get_ticker_info` skips caching when the response is falsy → every request re-fetches Yahoo for permanently-bad tickers. Cost-relevant.
- **Caching**: in-memory tiered TTL via `data_fetcher.py`. Not persistent across restarts. The Recommendations payload is the exception — it is mirrored to S3 by the precompute Lambda (`S3_CACHE_BUCKET` env) in prod.

---

## Maintenance Note

**Update this file when:**
- A new data source is added (not just yfinance)
- A new yfinance quirk or defensive pattern is discovered
- The RSI implementation is standardized across the codebase
- The caching strategy changes (TTLs, persistence, new providers)
- A new `stock.info` field is used and has known null behavior
