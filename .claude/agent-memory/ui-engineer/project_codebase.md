---
name: Hatfield Investments — UI Codebase Snapshot
description: Component inventory, CSS class patterns, color palette, and Chart.js conventions discovered in the frontend source
type: project
---

## Component Inventory (Frontend/src/)

| File | Purpose |
|------|---------|
| App.js | Root component — tab nav (Stock Analysis / Strategy Guide), ticker input, date range, strategy dropdown |
| components/StockChart.js | Main chart component — price Line + volume Bar + MACD Bar + optional RSI Line; signals table below |
| components/StockInfo.js | Fundamental analysis panel — cards for Valuation, RSI, 52-week range, MACD, Volatility, Volume + key metrics table |
| components/StrategyGuide.js | Static reference tab — per-strategy educational content with section cards |
| App.css | All styles — single flat CSS file, no modules |

## Color Palette

| Token | Hex | Usage |
|-------|-----|-------|
| bg-base | #0d1117 | Page background (index.css body) |
| bg-surface | #161b22 | Cards, chart backgrounds, inputs |
| bg-elevated | #21262d | Hover states, secondary backgrounds |
| border | #30363d | All borders |
| border-subtle | #21262d | Table row dividers |
| text-primary | #e6edf3 | Headings, values |
| text-secondary | #8b949e | Labels, subtitles, axis ticks |
| text-body | #c9d1d9 | Body copy in guide sections |
| text-placeholder | #484f58 | Input placeholder |
| accent-blue | #58a6ff | Primary accent, links, price line |
| accent-orange | #f0883e | MA20 line, MACD signal line |
| accent-purple | #bc8cff | MA50 line |
| accent-green | #3fb950 | BUY signals, positive values |
| accent-green-border | #1a7f37 | BUY signal point border |
| accent-red | #f85149 | SELL signals, errors, negative values |
| accent-red-border | #b62324 | SELL signal point border |
| accent-yellow | #d2993a | "Slightly overvalued" / consolidation badge |
| btn-green | #238636 | Primary action button bg |
| btn-green-hover | #2ea043 | Hover |
| btn-green-active | #1a7f37 | Active |

## CSS Class Naming Conventions

- Layout wrappers: `.app`, `.app-main`, `.app-header`
- Tab nav: `.tab-nav`, `.tab-btn`, `.tab-btn.active`
- Forms: `.search-form`, `.ticker-input`, `.search-btn`, `.date-range-row`, `.date-group`, `.date-input`
- Controls row: `.controls-row`, `.ticker-label`, `.strategy-group`, `.strategy-select`
- Chart areas: `.chart-container`, `.price-chart` (420px), `.volume-chart` (130px), `.macd-chart` (130px), `.rsi-chart` (130px)
- Status: `.chart-status`, `.chart-status.error`, `.strategy-loading`, `.no-signals`
- Signals table: `.signals-summary`, `.signals-table`, `.signals-table-wrapper`, `.buy-row`, `.sell-row`, `.signal-badge.buy/.sell`, `.badge.buy/.sell`
- Conviction badge: `.conviction-badge.high/.medium/.low`
- Stock info: `.stock-info`, `.info-overview`, `.info-cards`, `.info-card`, `.card-title`, `.card-detail`
- Status badges: `.status-badge`, `.status-green/.yellow/.red/.blue/.gray`
- RSI indicator: `.rsi-row`, `.rsi-value`, `.rsi-track`, `.rsi-fill`, `.rsi-zone-markers`
- Range track: `.range-labels`, `.range-track`, `.range-thumb`
- Metrics: `.info-metrics`, `.metrics-grid`, `.metric-row`, `.metric-label`, `.metric-value`
- Strategy guide: `.guide-container`, `.guide-nav`, `.guide-nav-btn`, `.guide-section`, `.guide-summary-card`

## Chart.js Conventions

- All charts: `responsive: true, maintainAspectRatio: false, animation: false`
- Tooltip style: `backgroundColor: '#161b22', borderColor: '#30363d', borderWidth: 1, titleColor: '#e6edf3', bodyColor: '#8b949e'`
- Axis tick color: `#8b949e`
- Grid color: `#21262d` (x-axis often `display: false` on sub-charts)
- Price chart height: 420px container div
- Sub-charts (volume, MACD, RSI) height: 130px container div
- Signal triangles: `pointStyle: 'triangle'`, BUY rotation 0, SELL rotation 180
- `interaction: { mode: 'index', intersect: false }` on price chart only
- Sub-charts hide legend (`legend: { display: false }`) or show minimal legend

## API Endpoints Used by Frontend

- `GET /api/stock/<ticker>?start=&end=` — returns `{ dates, close, volume, ma20, ma50, macd, macd_signal, macd_hist, rsi }`
- `GET /api/strategy/<strategy>/<ticker>?start=&end=` — returns `{ signals: [{date, price, type, reason, conviction, score}] }`
- `GET /api/stock-info/<ticker>` — returns fundamentals object for StockInfo component

## Key UX Decisions (as-built)

- One strategy active at a time via dropdown; "None" shows raw chart
- RSI sub-panel only shown for strategies where it adds context (bollinger-bands, mean-reversion, rsi)
- MACD sub-chart is always visible regardless of strategy
- Signals table rendered below all charts, sorted by date ascending
- Strategy dropdown only appears after a ticker has been submitted
- Date validation: start must be before end; error shown inline
- `strategy` resets to 'none' when a new ticker is submitted

**Why:** Financial users want progressive disclosure — raw chart first, then overlay strategy signals on demand.
