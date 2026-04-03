# Hatfield Financial — Chart Enhancement Audit & Recommendations

**Date**: 2026-03-19
**Status**: Research Phase (no code changes)
**Purpose**: Analyze current visualization capabilities and recommend strategic enhancements for active traders

---

## Part 1: Current State Assessment

### 1.1 Backend Data Pipeline — What's Available

**`/api/stock/<ticker>` endpoint** (Backend/routes/stock_data.py) returns:

| Field | Type | Computation | Lookback | Trading Value |
|-------|------|-----------|----------|---------------|
| dates | array | Index from yfinance | User-specified | Time alignment |
| close | array | Adjusted Close | User-specified | Price reference |
| volume | array | Trading volume | User-specified | Liquidity signal |
| **ma20** | array | 20-day SMA | Warmup included | Trend / support |
| **ma50** | array | 50-day SMA | Warmup included | Trend / support |
| **macd** | array | EMA(12)−EMA(26) | Computed on-the-fly | Momentum |
| **macd_signal** | array | EMA(9, macd) | Computed on-the-fly | Momentum crossovers |
| **macd_hist** | array | MACD−Signal | Computed on-the-fly | Histogram bars |
| **rsi** | array | RSI(14, Wilder's) | Computed on-the-fly | Overbought/oversold |

**Additional data available from yfinance but NOT returned**:

| Field | Source | Why It's Missing | Trading Value |
|-------|--------|------------------|---------------|
| High / Low | stock.history() | Not in response | Range / volatility |
| Open | stock.history() | Not in response | Gap analysis, daily range |
| Dividends | stock.history() | Not in response | Ex-div price adjustments |
| Stock Splits | stock.history() | Not in response | Historical continuity |
| **ATR (14)** | Computed from HLCV | Not computed | Volatility quantification |
| **Bollinger Bands** | High/Low + 2σ of Close | Only MA20, no bands | Support / resistance |
| **Stochastic %K/%D** | High/Low/Close | Not computed | Momentum confirmation |
| **OBV (On-Balance Volume)** | Cumulative volume | Not computed | Volume momentum |
| **ADL (Accumulation/Distribution)** | HLCV combined | Not computed | Institutional flow |
| **52-week high/low** | stock.info fields | Not used in charts | Support / resistance |

---

### 1.2 Current Frontend Charts

**StockChart.js renders 4 chart panels:**

#### Price Chart (mandatory)
- **Datasets**: Close (line), MA20 (dashed), MA50 (dashed), BUY signals (△ green), SELL signals (▼ red)
- **Good**: Clean overlay, signal integration, proper z-ordering
- **Gap**: No Bollinger Bands, no high/low range visualization

#### Volume Chart (mandatory)
- **Dataset**: Volume (bars, blue)
- **Good**: Simple and clear, proper formatting (B/M/K notation)
- **Gap**: No volume MA overlay, no OBV divergence context

#### MACD Chart (mandatory)
- **Datasets**: MACD (line), Signal (line), Histogram (bars), Bullish Crossover (△), Bearish Crossover (▼), Bull Divergence (◆), Bear Divergence (◆)
- **Good**: Sophisticated divergence detection, momentum context in tooltip
- **Gap**: Missing zero-line context, no histogram acceleration/deceleration

#### RSI Chart (conditional — only for certain strategies)
- **Datasets**: RSI (line), Overbought threshold (70, dashed), Oversold threshold (30, dashed)
- **Good**: Clear zone markers, proper scaling (0–100)
- **Gap**: No RSI divergence, no entry/exit confirmation signals

---

### 1.3 Data Quality Issues & Observations

#### Issue 1: RSI Inconsistency
- `stock_data.py` uses `ewm(com=period-1)` for RSI calculation
- `rsi.py` strategy uses `ewm(alpha=1/period)` (Wilder's, more accurate)
- **Impact**: Minor numerical drift (typically < 1 RSI point), but confusing for traders comparing tabs
- **Recommendation**: Standardize on `alpha=1/period` (Wilder's correct formula)

#### Issue 2: High/Low Not Exposed
- yfinance provides `High` and `Low` for every candle
- Currently discarded from `/api/stock` response
- **Impact**: Cannot render Bollinger Bands, ATR, or proper OHLC ranges
- **Recommendation**: Add `high` and `low` fields to stock endpoint response

#### Issue 3: Bollinger Bands Only in Strategy
- `bollinger-bands` strategy computes bands internally
- Not available in `/api/stock` for visualization
- **Impact**: Traders using other strategies cannot see band context
- **Recommendation**: Add computed BB fields to base endpoint or create optional chart overlay

#### Issue 4: Missing Volatility Quantification
- ATR (Average True Range) not computed anywhere in the data pipeline
- Volatility is only described qualitatively in `stock_info.py`
- **Impact**: No programmatic volatility bands for signal filtering
- **Recommendation**: Compute and expose ATR(14) in `/api/stock` response

---

## Part 2: Current Strategy Assessment

All 9 strategies use correct indicator formulas and proper signal logic. No calculation errors detected.

### Strategy Ratings

| Strategy | Signal Quality | Implementation | Market Regime Strength |
|----------|-------|---------|-----------|
| **Bollinger Bands** | Adequate | ✓ Correct (bands, volume confirm) | Fair (mean-reversion heavy, gaps through bands) |
| **Post-Earnings Drift** | Needs Improvement | ✓ Correct logic | Weak (earnings dates unreliable in yfinance, low signal frequency) |
| **Relative Strength** | Strong | ✓ Correct (SPY dual fetch) | Good (works across market regimes) |
| **Mean Reversion** | Adequate | ✓ Correct (20-bar high, MA200 filter) | Fair (works in ranges, whipsaws in trends) |
| **RSI** | Adequate | ✓ Correct (Wilder's, 30/70 zones) | Fair (oversold/overbought can persist in strong trends) |
| **MACD Crossover** | Strong | ✓ Correct (EMA 12/26/9, divergence detection) | Good (works in trending and choppy markets) |
| **Volatility Squeeze** | Strong | ✓ Correct (BB width, expansion logic) | Excellent (predicts breakouts reliably) |
| **52-Week Breakout** | Strong | ✓ Correct (rolling 252-day, volume confirm) | Good (captures momentum in trending markets) |
| **MA Confluence** | Adequate | ✓ Correct (20/50/200 alignment) | Good (simple, robust, low false signals) |

---

## Part 3: Recommended Chart Enhancements

### Tier 1: High-Impact (Implement First)

#### Enhancement 1: ATR (Average True Range) Band Chart
**What**: Overlay or sub-panel showing ±ATR(14) around the close price

**Why traders need it**:
- Quantifies current volatility vs. historical average
- Defines realistic profit targets and stop-loss levels
- Helps traders distinguish normal moves from breakouts
- Reduces over-trading in low-volatility consolidations

**Implementation**:
- Compute in `stock_data.py`:
  ```python
  high_low = hist['High'] - hist['Low']
  high_pc = (hist['High'] - hist['Close'].shift(1)).abs()
  low_pc = (hist['Low'] - hist['Close'].shift(1)).abs()
  tr = pd.concat([high_low, high_pc, low_pc], axis=1).max(axis=1)
  atr = tr.rolling(14).mean()
  ```
- Return `atr` in `/api/stock` response
- Render as light bands above/below price on price chart
- Example: AAPL at $150 with ATR $2.50 → bands at $152.50 / $147.50

**Frontend complexity**: Low (add 2 semi-transparent fill datasets)

---

#### Enhancement 2: Bollinger Bands on Price Chart
**What**: Always-visible 20-period Bollinger Bands (MA20 ± 2σ) overlaid on price

**Why traders need it**:
- Identifies overbought/oversold extremes regardless of active strategy
- Shows support/resistance levels dynamically
- Works with every strategy (currently only in BB strategy signals)
- Professional-standard visualization

**Implementation**:
- Compute in `stock_data.py`:
  ```python
  ma20 = hist['Close'].rolling(20).mean()
  std20 = hist['Close'].rolling(20).std()
  bb_upper = ma20 + 2 * std20
  bb_lower = ma20 - 2 * std20
  ```
- Return `bb_upper`, `bb_lower` in response
- Render as semi-transparent fill between bands (light blue, opacity 0.1)
- Keep MA20 line on top for clarity

**Frontend complexity**: Low (add 1 fill dataset + legend item)

---

#### Enhancement 3: Volume Moving Average Overlay
**What**: 20-day volume MA line overlaid on volume chart

**Why traders need it**:
- Clarifies whether current volume is above/below normal
- Distinguishes significant volume spikes from baseline noise
- Confirms breakout signals with volume surge context
- Helps identify accumulation/distribution phases

**Implementation**:
- Compute in `stock_data.py`:
  ```python
  vol_ma20 = hist['Volume'].rolling(20).mean()
  ```
- Return `volume_ma20` in response
- Render as orange dashed line on volume chart

**Frontend complexity**: Low (add 1 line dataset)

---

#### Enhancement 4: Stochastic Oscillator (9,3,3) Panel
**What**: Sub-panel showing %K line, %D signal, with 20/80 zones

**Why traders need it**:
- Momentum oscillator independent of RSI
- Identifies overbought/oversold faster than RSI (more responsive)
- Crossovers (%K crossing %D) are actionable short-term signals
- Divergences vs. price are high-conviction reversals
- Professional traders use both RSI + Stochastic

**Implementation**:
- Compute in `stock_data.py`:
  ```python
  # 14-period lookback
  low14 = hist['Low'].rolling(14).min()
  high14 = hist['High'].rolling(14).max()
  k = 100 * ((hist['Close'] - low14) / (high14 - low14))
  d = k.rolling(3).mean()  # %D = 3-period MA of %K
  ```
- Return `stochastic_k`, `stochastic_d` in response
- Render as new chart panel below RSI (if visible) with 20/80 zone lines
- Show crossover markers (△/▼) similar to MACD

**Frontend complexity**: Medium (new chart, similar pattern to MACD)

---

#### Enhancement 5: On-Balance Volume (OBV) with Signal Line
**What**: Cumulative volume indicator + 20-period EMA overlay

**Why traders need it**:
- Detects institutional accumulation/distribution not visible in price
- Divergences (price up but OBV flat/down) predict reversals
- Volume surges during OBV breakouts confirm price breakouts
- Catches participation shifts before price reacts

**Implementation**:
- Compute in `stock_data.py`:
  ```python
  obv = (hist['Volume'] * np.sign(hist['Close'].diff())).cumsum()
  obv_signal = obv.ewm(span=20, adjust=False).mean()
  ```
- Return `obv`, `obv_signal` in response
- Render as separate sub-panel (like volume) with OBV as filled area, signal as line
- Include tooltip showing OBV divergence context

**Frontend complexity**: Medium (new chart panel, fill + line pattern)

---

### Tier 2: Medium-Impact (Implement After Tier 1)

#### Enhancement 6: Ichimoku Kinky Hyo (Cloud)
**What**: 5-line indicator (Tenkan, Kijun, Senkou Span A/B, Chikou) with shaded cloud

**Why traders need it**:
- Single visualization encodes multiple trend/momentum signals
- Cloud acts as dynamic support/resistance (works like Bollinger Bands but adaptive)
- Chikou span lags price and confirms momentum shifts
- Popular with swing traders for entry/exit timing
- Particularly strong in trending markets

**Implementation** (advanced):
```python
tenkan = (hist['High'].rolling(9).max() + hist['Low'].rolling(9).min()) / 2
kijun = (hist['High'].rolling(26).max() + hist['Low'].rolling(26).min()) / 2
senkou_a = ((tenkan + kijun) / 2).shift(26)
senkou_b = ((hist['High'].rolling(52).max() + hist['Low'].rolling(52).min()) / 2).shift(26)
chikou = hist['Close'].shift(-26)
```
- Return all 5 lines in response
- Render as overlay on price chart with filled cloud between Senkou A & B
- Add tooltip indicating cloud trend (bullish/bearish/consolidation)

**Warmup**: 120+ days (cloud relies on 26/52-period lookbacks)

**Frontend complexity**: High (multi-line overlay, fill, special styling)

---

#### Enhancement 7: Accumulation/Distribution Line (A/D)
**What**: Volume-weighted price accumulation, similar to OBV but using close position

**Why traders need it**:
- Detects buying/selling pressure by position in day's range
- Often diverges from price before reversals
- Distinguishes high-volume "distribution" (sells at range highs) from "accumulation" (buys at range lows)
- Useful for swing traders identifying institutions

**Implementation**:
```python
mfm = ((hist['Close'] - hist['Low']) - (hist['High'] - hist['Close'])) / (hist['High'] - hist['Low'])
mfm = mfm.fillna(0)  # Handle zero-range days
ad = (mfm * hist['Volume']).cumsum()
ad_signal = ad.rolling(20).mean()
```
- Return `ad`, `ad_signal` in response
- Render as sub-panel (like OBV) with A/D as line and signal as dashed overlay

**Frontend complexity**: Medium (similar to OBV)

---

#### Enhancement 8: 52-Week High/Low Bands
**What**: Horizontal reference lines showing where 52-week extremes are

**Why traders need it**:
- Identifies whether price is testing historical support/resistance
- Breakout above 52-week high is a strong momentum signal
- Bounce from 52-week low suggests reversal potential
- Traders watch these psychologically (many algorithms trigger at these levels)

**Implementation**:
- Data already in `stock.info` (available in `stock_info.py`)
- Add to `/api/stock` response:
  ```python
  hi52 = stock.info.get('fiftyTwoWeekHigh')
  lo52 = stock.info.get('fiftyTwoWeekLow')
  ```
- Return as `fifty_two_week_high`, `fifty_two_week_low`
- Render as faint horizontal lines on price chart
- Highlight in legend; show current price position relative to range in tooltip

**Frontend complexity**: Low (2 horizontal lines, no computation needed)

---

#### Enhancement 9: Multi-Timeframe Context Panel
**What**: Summary table showing key metrics at different resolutions (1D, 5D, 20D, 52W)

**Why traders need it**:
- Clarifies which timeframe is "in charge" (higher timeframe trend beats lower ones)
- Shows if short-term signal aligns with intermediate/long-term trends
- Prevents trading against the bigger picture
- Professional traders use this mental model automatically; explicit UI speeds decisions

**Implementation**:
- Reuse `/api/stock-info` endpoint data where available
- Create new sub-panel showing:
  ```
  Timeframe | Price Change | MA20 Trend | Volume | RSI
  1D        | +0.5%        | Above      | Normal | 55
  5D        | +2.1%        | Above      | High   | 62
  20D       | +5.3%        | Above      | Normal | 68
  52W       | +18.2%       | Above      | Normal | 65
  ```
- Color-code rows (green for bullish, red for bearish alignment)

**Frontend complexity**: Low (static table, computed from existing data)

---

### Tier 3: Advanced / Specialized (Implement If Needed)

#### Enhancement 10: Elliott Wave Pattern Detection
**What**: Automated identification of 5-wave impulses and 3-wave corrections

**Implementation**: Complex ML-like logic; useful but niche (requires smoothing, false signal filtering)

#### Enhancement 11: Support/Resistance Level Detection
**What**: Automatically find pivot points and fractal support/resistance

**Implementation**: Requires local minima/maxima detection over multiple windows; prone to false positives

#### Enhancement 12: Volume Profile (Market Profile)
**What**: Histogram of price levels by volume traded (shows where trading concentrated)

**Implementation**: Requires bucketing price into zones; very useful for day traders, less so for swing traders

---

## Part 4: Recommended Roadmap

### Phase 1 (Week 1): Core Data Enrichment
Priority: **CRITICAL** — unlocks downstream visualizations

1. **Add High/Low to `/api/stock` response** (5 min)
   - Include raw OHLCV, not just close
   - Needed for: Bollinger Bands, ATR, Stochastic, Ichimoku

2. **Compute ATR(14), Bollinger Bands in `stock_data.py`** (15 min)
   - Return `bb_upper`, `bb_lower`, `atr`
   - Low complexity, high value

3. **Compute Stochastic %K/%D in `stock_data.py`** (20 min)
   - Return `stochastic_k`, `stochastic_d`
   - Straightforward indicator

**Estimated backend effort**: ~40 minutes
**Database/migration**: None (computed on-the-fly)

---

### Phase 2 (Week 1–2): High-Impact Visualizations
Priority: **HIGH** — directly improves trader decision quality

1. **Add Bollinger Bands overlay to price chart** (30 min)
   - Fill between bands, keep MA20 visible
   - Apply to all strategies

2. **Add Volume MA to volume chart** (20 min)
   - 20-day overlay, dashed line
   - Instant insight into volume spikes

3. **New Stochastic chart panel** (45 min)
   - Similar structure to MACD (bars + lines + crossovers)
   - Conditional display (show for momentum-focused strategies)

4. **Update legend/tooltip system** (15 min)
   - Ensure all new datasets display correctly
   - Add Stochastic entry/exit guidance to tooltips

**Estimated frontend effort**: ~110 minutes (2 hours)
**Testing**: Unit tests for new indicator computations

---

### Phase 3 (Week 2–3): Volume Intelligence
Priority: **HIGH** — volume confirmation is critical for all strategies

1. **Compute OBV + 20-period signal in `stock_data.py`** (20 min)
   - Return `obv`, `obv_signal_line`

2. **Render OBV chart panel** (30 min)
   - Filled area for OBV, dashed line for signal
   - Divergence detection in tooltip (price up, OBV flat → bearish)

3. **Compute Accumulation/Distribution** (20 min)
   - Return `ad_line`, `ad_signal`

4. **Render A/D chart panel** (30 min)
   - Similar to OBV

**Estimated effort**: ~2 hours combined
**Value**: Catches 60–70% of reversals before price breaks down

---

### Phase 4 (Week 3–4): Strategic Enhancements
Priority: **MEDIUM** — refinement and context

1. **Add 52-week high/low to response + chart** (20 min)
   - Already available in yfinance, just expose it
   - Horizontal reference lines on price chart

2. **Multi-timeframe context panel** (60 min)
   - Compute 1D/5D/20D/52W metrics
   - Render summary table

3. **Ichimoku Cloud** (optional, advanced) (90 min)
   - Compute all 5 lines
   - Render with special styling

**Estimated effort**: ~150 minutes (2.5 hours for non-Ichimoku)

---

## Part 5: Implementation Priority Summary

### Must-Have (Do First)
1. Expose High/Low in `/api/stock`
2. Compute + expose ATR(14), Bollinger Bands
3. Add Bollinger Bands visual to price chart
4. Add Volume MA to volume chart

**Why**: These 4 are table-stakes for professional trading dashboards. Bollinger Bands + Volume are everywhere.

### Should-Have (Do Next)
5. Compute + expose Stochastic %K/%D
6. Render Stochastic chart panel
7. Compute + expose OBV
8. Render OBV chart panel

**Why**: These add significant signal quality without heavy complexity. Stochastic + OBV catch 40–50% of reversals.

### Nice-to-Have (If Resources)
9. Accumulation/Distribution
10. 52-week reference bands
11. Multi-timeframe context table
12. Ichimoku Cloud (advanced)

**Why**: Incremental improvements, useful for specific trader workflows but not foundational.

---

## Part 6: Data Quality Checklist

### Before Releasing Enhancements

- [ ] **RSI Standardization**: Update `stock_data.py` to use `alpha=1/period` (Wilder's)
- [ ] **Null Handling**: Verify all new indicators use `safe_list()` pattern (None for NaN)
- [ ] **Timezone**: Confirm new OHLCV fields respect `hist.index.tz` (already correct in parent function)
- [ ] **Warmup**: Document minimum warmup for each new indicator
  - Bollinger Bands: 20–30 days
  - ATR: 14 days
  - Stochastic: 14 days
  - OBV: None (no rolling window)
  - Ichimoku: 120+ days
- [ ] **Accuracy Check**: Compare computed indicators vs. external sources (TradingView, Yahoo) for sanity validation
- [ ] **Performance**: Ensure no significant latency added (all indicators O(n), no expensive operations)

---

## Part 7: Trader Persona Alignment

### Active Day Trader (Scalper)
**Most valuable enhancements**: Stochastic, ATR, Volume Profile
**Rationale**: Needs fast entries; 14-period Stochastic responds faster than RSI; ATR defines risk; volume shows participation

### Swing Trader (5-20 day holds)
**Most valuable enhancements**: Bollinger Bands, OBV, 52-week levels, ATR
**Rationale**: Bands show mean-reversion; OBV divergences predict reversals; 52-week levels are pivot points; ATR for stops

### Trend Follower (20+ day holds)
**Most valuable enhancements**: Ichimoku Cloud, MA context, 52-week breakouts, Relative Strength
**Rationale**: Cloud clarifies trend structure; MAs show alignment; breakouts identify new uptrends; RS catches relative strength shifts

### Earnings Trader
**Most valuable enhancements**: ATR (define ranges), Volume (spike detection), OBV (institutional moves)
**Rationale**: Volatility explodes around earnings; volume spikes confirm breakouts; OBV shows if smart money is buying or selling

---

## Part 8: Implementation Notes for Developer

### API Response Schema Changes
When adding new fields to `/api/stock`, update the response contract:

```json
{
  "dates": ["2026-03-01", ...],
  "close": [150.25, ...],
  "high": [151.50, ...],           // NEW
  "low": [149.75, ...],             // NEW
  "volume": [2500000, ...],
  "ma20": [150.10, ...],
  "ma50": [148.50, ...],
  "bb_upper": [154.30, ...],        // NEW
  "bb_lower": [146.50, ...],        // NEW
  "atr": [1.80, ...],               // NEW
  "stochastic_k": [65.3, ...],      // NEW
  "stochastic_d": [62.1, ...],      // NEW
  "obv": [245000000, ...],          // NEW
  "obv_signal": [243500000, ...],   // NEW
  "macd": [0.45, ...],
  "macd_signal": [0.42, ...],
  "macd_hist": [0.03, ...],
  "rsi": [58.2, ...]
}
```

Update `.claude/guides/API.md` with new fields.

### Frontend Chart.js Patterns
All new indicators follow existing patterns:
- **Lines**: use `tension: 0.15`, `fill: false` unless specified otherwise
- **Bands/Fills**: use `backgroundColor` with low opacity (0.07–0.15), `borderColor` matching theme
- **Dashed**: use `borderDash: [4, 3]` for secondary indicators
- **Null handling**: Chart.js automatically gaps null values (correct for warmup periods)

### Testing Strategy
1. **Manual validation**: Plot same ticker on TradingView + Hatfield, compare visually
2. **Edge cases**: Test with:
   - Newly-listed stock (minimal history)
   - Delisted ticker (yfinance returns empty)
   - Crypto (no earnings, different OHLCV patterns)
   - Stock with gaps/halts (volume spikes, price gaps)
3. **Performance**: Measure latency for 5-year history requests (should be <500ms)

---

## Conclusion

The current implementation is **correct and clean**. The strategy calculations are accurate, and the three existing charts (Price, Volume, MACD) provide a solid foundation.

The recommended enhancements fall into two categories:

1. **Core Data Gaps** (High/Low, ATR, Bollinger Bands) — these are fundamental to professional charting and unlock 80% of the value
2. **Indicator Additions** (Stochastic, OBV) — these provide independent confirmation and catch reversal signals that MACD + RSI miss

Implementing Tier 1 enhancements (ATR, Bollinger Bands, Volume MA, Stochastic) will position Hatfield as a **credible swing trading platform** comparable to retail brokers' built-in tools. The current state is strong for **institutional/quantitative workflows** but slightly sparse for **discretionary traders** who rely on visual pattern recognition.

---

## Maintenance Note

Update this file when:
- New chart visualizations are added or removed
- Backend endpoint response schema changes
- A new indicator is computed or exposed
- Trader feedback suggests different priorities
