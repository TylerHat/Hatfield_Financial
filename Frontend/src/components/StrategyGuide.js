import React, { useState } from 'react';

const STRATEGIES = [
  {
    id: 'pead',
    title: 'Post-Earnings Drift Strategy',
    subtitle: 'Riding the market\'s slow reaction to earnings surprises',
    color: '#58a6ff',
    sections: [
      {
        heading: 'What Is It?',
        body: `The Post-Earnings Announcement Drift (PEAD) strategy is based on a well-documented
market anomaly: after a company reports earnings, the stock price often continues to drift
in the direction of the earnings surprise for days or even weeks afterward.

A positive earnings surprise (beat) tends to be followed by further upward drift, while a
negative surprise (miss) tends to be followed by continued selling pressure.`,
      },
      {
        heading: 'Why Does It Work?',
        body: `PEAD exploits a form of market underreaction. Efficient Market Hypothesis (EMH) suggests
prices instantly reflect new information — but in practice, investors and analysts take time
to fully digest earnings reports, update price targets, and rotate into winning positions.

This gradual repricing creates a tradeable window, typically 2–5 trading days after the
announcement. Academic studies (Ball & Brown, 1968; Bernard & Thomas, 1989) have confirmed
this drift persists even after accounting for transaction costs.`,
      },
      {
        heading: 'How This Implementation Works',
        body: `1. Earnings dates are fetched from Yahoo Finance for the selected date range.
2. For each earnings date, the closing price the day before earnings is compared to
   the close on Day 1 and Day 2 post-earnings.
3. A BUY signal is generated if Day 1 and Day 2 both close higher than the pre-earnings price
   (upward drift confirmed over two days).
4. A SELL signal is generated if both Day 1 and Day 2 close lower (downward drift).`,
      },
      {
        heading: 'Strengths',
        body: `• Grounded in decades of academic research\n• Clear, objective entry rules based on price action\n• Works across market caps and sectors\n• Combines well with fundamental catalysts (large beats/misses)`,
      },
      {
        heading: 'Risks & Limitations',
        body: `• Not all earnings surprises produce sustained drift — gaps can reverse\n• Works best with strong, clear surprises; mixed results are noisy\n• Pre-announcement run-ups can reduce the post-earnings edge\n• Liquidity risk around earnings in small-cap stocks\n• Best used alongside fundamental research, not in isolation`,
      },
      {
        heading: 'Best Conditions',
        body: `• Stock reported a significant earnings beat or miss (>5% gap)\n• Sector momentum aligns with the direction of the surprise\n• Low short interest (avoids short-squeeze distortions)\n• First 1–3 sessions after earnings — drift weakens after that`,
      },
    ],
  },
  {
    id: 'rs',
    title: 'Relative Strength vs Market',
    subtitle: 'Buying the leaders, avoiding the laggards',
    color: '#f0883e',
    sections: [
      {
        heading: 'What Is It?',
        body: `Relative Strength (RS) measures how a stock is performing compared to a benchmark —
in this case, the S&P 500 (SPY). A stock with rising relative strength is outperforming
the broader market; one with falling relative strength is underperforming.

The strategy generates BUY signals when a stock's RS ratio crosses above its own moving
average (gaining momentum vs the market), and SELL signals when it crosses below.`,
      },
      {
        heading: 'Why Does It Work?',
        body: `Momentum is one of the most robust factors in finance. Stocks that are outperforming
the market tend to continue outperforming for weeks to months, while laggards tend to
continue lagging. This is the foundation of factor investing and is used extensively
by institutional investors.

The comparison to SPY normalizes for broad market moves — a stock rising 5% in a market
up 6% is actually underperforming, while a stock flat in a down market is showing strength.`,
      },
      {
        heading: 'How This Implementation Works',
        body: `1. Daily closing prices are fetched for both the stock and SPY.
2. The RS Ratio is calculated as: Stock Price ÷ SPY Price (each day).
3. A 10-day moving average of the RS Ratio is computed as a signal smoother.
4. A BUY signal is generated when the RS Ratio crosses above its 10-day MA
   (stock beginning to outperform the market).
5. A SELL signal is generated when the RS Ratio crosses below its 10-day MA
   (stock beginning to underperform).`,
      },
      {
        heading: 'Strengths',
        body: `• Market-neutral framing — accounts for broad moves automatically\n• Works well in trending markets and sector rotations\n• Useful for both stock selection and exit timing\n• Backed by decades of momentum factor research`,
      },
      {
        heading: 'Risks & Limitations',
        body: `• Generates frequent signals in choppy, sideways markets\n• 10-day MA is relatively fast — adjust for fewer, higher-conviction signals\n• Momentum strategies can suffer sharp reversals during market regime changes\n• Does not account for fundamental value — a stock can have high RS at any valuation`,
      },
      {
        heading: 'Best Conditions',
        body: `• Trending market environment (not choppy or range-bound)\n• Stock showing RS improvement alongside rising volume\n• Sector also outperforming the S&P 500 (sector tailwind)\n• Combine with valuation screens to avoid buying expensive momentum traps`,
      },
    ],
  },
  {
    id: 'bb',
    title: 'Bollinger Bands',
    subtitle: 'Trading mean reversion using statistical price envelopes',
    color: '#bc8cff',
    sections: [
      {
        heading: 'What Is It?',
        body: `Bollinger Bands, developed by John Bollinger in the 1980s, place two bands around a
20-day moving average at ±2 standard deviations. Because standard deviation measures
volatility, the bands automatically widen during high-volatility periods and narrow
during low-volatility (consolidation) periods.

Approximately 95% of price action statistically occurs within the bands. When price
moves outside, it signals an extreme condition.`,
      },
      {
        heading: 'Why Does It Work?',
        body: `The strategy exploits mean reversion — the tendency of prices to return toward their
average after extreme moves. When a stock closes beyond the upper or lower band, it has
moved more than 2 standard deviations from its 20-day average, which historically is
unsustainable for extended periods.

The bands also act as dynamic support and resistance levels that adapt to changing
volatility, making them more robust than fixed-price levels.`,
      },
      {
        heading: 'How This Implementation Works',
        body: `1. The 20-day simple moving average (SMA) is calculated.
2. The 20-day standard deviation of closing prices is computed.
3. Upper Band = SMA + (2 × Standard Deviation)
   Lower Band = SMA − (2 × Standard Deviation)
4. A BUY signal is generated when the closing price crosses below the lower band
   (statistically oversold — mean reversion upward expected).
5. A SELL signal is generated when the closing price crosses above the upper band
   (statistically overbought — mean reversion downward expected).`,
      },
      {
        heading: 'Strengths',
        body: `• Self-adjusting to volatility — works in different market regimes\n• Clear, objective signal rules based on statistical thresholds\n• Useful for both entry timing and identifying overextended moves\n• Band width itself is a volatility indicator (narrow = potential breakout ahead)`,
      },
      {
        heading: 'Risks & Limitations',
        body: `• In strong trending markets, price can "walk the band" — repeatedly touching
  the upper band without reversing (false sell signals in uptrends)\n• Does not indicate direction of breakout when bands are narrow\n• 2-standard-deviation threshold may miss signals in very low-volatility stocks\n• Best used with a volume confirmation to filter false signals`,
      },
      {
        heading: 'Best Conditions',
        body: `• Mean-reverting (range-bound) stocks and markets — not strong trends\n• Combine with RSI: a band touch + RSI extreme = higher-conviction signal\n• Narrow bands (consolidation) preceding a band break can signal trend initiation\n• Higher timeframes (daily/weekly) produce more reliable signals than intraday`,
      },
    ],
  },
  {
    id: 'mr',
    title: 'Mean Reversion After Large Drawdown',
    subtitle: 'Buying oversold dips after significant pullbacks from recent highs',
    color: '#3fb950',
    sections: [
      {
        heading: 'What Is It?',
        body: `This strategy identifies stocks that have experienced a significant short-term
drawdown — specifically, a 10% or greater decline from their 20-day trailing high.
After such a pullback, the strategy anticipates that the stock will revert toward
its recent high, providing a mean reversion buying opportunity.

The exit signal triggers when the stock recovers to within 3% of the 20-day high,
capturing the majority of the rebound.`,
      },
      {
        heading: 'Why Does It Work?',
        body: `Large short-term drawdowns often represent market overreaction to news, technical
selling pressure, or temporary sentiment shifts — not a permanent change in a
company's fundamental value. Research shows that stocks with strong fundamentals
tend to recover from sharp, short-term selloffs.

This strategy exploits the difference between price and value: when price falls
sharply without a corresponding change in intrinsic value, the gap eventually closes
as the market corrects its overreaction.`,
      },
      {
        heading: 'How This Implementation Works',
        body: `1. The 20-day trailing high (rolling max of closing prices) is computed each day.
2. Daily drawdown is calculated as: (Close − 20-day High) ÷ 20-day High.
3. A BUY signal is generated when drawdown first reaches −10% or worse.
4. The strategy enters "drawdown mode" and waits for recovery.
5. A SELL signal is generated when the drawdown recovers to within 3%
   of the 20-day high (drawdown < −3%).
6. The position resets, ready for the next drawdown opportunity.`,
      },
      {
        heading: 'Strengths',
        body: `• Simple, rule-based logic with clear entry and exit criteria\n• Naturally buys on weakness and sells into strength\n• Captures short-term reversals that momentum strategies miss\n• Can produce strong risk/reward ratios when correctly timed`,
      },
      {
        heading: 'Risks & Limitations',
        body: `• Risk of "catching a falling knife" — drawdowns can deepen beyond 10%\n• Works best for fundamentally sound stocks; dangerous for deteriorating businesses\n• Does not distinguish between a healthy pullback and a fundamental breakdown\n• May have long periods with no signals in smoothly trending stocks\n• Single threshold (10%) is a starting point — adjust based on stock volatility`,
      },
      {
        heading: 'Best Conditions',
        body: `• High-quality stocks in uptrends experiencing a temporary pullback\n• Drawdown caused by market-wide selling, not company-specific bad news\n• Volume drying up at the lows (sellers exhausted)\n• Combine with Bollinger Bands: buy signal near lower band strengthens the case\n• Avoid during earnings season unless you understand the fundamental catalyst`,
      },
    ],
  },
  {
    id: 'macd',
    title: 'MACD Crossover',
    subtitle: 'Capturing momentum shifts with moving average convergence',
    color: '#58a6ff',
    sections: [
      {
        heading: 'What Is It?',
        body: `The Moving Average Convergence Divergence (MACD), developed by Gerald Appel in the
1970s, is a trend-following momentum indicator built from the difference between a
12-period and 26-period exponential moving average (EMA).

A 9-period EMA of the MACD line — called the Signal line — acts as a trigger. When
the MACD crosses above the Signal line, it indicates building bullish momentum.
When it crosses below, bearish momentum is taking over.`,
      },
      {
        heading: 'Why Does It Work?',
        body: `MACD captures the convergence and divergence of two EMAs with different time horizons.
The faster 12-period EMA reacts quickly to price changes; the slower 26-period EMA
reflects the longer trend. When short-term momentum accelerates beyond the long-term
trend, the crossover flags a potential directional move.

Because both lines are exponential (giving more weight to recent prices), MACD is
more responsive than simple moving average crossovers, making it useful for detecting
early momentum shifts rather than lagging behind them.`,
      },
      {
        heading: 'How This Implementation Works',
        body: `1. EMA(12) and EMA(26) are computed on daily closing prices.
2. MACD Line = EMA(12) − EMA(26).
3. Signal Line = EMA(9) of the MACD Line.
4. Histogram = MACD Line − Signal Line (positive = bullish, negative = bearish).
5. A BUY signal is generated when MACD crosses above the Signal line.
6. A SELL signal is generated when MACD crosses below the Signal line.
7. Signal score is normalized against the recent average histogram magnitude —
   a larger, more decisive crossover receives a higher conviction score.`,
      },
      {
        heading: 'Strengths',
        body: `• Combines trend direction and momentum in a single indicator\n• More responsive than simple MA crossovers due to exponential weighting\n• Histogram visually shows momentum acceleration before the crossover occurs\n• Works across asset classes and timeframes\n• The MACD sub-chart is always visible, so signals can be confirmed visually`,
      },
      {
        heading: 'Risks & Limitations',
        body: `• Lags by nature — crossovers occur after the momentum shift has begun\n• Generates frequent false signals in choppy, sideways markets\n• Does not indicate overbought/oversold conditions (use with RSI for that)\n• Signal line crossovers near the zero line are weaker than those far from zero\n• Not suitable as a standalone system — best used with trend or volume confirmation`,
      },
      {
        heading: 'Best Conditions',
        body: `• Trending markets — MACD thrives when there is a clear directional bias\n• Crossovers that occur well above or below the zero line carry more weight\n• Combine with RSI: MACD BUY + RSI leaving oversold = high-conviction setup\n• Divergence: price makes a new low but MACD does not → hidden bullish strength\n• Higher timeframes (daily) reduce noise vs intraday MACD signals`,
      },
    ],
  },
  {
    id: 'bk52',
    title: '52-Week Breakout',
    subtitle: 'Trading new highs and lows with volume-confirmed momentum',
    color: '#3fb950',
    sections: [
      {
        heading: 'What Is It?',
        body: `The 52-Week Breakout strategy is one of the most time-tested momentum approaches in
technical analysis. It buys when a stock closes at a new 52-week high and sells
(signals bearish risk) when it closes at a new 52-week low.

The 52-week high and low act as significant psychological and technical levels.
A breakout above the 52-week high signals that all buyers over the past year are
now in profit — removing overhead supply. A breakdown below the 52-week low is
the opposite: all recent buyers are at a loss, creating persistent selling pressure.`,
      },
      {
        heading: 'Why Does It Work?',
        body: `New 52-week highs attract institutional attention. Fund managers use price milestones
as screens for new positions, and algorithmic strategies are often programmed to
buy breakouts from annual highs. This self-reinforcing demand pushes prices further.

Academically, the "52-week high effect" (George & Hwang, 2004) is a documented
anomaly: stocks near their 52-week high tend to underreact to positive news,
then continue higher. The volume filter (> 1.2× average) confirms that the breakout
has institutional participation — not just a low-volume anomaly.`,
      },
      {
        heading: 'How This Implementation Works',
        body: `1. The rolling 252-day (52-week) high and low are calculated using prior day's close
   (shifted by 1 so today's price doesn't count toward today's threshold).
2. A BUY signal is generated when the closing price first exceeds the 252-day high
   AND volume is above 1.2× the 20-day average.
3. A SELL signal is generated when the closing price first falls below the 252-day low
   AND volume is above 1.2× the 20-day average.
4. Score is based on the distance of the breakout above/below the threshold plus the
   volume ratio — a bigger, higher-volume breakout earns a higher conviction score.`,
      },
      {
        heading: 'Strengths',
        body: `• Grounded in well-researched market anomaly (52-week high effect)\n• Volume confirmation filters false breakouts from low-liquidity moves\n• Clear, objective levels — the 52-week high/low are widely watched by all participants\n• Works best in trending markets and for growth/momentum stocks\n• Simple to understand and execute; widely used by institutional traders`,
      },
      {
        heading: 'Risks & Limitations',
        body: `• Late entry — by the time a 52-week high is broken, the move is already mature\n• "Buy high, sell higher" is psychologically difficult; most investors resist\n• False breakouts occur frequently in choppy, news-driven markets\n• Does not account for valuation — a breakout can happen at any P/E\n• Requires longer date ranges (1+ year) to build the 252-day rolling window`,
      },
      {
        heading: 'Best Conditions',
        body: `• Bull market or sector in a clear uptrend\n• Breakout on unusually high volume (2× average is even better)\n• No major fundamental headwinds (earnings risk, regulatory issues)\n• Stock consolidating just below 52-week high for weeks before the break\n• Combine with RS vs market: outperforming stocks at new highs are the strongest setups`,
      },
    ],
  },
  {
    id: 'vs',
    title: 'Volatility Squeeze',
    subtitle: 'Catching explosive breakouts after periods of compressed volatility',
    color: '#f0883e',
    sections: [
      {
        heading: 'What Is It?',
        body: `The Volatility Squeeze strategy identifies periods when price volatility contracts
to an unusually narrow range — a "squeeze" — and then waits for volatility to
expand explosively. The squeeze is measured using Bollinger Band width (distance
between upper and lower bands), which narrows when volatility is low.

When the squeeze releases and Band width expands sharply, a directional move
is likely underway. Price position relative to the 20-day moving average
determines whether that move is bullish or bearish.`,
      },
      {
        heading: 'Why Does It Work?',
        body: `Markets alternate between trending (high volatility) and consolidating (low volatility)
phases. Bollinger Band squeezes mark the transition from consolidation to trend.
Institutional traders often accumulate or distribute positions during quiet periods,
and the squeeze release reveals the direction of that activity.

This approach is related to John Bollinger's "Squeeze" concept and is used by
traders who want to enter at the beginning of a new trend rather than chasing
a move that has already extended.`,
      },
      {
        heading: 'How This Implementation Works',
        body: `1. Bollinger Bands (20-day MA, ±2 standard deviations) are calculated.
2. BB Width = Upper Band − Lower Band (measures current volatility).
3. The 60-day 20th percentile of BB Width defines the "squeeze threshold."
4. When BB Width drops below the 20th percentile, the stock is in a squeeze.
5. When BB Width expands back above the 60-day median after a squeeze, a signal fires.
6. If price > MA20 at the time of expansion → BUY (bullish breakout expected).
7. If price < MA20 at the time of expansion → SELL (bearish breakdown expected).
8. Score is based on how aggressively the width expanded vs the squeeze level.`,
      },
      {
        heading: 'Strengths',
        body: `• Filters out random volatility — only signals when a genuine squeeze releases\n• Direction-aware: uses MA20 to distinguish bullish from bearish breakouts\n• Score reflects breakout force — higher expansion = higher conviction\n• Works well on individual stocks and ETFs across multiple timeframes`,
      },
      {
        heading: 'Risks & Limitations',
        body: `• False breakouts can occur — price may expand briefly then reverse\n• Squeeze duration varies; a long squeeze may not lead to a sustained move\n• MA20 direction filter can be wrong at major turning points\n• Best used with additional confirmation (volume, sector alignment)\n• 60-day rolling window requires adequate history — newer stocks may not have enough data`,
      },
      {
        heading: 'Best Conditions',
        body: `• Stock in a multi-week consolidation with declining volume (classic squeeze setup)\n• Volume surge at the moment of squeeze release strengthens conviction\n• Sector or market index also breaking out in the same direction\n• Wider pre-squeeze price range followed by tighter consolidation (coiling pattern)\n• Avoid during earnings announcements — volatility expansion is not directional then`,
      },
    ],
  },
  {
    id: 'rsi',
    title: 'RSI Oversold / Overbought',
    subtitle: 'Using momentum exhaustion to time reversals',
    color: '#f85149',
    sections: [
      {
        heading: 'What Is It?',
        body: `The Relative Strength Index (RSI), developed by J. Welles Wilder in 1978, is a
momentum oscillator that measures the speed and magnitude of recent price changes.
It oscillates between 0 and 100 and is used to identify whether a stock is
overbought (likely to fall) or oversold (likely to rise).

Readings below 30 are traditionally considered oversold; readings above 70 are
considered overbought.`,
      },
      {
        heading: 'Why Does It Work?',
        body: `RSI captures momentum exhaustion. When a stock moves sharply in one direction for
several consecutive sessions, buyers or sellers become fatigued and the move tends
to slow or reverse. The RSI quantifies this exhaustion by comparing the average
size of up-closes to down-closes over a 14-day window.

The 30/70 thresholds correspond to extreme average gain-to-loss ratios, signaling
that the recent trend has outpaced fundamentals and a mean reversion is probable.`,
      },
      {
        heading: 'How This Implementation Works',
        body: `1. The 14-period RSI is computed using Wilder's exponential smoothing
   (alpha = 1/14) applied separately to gains and losses.
2. A BUY signal is generated when RSI crosses from above 30 to below 30
   (price enters oversold territory — reversal upward expected).
3. A SELL signal is generated when RSI crosses from below 70 to above 70
   (price enters overbought territory — reversal downward expected).
4. Crossover detection prevents repeated signals during sustained extremes.
5. Signal score reflects how deep into oversold/overbought territory the RSI moved.`,
      },
      {
        heading: 'Strengths',
        body: `• One of the most widely used and battle-tested indicators in technical analysis\n• Clear, objective thresholds (30/70) with decades of supporting literature\n• Works across all asset classes and timeframes\n• Crossover-based signals filter out noise from prolonged extremes`,
      },
      {
        heading: 'Risks & Limitations',
        body: `• In strong trends, RSI can stay overbought/oversold for extended periods\n• Does not indicate how far or how fast the reversal will be\n• Less reliable on low-volume or thinly traded stocks\n• 14-period window is standard but may need adjustment for very volatile names\n• Signals are more reliable when confirmed by price action (e.g., a reversal candle)`,
      },
      {
        heading: 'Best Conditions',
        body: `• Range-bound or mean-reverting markets — not strong trends\n• RSI extreme combined with a Bollinger Band touch = high-conviction setup\n• Divergence: price makes a new low but RSI does not → hidden strength\n• Higher win rate when RSI reaches extreme levels (< 20 or > 80) rather than just 30/70\n• Confirm with volume: a reversal on rising volume strengthens the signal`,
      },
    ],
  },
];

export default function StrategyGuide() {
  const [active, setActive] = useState('pead');
  const strategy = STRATEGIES.find((s) => s.id === active);

  return (
    <div className="guide-container">
      <div className="guide-header">
        <h2>Strategy Guide</h2>
        <p>
          A reference for understanding each trading strategy available in this dashboard —
          what it is, why it works, and how to use it effectively.
        </p>
      </div>

      {/* Strategy selector tabs */}
      <div className="guide-nav">
        {STRATEGIES.map((s) => (
          <button
            key={s.id}
            className={`guide-nav-btn ${active === s.id ? 'active' : ''}`}
            style={active === s.id ? { borderColor: s.color, color: s.color } : {}}
            onClick={() => setActive(s.id)}
          >
            {s.title.split(' ').slice(0, 2).join(' ')}…
          </button>
        ))}
      </div>

      {/* Strategy content */}
      {strategy && (
        <div className="guide-content">
          <div className="guide-strategy-header" style={{ borderLeftColor: strategy.color }}>
            <h3 style={{ color: strategy.color }}>{strategy.title}</h3>
            <p className="guide-subtitle">{strategy.subtitle}</p>
          </div>

          <div className="guide-sections">
            {strategy.sections.map((sec) => (
              <div key={sec.heading} className="guide-section">
                <h4 className="guide-section-title">{sec.heading}</h4>
                <div className="guide-section-body">
                  {sec.body.split('\n').map((line, i) =>
                    line.trim() === '' ? (
                      <br key={i} />
                    ) : (
                      <p key={i}>{line}</p>
                    )
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Quick-reference summary card */}
          <div className="guide-summary-card" style={{ borderColor: strategy.color }}>
            <div className="summary-row">
              <span className="summary-label">Signal Type</span>
              <span>BUY and SELL overlays on the price chart</span>
            </div>
            <div className="summary-row">
              <span className="summary-label">Data Required</span>
              <span>Daily closing prices via Yahoo Finance (free)</span>
            </div>
            <div className="summary-row">
              <span className="summary-label">How to Activate</span>
              <span>
                Enter a ticker, select <strong>{strategy.title}</strong> from the dropdown
              </span>
            </div>
            <div className="summary-row">
              <span className="summary-label">Signal Display</span>
              <span>
                Green ▲ triangle = BUY &nbsp;·&nbsp; Red ▼ triangle = SELL. Hover for reason.
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
