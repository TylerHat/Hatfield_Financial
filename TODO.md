# Major Features
## Features
- Adding other yfinance ONLY ADD IF IT DOESNT BOG DOWN 
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

### 8. Short Interest Signal on Stock Detail
**Description**: Display short interest % of float alongside a contextual label (e.g. "High Short Interest — potential squeeze" if >15%) on the stock info page.
**Why it matters**: `shortPercentOfFloat` is already fetched from `stock.info` and included in the `/api/stock-info` response, but it is never rendered in the frontend. High short interest combined with a bullish technical setup is a classic squeeze precursor.
**yfinance data**: `info['shortPercentOfFloat']` — already in the API response field `shortPercentOfFloat`.
**Reward**: 7 | **Effort**: 1 | **Score**: 7.00
**Implementation notes**: Pure frontend change. Add a "Short Interest" StatCard to the StockInfo component (last row or Price Action row). Read `props.shortPercentOfFloat`, format as %, label as "High" (>15%), "Elevated" (8-15%), or "Normal" (<8%) with matching badge color. No backend work required — field is already returned.


---
# Could be Cool to add Priority #2
### 11. Sector / Industry Relative Strength Heatmap
**Description**: On the Recommendations tab, add a sector-level heatmap showing average 1-month momentum by sector (already computed per stock as `momentum` field), helping users identify which sectors are leading vs lagging the market.
**Why it matters**: Sector rotation is a core portfolio strategy. The data is already computed for every stock — grouping by `sector` from `stock.info` and averaging momentum is a near-zero-cost aggregation that surfaces macro-level insights.
**yfinance data**: `info['sector']` (already fetched in batch); `momentum` (already computed in `_build_stock_data`). Need to add `sector` to the returned dict.
**Reward**: 8 | **Effort**: 3 | **Score**: 2.67
**Implementation notes**: In `_build_stock_data()`, add `'sector': info.get('sector', 'Unknown')` to the returned dict. Return it in the `/api/recommendations` response. Frontend aggregates sector data client-side, renders a heatmap-style grid (CSS grid, color-coded by average momentum) above the stock table. No extra API calls needed.
