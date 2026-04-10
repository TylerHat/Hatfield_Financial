# yfinance Screener Reference

Notes on using `yf.screen()`, `PREDEFINED_SCREENER_QUERIES`, and `EquityQuery` for the Hatfield Financial project.

> **Applies to:** `yfinance >= 0.2.50` (when the screener module was added via [PR #2066](https://github.com/ranaroussi/yfinance/pull/2066)).

---

## 1. Rate Limits

### The important thing
`PREDEFINED_SCREENER_QUERIES` itself is a **Python dict** — accessing it costs nothing. The rate limit applies when you *execute* a query with `yf.screen(...)`, which calls Yahoo's screener API.

### What Yahoo enforces
- **No officially documented rate limit.** Yahoo publishes nothing.
- **Community consensus** (from [yfinance discussion #2129](https://github.com/ranaroussi/yfinance/discussions/2129) and [issue #2152](https://github.com/ranaroussi/yfinance/issues/2152)): stay under ~**2 requests per 5 seconds** to avoid 429s and IP bans.
- Exceeding this triggers progressively longer temporary blocks.

### Result size caps (hard Yahoo limits)
| Query type | Parameter | Default | Max |
|---|---|---|---|
| Predefined | `count` | 25 | **250** |
| Custom (`EquityQuery`) | `size` | 100 | **250** |

Pagination beyond 250 is not supported in a single call — you must make multiple calls with an offset.

### Recommended: `CachedLimiterSession`
Combine `requests_cache` + `pyrate_limiter` so repeated calls hit the local cache and new calls are throttled:

```python
from requests import Session
from requests_cache import CacheMixin, SQLiteCache
from requests_ratelimiter import LimiterMixin, MemoryQueueBucket
from pyrate_limiter import Duration, RequestRate, Limiter
import yfinance as yf

class CachedLimiterSession(CacheMixin, LimiterMixin, Session):
    pass

session = CachedLimiterSession(
    limiter=Limiter(RequestRate(2, Duration.SECOND * 5)),  # 2 req / 5s
    bucket_class=MemoryQueueBucket,
    backend=SQLiteCache("yfinance.cache"),
)

# Pass the session to yfinance calls
yf.Ticker("AAPL", session=session)
```

### How this project already handles it
[Backend/data_fetcher.py](Backend/data_fetcher.py) already uses tiered TTL caching on `yfinance` calls to minimize hits to Yahoo. Any new screener usage should route through the same pattern rather than calling `yf.screen()` directly from a route — otherwise you'll share the same global rate budget as the recommendations prewarm job.

---

## 2. Predefined Queries

### Listing them
```python
import yfinance as yf
print(list(yf.PREDEFINED_SCREENER_QUERIES.keys()))
```

### Common keys
Names may change between yfinance versions — always verify with the `keys()` call above.

| Key | What it returns |
|---|---|
| `aggressive_small_caps` | Small caps with high growth metrics |
| `day_gainers` | Top % gainers today |
| `day_losers` | Top % losers today |
| `most_actives` | Highest volume today |
| `growth_technology_stocks` | High-growth tech names |
| `undervalued_growth_stocks` | Growth names trading below intrinsic value |
| `undervalued_large_caps` | Large caps on discount |
| `conservative_foreign_funds` | Low-risk foreign ETFs/funds |
| `high_yield_bond` | High-yield bond funds |
| `portfolio_anchors` | Core holding candidates |
| `small_cap_gainers` | Small-cap day gainers |
| `top_mutual_funds` | Top-rated mutual funds |

### Running a predefined query
```python
import yfinance as yf

result = yf.screen(
    yf.PREDEFINED_SCREENER_QUERIES["aggressive_small_caps"],
    count=50,   # default 25, max 250
    offset=0,
)

for quote in result["quotes"]:
    print(quote["symbol"], quote.get("shortName"), quote.get("regularMarketPrice"))
```

`result` is a dict containing:
- `quotes`: list of matching stock dicts
- `total`: total number available (can exceed `count`)
- `start`, `count`, `criteriaMeta`: pagination + the underlying criteria

---

## 3. Custom Queries with `EquityQuery`

### Operators
| Operator | Meaning | Example |
|---|---|---|
| `GT` | `>` | `EquityQuery("gt", ["marketcap", 1_000_000_000])` |
| `LT` | `<` | `EquityQuery("lt", ["peratio.lasttwelvemonths", 15])` |
| `EQ` | `=` | `EquityQuery("eq", ["region", "us"])` |
| `BTWN` | between (inclusive) | `EquityQuery("btwn", ["epsgrowth.lasttwelvemonths", 10, 50])` |
| `AND` | all children must match | combine sub-queries |
| `OR` | any child must match | combine sub-queries |

### Common screenable fields
Not all Yahoo fields are queryable. Frequently-usable ones:

- `region` — e.g. `"us"`, `"gb"`, `"de"`
- `sector` — e.g. `"Technology"`, `"Healthcare"`
- `industry`
- `exchange` — e.g. `"NMS"` (Nasdaq), `"NYQ"` (NYSE)
- `marketcap`
- `intradayprice`
- `peratio.lasttwelvemonths`
- `pegratio_5y`
- `epsgrowth.lasttwelvemonths`
- `dayvolume`
- `percentchange` (day % change)
- `fiftytwowkpercentchange`

For the full list, see the [yfinance.screener API reference](https://ranaroussi.github.io/yfinance/reference/yfinance.screener.html).

### Example: US large-cap value screen
```python
import yfinance as yf
from yfinance import EquityQuery

query = EquityQuery("and", [
    EquityQuery("eq", ["region", "us"]),
    EquityQuery("gt", ["marketcap", 10_000_000_000]),        # > $10B
    EquityQuery("lt", ["peratio.lasttwelvemonths", 20]),      # P/E < 20
    EquityQuery("gt", ["epsgrowth.lasttwelvemonths", 5]),     # EPS growth > 5%
])

result = yf.screen(query, size=100, sortField="marketcap", sortAsc=False)

for q in result["quotes"]:
    print(f"{q['symbol']:6} {q.get('shortName', '')[:30]:30} "
          f"${q.get('marketCap', 0)/1e9:>6.1f}B  "
          f"P/E {q.get('trailingPE', 'n/a')}")
```

### Example: high-momentum small caps
```python
from yfinance import EquityQuery

query = EquityQuery("and", [
    EquityQuery("eq", ["region", "us"]),
    EquityQuery("btwn", ["marketcap", 300_000_000, 2_000_000_000]),  # $300M–$2B
    EquityQuery("gt", ["fiftytwowkpercentchange", 25]),              # up 25%+ YoY
    EquityQuery("gt", ["dayvolume", 500_000]),                       # liquid
])
```

### Sorting
```python
result = yf.screen(
    query,
    size=50,
    sortField="percentchange",
    sortAsc=False,       # descending
)
```

Common `sortField` values: `marketcap`, `percentchange`, `dayvolume`, `intradayprice`, `peratio.lasttwelvemonths`.

### Pagination
```python
all_quotes = []
for offset in range(0, 1000, 250):           # 4 pages of 250
    result = yf.screen(query, size=250, offset=offset)
    all_quotes.extend(result["quotes"])
    if len(result["quotes"]) < 250:
        break                                  # ran out of matches
    time.sleep(3)                              # respect rate limit
```

---

## 4. Integration Notes for Hatfield Financial

- **Where to add screener calls:** wrap in a service under `Backend/` (e.g. `Backend/screener_service.py`), call from a new route in `Backend/routes/`, follow the pattern in [Backend/routes/recommendations.py](Backend/routes/recommendations.py). Never call `yf.screen()` directly from a route — cache the result.
- **Caching:** suggest TTL of 5–15 minutes for day-sensitive screens (`day_gainers`), 1+ hour for fundamental screens (`undervalued_large_caps`). Fits the tiered caching model in [Backend/data_fetcher.py](Backend/data_fetcher.py).
- **Rate-limit budget:** the recommendations prewarm job ([Backend/routes/recommendations.py](Backend/routes/recommendations.py)) already hammers yfinance with ~500 ticker fetches at startup. Add screener calls to the **same** throttled session, or offset the schedules so they don't collide.
- **Error handling:** Yahoo returns 429 and sometimes empty `{"quotes": []}` under load. Always check `len(result["quotes"])` and retry with exponential backoff on 429 — see the `MAX_RETRIES` pattern in [Frontend/src/api.js](Frontend/src/api.js) for inspiration.

---

## 5. References

- [yfinance Screener & Query reference](https://ranaroussi.github.io/yfinance/reference/yfinance.screener.html)
- [yf.screen() API](https://ranaroussi.github.io/yfinance/reference/api/yfinance.screen.html)
- [Screener System — DeepWiki](https://deepwiki.com/ranaroussi/yfinance/4.5-screener-system)
- [How to use Query and Screener (examples) — GitHub discussion #2129](https://github.com/ranaroussi/yfinance/discussions/2129)
- [Screener feature PR #2066](https://github.com/ranaroussi/yfinance/pull/2066)
- [Screener issue #2152 (size limits, rate limits)](https://github.com/ranaroussi/yfinance/issues/2152)
- [yfscreen: Yahoo Finance Screener in R and Python — IBKR Quant](https://www.interactivebrokers.com/campus/ibkr-quant-news/yfscreen-yahoo-finance-screener-in-r-and-python/)
