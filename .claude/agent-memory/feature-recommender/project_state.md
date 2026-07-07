---
name: Codebase audit — existing features and yfinance gaps
description: Summary of what Hatfield Financial already does vs what yfinance data is unused, as of 2026-07-02 (updated)
metadata:
  type: project
---

## Already implemented (do not re-recommend)

### Strategies (9 chart strategies)
- Bollinger Bands, Mean Reversion, Relative Strength, PEAD, MACD, RSI, Volatility Squeeze, 52-Week Breakout, MA Confluence
- Backtest engine: supports 5 of 9 (BB, RSI, MACD, mean-reversion, rel-strength); equity curve, win rate, profit factor, max drawdown — STILL no Sharpe/Sortino/Calmar or SPY benchmark (verified 2026-07-02 in routes/backtest.py)

### Custom ETF Strategies (now 6, in Backend/services/custom_etf/strategies/)
- buy-score-top10, momentum-top10, low-vol-defensive, analyst-conviction-top10
- undervalued-strong-buy-top10 (NEW since 05-11: valuation 50% + shrunk upside 40% + quality 10%)
- markov-regime (NEW: P(Bull 5d/3d) blend, non-equal weighting via weight() hook)
- `prepare(recs)` hook pattern for universe-wide stats; `weight()` hook for non-equal sizing

### Stock Info / Analyst panels
- Insider transactions + institutional holders + insiderNet90d ARE NOW RENDERED (App.js passes to dedicated panels — was unrendered in prior audits)
- Full fundamentals, key metrics, analyst panel (targets, rec trend, upgrades/downgrades, estimates 0q/+1q/0y/+1y, governance risk) all live

### Data layer (data_fetcher.py — verified 2026-07-02)
- get_ohlcv, get_ticker_info, get_earnings_dates, get_spy_history/period/1m_return, get_analyst_data (price_targets, recommendations_summary, upgrades_downgrades, earnings_estimate, revenue_estimate), get_insider_transactions, get_institutional_holders, get_many_ohlcv, get_news
- `get_news()` EXISTS (1h TTL, normalizes legacy+nested formats) but is ONLY used by sandbox_ollama.py — no production route serves news yet
- YFinanceQueue: priority levels, 0.3s call interval, starvation promotion, per-minute metrics recording

### In-flight work (branch HFA-068-1-ollama-reporting-poc, 2026-07-02)
- sandbox_ollama.py: per-stock AI reports via local Ollama (qwen3:4b), news-led, grounded in existing analytics (_build_stock_data, markov, analyst). news_scraper.py adds free RSS/HTML sources. Productionization (S&P-500 batch, reuse _fetch_all_data) is the stated next step.

## yfinance attributes STILL UNUSED (verified 2026-07-02 via grep)
- `stock.options` + `stock.option_chain()` — IV, put/call OI ratio, skew
- `stock.sustainability` — ESG scores
- `stock.earnings_history` — epsActual/epsEstimate/surprisePercent per past quarter (beat/miss history)
- `stock.eps_trend` / `stock.eps_revisions` — estimate revision momentum (current vs 7/30/60/90d ago; up/down revision counts)
- `stock.income_stmt` / `balance_sheet` / `cashflow` (+ quarterly variants) — full statements (needed for Piotroski F-Score, accruals)
- `stock.recommendations` — raw rec history (summary + upgrades_downgrades ARE used)
- `stock.dividends` — full dividend history series (only info-dict dividend fields used)
- `info['sector']` — STILL not in recommendations response dict (no 'sector' key in routes/recommendations.py)

## Persistent gaps (re-verified 2026-07-02)
- Backtest: no Sharpe/Sortino/Calmar, no SPY benchmark, 4/9 strategies unsupported (PEAD, vol-squeeze, 52w-breakout, ma-confluence)
- Recommendations: no sector field/heatmap, no multi-strategy consensus, no earnings-surprise/beat-rate anywhere, no days-to-earnings column
- PEAD strategy ignores surprise magnitude (only uses price action) — earnings_history would let it gate on SUE
- No stock-vs-stock comparison tool; no watchlist signal alerts

**Why:** Refreshed during 2026-07-02 feature recommendation audit; prior 2026-05-11 memory was stale on insider/institutional rendering, ETF strategy count, and get_news existence.
**How to apply:** Avoid re-recommending built features (insider panels, news fetcher, undervalued/markov ETF strategies). Highest-leverage: earnings_history, eps_trend/eps_revisions, sector field, backtest risk metrics, options chain.
