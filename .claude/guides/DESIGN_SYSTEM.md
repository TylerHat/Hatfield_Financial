# Hatfield Financial — Design System

Dark GitHub-style theme. Desktop-only. Plain CSS — no frameworks.

---

## Color Palette

### Base Surfaces

| Token | Hex | Usage |
|-------|-----|-------|
| Background | `#0d1117` | `body` background, page root |
| Surface | `#161b22` | Cards, panels, chart containers, inputs |
| Inner divider | `#21262d` | Secondary surfaces, metric row separators, code backgrounds |
| Border | `#30363d` | All borders: cards, inputs, table rows, chart containers |
| Muted border | `#484f58` | Placeholder text, inactive indicators, zone markers |

### Text

| Token | Hex | Usage |
|-------|-----|-------|
| Text primary | `#e6edf3` | Headings, values, primary content |
| Text secondary | `#8b949e` | Labels, captions, secondary info, column headers |
| Text muted | `#c9d1d9` | Body text, table cell content, guide body |

### Accent Colors

| Token | Hex | Usage |
|-------|-----|-------|
| Accent blue | `#58a6ff` | Links, active tabs, focused inputs, ticker labels, headings |
| Green | `#3fb950` | BUY signals, positive deltas, `status-green` |
| Red | `#f85149` | SELL signals, negative deltas, errors, `status-red` |
| Orange | `#f0883e` | MEDIUM conviction, warnings |
| Yellow | `#d2993a` | MEDIUM conviction (badge), `status-yellow` |

### Interactive

| Token | Hex | Usage |
|-------|-----|-------|
| Button primary | `#238636` | `.search-btn` background |
| Button hover | `#2ea043` | `.search-btn:hover` |
| Button active | `#1a7f37` | `.search-btn:active` |
| Focus ring | `rgba(88, 166, 255, 0.15)` | Input focus `box-shadow` |

### Signal / Status Backgrounds (semi-transparent)

All status colors use 15–20% opacity backgrounds against the surface color:

| Color | Background | Text |
|-------|-----------|------|
| Green | `rgba(63, 185, 80, 0.15–0.20)` | `#3fb950` |
| Red | `rgba(248, 81, 73, 0.15–0.20)` | `#f85149` |
| Blue | `rgba(88, 166, 255, 0.15–0.18)` | `#58a6ff` |
| Yellow | `rgba(210, 153, 34, 0.15–0.18)` | `#d2993a` |
| Gray | `rgba(139, 148, 158, 0.15)` | `#8b949e` |
| Orange | `rgba(240, 136, 62, 0.18–0.20)` | `#f0883e` |

Row accents (signals table):
- BUY row: `rgba(46, 160, 67, 0.05)` — very subtle green tint
- SELL row: `rgba(248, 81, 73, 0.05)` — very subtle red tint

---

## Typography

**Font stack**: `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif`

Set globally on `body` in `index.css`.

### Type Scale

| Use | Size | Weight | Color |
|-----|------|--------|-------|
| Page title (h1) | `2rem` | 700 | `#58a6ff` |
| Section heading | `1.4rem` | 700 | `#e6edf3` |
| Ticker/symbol | `1.5rem` | 700 | `#58a6ff` |
| Card title (uppercase label) | `0.78rem` | 600 | `#8b949e` |
| Body / table cells | `0.85–0.88rem` | 400 | `#c9d1d9` |
| Secondary labels | `0.82rem` | 400–600 | `#8b949e` |
| Badges | `0.72–0.78rem` | 700 | varies |
| Captions / meta | `0.75–0.78rem` | 400–600 | `#8b949e` |

### Card Title Convention

Section headers inside cards use uppercase + letter-spacing:

```css
font-size: 0.78rem;
font-weight: 600;
text-transform: uppercase;
letter-spacing: 0.6px;
color: #8b949e;
```

---

## Spacing & Layout

**Max content width**: `1400px` (`.app`)
**Page padding**: `20px 24px 48px`

### Border Radius

| Context | Radius |
|---------|--------|
| Cards, panels, chart containers | `8px` |
| Inputs, buttons, dropdowns | `6px` |
| Badges, pills | `4px` (badges) / `20px` (overview pills) |
| Range thumb | `2px` |

### Card / Panel Pattern

All surface cards follow this pattern:

```css
background: #161b22;
border: 1px solid #30363d;
border-radius: 8px;
padding: 16px;        /* compact */
padding: 16px 20px;   /* standard */
```

### Grid Layouts

Use `repeat(auto-fill, minmax(Xpx, 1fr))` with `gap: 12px`. Min column widths in use: `220px` (metrics), `260px` (info cards), `340px` (guide sections).

---

## Chart Heights

Fixed heights for consistent desktop layout. All charts use `maintainAspectRatio: false`.

| Chart | Height | Class |
|-------|--------|-------|
| Price chart | `420px` | `.price-chart` |
| Volume chart | `220px` | `.volume-chart` |
| MACD chart | `220px` | `.macd-chart` |
| ATR chart | `220px` | `.atr-chart` |
| Stochastic chart | `220px` | `.stochastic-chart` |
| OBV chart | `220px` | `.obv-chart` |
| RSI chart | `130px` | `.rsi-chart` (conditional) |

Chart container pattern:
```css
background: #161b22;
border: 1px solid #30363d;
border-radius: 8px;
padding: 16px;
```

---

## Interactive Elements

### Inputs & Dropdowns

```css
background: #161b22;
border: 1px solid #30363d;
border-radius: 6px;
color: #e6edf3;
outline: none;
transition: border-color 0.15s;
```

Focus state:
```css
border-color: #58a6ff;
box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.15);
```

Placeholder: `color: #484f58`
Date inputs: include `color-scheme: dark` to style the native calendar picker.

### Tab Navigation

```css
/* Inactive */
color: #8b949e;
border-bottom: 2px solid transparent;

/* Hover */
color: #e6edf3;

/* Active */
color: #58a6ff;
border-bottom-color: #58a6ff;
font-weight: 600;
```

---

## CSS Class Naming Conventions

| Pattern | Used For |
|---------|----------|
| `hf-badge--*` | Badge component color and size modifiers |
| `stat-card__*` | StatCard BEM elements |
| `dt-*` | DataTable elements and states |
| `.status-green/red/yellow/blue/gray` | Inline status badges in `App.css` (legacy — prefer Badge component) |
| `.signal-badge.buy/sell` | Inline signal pills in StockChart (legacy) |
| `.conviction-badge.high/medium/low` | Inline conviction pills (legacy) |
| `.buy-row` / `.sell-row` | DataTable row accent classes |
| `.info-card` | Analysis cards in StockInfo |
| `.guide-*` | StrategyGuide-specific layout |

**Legacy badge classes** (`.status-badge`, `.signal-badge`, `.conviction-badge`) exist in `App.css` and are still used by `StockInfo.js` and `StockChart.js`. New code should use the `<Badge>` component instead.

---

## Left-Border Accent Pattern

Used for visual hierarchy on section headers and summary cards:

```css
/* Blue accent — section headers */
border-left: 4px solid #58a6ff;
padding-left: 16px;

/* Colored card accent — StatCard, summary cards */
border-left-width: 3px;
/* color set via CSS custom property or inline style */
```

---

## State Patterns

Always handle all three states. Never leave empty containers.

### Loading
- StatCard: skeleton shimmer bars (`.stat-card__skeleton`)
- DataTable: 5 animated skeleton rows (`.dt-skeleton`)
- Generic: `.chart-status` centered text with `color: #8b949e`

### Error
- Color: `#f85149`
- DataTable: `.dt-state--error`
- StatCard: `.stat-card__error`
- Generic: `.chart-status.error`

### Empty
- Color: `#8b949e`
- DataTable: `.dt-state--empty` with `emptyMessage` prop
- Charts: `.no-signals` panel with border

---

## Number Formatting Rules

| Type | Format |
|------|--------|
| Price | `$185.20` (2 decimals) |
| Percentage | `+2.4%` / `-1.8%` (2 decimals, explicit sign) |
| Large numbers | `$2.85T` / `$1.20B` / `$450.00M` |
| Volume | Integer with commas |
| Ratios (P/E, beta) | 2 decimals |
| Scores | Integer 0–100 |

Positive values: prefix `+`, color `#3fb950`
Negative values: prefix `-`, color `#f85149`
Right-align all numeric columns in tables.

---

## Maintenance Note

**Update this file when:**
- A new color token is introduced (new component, new semantic color)
- A new component establishes a new CSS class naming pattern
- Chart heights or layout constants change
- A new state pattern (loading/error/empty) is introduced
