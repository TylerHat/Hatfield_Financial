---
name: Codebase audit — existing features and yfinance gaps
description: Summary of what Hatfield Financial already does vs what yfinance data is unused, as of 2026-04-11
type: project
---

## Already implemented (do not re-recommend)
- 9 strategies: Bollinger Bands, Mean Reversion, Relative Strength, PEAD, MACD, RSI, Volatility Squeeze, 52-Week Breakout, MA Confluence
- Backtest engine: supports 5 of 9 strategies; equity curve, win rate, profit factor, max drawdown
- Stock info page: RSI, MACD, ATR volatility, consolidation, trend alignment (MA20/50/200), earnings proximity, rel strength vs SPY 1M/3M, dividend health, valuation (P/E), short % of float (FETCHED but NOT rendered in frontend)
- Analyst panel: price targets, recommendation trend, upgrades/downgrades, earnings/revenue estimates
- Recommendations tab: batch S&P 500 screener with MACD, trend, price action, momentum, analyst rec, target upside filters
- Watchlists + portfolio CRUD
- `institutionalPctHeld` and `insiderPctHeld` are returned by /api/stock-info but only as scalar %s — no transaction detail

## yfinance attributes unused as of 2026-04-11
- `stock.insider_transactions` — not fetched anywhere
- `stock.institutional_holders` — not fetched (only scalar % from info dict)
- `stock.major_holders` — not fetched
- `stock.earnings_history` — not fetched (epsActual/epsEstimate/surprise per quarter)
- `stock.options` + `stock.option_chain()` — not fetched anywhere (IV data)
- `stock.sustainability` — not fetched (ESG scores)
- `info['sector']` — fetched in batch but discarded before response (not in returned dict)
- `rsi_val` in recommendations `_build_stock_data` — computed but not returned in response dict

## Key gaps
- No multi-strategy consensus view on a single ticker
- Backtest has no risk-adjusted metrics (Sharpe, Calmar)
- `shortPercentOfFloat` is in the API response but never rendered in StockInfo frontend
- Sector-level aggregation of momentum is possible client-side with zero new API calls once `sector` is added to recommendations response

**Why:** All gaps identified during 2026-04-11 feature recommendation task. These informed the 11 features written to TODO.md under "New Feature Recommendations (added 2026-04-11)".
**How to apply:** Use this to avoid re-recommending already-built features and to quickly identify the highest-leverage yfinance additions in future sessions.
