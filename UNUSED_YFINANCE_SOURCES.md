# Unused yfinance Data Sources

13 yfinance attributes available but not currently used in Hatfield Financial.
Your existing `data_fetcher.py` throttle (`_MIN_CALL_INTERVAL = 0.25s`) and `_fetch_with_retry` pattern apply to all of these.

---

## General Rate Limiting Notes

yfinance scrapes Yahoo Finance's unofficial API. There are **no officially documented rate limits** — Yahoo enforces them dynamically. In practice:

- **~2,000 requests/hour** per IP before throttling kicks in
- HTTP 429 responses increase in frequency after sustained bursts of 5+ req/sec
- Financial statement endpoints (balance sheet, income stmt, cashflow) are the most aggressive rate-limit triggers because each one scrapes multiple Yahoo pages
- Your existing 4 calls/sec throttle is at the upper edge — consider dropping to 2/sec when adding batch financial statement fetches
- Multithreading with >5 concurrent yfinance calls is known to produce empty DataFrames silently (no error, just missing data)

---

## 1. `stock.insider_transactions`

**What it returns:** DataFrame of recent insider buy/sell transactions.

| Column | Type | Description |
|--------|------|-------------|
| Insider | str | Name of the insider |
| Position | str | Title (CEO, CFO, Director, etc.) |
| Transaction | str | "Buy", "Sale", "Stock Award", etc. |
| Start Date | datetime | Filing/transaction date |
| Shares | int | Number of shares transacted |
| Value | float | Dollar value of the transaction |
| URL | str | Link to SEC filing |
| Text | str | Description of the transaction |

**Rate limit risk:** Moderate. Scrapes SEC filing data. 5-10 sequential calls may trigger 429.

**Concerns:**
- Returns empty DataFrame for many small/mid-cap tickers — Yahoo doesn't publish data for all insiders
- Data lags SEC Form 4 filings by 1-3 business days
- Lookback window is typically 90-180 days (undocumented, varies by ticker)
- "Stock Award" transactions are not the same as open-market purchases — filter these out if you want to detect genuine insider conviction buying
- Delisted or OTC tickers return nothing

**Recommended TTL:** 1 hour

---

## 2. `stock.insider_roster_holders`

**What it returns:** DataFrame of named insiders and their most recent trades.

| Column | Type | Description |
|--------|------|-------------|
| Name | str | Insider name |
| Relation | str | Relationship to company |
| Url | str | SEC filing link |
| Most Recent Trade | str | "Buy" or "Sell" |
| Latest Trade Date | datetime | Date of last transaction |
| Position | str | Title or role |

**Rate limit risk:** Low.

**Concerns:**
- Only sourced from Form 3 & Form 4 filings from the last ~24 months
- Sparse for small-cap, international, or newly listed stocks
- Duplicate rows possible if an insider held multiple positions (e.g., both Director and 10% Owner)
- URL field is sometimes `None`
- Lower value than `insider_transactions` — this is a roster, not a transaction log

**Recommended TTL:** 4 hours

---

## 3. `stock.institutional_holders`

**What it returns:** DataFrame of top institutional holders from 13F SEC filings.

| Column | Type | Description |
|--------|------|-------------|
| Holder | str | Fund/institution name |
| Shares | int | Number of shares held |
| Date Reported | datetime | 13F filing date |
| % Out | float | Percentage of outstanding shares |
| Value | float | Dollar value of holding |

**Rate limit risk:** Low. Single endpoint, data changes quarterly.

**Concerns:**
- **13F data is 45 days stale** — filings are due 45 days after quarter-end, so the data you see reflects holdings from ~1.5 months ago
- Only institutions managing >$100M in qualifying securities are required to file 13F
- Micro-cap and non-US-listed stocks often return `None` or empty DataFrame
- No quarter-over-quarter change is provided — you'd need to cache and diff yourself to detect accumulation/distribution
- Passive index funds (Vanguard, BlackRock) will always appear at the top; they're not making active bets

**Recommended TTL:** 4 hours (quarterly data)

---

## 4. `stock.major_holders`

**What it returns:** Small DataFrame (4 rows) summarizing ownership breakdown.

| Row Label | Type | Description |
|-----------|------|-------------|
| % of Shares Held by All Insider | float | Insider ownership percentage |
| % of Shares Held by Institutions | float | Institutional ownership percentage |
| % of Float Held by Institutions | float | Float-adjusted institutional % |
| Number of Institutions Holding Shares | int | Count of institutional holders |

**Rate limit risk:** Very low. Lightweight single request.

**Concerns:**
- Some of this data already exists in `stock.info` as `heldPercentInsiders`, `heldPercentInstitutions` — check for duplication before adding a separate endpoint
- Float % calculation is inconsistent across tickers (Yahoo's methodology is opaque)
- Returns `None` for some international stocks

**Recommended TTL:** 4 hours

---

## 5. `stock.balance_sheet` / `stock.quarterly_balance_sheet`

**What it returns:** DataFrame with account line items as rows and fiscal periods as columns.

| Key Row Labels | Type | Description |
|----------------|------|-------------|
| Total Assets | float | USD |
| Current Assets | float | USD |
| Cash And Cash Equivalents | float | USD |
| Total Liabilities Net Minority Interest | float | USD |
| Current Liabilities | float | USD |
| Long Term Debt | float | USD |
| Stockholders Equity | float | USD |
| Net PPE | float | USD |
| Goodwill And Other Intangible Assets | float | USD |

Columns are datetime objects representing fiscal period end dates (most recent first). Typically 4 annual periods or 4-5 quarterly periods.

**Rate limit risk:** HIGH. Multiple endpoint scrapes per ticker. Sequential calls for >10 tickers often trigger 429.

**Concerns:**
- **Empty DataFrames are a widespread, well-documented issue** (GitHub issues #191, #254, #419, #465). Yahoo frequently fails to return data even for large-cap US stocks.
- Quarterly data is significantly less reliable than annual — some tickers only have Q4 data, missing Q1-Q3
- Fiscal year-end varies by company (not always Dec 31) — column ordering can be confusing if you assume calendar alignment
- Row labels are not fully standardized — some tickers use slightly different names for the same line items
- International stocks may have values in local currency without conversion
- Data lags 60+ days from fiscal period end (SEC filing deadlines)
- **Multithreading is unreliable** — scanning many tickers with threads causes silent empty results after ~5 minutes (GitHub issue #1370)

**Recommended TTL:** 6 hours (data changes quarterly at most)

---

## 6. `stock.cashflow` / `stock.quarterly_cashflow`

**What it returns:** DataFrame with cash flow statement line items as rows and fiscal periods as columns.

| Key Row Labels | Type | Description |
|----------------|------|-------------|
| Operating Cash Flow | float | USD |
| Capital Expenditure | float | USD (negative value) |
| Free Cash Flow | float | USD |
| Investing Cash Flow | float | USD |
| Financing Cash Flow | float | USD |
| Issuance Of Debt | float | USD |
| Repayment Of Debt | float | USD |
| Common Stock Dividend Paid | float | USD (negative value) |
| Repurchase Of Capital Stock | float | USD (negative value) |

Same column structure as balance_sheet (fiscal period datetime columns).

**Rate limit risk:** HIGH. Same multi-scrape pattern as balance_sheet.

**Concerns:**
- Same empty DataFrame problem as balance_sheet — GitHub issues #191, #465, #475
- Quarterly data frequently missing or misaligned with income statement quarters
- Free Cash Flow calculation is inconsistent — some tickers require manual calc (Operating CF - CapEx) because the FCF row is missing
- Capital Expenditure is sometimes positive, sometimes negative depending on the ticker — normalize the sign
- Currency conversion not always applied for foreign entities
- Often requested alongside balance_sheet — making both calls together significantly increases 429 risk

**Recommended TTL:** 6 hours

---

## 7. `stock.income_stmt` / `stock.quarterly_income_stmt`

**What it returns:** DataFrame with P&L line items as rows and fiscal periods as columns.

| Key Row Labels | Type | Description |
|----------------|------|-------------|
| Total Revenue | float | USD |
| Cost Of Revenue | float | USD |
| Gross Profit | float | USD |
| Operating Expense | float | USD |
| Operating Income | float | USD |
| EBITDA | float | USD |
| Net Income | float | USD |
| Basic EPS | float | USD per share |
| Diluted EPS | float | USD per share |
| Tax Provision | float | USD |

**Rate limit risk:** VERY HIGH. Multiple sequential scrapes per ticker. Multithreading is unreliable.

**Concerns:**
- **quarterly_income_stmt is the most unstable of all financial statement endpoints** (GitHub issue #1345). Non-US stocks (AALB.AS, BHP.L, CFR.SW) frequently return empty DataFrames
- Multithreading to scan many tickers causes empty results after ~5 minutes silently (no exception thrown — just empty data)
- Row labels vary: some tickers use "Total Revenue", others use "Revenue" or "Net Revenue"
- EBITDA row is sometimes missing — calculate manually from Operating Income + Depreciation
- Quarterly data is worse than annual across the board
- Revenue recognition and accounting method variations are not normalized

**Recommended TTL:** 6 hours

---

## 8. `stock.earnings_history`

**What it returns:** DataFrame of historical EPS actuals vs. estimates.

| Column | Type | Description |
|--------|------|-------------|
| Quarter | str | e.g., "Q1 2026", "4Q2025" |
| epsActual | float | Reported EPS |
| epsEstimate | float | Consensus estimate before announcement |
| epsDifference | float | Actual - Estimate |
| surprisePercent | float | Surprise as percentage |

**Rate limit risk:** Low-Moderate.

**Concerns:**
- Lookback is typically 8-12 quarters — exact window is undocumented and varies by ticker
- **Surprise % is unreliable when expected EPS is near zero** — a $0.01 beat on a $0.01 estimate shows as 100% surprise, which is misleading
- Pre-market/after-hours adjustments not always applied (the "actual" EPS may be the initial report, not the restated figure)
- Delayed by 1-2 business days from actual earnings announcement
- No forward guidance or revised estimates — this is a static backward-looking snapshot
- Quarter label format is inconsistent ("Q1 2026" vs "1Q2026" vs other formats)

**Recommended TTL:** 1 hour

---

## 9. `stock.options`

**What it returns:** Tuple of date strings (available option expiration dates).

```python
('2026-04-10', '2026-04-17', '2026-04-24', '2026-05-01', ...)
```

**Rate limit risk:** Very low. Single lightweight request.

**Concerns:**
- Returns a tuple, not a DataFrame — handle type differently from other attributes
- Typically includes 1-2 years of forward expirations (weeklies + monthlies + quarterlies)
- Illiquid or zero-open-interest expirations may not appear
- Non-optionable stocks (some small-caps, ADRs) return an empty tuple
- Delisted or suspended tickers return empty tuple with no error

**Recommended TTL:** 30 minutes

---

## 10. `stock.option_chain(expiry)`

**What it returns:** Named tuple with `.calls` and `.puts` DataFrames.

| Column | Type | Description |
|--------|------|-------------|
| contractSymbol | str | Option contract identifier |
| lastTradeDate | datetime | Last time this contract traded |
| strike | float | Strike price |
| lastPrice | float | Last traded price |
| bid | float | Current bid |
| ask | float | Current ask |
| change | float | Price change |
| percentChange | float | Percent change |
| volume | int | Day's trading volume |
| openInterest | int | Open interest |
| impliedVolatility | float | IV (0-1 scale, e.g., 0.35 = 35%) |
| inTheMoney | bool | Whether the option is ITM |
| contractSize | str | "REGULAR" (100 shares) |
| currency | str | "USD" |

**Rate limit risk:** HIGH. **Each expiry date requires a separate HTTP request.** A stock with 50+ expirations means 50+ calls — this will trigger 429 fast.

**Concerns:**
- **This is the most dangerous endpoint for rate limiting** — always limit to 1-3 nearest expirations, never fetch all
- Bid/ask spreads are unreliable for far OTM strikes (wide spreads, zero volume)
- Implied volatility is last-trade-based, not real-time — can be hours or days stale for illiquid strikes
- Volume and open interest are 0 for most strikes >20% out of the money
- **No Greeks** (delta, gamma, vega, theta) — you'd need to calculate these yourself using Black-Scholes
- `lastTradeDate` can be days or weeks old for illiquid contracts — check before displaying as "current"
- Filter to near-the-money strikes (within 10-15% of current price) to keep data meaningful

**Recommended TTL:** 5 minutes (options data is time-sensitive)

---

## 11. `stock.news`

**What it returns:** List of dictionaries (not a DataFrame).

```python
[
    {
        "uuid": "abc123...",
        "title": "Company Reports Q1 Earnings Beat",
        "publisher": "Reuters",
        "link": "https://...",
        "providerPublishTime": 1712505000,  # Unix timestamp
        "type": "STORY",
        "relatedTickers": ["AAPL", "MSFT"]
    },
    ...
]
```

**Rate limit risk:** Moderate-High. Scrapes Yahoo's news aggregator, which is more aggressively rate-limited than financial data endpoints.

**Concerns:**
- **Endpoint is unreliable** — the library has had multiple fixes for "faulty response objects." No uptime guarantee
- `providerPublishTime` is a Unix timestamp (seconds) — must convert to datetime
- News lags wire services by 1-6 hours — not suitable for real-time news trading
- Coverage biased toward large-cap stocks; micro-caps may get 0-2 articles per day
- Duplicates are common (same story syndicated across Reuters, AP, Bloomberg)
- `type` field: filter to `"STORY"` — other types include `"VIDEO"` and ads
- Summary/description text is often truncated or missing entirely
- Links may be behind paywalls
- Consider an alternative provider (NewsAPI, IEX Cloud) if reliability matters

**Recommended TTL:** 15 minutes

---

## 12. `stock.dividends`

**What it returns:** Pandas Series with DatetimeIndex.

```python
Date
2025-01-15    0.25
2025-04-15    0.25
2025-07-15    0.26
2025-10-15    0.26
2026-01-15    0.26
Name: Dividends, dtype: float64
```

**Rate limit risk:** Very low. Single lightweight request.

**Concerns:**
- The index date is the **ex-dividend date**, not the payment date — these differ by 1-5 business days. Don't label it as "payment date"
- Special/one-time dividends are sometimes omitted or mixed in without distinction from regular dividends
- Stock dividends (shares distributed instead of cash) may appear and inflate the series — filter by checking for unusually large values
- **International stocks report dividends in local currency** — no USD conversion applied. You'd need to convert manually
- The `Dividends` column is actually already present in `stock.history()` output (which `get_ohlcv()` fetches) — it's just never extracted. You could get this data without a separate API call by filtering the existing OHLCV DataFrame for non-zero `Dividends` values
- Lookback is typically 5-10 years
- Non-dividend-paying stocks return an empty Series (not None) — check `.empty`

**Recommended TTL:** 6 hours (dividends are declared weeks in advance)

---

## 13. `stock.splits`

**What it returns:** Pandas Series with DatetimeIndex.

```python
Date
2014-06-09    7.0    # 7:1 split (AAPL)
2020-08-31    4.0    # 4:1 split (AAPL)
Name: Stock Splits, dtype: float64
```

**Rate limit risk:** Very low. Single lightweight request.

**Concerns:**
- Reverse splits appear as values <1.0 (e.g., 0.5 for a 1:2 reverse split) — display these differently since reverse splits are usually a bearish signal
- The `Stock Splits` column is also present in `stock.history()` output — same as dividends, you could extract from existing OHLCV data without a separate call
- Spin-offs are NOT included as splits — these require manual handling
- Special corporate actions (rights offerings, warrant distributions) are occasionally misclassified as splits
- Lookback is typically 20+ years
- Most stocks have very few splits (0-3 in their entire history) — the Series will usually be very short
- Non-splitting stocks return an empty Series

**Recommended TTL:** 24 hours (splits are rare events)

---

## Risk Summary Table

| Source | Rate Limit Risk | Empty Data Risk | Data Staleness | Worth Adding? |
|--------|----------------|-----------------|----------------|---------------|
| insider_transactions | Moderate | Moderate | 1-3 days | Yes |
| insider_roster_holders | Low | Moderate | Weeks | Low priority |
| institutional_holders | Low | Low (large-cap) | 45 days | Yes |
| major_holders | Very Low | Low | Weeks | Yes (trivial) |
| balance_sheet / quarterly | **HIGH** | **HIGH** | 60+ days | Yes, with caution |
| cashflow / quarterly | **HIGH** | **HIGH** | 60+ days | Yes, with caution |
| income_stmt / quarterly | **VERY HIGH** | **VERY HIGH** | 60+ days | Yes, with caution |
| earnings_history | Low-Moderate | Low | 1-2 days | Yes |
| options (expiry list) | Very Low | Low | N/A | Yes |
| option_chain(expiry) | **HIGH** | Moderate | Minutes-days | Yes, limit to 1-3 expiries |
| news | Moderate-High | Moderate | 1-6 hours | Yes, but unreliable |
| dividends | Very Low | None (empty = no divs) | N/A | Yes (already in OHLCV) |
| splits | Very Low | None (empty = no splits) | N/A | Yes (already in OHLCV) |

---

## Implementation Advice

### Safe to add immediately (low risk, high value)
- **dividends** and **splits** — already in the OHLCV DataFrame from `get_ohlcv()`. Just filter for non-zero rows. Zero additional API calls needed.
- **earnings_history** — lightweight endpoint, high analytical value for PEAD strategy.
- **major_holders** — single tiny request, useful context.
- **insider_transactions** — moderate rate limit risk but high signal value.

### Add with care (rate limit sensitive)
- **institutional_holders** — safe individually but cache aggressively (4h+ TTL) since it's quarterly data.
- **news** — the endpoint itself is unreliable. Wrap in a try/except that gracefully returns empty. Don't let a news failure block the page load.
- **option_chain** — **never fetch all expiries**. Limit to the 1-3 nearest expirations. Add a 2-second delay between expiry fetches. Consider a dedicated rate limit bucket separate from your main throttle.

### Add with significant caution (high failure rate)
- **balance_sheet, cashflow, income_stmt** (annual + quarterly = 6 endpoints) — these are the most problematic yfinance attributes. Empty DataFrames are common even for large-cap US stocks. **Do not batch these across many tickers** — fetch on-demand for a single ticker only. Always validate the DataFrame is non-empty before caching. Use sequential fetching (not ThreadPoolExecutor) to avoid silent empty results. Consider a fallback message ("Financial statements unavailable for this ticker") as a first-class UI state.

### Probably skip
- **insider_roster_holders** — low incremental value over `insider_transactions`.
