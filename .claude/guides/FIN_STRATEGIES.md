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

**Indicators**: 20-day rolling-max high (currently **includes today's close** — no `shift(1)`, unlike 52-Week Breakout which does shift), drawdown from that high, 200-day MA (trend filter)

**Signal logic**
- **BUY**: Drawdown ≥ 10% from 20-day high AND price above MA200 (uptrend filter) → dip-buying in uptrend
- **SELL**: Price recovers to within 3% of the 20-day high → take-profit exit

State machine: only one BUY allowed per drawdown episode; SELL resets it.

**Score**: `abs(drawdown_pct) × 500`, capped at 100

> ⚠️ The 20-day high not being shifted is a known mild look-ahead. See OPTIMIZATION_FINDINGS.md (Financial Bugs).

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

## Custom ETF Strategies

Distinct from the 9 chart-analysis strategies above. Custom ETF strategies are **universe-wide
portfolio simulators**: each maps a recommendation row → 0-100 score, and the engine buys the
top-`max_positions` names (equal-weight unless the strategy overrides `weight()`), rebalancing on
the Recommendations refresh (24h cooldown). Registered in
`Backend/services/custom_etf/strategies/__init__.py`.

**Shared machinery (HFA-069):** the sell/mark/buy decision pass lives in
`services/custom_etf/rebalance_core.py` and is executed verbatim by BOTH the live simulator and
the walk-forward backtest engine (`services/custom_etf/walk_forward.py`) — a backtest is the live
strategy replayed over history. Price-derived row fields (`momentum`, `momentum6m`, `realizedVol`,
`trendAlignment`, `macdStatus`, `fiftyTwoWeekPosition`, markov fields) are computed by
`services/row_features.py`, shared between the prewarm and the engine so the two can't drift.
Strategies with `historical_backtest_safe = False` (inputs are today-snapshot .info/analyst
fields) are refused by the engine.

### Backtest support (Custom ETF)

| Strategy | ID | Backtestable | Why not |
|----------|----|--------------|---------|
| Buy Score | `buy-score-top10` | No | Valuation/quality/growth/analyst inputs are today-snapshot |
| Momentum | `momentum-top10` | **Yes** | Price-derived only |
| Low Volatility | `low-vol-defensive` | No | Quality inputs (ROE/debt/margins/risk) are today-snapshot |
| Analyst Conviction | `analyst-conviction-top10` | No | Analyst consensus is today-snapshot |
| Undervalued Strong Buy | `undervalued-strong-buy-top10` | No | Analyst + valuation inputs are today-snapshot |
| Markov Regime | `markov-regime` | **Yes** | Price-derived only |
| 52-Week-High | `52-week-high-top10` | **Yes** | Price-derived only |
| Sector Rotation | `sector-rotation-top3` | **Yes** | Price-derived only (fixed SPDR universe) |

### Buy Score — Top 10 Green
**ID**: `buy-score-top10` · **Buy ≥** 70 · **Sell ≤** 65 · **Max** 10

Quality/Value/GARP blend mirroring the Recommendations table Buy Score. Weights: Valuation 18%,
Trend composite 25%, Analyst 12%, Quality 10%, Growth 10%, 52-week position 8%, Volatility 7%,
RSI (regime-conditioned) 5%, Governance 3%, Coverage 2%. See `buy_score.py` for curves.

### Momentum — Top 10 Trending
**ID**: `momentum-top10` · **Buy ≥** 70 · **Sell ≤** 60 · **Max** 10 · **Backtestable**

Cross-sectional momentum factor — uncorrelated to Buy Score. **Corrected in HFA-069**: the
original ranked on 1-MONTH relative return (the short-term-reversal horizon) with an absolute
scale that needed a ~+10% one-month excess move to buy, leaving the sleeve mostly in cash.
Now ranks on `momentum6m` (6-1 month excess return vs SPY — the Jegadeesh–Titman window,
skipping the mean-reverting most recent month) mapped to a **cross-sectional percentile** of the
day's universe via the `prepare()` hook. Weights: momentum percentile 50%, trend alignment 25%,
MACD status 15%, 52-week position 10%. Bearish trend/MACD confirmations act as a soft
absolute-momentum gate (pushes toward cash in broad downtrends). See `momentum_top10.py`.

### Low Volatility — Defensive Top 10
**ID**: `low-vol-defensive` · **Buy ≥** 65 · **Sell ≤** 55 · **Max** 10

Defensive ballast — captures the low-volatility anomaly (Frazzini–Pedersen). **Corrected in
HFA-069**: the original scored `volRatio` (ATR vs the stock's OWN average — a self-relative
compression signal, not low volatility). Now ranks `realizedVol` (annualized σ of daily returns,
126d, from the prewarm) **cross-sectionally** via `prepare()`: lowest-vol names in the universe
score highest. Weights: low realized vol 35%, ROE 20%, low debt 15%, inverted overall-risk 15%,
gross margin 15%. Lower thresholds keep the portfolio invested when high-quality low-vol names
are scarce. Not backtestable (quality inputs are today-snapshot). See `low_vol_defensive.py`.

### Analyst Conviction — Top 10
**ID**: `analyst-conviction-top10` · **Buy ≥** 60 · **Sell ≤** 50 · **Max** 10

Strong_buy-filtered analyst-target strategy. Eligibility: `recommendationKey == 'strong_buy'`
AND `numberOfAnalysts ≥ 3`. Ranking: Bayesian-shrunk `targetUpsidePct` using
`adjusted = (n·upside + k·μ) / (n + k)` where `μ` is the strong_buy-universe mean upside
(recomputed each rebalance in `prepare()`) and `k = 10`. Shrunk upside is clamped to
[−10%, +50%] and linear-scaled to 0-100. Solves the small-sample problem so a 2-analyst
60%-target name doesn't dominate a 25-analyst 25%-target name. See `analyst_conviction.py`.

**Note**: this strategy uses the `EtfStrategy.prepare(recs)` hook to cache `μ` before scoring;
the simulator calls `prepare()` once per rebalance pass. Any future strategy that needs
universe-wide statistics should follow the same pattern.

### Undervalued Strong Buy — Top 10
**ID**: `undervalued-strong-buy-top10` · **Buy ≥** 65 · **Sell ≤** 55 · **Max** 10

Valuation-led companion to `analyst-conviction-top10`. Same strong_buy + ≥3 analysts gate,
plus a value-trap guard (positive ROE, debt/equity < 200) and a hard requirement that
`forwardPE` or `fcfYield` be available so the valuation component isn't a fallback.
Score blend: **valuation 50%** (forwardPE + FCF yield via `buy_score` curves),
**Bayesian-shrunk analyst upside 40%** (same k=10 shrinkage as analyst-conviction,
clamped −10% → +50%), **quality 10%** (ROE + debt + gross margin). Uses the
`prepare()` hook to cache the strong_buy-universe mean upside each rebalance.
See `undervalued_strong_buy.py`.

### Markov Regime — Conviction-Weighted Bull
**ID**: `markov-regime` · **Buy ≥** 65 · **Sell ≤** 50 · **Max** 10 · **Slippage** 5 bps · **Starting capital** $100k

Per-ticker Markov regime classifier (Bull / Sideways / Bear) with a 3×3 transition
matrix forecast. The Recommendations prewarm computes `markovRegime`, `markovBull3d`,
`markovBull5d`, `markovBear5d` for every S&P 500 row. Score blend:
**P(Bull in 5d) 50%**, **P(Bull in 3d) 30%**, **current regime is Bull 10%**,
**(1 − P(Bear in 5d)) 10%** → clamped 0-100.

Eligibility gates: `currentPrice` present, Markov fields present, current regime ≠ Bear,
`markovBear5d < 0.35`. Position sizing is non-uniform — `weight()` returns
`max(1.0, 1.0 + (bull_5d − 0.5) × 10)` so a 90% bull forecast gets ~5× the dollar
allocation of a marginal 55% pick. The only registered strategy that uses non-equal
weighting today. See `markov_regime.py` and `services/markov/analyze.py` for the
regime classification math.

**Backtest note (HFA-069):** the Markov backtest now runs on the generic walk-forward engine and
replays these exact live rules (composite score, hold-until-sell hysteresis, eligibility gates,
conviction weights). The retired engine ranked by raw `bull_5d` and force-sold anything outside
the day's top 10 — a different, higher-turnover strategy — so pre-HFA-069 backtest numbers are not
comparable to current ones.

### 52-Week-High Momentum — Top 10
**ID**: `52-week-high-top10` · **Buy ≥** 85 · **Sell ≤** 70 · **Max** 10 · **Backtestable** · Added HFA-069

George & Hwang (2004) anchoring effect: names pressing their 52-week highs keep drifting because
investors are slow to bid through a salient reference price. Distinct from (and complementary to)
6-1M return momentum. Weights: **52-week position 70%**, trend alignment 20%, MACD status 10%.
Buy ≥ 85 admits only names within ~10-15% of their high AND in an uptrend; sell ≤ 70 exits once a
holding slides roughly a third down its 52-week range or the trend breaks. Wide hysteresis keeps
turnover low. See `fifty_two_week_high.py`.

### Sector Rotation — Top 3 Momentum
**ID**: `sector-rotation-top3` · **Buy ≥** 60 · **Sell ≤** 45 · **Max** 3 · **Backtestable** · Added HFA-069

Dual-momentum (Antonacci) rotation over a **fixed custom universe** — the 11 SPDR select-sector
ETFs (XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY). Rows are synthesized from price
history by `services/custom_etf/custom_universe.py` (the SPDRs aren't in the Recommendations
snapshot). Score: 6-1M excess return vs SPY clamped ±15% → 0-100 (0% excess = 50), so buy ≥ 60 ≈
+3% excess and sell ≤ 45 ≈ −1.5% excess. Eligibility requires `momentum6mAbs > 0` — the
**absolute-momentum gate**: when a sector's own 6-1M return is negative it can't be bought no
matter its relative rank, so the sleeve degrades to cash in broad downtrends. Equal weight.
See `sector_rotation.py`.

---

## Maintenance Note

**Update this file when:**
- A new strategy is added → add its section with key, warmup, indicators, signal logic, and score formula
- An existing strategy's signal logic changes (thresholds, filters, indicators)
- A strategy is added to or removed from backtest support
- A Custom ETF strategy is added, removed, or has its weights/thresholds changed
