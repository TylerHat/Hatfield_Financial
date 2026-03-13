# Implementation Guide — Hatfield Investments Improvements
**Quick Reference for Recommended Changes**

---

## Quick Wins (Implement This Week)

### 1. RSI Strategy (30 min)

**File**: Create `Backend/routes/strategies/rsi.py`

```python
import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

rsi_bp = Blueprint('rsi', __name__)

def compute_rsi(prices, period=14):
    """RSI using Wilder's smoothing (exponential moving average)"""
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

@rsi_bp.route('/api/strategy/rsi/<ticker>')
def rsi_strategy(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)
        fetch_start = user_start - timedelta(days=30)

        stock = yf.Ticker(ticker.upper())
        hist = stock.history(start=fetch_start, end=end)

        if hist.empty:
            return jsonify({'signals': []})

        # Compute RSI
        rsi = compute_rsi(hist['Close'])

        # Trim to user-requested window
        cutoff = pd.Timestamp(user_start).tz_localize('UTC')
        if hist.index.tz is None:
            cutoff = cutoff.tz_localize(None)
        hist = hist[hist.index >= cutoff]
        rsi = rsi[rsi.index >= cutoff]

        signals = []

        for i in range(1, len(hist)):
            if pd.isna(rsi.iloc[i]) or pd.isna(rsi.iloc[i-1]):
                continue

            rsi_val = float(rsi.iloc[i])
            prev_rsi = float(rsi.iloc[i-1])

            # Enters oversold (< 30)
            if prev_rsi >= 30 and rsi_val < 30:
                conviction = 'HIGH' if rsi_val < 20 else 'MEDIUM'
                signals.append({
                    'date': hist.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(hist.iloc[i]['Close']), 2),
                    'type': 'BUY',
                    'score': int((30 - rsi_val) * 3),  # Scale 0-30 to 0-90
                    'conviction': conviction,
                    'reason': f'RSI {rsi_val:.1f} entered oversold territory (< 30)'
                })

            # Enters overbought (> 70)
            elif prev_rsi <= 70 and rsi_val > 70:
                conviction = 'HIGH' if rsi_val > 80 else 'MEDIUM'
                signals.append({
                    'date': hist.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(hist.iloc[i]['Close']), 2),
                    'type': 'SELL',
                    'score': int((rsi_val - 70) * 3),  # Scale 0-30 to 0-90
                    'conviction': conviction,
                    'reason': f'RSI {rsi_val:.1f} entered overbought territory (> 70)'
                })

        return jsonify({'signals': signals})

    except Exception as e:
        return jsonify({'error': str(e), 'signals': []}), 500
```

**File**: Update `Backend/app.py`
```python
# Add import
from routes.strategies.rsi import rsi_bp

# Add registration (after other strategy blueprints)
app.register_blueprint(rsi_bp)
```

**File**: Update `Frontend/src/App.js` (STRATEGIES array)
```javascript
const STRATEGIES = [
  { value: 'none', label: 'None (Raw Price Chart)' },
  { value: 'rsi', label: 'RSI Oversold/Overbought' },  // ADD THIS
  { value: 'post-earnings-drift', label: 'Post-Earnings Drift Strategy' },
  { value: 'relative-strength', label: 'Relative Strength vs Market' },
  { value: 'bollinger-bands', label: 'Bollinger Bands' },
  { value: 'mean-reversion', label: 'Mean Reversion After Large Drawdown' },
];
```

---

### 2. MACD Crossover Strategy (30 min)

**File**: Create `Backend/routes/strategies/macd_crossover.py`

```python
import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

macd_bp = Blueprint('macd_crossover', __name__)

@macd_bp.route('/api/strategy/macd-crossover/<ticker>')
def macd_crossover(ticker):
    try:
        end_str = request.args.get('end')
        start_str = request.args.get('start')

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)
        fetch_start = user_start - timedelta(days=40)  # Ensure MACD is populated

        stock = yf.Ticker(ticker.upper())
        hist = stock.history(start=fetch_start, end=end)

        if hist.empty:
            return jsonify({'signals': []})

        # Compute MACD (12, 26, 9)
        ema12 = hist['Close'].ewm(span=12, adjust=False).mean()
        ema26 = hist['Close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()

        # Trim to user-requested window
        cutoff = pd.Timestamp(user_start).tz_localize('UTC')
        if hist.index.tz is None:
            cutoff = cutoff.tz_localize(None)
        hist = hist[hist.index >= cutoff]
        macd = macd[macd.index >= cutoff]
        signal = signal[signal.index >= cutoff]

        signals = []

        for i in range(1, len(hist)):
            if pd.isna(macd.iloc[i]) or pd.isna(signal.iloc[i]) or \
               pd.isna(macd.iloc[i-1]) or pd.isna(signal.iloc[i-1]):
                continue

            macd_val = float(macd.iloc[i])
            signal_val = float(signal.iloc[i])
            prev_macd = float(macd.iloc[i-1])
            prev_signal = float(signal.iloc[i-1])

            # BULLISH CROSSOVER: MACD crosses above signal
            if prev_macd <= prev_signal and macd_val > signal_val:
                momentum = abs(macd_val - signal_val)
                score = min(100, int(momentum * 500))
                signals.append({
                    'date': hist.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(hist.iloc[i]['Close']), 2),
                    'type': 'BUY',
                    'score': score,
                    'conviction': 'HIGH' if momentum > 0.5 else 'MEDIUM' if momentum > 0.2 else 'LOW',
                    'reason': f'MACD bullish crossover (MACD: {macd_val:.4f}, Signal: {signal_val:.4f})'
                })

            # BEARISH CROSSOVER: MACD crosses below signal
            elif prev_macd >= prev_signal and macd_val < signal_val:
                momentum = abs(macd_val - signal_val)
                score = min(100, int(momentum * 500))
                signals.append({
                    'date': hist.index[i].strftime('%Y-%m-%d'),
                    'price': round(float(hist.iloc[i]['Close']), 2),
                    'type': 'SELL',
                    'score': score,
                    'conviction': 'HIGH' if momentum > 0.5 else 'MEDIUM' if momentum > 0.2 else 'LOW',
                    'reason': f'MACD bearish crossover (MACD: {macd_val:.4f}, Signal: {signal_val:.4f})'
                })

        return jsonify({'signals': signals})

    except Exception as e:
        return jsonify({'error': str(e), 'signals': []}), 500
```

**File**: Update `Backend/app.py`
```python
from routes.strategies.macd_crossover import macd_bp

app.register_blueprint(macd_bp)
```

**File**: Update `Frontend/src/App.js`
```javascript
const STRATEGIES = [
  { value: 'none', label: 'None (Raw Price Chart)' },
  { value: 'rsi', label: 'RSI Oversold/Overbought' },
  { value: 'macd-crossover', label: 'MACD Crossover' },  // ADD THIS
  { value: 'post-earnings-drift', label: 'Post-Earnings Drift Strategy' },
  { value: 'relative-strength', label: 'Relative Strength vs Market' },
  { value: 'bollinger-bands', label: 'Bollinger Bands' },
  { value: 'mean-reversion', label: 'Mean Reversion After Large Drawdown' },
];
```

---

### 3. Improve Mean Reversion: Add Trend Filter (30 min)

**File**: Update `Backend/routes/strategies/mean_reversion.py`

Replace the signal generation section with:

```python
signals = []
in_drawdown = False

for i in range(len(hist)):
    row = hist.iloc[i]

    if pd.isna(row['Drawdown']):
        continue

    drawdown_pct = float(row['Drawdown'])
    price = float(row['Close'])

    # NEW: Add trend filter
    # Only generate BUY if stock is not in a downtrend
    # Check: is price above 50-day MA? (simple trend filter)
    ma50_val = float(row.get('MA50', float('nan')))

    # Compute MA50 if not in data
    if pd.isna(ma50_val) or i < 50:
        # Fallback: use rolling mean from current data
        ma50_val = hist['Close'].iloc[max(0, i-50):i+1].mean()

    # BUY only if price is not too far below its 50-day MA (avoid downtrends)
    is_not_in_downtrend = price > ma50_val * 0.95  # Allow 5% below MA50

    # Drawdown >= 10% from 20-day high → BUY (but only if not in downtrend)
    if not in_drawdown and drawdown_pct <= -0.10 and is_not_in_downtrend:
        score = min(100, int(abs(drawdown_pct) * 500))
        conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
        signals.append({
            'date': hist.index[i].strftime('%Y-%m-%d'),
            'price': round(price, 2),
            'type': 'BUY',
            'score': score,
            'conviction': conviction,
            'reason': (
                f'Large drawdown of {drawdown_pct:.1%} from 20-day high '
                f'(${float(row["High20"]):.2f}) — mean reversion entry (above MA50)'
            ),
        })
        in_drawdown = True

    # Recovery to within 3% of 20-day high → SELL / take profit
    elif in_drawdown and drawdown_pct > -0.03:
        signals.append({
            'date': hist.index[i].strftime('%Y-%m-%d'),
            'price': round(price, 2),
            'type': 'SELL',
            'score': 55,
            'conviction': 'MEDIUM',
            'reason': (
                f'Price recovered to within 3% of 20-day high '
                f'(${float(row["High20"]):.2f}) — exit mean reversion trade'
            ),
        })
        in_drawdown = False
```

---

### 4. Improve Bollinger Bands: Add Volume Filter (30 min)

**File**: Update `Backend/routes/strategies/bollinger_bands.py`

Add after computing bands:

```python
# NEW: Add 20-day average volume
hist['Volume_MA20'] = hist['Volume'].rolling(20).mean()

# Then in signal detection loop, modify the BUY and SELL conditions:

for i in range(1, len(hist)):
    row = hist.iloc[i]
    prev = hist.iloc[i - 1]

    if pd.isna(row['Upper']) or pd.isna(row['Lower']):
        continue

    band_width = float(row['Upper'] - row['Lower'])

    # NEW: Get current volume and MA
    current_volume = float(row['Volume'])
    volume_ma = float(row.get('Volume_MA20', current_volume))
    volume_ratio = current_volume / volume_ma if volume_ma > 0 else 1.0

    # Price crosses below lower band → oversold → BUY
    # NEW: Require volume > 1.2x average
    if (prev['Close'] >= prev['Lower'] and row['Close'] < row['Lower'] and
        volume_ratio > 1.2):  # Volume confirmation
        raw_score = int(abs(float(row['Lower']) - float(row['Close'])) / band_width * 200) if band_width > 0 else 0
        score = min(100, raw_score)
        conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
        signals.append({
            'date': hist.index[i].strftime('%Y-%m-%d'),
            'price': round(float(row['Close']), 2),
            'type': 'BUY',
            'score': score,
            'conviction': conviction,
            'reason': (
                f'Price crossed below lower Bollinger Band '
                f'(${row["Lower"]:.2f}) with {volume_ratio:.1f}x volume — oversold'
            ),
        })

    # Similar for SELL (volume confirmation improves quality)
    elif (prev['Close'] <= prev['Upper'] and row['Close'] > row['Upper'] and
          volume_ratio > 1.2):  # Volume confirmation
        raw_score = int(abs(float(row['Close']) - float(row['Upper'])) / band_width * 200) if band_width > 0 else 0
        score = min(100, raw_score)
        conviction = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
        signals.append({
            'date': hist.index[i].strftime('%Y-%m-%d'),
            'price': round(float(row['Close']), 2),
            'type': 'SELL',
            'score': score,
            'conviction': conviction,
            'reason': (
                f'Price crossed above upper Bollinger Band '
                f'(${row["Upper"]:.2f}) with {volume_ratio:.1f}x volume — overbought'
            ),
        })
```

---

## Medium-term Improvements (1-2 hours each)

### 5. 52-Week Breakout Strategy
Create `Backend/routes/strategies/breakout.py` (similar structure to above)
- Fetch 1-year history to establish 52-week range
- Generate BUY on break above high, SELL on break below low
- ~45 min implementation

### 6. Moving Average Trend System
Create `Backend/routes/strategies/ma_trend.py`
- Use 50-day MA > 200-day MA as uptrend filter
- Generate signals on MA20 crossovers
- ~45 min implementation

### 7. Volatility Squeeze Strategy
Create `Backend/routes/strategies/volatility_squeeze.py`
- Compute Bollinger Band width
- Detect compression (squeeze)
- Generate signal on band break after squeeze
- ~1 hour implementation

---

## Data Quality Improvements

### Add Data Freshness Timestamp

**File**: Update `Backend/routes/stock_data.py`

```python
from datetime import datetime, timezone

@stock_data_bp.route('/api/stock/<ticker>')
def get_stock_data(ticker):
    try:
        # ... existing code ...

        data = {
            'ticker': ticker.upper(),
            'dates': hist.index.strftime('%Y-%m-%d').tolist(),
            'close': [...],
            'volume': [...],
            'ma20': [...],
            'ma50': [...],
            'macd': [...],
            'macd_signal': [...],
            'macd_hist': [...],
            # NEW: Add metadata
            'metadata': {
                'fetched_at': datetime.now(timezone.utc).isoformat(),
                'timezone': 'US/Eastern',
                'rows': len(hist)
            }
        }

        return jsonify(data)
```

**File**: Update `Frontend/src/components/StockChart.js`

```javascript
// Display data freshness
const fetchedAt = stockData?.metadata?.fetched_at;
const fetchedDate = fetchedAt ? new Date(fetchedAt).toLocaleString() : 'Unknown';

// Add to chart title or info display:
<div className="data-freshness">Data as of {fetchedDate}</div>
```

---

## Testing Recommendations

### For Each New Strategy:

1. **Backtest on 3-year history** (AAPL, TSLA, SPY)
   - Count BUY signals that led to 5%+ gains in 5 days
   - Count SELL signals that avoided 5% losses in 5 days
   - Calculate win rate %

2. **Measure signal frequency**
   - How many signals per 6-month period?
   - Strategy should generate 5-20 signals per 6 months (not too noisy, not too sparse)

3. **Check for false positives in downtrends**
   - Run strategy on 2022 (bear market)
   - BUY signals should be rare or well-filtered

4. **Compare to baseline (buy & hold)**
   - Strategy must outperform random entry/exit
   - At least 55% win rate to be useful

---

## Summary of Time Investment

| Task | Time | Impact |
|------|------|--------|
| RSI strategy | 30 min | HIGH |
| MACD crossover strategy | 30 min | HIGH |
| Mean reversion trend filter | 30 min | HIGH |
| Bollinger Bands volume filter | 30 min | HIGH |
| Data freshness timestamps | 30 min | MEDIUM |
| **Phase 1 Total** | **3 hours** | **VERY HIGH** |
| 52-week breakout | 45 min | MEDIUM |
| Moving average trend | 45 min | MEDIUM |
| Volatility squeeze | 1 hour | MEDIUM |
| **Phase 2 Total** | **2.5 hours** | **HIGH** |
| Portfolio tracking (full) | 6 hours | VERY HIGH |
| Earnings calendar | 2 hours | HIGH |
| Screener MVP | 4 hours | VERY HIGH |
| **Phase 3 Total** | **12 hours** | **VERY HIGH** |

**Recommended approach**:
- Do Phase 1 this week (3 hours → massive quality improvement)
- Phase 2 next week (2.5 hours → coverage expansion)
- Phase 3 over next 2 weeks (12 hours → investor-ready platform)

---

## Files to Update in Summary

### Quick Wins (This Week)
1. Create: `Backend/routes/strategies/rsi.py`
2. Create: `Backend/routes/strategies/macd_crossover.py`
3. Update: `Backend/app.py` (register blueprints)
4. Update: `Backend/routes/strategies/mean_reversion.py` (add trend filter)
5. Update: `Backend/routes/strategies/bollinger_bands.py` (add volume filter)
6. Update: `Frontend/src/App.js` (add strategies to list)
7. Update: `Backend/routes/stock_data.py` (add metadata)
8. Update: `Frontend/src/components/StockChart.js` (display freshness)

### Next Priority
- Create portfolio DB schema
- Implement `/api/portfolio/*` routes
- Build watchlist UI
- Add earnings calendar integration

---

**See AUDIT_REPORT.md for full strategy analysis and recommendations.**
