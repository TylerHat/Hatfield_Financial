---
name: Codebase audit — existing features and yfinance gaps
description: Summary of what Hatfield Financial already does vs what yfinance data is unused, as of 2026-05-11 (updated)
type: project
---

## Already implemented (do not re-recommend)

### Strategies (9 total)
- Bollinger Bands, Mean Reversion, Relative Strength, PEAD, MACD, RSI, Volatility Squeeze, 52-Week Breakout, MA Confluence
- Backtest engine: supports 5 of 9 strategies; equity curve, win rate, profit factor, max drawdown (no Sharpe/Calmar)

### Custom ETF Strategies (4 simulators in Backend/services/custom_etf/)
- buy-score-top10 (quality/value/GARP blend, 10 factors)
- momentum-top10 (pure trend, 4 sub-factors)
- low-vol-defensive (defensive ballast, 5 sub-factors)
- analyst-conviction-top10 (Bayesian-shrunk target upside, strong_buy filter)

### Stock Info page (rendered in StockInfo.js)
- RSI, MACD, ATR volatility, consolidation, trend alignment (MA20/50/200)
- Earnings proximity, rel strength vs SPY 1M/3M, dividend health, valuation (P/E)
- Key Metrics table: P/E, P/B, P/S, Beta, Dividend, EPS, EV/EBITDA, PEG
- Fundamentals section: revenue/earnings growth, margins, ROE, ROA, D/E, current ratio, FCF, short %, quick ratio, cash, debt, OCF, EBITDA, revenue TTM, insider %, institutional %
- Company Profile: business summary, employees, website, location, shares, float, split history
- insiderTransactions (list of 10 transactions — fetched and in API response, NOT rendered in frontend yet)
- institutionalHolders (top 15 holders list — fetched and in API response, NOT rendered in frontend yet)
- institutionalMajor (insider%, institutions%, institutionsFloatPct — fetched, NOT rendered)
- shortPercentOfFloat: fetched and returned in API, rendered as MetricRow in Fundamentals (was unrendered as of 2026-04-11, now confirmed in frontend code)

### Analyst Panel (AnalystPanel.js)
- Price targets (low/mean/median/high + range bar), recommendation breakdown bar
- Recommendation trend table (4 months), upgrades/downgrades table
- Earnings/revenue estimates (4 periods: 0q, +1q, 0y, +1y) with YoY growth %
- Governance risk (ISS audit/board/compensation/shareholder rights/overall)

### Recommendations tab
- Batch S&P 500 screener: Buy Score composite (10 factors, 0-100), MACD, trend, price action, momentum, analyst rec, target upside, volatility, RSI, FCF yield, ROE, D/E, gross margin, 52w position
- 4 Custom ETF strategies with portfolio simulator and rebalance tracking
- localStorage cache (20 min, schema-versioned)

### Data layer (data_fetcher.py)
- get_ohlcv, get_ticker_info, get_earnings_dates, get_spy_history/period, get_analyst_data
- get_insider_transactions (built, used in stock_info)
- get_institutional_holders (built, used in stock_info)
- get_many_ohlcv (bulk download for recommendations)
- YFinanceQueue with priority levels, rate-limiting, retry, starvation prevention

## yfinance attributes STILL UNUSED (as of 2026-05-11)
- `stock.options` + `stock.option_chain()` — IV data, options chain, put/call ratio
- `stock.sustainability` — ESG/sustainability scores
- `stock.earnings_history` — epsActual/epsEstimate/surprise per historical quarter (earnings beat/miss history)
- `info['sector']` — fetched per-ticker in batch but NOT added to recommendations response dict
- `stock.income_stmt` / `stock.quarterly_income_stmt` — full income statement (revenue, EBIT, net income by period)
- `stock.balance_sheet` / `stock.quarterly_balance_sheet` — balance sheet items
- `stock.cashflow` / `stock.quarterly_cashflow` — cash flow statement
- `stock.recommendations` — raw analyst recommendation history (separate from recommendations_summary)
- `stock.news` — company news articles (title, link, pubDate) — yfinance 0.2+

## Key data fetched but NOT rendered in frontend
- `insiderTransactions` list (10 rows per ticker) — API returns it, StockInfo.js does not render it
- `institutionalHolders` list (top 15) — API returns it, StockInfo.js does not render it
- `institutionalMajor` (ownership % breakdown) — API returns it, StockInfo.js does not render it
- `insiderNet90d` badge (net buy/sell value over 90 days) — API returns it, not rendered

## Backtest gaps
- No risk-adjusted metrics (Sharpe ratio, Calmar ratio, Sortino)
- No benchmark comparison (vs SPY buy-and-hold over same period)
- 4 of 9 strategies still not supported (post-earnings-drift, volatility-squeeze, 52-week-breakout, ma-confluence)

## Recommendations tab gaps
- `sector` field not included in recommendations response (needed for heatmap — noted in TODO.md)
- No multi-strategy consensus view on a single stock (how many of the 9 strategies agree right now)
- No earnings surprise history / beat rate shown anywhere

**Why:** All gaps identified during 2026-05-11 feature recommendation audit (updated from 2026-04-11).
**How to apply:** Use this to avoid re-recommending already-built features and to quickly identify highest-leverage additions.
