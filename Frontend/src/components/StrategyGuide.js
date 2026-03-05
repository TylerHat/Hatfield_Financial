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
