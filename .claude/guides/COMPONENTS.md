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

### Loading State

When `loading={true}`, the value, delta, and subtext are rendered at 50% opacity, and a centered CSS spinner (16px, `#58a6ff`) appears overlaid on the card. There are no skeleton bar elements — the content dims in place.

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
| `onRowDoubleClick` | `(row, index) => void` \| null | `null` | Called when a row is double-clicked. |

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

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `ticker` | string | — | Active ticker symbol |
| `strategy` | string \| null | — | Active strategy key or `null` for raw chart |
| `fetchStart` | string | — | `YYYY-MM-DD` — start of data fetch window (includes warmup) |
| `fetchEnd` | string | — | `YYYY-MM-DD` — end of data fetch window |
| `startDate` | string | — | `YYYY-MM-DD` — start of user-visible chart window |
| `endDate` | string | — | `YYYY-MM-DD` — end of user-visible chart window |
| `onSignals` | function | — | `(signals) => void` — lifts signals to parent (`App.js`) |
| `onRangePerformance` | function | — | `(perf) => void` — lifts range performance stats to parent |
| `refreshKey` | number | `0` | Increment to force a data re-fetch |

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

```
recommendations
recommendations__header
recommendations__filter-bar
recommendations__filter-input
recommendations__strategy-select
recommendations__table
recommendations__detail-panel
recommendations__detail-header
recommendations__detail-signals
recommendations__loading
recommendations__nav-btn
```

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

## Backtester

**File**: `components/Backtester.js` + `Backtester.css`
**Import**: `import Backtester from './components/Backtester'`

Strategy backtesting panel with equity curve chart, trade history table, and performance summary metrics. Fetches backtest data via `/api/backtest/<ticker>` internally.

### Props

| Prop | Type | Description |
|------|------|-------------|
| `ticker` | string | Active ticker symbol |
| `strategy` | string | Strategy key (e.g. `bollinger-bands`) |
| `startDate` | string | `YYYY-MM-DD` backtest start |
| `endDate` | string | `YYYY-MM-DD` backtest end |

---

---

## InsiderTransactions

**File**: `components/InsiderTransactions.js`
**Import**: `import InsiderTransactions from './components/InsiderTransactions'`

Displays recent insider buy/sell transactions in a DataTable. Data fetched internally via `/api/stock-info/<ticker>` (insider transactions sub-field) or a dedicated endpoint.

Sub-tab in the Stock Analysis **Insider Activity** panel.

---

## InstitutionalHoldings

**File**: `components/InstitutionalHoldings.js`
**Import**: `import InstitutionalHoldings from './components/InstitutionalHoldings'`

Displays top institutional holders and their share counts/percentages. Sub-tab in the Stock Analysis **Institutional** panel.

---

## Watchlist

**File**: `components/Watchlist.js` + `Watchlist.css`
**Import**: `import Watchlist from './components/Watchlist'`

Watchlist management tab. Allows creating/deleting watchlists and adding/removing ticker symbols. Displays each watchlist with its tickers and the price recorded when the ticker was added (`price_at_add`). Requires auth.

---

## AccountPanel

**File**: `components/AccountPanel.js` + `AccountPanel.css`
**Import**: `import AccountPanel from './components/AccountPanel'`

Account settings tab. Allows the logged-in user to update their email address via `PATCH /api/auth/me`.

---

## AdminPanel

**File**: `components/AdminPanel.js` + `AdminPanel.css`
**Import**: `import AdminPanel from './components/AdminPanel'`

Admin-only user management tab. Lists all users, allows granting/revoking admin status (`PATCH /api/admin/users/<id>/role`) and deleting accounts (`DELETE /api/admin/users/<id>`). Only rendered when `user.is_admin === true`.

---

## ApiMonitorPanel

**File**: `components/ApiMonitorPanel.js` + `ApiMonitorPanel.css`
**Import**: `import ApiMonitorPanel from './components/ApiMonitorPanel'`

Admin-only API metrics tab. Starts/stops recording and displays captured API queue metrics. Uses `POST /api/admin/metrics/start/<minutes>`, `GET /api/admin/metrics/status`, and `POST /api/admin/metrics/clear`. Only rendered when `user.is_admin === true`.

---

## Maintenance Note

**Update this file when:**
- A new reusable component is created → add its full prop table, CSS classes, and usage example
- An existing component gains new props or variants
- A component's CSS class names change
- `StockChart` gains new props or chart panels
