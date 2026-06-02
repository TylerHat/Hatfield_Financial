# Hatfield Financial — Component Reference

All components live in `Frontend/src/components/`. Plain CSS only — no UI frameworks.

---

## Badge

**File**: `components/Badge.js` + `Badge.css`
**Import**: `import Badge from './components/Badge'`

Colored status pill for signal types, conviction levels, and categorical labels.

### Props

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `variant` | string | `'gray'` | Controls color. See variants below. |
| `size` | `'sm'` \| `'md'` | `'md'` | `'sm'` for dense table cells, `'md'` for standalone display |
| `children` | ReactNode | — | Label text inside the pill |

### Variant → Color Map

| Variant | Resolves To | Use Case |
|---------|-------------|----------|
| `'buy'` | green | BUY signal type |
| `'sell'` | red | SELL signal type |
| `'neutral'` | blue | Neutral/informational |
| `'high'` | green | HIGH conviction |
| `'medium'` | yellow | MEDIUM conviction |
| `'low'` | gray | LOW conviction |
| `'green'` | green | Direct color |
| `'red'` | red | Direct color |
| `'blue'` | blue | Direct color |
| `'yellow'` | yellow | Direct color |
| `'gray'` | gray | Direct color / fallback |
| `'orange'` | orange | Direct color |

Unknown variants fall back to gray — the component never renders unstyled.

### CSS Classes

```
hf-badge
hf-badge--{color}     (green | red | blue | yellow | gray | orange)
hf-badge--{size}      (sm | md)
```

### Usage Examples

```jsx
<Badge variant="buy">BUY</Badge>
<Badge variant="high" size="sm">HIGH</Badge>
<Badge variant="sell" size="sm">SELL</Badge>
<Badge variant="neutral">N/A</Badge>
```

---

## StatCard

**File**: `components/StatCard.js` + `StatCard.css`
**Import**: `import StatCard, { StatCardGrid } from './components/StatCard'`

Single-metric display card for portfolio and stock summary data.

### Props

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `label` | string | — | Metric name shown in the header |
| `value` | string \| number \| ReactNode | — | Primary display value. Pre-format strings for full control — component does not auto-format |
| `delta` | string \| number \| null | `null` | Change value below primary. Sign determines color: positive → green, negative → red. Omit to hide. |
| `deltaLabel` | string \| null | `null` | Optional suffix after delta (e.g. `"vs prev close"`) |
| `subtext` | string \| ReactNode \| null | `null` | Secondary line below the delta |
| `accent` | `'default'` \| `'green'` \| `'red'` \| `'blue'` \| `'yellow'` | `'default'` | Colored left border for visual categorization |
| `size` | `'sm'` \| `'md'` \| `'lg'` | `'md'` | Controls value font size |
| `loading` | bool | `false` | Shows skeleton shimmer animation when true |
| `error` | string \| null | `null` | Shows red error text when set |

### Delta Color Logic

- String starting with `'+'` or positive number → green (`.stat-card__delta--positive`)
- String starting with `'-'` or negative number → red (`.stat-card__delta--negative`)
- Zero or neutral → gray (`.stat-card__delta--neutral`)

### CSS Classes

```
stat-card
stat-card--accent-{accent}    (default | green | red | blue | yellow)
stat-card__label
stat-card__value
stat-card__value--{size}      (sm | md | lg)
stat-card__delta
stat-card__delta--positive
stat-card__delta--negative
stat-card__delta--neutral
stat-card__delta-label
stat-card__subtext
stat-card__error
stat-card__skeleton
stat-card__skeleton-bar
stat-card__skeleton-bar--wide
stat-card__skeleton-bar--narrow
```

### Usage Examples

```jsx
<StatCard
  label="Current Price"
  value="$185.20"
  delta="+2.4%"
  deltaLabel="today"
  accent="green"
/>

<StatCard
  label="P/E Ratio"
  value="28.5"
  subtext="vs market avg ~20x"
  accent="yellow"
/>

<StatCard label="Loading..." loading={true} />
<StatCard label="Beta" value={null} error="Data unavailable" />
```

### StatCardGrid

Lays StatCards out in a multi-column grid.

```jsx
import { StatCardGrid } from './components/StatCard'

<StatCardGrid columns={4}>
  <StatCard ... />
  <StatCard ... />
</StatCardGrid>
```

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `columns` | number | `4` | Minimum column count hint. Grid fills available width. |

CSS class: `stat-card-grid`. Uses CSS custom property `--stat-grid-columns`.

---

## DataTable

**File**: `components/DataTable.js` + `DataTable.css`
**Import**: `import DataTable from './components/DataTable'`

Sortable, scannable data table for signals, screener results, and any tabular financial data.

### Props

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `columns` | `ColumnDef[]` | `[]` | Column definitions. See ColumnDef below. |
| `rows` | `object[]` | `[]` | Data rows. Each object must have keys matching `column.key` values. |
| `defaultSortKey` | string \| null | `null` | Column key to sort by on first render |
| `defaultSortDir` | `'asc'` \| `'desc'` | `'asc'` | Initial sort direction |
| `stickyHeader` | bool | `true` | Makes `<thead>` stick during scroll |
| `emptyMessage` | string | generic | Text shown when `rows` is empty |
| `loading` | bool | `false` | Shows 5-row skeleton when true |
| `error` | string \| null | `null` | Shows red error state when set |
| `caption` | string \| null | `null` | Accessible `<caption>` for screen readers |
| `rowKey` | string \| function \| null | `null` | React key: field name, `(row, i) => key` function, or falls back to index |
| `onRowClick` | `(row, index) => void` \| null | `null` | Called when a row is clicked. Adds pointer cursor style to rows via inline style. |
| `onRowDoubleClick` | `(row, index) => void` \| null | `null` | Called when a row is double-clicked. Used by Recommendations + Watchlist for ticker navigation. |

### ColumnDef Shape

```js
{
  key:      string,              // matches field name in row objects
  label:    string,              // column header text
  numeric:  bool,                // right-aligns + sorts numerically (default false)
  sortable: bool,                // click-to-sort (default true)
  width:    string | null,       // CSS width e.g. '120px' (optional)
  render:   (value, row) => ReactNode | null  // custom cell renderer (optional)
}
```

### Row Accent

Add `_rowClass` to any row object to append a CSS class to its `<tr>`:

```js
{ date: '2024-03-15', type: 'BUY', _rowClass: 'buy-row' }
{ date: '2024-03-20', type: 'SELL', _rowClass: 'sell-row' }
```

`buy-row` and `sell-row` are defined in `App.css`:
- `buy-row td` → subtle green background `rgba(46, 160, 67, 0.05)`
- `sell-row td` → subtle red background `rgba(248, 81, 73, 0.05)`

### Null Cell Rendering

Cells with `null` or `undefined` values render `—` (em dash) via `.dt-null` span.

### CSS Classes

```
dt-wrapper
dt-scroll
dt-table
dt-table--sticky-header
dt-caption
dt-thead
dt-th
dt-th--numeric
dt-th--sortable
dt-th--sorted
dt-tbody
dt-tr
dt-td
dt-td--numeric
dt-sort-arrow
dt-sort-arrow--active
dt-sort-arrow--inactive
dt-footer
dt-footer__sort-info
dt-null
dt-state
dt-state--loading
dt-state--error
dt-state--empty
dt-skeleton
dt-skeleton-row
dt-skeleton-cell
```

### Usage Example

```jsx
const SIGNAL_COLUMNS = [
  { key: 'date', label: 'Date', width: '110px' },
  { key: 'price', label: 'Price', numeric: true, render: v => `$${v.toFixed(2)}` },
  { key: 'type', label: 'Type', render: v => <Badge variant={v.toLowerCase()}>{v}</Badge> },
  { key: 'conviction', label: 'Conviction', render: (v, row) => (
    <><Badge variant={v.toLowerCase()} size="sm">{v}</Badge> {row.score}</>
  )},
  { key: 'reason', label: 'Reason' },
];

<DataTable
  columns={SIGNAL_COLUMNS}
  rows={signals.map(s => ({ ...s, _rowClass: s.type === 'BUY' ? 'buy-row' : 'sell-row' }))}
  defaultSortKey="date"
  defaultSortDir="desc"
  rowKey="date"
  emptyMessage="No signals in this date range."
  loading={loading}
  error={error}
/>
```

---

## StockInfo

**File**: `components/StockInfo.js`
**Import**: `import StockInfo from './components/StockInfo'`

Renders company overview, analysis cards, key metrics, and fundamentals. Data is fetched once in `App.js` and passed down via props (no internal fetch).

### Props

| Prop | Type | Description |
|------|------|-------------|
| `ticker` | string | Active ticker symbol |
| `stockInfoData` | object \| null | Pre-fetched stock-info response from App.js |
| `stockInfoLoading` | boolean | Whether stock-info is currently loading |
| `stockInfoError` | string \| null | Error message if stock-info fetch failed |
| `hideOverview` | boolean | `false` | Hides the company overview section when true |

### Analysis Cards Layout (3 rows)

| Row | Cards | CSS Class |
|-----|-------|-----------|
| Top (3 cols) | Valuation, Momentum (RSI 14), 52-Week Range | `info-cards-row--top` |
| Bottom (4 cols) | Price Action, MACD, Volatility (ATR), Volume | `info-cards-row--bottom` |
| Third (4 cols) | Trend Alignment, Earnings Proximity, Relative Strength vs SPY, Dividend Health | `info-cards-row--third` |

### Third Row Cards Detail

| Card | Badge Values | Color Helper |
|------|-------------|--------------|
| **Trend Alignment** | `Strong Uptrend` / `Strong Downtrend` / `Bullish (Mixed)` / `Bearish (Mixed)` | `trendColor()` — green for bullish, red for bearish |
| **Earnings Proximity** | `X days away` / `Earnings TODAY` / `Reported X days ago` | red if `earningsWarning`, blue otherwise |
| **Relative Strength vs SPY** | `1M: +X%` / `3M: +X%` badges | `relStrengthColor()` — green >+5%, red <-5%, yellow in between |
| **Dividend Health** | `Very Healthy` / `Healthy` / `Moderate` / `Stretched` / `Unsustainable` | `divHealthColor()` — green healthy, yellow moderate, red stretched |

### Key Metrics Table

P/E (trailing/forward), P/B, P/S, Beta, Dividend Yield, EPS, Revenue/Share, Current Price, Analyst Rec, Analyst Target, **EV/EBITDA**, **PEG Ratio**, **Dividend Rate**, **Ex-Dividend Date**, **Earnings Date**, **50-Day MA**, **200-Day MA**

### Fundamentals Table

Revenue Growth, Earnings Growth, Gross/Operating/Net Margin, ROE, ROA, D/E, Current Ratio, FCF, Short % of Float, **Quick Ratio**, **Total Cash**, **Total Debt**, **Operating Cash Flow**, **EBITDA**, **Revenue (TTM)**, **Insider % Held**, **Institutional % Held**

---

## StockChart

**File**: `components/StockChart.js`
**Import**: `import StockChart from './components/StockChart'`

Multi-panel chart stack with technical indicators, signal overlays, expand/info UI, and a signals table.

### Key Props

| Prop | Type | Description |
|------|------|-------------|
| `ticker` | string | Active ticker symbol |
| `fetchStart` | string | `YYYY-MM-DD` upper-bound start for the wider data fetch (App pre-fetches ~1y, then slices) |
| `fetchEnd` | string | `YYYY-MM-DD` upper-bound end for the data fetch |
| `startDate` | string | `YYYY-MM-DD` visible chart start (subset of fetch range) |
| `endDate` | string | `YYYY-MM-DD` visible chart end |
| `strategy` | string \| null | Active strategy key or `null` for raw chart |
| `onRangePerformance` | `(perf \| null) => void` | Reports `{ up, pct }` for the visible range to the parent |
| `refreshKey` | number | Incrementing key to force a fresh fetch (POSTs to bust the server cache) |
| `onSignals` | function | `(signals) => void` — **currently dead**: declared and wired internally, but App.js never passes a handler. Lift is a no-op until App.js opts in. |

### Chart Layout (top to bottom)

| # | Chart | Height | CSS Class | Description |
|---|-------|--------|-----------|-------------|
| 1 | Price | 420px | `.price-chart` | Close, MA20, MA50, Bollinger Bands, 52W high/low lines, earnings markers, BUY/SELL signals |
| 2 | Volume | 220px | `.volume-chart` | Volume bars + 20-day volume MA |
| 3 | MACD | 220px | `.macd-chart` | MACD/Signal lines, histogram (opacity-scaled), zero line, crossover markers, divergence diamonds |
| 4 | ATR | 220px | `.atr-chart` | 14-period Average True Range with fill |
| 5 | Stochastic | 220px | `.stoch-chart` | %K/%D lines, overbought (80) / oversold (20) zones |
| 6 | OBV | 220px | `.obv-chart` | On-Balance Volume + 20-day signal line |
| 7 | RSI | 130px | `.rsi-chart` | RSI line, 70/30 zones, divergence diamonds. Conditional: shown for `bollinger-bands`, `mean-reversion`, `rsi`, `macd-crossover` strategies |

All charts use `maintainAspectRatio: false` with explicit container heights.

### Chart UI Controls

Each chart panel has two buttons (visible on hover):

- **Expand (⛶)** — `.chart-expand-btn` — expands chart to 75vh, hides other panels. Close button (✕) returns to normal view.
- **Info (i)** — `.chart-info-btn` — toggles a popover (`.chart-info-popover`) with colored legend matching chart colors. Uses `L` (line swatch) and `S` (symbol) helper components.

### Signal & Indicator Markers

| Marker | Shape | Color | Used In |
|--------|-------|-------|---------|
| ▲ BUY | triangle up | `#3fb950` | Price chart |
| ▼ SELL | triangle down | `#f85149` | Price chart |
| ▲ Bullish Cross | triangle up | `#3fb950` | MACD chart |
| ▼ Bearish Cross | triangle down | `#f85149` | MACD chart |
| ◆ Bull Divergence | diamond | `#3fb950` | MACD, RSI charts |
| ◆ Bear Divergence | diamond | `#f85149` | MACD, RSI charts |
| \| Earnings | vertical line | `#d2a8ff` | Price chart |

### MACD Enhancements

- **Zero line**: dashed gray at y=0, hidden from legend
- **Crossover markers**: detected where MACD crosses Signal line
- **Histogram gradient**: bar opacity scales with magnitude (stronger = more opaque)
- **Divergence detection**: compares price local highs/lows with MACD highs/lows in 10-bar windows
- **Momentum tooltip**: shows "Momentum building/fading (bullish/bearish)" based on histogram trend

### Helper: `buildSignalArray()`

Maps signal dates to chart data index positions so scatter points align with price line x-axis.

---

## Recommendations

**File**: `components/Recommendations.js` + `Recommendations.css`
**Import**: `import Recommendations from './components/Recommendations'`

S&P 500 batch screener tab. Fetches `/api/recommendations`, displays a filterable DataTable of all stocks with technical and fundamental signals. Supports on-demand strategy signal analysis for individual stocks.

### Props

| Prop | Type | Description |
|------|------|-------------|
| `onNavigateToStock` | `(ticker: string) => void` | Callback to switch to Stock Analysis tab with the given ticker |

### Internal State

| State | Type | Description |
|-------|------|-------------|
| `stocks` | array | Full list of stock objects from API |
| `filter` | string | Text filter applied to ticker/name |
| `selectedStrategy` | string \| null | Strategy key for on-demand signal fetch |
| `expandedTicker` | string \| null | Ticker whose detail panel is currently open |

### Features

- **Filter bar**: text input filters the stock list by ticker or company name
- **Strategy dropdown**: select a strategy to fetch signals for the expanded stock
- **DataTable with clickable rows**: uses the `onRowClick` prop to expand a detail panel for the clicked stock
- **Detail panel**: shows on-demand strategy signals for the selected stock, with a button to navigate to full Stock Analysis
- **Loading state**: renders a loading indicator while the API returns `202 (loading)`; polls until data is ready

### CSS Classes

The actual CSS file uses the short `rec-*` prefix (NOT `recommendations__*`). Key classes:

```
rec-header
rec-filter-bar
rec-strategy-bar
rec-detail
rec-loading-banner
rec-loading-spinner
rec-table
rec-buy-score-cell
rec-nav-btn
```

See `Recommendations.css` for the full list.

---

## AnalystPanel

**File**: `components/AnalystPanel.js` + `AnalystPanel.css`
**Import**: `import AnalystPanel from './components/AnalystPanel'`

Displays analyst coverage data: price targets, recommendation trends, upgrades/downgrades, and earnings/revenue estimates. Uses Badge and DataTable internally.

### Props

| Prop | Type | Description |
|------|------|-------------|
| `data` | object \| null | Analyst data response from `/api/analyst-data/<ticker>` |
| `ticker` | string | Active ticker symbol |
| `currentPrice` | number | Current stock price (for price target comparison) |
| `loading` | boolean | Whether analyst data is currently loading |

---

## Backtester (ORPHANED)

**File**: `components/Backtester.js` + `Backtester.css`
**Status**: **Not imported anywhere.** App.js does not render it; recent commit "made backtesting admin only" did not include re-wiring it into the AdminPanel. The `/api/backtest/<ticker>` endpoint is still live on the backend.

The CSS file also contains the only `@media (max-width: …)` blocks in the entire frontend bundle — a violation of the desktop-only rule. Either delete the component or re-import it under AdminPanel and strip the media queries.

### Original Props (preserved for when it is re-wired)

| Prop | Type | Description |
|------|------|-------------|
| `ticker` | string | Active ticker symbol |
| `strategy` | string | Strategy key (e.g. `bollinger-bands`) |
| `startDate` | string | `YYYY-MM-DD` backtest start |
| `endDate` | string | `YYYY-MM-DD` backtest end |

---

## Watchlist

**File**: `components/Watchlist.js` + `Watchlist.css`

User watchlist tab — add/remove tickers, click-to-navigate to Stock Analysis. Fetches `/api/user/watchlists` and `/api/user/watchlists/<id>/data` (bulk price/change/volatility refresh).

| Prop | Type | Description |
|------|------|-------------|
| `onNavigateToStock` | `(ticker) => void` | Switch the parent App to the Stock Analysis tab with the given ticker |
| `onWatchlistChange` | `(items) => void` | Notify the parent when the watchlist contents change (used to sync the "+ Watchlist" button state on the analysis tab) |

---

## CustomEtfPanel

**File**: `components/CustomEtfPanel.js` + `CustomEtfPanel.css`

Custom ETF simulator UI. Strategy sidebar (one row per registered strategy), positions table, trade history, equity curve chart, rebalance button (admin-only). Includes a `NextRebalanceTimer` sub-component that ticks every second to display countdown to the next 9:30 ET auto-rebalance window.

| Prop | Type | Description |
|------|------|-------------|
| `onNavigateToStock` | `(ticker) => void` | Switch App to the Stock Analysis tab with the given ticker |

---

## MarkovMethod

**File**: `components/MarkovMethod.js`

Markov regime analysis UI for the active ticker. Renders the current regime, the 3×3 transition matrix, stationary distribution, and 1/3/5/10-step forecasts. Used as a sub-tab inside Stock Analysis.

| Prop | Type | Description |
|------|------|-------------|
| `ticker` | string | Active ticker symbol |
| `start` | string | `YYYY-MM-DD` window start |
| `end` | string | `YYYY-MM-DD` window end |

---

## MarkovBacktestPanel

**File**: `components/MarkovBacktestPanel.js`

Admin-launched long-running backtest of the Markov-regime ETF strategy across the full S&P 500. Submits a job via `/api/custom-etf/markov-regime/backtest`, polls `/api/custom-etf/backtest/<job_id>` every 2 s. Displays portfolio metrics + win/loss + drawdown when complete.

No required props.

---

## MarkovExplainPanel

**File**: `components/MarkovExplainPanel.js`

Static explanation card describing the Markov regime classification approach. No props.

---

## InsiderTransactions

**File**: `components/InsiderTransactions.js`

Renders insider buy/sell history (from `stockInfo.insiderTransactions`) and a 90-day net summary.

| Prop | Type | Description |
|------|------|-------------|
| `transactions` | array | Insider transaction rows from `/api/stock-info` |
| `net90d` | number | Net shares bought minus sold in the last 90 days |
| `net90dValue` | number | Dollar value of the 90-day net |

---

## InstitutionalHoldings

**File**: `components/InstitutionalHoldings.js`

Renders the institutional holders table (from `stockInfo.institutionalHolders`) plus a "major holders" summary.

| Prop | Type | Description |
|------|------|-------------|
| `holders` | array | Per-institution holdings |
| `major` | object | Aggregate breakdown (insider %, institutional %, etc.) |
| `totalCount` | number | Total institutional holders disclosed |

---

## AccountPanel

**File**: `components/AccountPanel.js` + `AccountPanel.css`

Profile + email update form. Uses `useAuth()` for the current user; PATCHes `/api/auth/me`. No props.

---

## AdminPanel

**File**: `components/AdminPanel.js` + `AdminPanel.css`

Admin-only user-management table. Grant/revoke admin (PATCH `/api/admin/users/<id>/role`); delete user with a typed-confirm modal (`DeleteConfirmModal`, defined inline). No props.

---

## ApiMonitorPanel

**File**: `components/ApiMonitorPanel.js`

Admin-only yfinance queue metrics recorder. Start a 5- or 10-minute capture, poll every 3 s, display per-minute snapshots (calls, successes, failures, timeouts, cache hits/misses, queue depth, per-endpoint counts). Calls `/api/admin/metrics/start/<minutes>`, `/api/admin/metrics/status`, `/api/admin/metrics/clear`. No props.

---

## AuthPage

**File**: `components/AuthPage.js` + `AuthPage.css`

Login / register form with toggle. Used by App.js's auth gate when no user is logged in. No props.

---

## AboutPage

**File**: `components/AboutPage.js`

Static personal-bio page. No props.

---

## Maintenance Note

**Update this file when:**
- A new reusable component is created → add its full prop table, CSS classes, and usage example
- An existing component gains new props or variants
- A component's CSS class names change
- `StockChart` gains new props or chart panels
