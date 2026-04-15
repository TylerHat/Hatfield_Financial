# Major Features
## Features
- add stock splits and divedends to font
- Adding other yfinance ONLY ADD IF IT DOESNT BOG DOWN SYSTEM AND EASY TO GET. NOT OVER THE TOP API GRABS
    * major_holders
    * earnings_history
    * dividends
    * splits
    * institutional_holders
- Potentially add a noteworthy tab that displays stock-splits and their dates. also potentially add nearest earnings reports?

If a stock is delisted dont ask for its info anymore.

# Minor Improvments
- Need to review strategies to usefulness. Maybe delete or add new ones
- Verify that Key Metrics and Fundimental data are accurate. % might not be calulated correctly
- Potentially Add Texas Stock Exchange if not already included
    * Not currently included — all market data comes from Yahoo Finance via yfinance (Backend/data_fetcher.py)
    * TXSE is pre-launch (targeting 2026); no public feed exists yet
    * Revisit once TXSE lists securities — if Yahoo ingests the TXSE feed, tickers may work through the existing pipeline (possibly with an exchange suffix like `.TX`); otherwise a separate provider integration would be needed

---

## New Feature Recommendations (added 2026-04-11)

Each entry: Reward (1-10 investor value) / Effort (1-10 implementation cost) / Score = Reward / Effort (higher = better ROI).

---

### 1. Multi-Strategy Signal Consensus on Single Ticker
**Description**: Run all 9 strategies against a ticker simultaneously and return a composite score (e.g. "6/9 strategies BUY") alongside each strategy's conviction, displayed as a summary panel above the chart.
**Why it matters**: Eliminates the need to manually tab through each strategy. A 7/9 BUY consensus is far more actionable than any individual signal.
**yfinance data**: No new data needed — reuses `get_ohlcv()` already in cache from current strategy calls.
**Reward**: 9 | **Effort**: 5 | **Score**: 1.80
**Implementation notes**: Backend adds `GET /api/strategy-consensus/<ticker>?start=&end=` that calls each of the 9 strategy route functions in parallel (ThreadPoolExecutor), aggregates the latest signal per strategy, and returns counts + per-strategy summary. Frontend adds a compact consensus bar above StockChart showing green/red strategy icons.

---

### 2. Insider Transaction Feed on Stock Info Page
**Description**: Display the most recent insider buy/sell transactions (officer name, role, shares, value, date) as a table on the stock detail view, with a net-buy/net-sell 90-day summary badge.
**Why it matters**: Insider buying — especially by CEOs and CFOs — is one of the highest-conviction fundamental signals available for free. It is entirely unused today despite yfinance exposing it cleanly.
**yfinance data**: `stock.insider_transactions` (DataFrame: filer, shares, value, text, startDate, ownership)
**Reward**: 9 | **Effort**: 3 | **Score**: 3.00
**Implementation notes**: Add `get_insider_transactions(ticker)` to `data_fetcher.py` with 1-hour TTL. Add a field to the `/api/stock-info/<ticker>` response (`insiderTransactions`: last 10 rows as list of dicts). Frontend renders a collapsible table in StockInfo with a badge showing net 90-day insider activity (e.g. "Net Buy: +$4.2M").

---

### 3. Institutional Holdings Change Tracker
**Description**: Show current institutional ownership % alongside the quarter-over-quarter change in institutional holder count, surfacing accumulation or distribution signals.
**Why it matters**: Rising institutional holder count + increasing % held is a classic accumulation pattern. The raw `institutionalPctHeld` is already in the API response but the change-over-time dimension is missing.
**yfinance data**: `stock.institutional_holders` (DataFrame: Holder, Shares, Date Reported, % Out, Value); `stock.major_holders` (4-row DataFrame: insidersPercentHeld, institutionsPercentHeld, institutionsFloatPercentHeld, institutionsCount)
**Reward**: 8 | **Effort**: 4 | **Score**: 2.00
**Implementation notes**: Add `get_institutional_holders(ticker)` and `get_major_holders(ticker)` to `data_fetcher.py` (1-hour TTL). Expose top 10 holders + total count via `/api/stock-info`. Frontend adds a "Institutional Holders" section to StockInfo showing a sortable table of top holders and a StatCard for institutions count.


### 6. Earnings Estimate Beat/Miss History
**Description**: Show a sparkline-style earnings surprise history (last 4-8 quarters): actual EPS vs estimate, beat/miss magnitude, and a streak indicator (e.g. "Beat 6 consecutive quarters").
**Why it matters**: Consistent EPS beats are a leading indicator of stock outperformance and analyst estimate revision cycles. The data is already partially fetched (`get_analyst_data` retrieves `earnings_estimate`) but the historical beat/miss pattern is not surfaced.
**yfinance data**: `stock.earnings_history` (DataFrame: epsActual, epsEstimate, epsDifference, surprisePercent, quarter)
**Reward**: 8 | **Effort**: 3 | **Score**: 2.67
**Implementation notes**: Add `get_earnings_history(ticker)` to `data_fetcher.py` (1-hour TTL, `stock.earnings_history`). Expose last 8 quarters as a list of `{ quarter, epsActual, epsEstimate, surprisePct }` in the `/api/analyst-data/<ticker>` response. Frontend extends AnalystPanel with an earnings surprise chart or badge row showing beat/miss per quarter in green/red with a streak badge.

---

### 7. Recommendations Screener: Add RSI + Trend Filter Columns
**Description**: Add RSI value and trend alignment to the recommendations table columns (they are computed in the batch run but not returned), and add filter controls for RSI range (e.g. Oversold: <35) and trend (e.g. Strong Uptrend only).
**Why it matters**: The Recommendations tab already computes RSI and trend alignment per stock (`_build_stock_data`) but discards RSI as a numeric value before returning — it only shows a qualitative "price action" label. Adding the numeric RSI and filtering on it is the most natural screener workflow a retail investor would expect.
**yfinance data**: No new data — RSI is already computed in `_build_stock_data`, just not returned in the response dict.
**Reward**: 7 | **Effort**: 2 | **Score**: 3.50
**Implementation notes**: In `recommendations.py` `_build_stock_data()`, add `'rsi': rsi_val` to the returned dict. Update the `/api/recommendations` response to include it. Frontend adds a RSI column to Recommendations DataTable and a numeric range filter (min/max inputs) to the filter bar alongside the existing MACD/trend filters.

---

### 8. Short Interest Signal on Stock Detail
**Description**: Display short interest % of float alongside a contextual label (e.g. "High Short Interest — potential squeeze" if >15%) on the stock info page.
**Why it matters**: `shortPercentOfFloat` is already fetched from `stock.info` and included in the `/api/stock-info` response, but it is never rendered in the frontend. High short interest combined with a bullish technical setup is a classic squeeze precursor.
**yfinance data**: `info['shortPercentOfFloat']` — already in the API response field `shortPercentOfFloat`.
**Reward**: 7 | **Effort**: 1 | **Score**: 7.00
**Implementation notes**: Pure frontend change. Add a "Short Interest" StatCard to the StockInfo component (last row or Price Action row). Read `props.shortPercentOfFloat`, format as %, label as "High" (>15%), "Elevated" (8-15%), or "Normal" (<8%) with matching badge color. No backend work required — field is already returned.

---
# Priority!!!
### 9. Watchlist Portfolio-Level Summary (Batch Quotes)
**Description**: When viewing a watchlist, show a summary row per ticker: current price, day change %, analyst recommendation, and RSI — fetched in a single batch call rather than ticker-by-ticker.
**Why it matters**: Today watchlists only show ticker symbols. A user with 10 stocks in a watchlist has no way to triage which ones need attention without clicking into each one individually.
**yfinance data**: `yf.download()` bulk OHLCV (already used in `get_many_ohlcv`); `stock.info` for rec/name (already cached per-ticker via `get_ticker_info`).
**Reward**: 7 | **Effort**: 4 | **Score**: 1.75
**Implementation notes**: Add `GET /api/user/watchlists/<id>/quotes` endpoint. Backend calls `get_many_ohlcv(tickers)` + parallel `get_ticker_info()` for each ticker in the watchlist, returns a compact array `[{ ticker, currentPrice, dayChangePct, analystRecommendation, rsi }]`. Frontend upgrades watchlist view from a plain item list to a mini-DataTable with those columns.

---

### 10. Sharpe Ratio and Calmar Ratio in Backtest Summary
**Description**: Add Sharpe ratio (risk-adjusted return) and Calmar ratio (return / max drawdown) to the backtest summary metrics, providing risk-adjusted performance context missing from the current win-rate / profit-factor view.
**Why it matters**: A strategy with 30% return and 40% max drawdown is worse than one with 20% return and 5% drawdown — but the current summary doesn't capture this. Sharpe and Calmar make that comparison explicit and immediate.
**yfinance data**: No new data — computed from the equity curve already built by `_build_equity_curve()`.
**Reward**: 7 | **Effort**: 2 | **Score**: 3.50
**Implementation notes**: In `backtest.py` `_compute_summary()`, derive daily returns from the equity curve, compute annualized Sharpe (risk-free = 0 is acceptable for retail use), and Calmar = `totalReturn / abs(maxDrawdown)`. Add `sharpeRatio` and `calmarRatio` fields to the summary response. Frontend adds two new StatCards in the Backtester summary panel.

---
# Could be Cool to add Priority #2
### 11. Sector / Industry Relative Strength Heatmap
**Description**: On the Recommendations tab, add a sector-level heatmap showing average 1-month momentum by sector (already computed per stock as `momentum` field), helping users identify which sectors are leading vs lagging the market.
**Why it matters**: Sector rotation is a core portfolio strategy. The data is already computed for every stock — grouping by `sector` from `stock.info` and averaging momentum is a near-zero-cost aggregation that surfaces macro-level insights.
**yfinance data**: `info['sector']` (already fetched in batch); `momentum` (already computed in `_build_stock_data`). Need to add `sector` to the returned dict.
**Reward**: 8 | **Effort**: 3 | **Score**: 2.67
**Implementation notes**: In `_build_stock_data()`, add `'sector': info.get('sector', 'Unknown')` to the returned dict. Return it in the `/api/recommendations` response. Frontend aggregates sector data client-side, renders a heatmap-style grid (CSS grid, color-coded by average momentum) above the stock table. No extra API calls needed.
