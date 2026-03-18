# Hatfield Financial — Strategy Reference

9 strategies, each returning a `signals` array. See `API.md` for the full response contract.

All strategies share the same signal object shape:
`{ date, price, type (BUY|SELL), score (0-100), conviction (HIGH|MEDIUM|LOW), reason }`

Conviction thresholds: **HIGH** ≥ 60 · **MEDIUM** ≥ 30 · **LOW** < 30

---

## Bollinger Bands
**Key**: `bollinger-bands` · **Warmup**: 40 days

**Indicators**: 20-day SMA ± 2 standard deviations, 20-day volume MA

**Signal logic**
- **BUY**: Close crosses *below* the lower band + volume > 1.3× 20-day avg → oversold with volume confirmation
- **SELL**: Close crosses *above* the upper band + volume > 1.3× 20-day avg → overbought with volume confirmation

**Score**: distance of close from the violated band, scaled to band width (max 100)

---

## Mean Reversion
**Key**: `mean-reversion` · **Warmup**: 280 days

**Indicators**: 20-day trailing high, drawdown from that high, 200-day MA (trend filter)

**Signal logic**
- **BUY**: Drawdown ≥ 10% from 20-day high AND price above MA200 (uptrend filter) → dip-buying in uptrend
- **SELL**: Price recovers to within 3% of the 20-day high → take-profit exit

State machine: only one BUY allowed per drawdown episode; SELL resets it.

**Score**: `abs(drawdown_pct) × 500`, capped at 100

---

## Relative Strength
**Key**: `relative-strength` · **Warmup**: 20 days

**Indicators**: RS ratio (stock price / SPY price), 10-day MA of RS ratio

**Signal logic**
- **BUY**: RS ratio crosses *above* its 10-day MA → stock gaining strength vs the market
- **SELL**: RS ratio crosses *below* its 10-day MA → stock losing strength vs the market

Fetches SPY in parallel for the same date range.

**Score**: deviation of RS from its MA, scaled by 2000 (max 100)

---

## Post-Earnings Drift (PEAD)
**Key**: `post-earnings-drift` · **Warmup**: none

**Indicators**: earnings dates from yfinance, 2-day post-earnings price action

**Signal logic**
- **BUY**: Day 1 close > pre-earnings close AND Day 2 close > Day 1 close → confirmed upward drift
- **SELL**: Day 1 close < pre-earnings close AND Day 2 close < Day 1 close → confirmed downward drift

Signals fire on Day 1 post-earnings. If earnings data is unavailable, returns empty signals.

**Score**: `abs(day1_pct_move) × 500`, capped at 100

---

## MACD Crossover
**Key**: `macd-crossover` · **Warmup**: 90 days

**Indicators**: MACD line (EMA12 − EMA26), Signal line (EMA9 of MACD), Histogram

**Signal logic**
- **BUY**: MACD crosses *above* Signal line → bullish momentum shift
- **SELL**: MACD crosses *below* Signal line → bearish momentum shift

**Score**: current histogram value normalized against 30-day average histogram range, scaled by 60 (max 100)

---

## RSI
**Key**: `rsi` · **Warmup**: 60 days

**Indicators**: 14-period RSI using Wilder's exponential smoothing (alpha = 1/14)

**Signal logic**
- **BUY**: RSI crosses *below* 30 → enters oversold territory
- **SELL**: RSI crosses *above* 70 → enters overbought territory

Signals fire on the crossing candle only, not while already in the zone.

**Score**
- BUY: `(30 - rsi) / 30 × 100`
- SELL: `(rsi - 70) / 30 × 100`

---

## Volatility Squeeze
**Key**: `volatility-squeeze` · **Warmup**: 120 days

**Indicators**: Bollinger Bands (20, 2), 60-day 20th percentile of BB width (squeeze threshold), 60-day median BB width (expansion threshold)

**Signal logic**
Squeeze condition: `BB_Width < 60-day 20th percentile`

- **BUY**: Was in squeeze AND BB width expands above 60-day median AND close > MA20 → bullish breakout
- **SELL**: Was in squeeze AND BB width expands above 60-day median AND close < MA20 → bearish breakdown

Direction is determined by price relative to MA20 at the moment of squeeze release.

**Score**: `(expansion_ratio - 1) × 100` where expansion_ratio = BB_width / squeeze_threshold (max 100)

---

## 52-Week Breakout
**Key**: `52-week-breakout` · **Warmup**: 280 days

**Indicators**: Rolling 252-day high and low (shifted by 1 day so today's close doesn't influence its own threshold), 20-day volume MA

**Signal logic**
- **BUY**: Close breaks *above* rolling 52-week high on volume ≥ 1.2× 20-day avg
- **SELL**: Close breaks *below* rolling 52-week low on volume ≥ 1.2× 20-day avg

**Score**: `breakout_pct × 20 + (vol_ratio - 1.2) × 30`, floor of 10, max 100

---

## MA Confluence
**Key**: `ma-confluence` · **Warmup**: 280 days

**Indicators**: MA20, MA50, MA200

**Signal logic**
- **BUY**: All MAs align bullish for the first time: `close > MA20 > MA50 > MA200` (was not true previous day)
- **SELL**: All MAs align bearish for the first time: `close < MA20 < MA50 < MA200` (was not true previous day)

Signals fire only on the first day the full confluence condition is met — not on every day it holds.

**Score**: sum of MA20-MA50 separation % + MA50-MA200 separation %, scaled by 10 (floor 10, max 100)

---

## Backtest Strategy Support

The `/api/backtest/<ticker>` endpoint supports a subset of strategies with internal signal generators:

| Strategy Key | Supported |
|-------------|-----------|
| `bollinger-bands` | Yes |
| `rsi` | Yes |
| `macd-crossover` | Yes |
| `mean-reversion` | Yes |
| `relative-strength` | Yes |
| `post-earnings-drift` | No |
| `volatility-squeeze` | No |
| `52-week-breakout` | No |
| `ma-confluence` | No |

---

## Maintenance Note

**Update this file when:**
- A new strategy is added → add its section with key, warmup, indicators, signal logic, and score formula
- An existing strategy's signal logic changes (thresholds, filters, indicators)
- A strategy is added to or removed from backtest support
