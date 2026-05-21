import React from 'react';

export default function MarkovExplainPanel() {
  return (
    <div className="markov-explain">
      <section className="markov-explain__section">
        <h3 className="markov-explain__title">What is the Markov Method?</h3>
        <p>
          The Markov Method classifies every trading day as one of three
          regimes — <span className="markov-explain__regime markov-explain__regime--bull">Bull</span>,
          {' '}<span className="markov-explain__regime markov-explain__regime--bear">Bear</span>, or
          {' '}<span className="markov-explain__regime markov-explain__regime--side">Sideways</span> —
          using a simple rolling log-return rule, then builds a 3×3 <strong>transition
          matrix</strong> describing how often each regime flips to each other.
          Raising that matrix to a power (P<sup>n</sup>) yields the probability
          distribution <em>n days from now</em> given today's regime — a Markov
          chain forecast.
        </p>
        <p>
          The framework is based on Lewis Jackson's{' '}
          <em>Markov hedge-fund method</em>, ported here as a tradeable strategy
          for the Custom ETF system.
        </p>
      </section>

      <section className="markov-explain__section">
        <h3 className="markov-explain__title">1. Regime Classification</h3>
        <p>
          For every bar, compute the 20-day rolling log return:
        </p>
        <pre className="markov-explain__formula">
{`log_ret = log(close_today / close_20_days_ago)`}
        </pre>
        <p>Then label the bar by where that return lands:</p>
        <ul className="markov-explain__list">
          <li><span className="markov-explain__regime markov-explain__regime--bull">Bull</span> — log_ret &gt; +5%</li>
          <li><span className="markov-explain__regime markov-explain__regime--bear">Bear</span> — log_ret &lt; −5%</li>
          <li><span className="markov-explain__regime markov-explain__regime--side">Sideways</span> — anything else</li>
        </ul>
      </section>

      <section className="markov-explain__section">
        <h3 className="markov-explain__title">2. Transition Matrix &amp; Forecast</h3>
        <p>
          Count every regime transition observed in history (e.g.{' '}
          <em>Bull → Bear</em>) and row-normalise into a 3×3 stochastic matrix
          <em> P</em>. Each cell <em>P</em>[i,j] is the probability of being in
          regime j tomorrow given regime i today.
        </p>
        <p>
          The <strong>5-day forecast</strong> the strategy uses is the row of
          P<sup>5</sup> matching today's regime — i.e. the distribution over
          regimes 5 trading days from now. Higher P(Bull in 5d) → higher
          conviction the bull state will persist or arrive soon.
        </p>
      </section>

      <section className="markov-explain__section">
        <h3 className="markov-explain__title">3. Buy / Sell Rules</h3>
        <p>The strategy computes a composite score 0–100 for each ticker:</p>
        <pre className="markov-explain__formula">
{`score = 100 × ( 0.50 · P(Bull in 5d)
              + 0.30 · P(Bull in 3d)
              + 0.10 · is_currently_Bull
              + 0.10 · (1 − P(Bear in 5d)) )`}
        </pre>

        <div className="markov-explain__rules">
          <div className="markov-explain__rule markov-explain__rule--buy">
            <h4>BUY when ALL hold</h4>
            <ul className="markov-explain__list">
              <li>score ≥ <strong>65</strong></li>
              <li>current regime is <strong>Bull</strong> or <strong>Sideways</strong> (not Bear)</li>
              <li>P(Bear in 5d) &lt; <strong>35%</strong></li>
            </ul>
            <p className="markov-explain__hint">
              Together these enforce <em>"high conviction the next 5 days lean bullish,
              with limited downside risk."</em>
            </p>
          </div>

          <div className="markov-explain__rule markov-explain__rule--sell">
            <h4>SELL when ANY holds</h4>
            <ul className="markov-explain__list">
              <li>score ≤ <strong>50</strong></li>
              <li>current regime turns <strong>Bear</strong></li>
              <li>P(Bear in 5d) ≥ <strong>50%</strong></li>
            </ul>
            <p className="markov-explain__hint">
              The 65 buy / 50 sell gap is a deliberate <em>15-point dead zone</em> that
              prevents flip-flopping right at the threshold.
            </p>
          </div>
        </div>

        <p>
          In the live rebalance flow, a position is also sold whenever its ticker
          drops out of the universe's top 10 — keeping concentration capped at the
          conviction leaders.
        </p>
      </section>

      <section className="markov-explain__section">
        <h3 className="markov-explain__title">4. Position Sizing — Variable by Conviction</h3>
        <p>
          Standard ETF strategies in this app size positions equally (one slot
          per pick). The Markov strategy instead <strong>scales position size
          with conviction</strong>: a stock with a 90% 5-day bull probability
          gets roughly 5× the dollars of a marginal 55%-bull pick.
        </p>

        <p>The weight formula:</p>
        <pre className="markov-explain__formula">
{`weight(pick) = max(1.0,  1.0 + (P(Bull 5d) − 0.5) × 10)`}
        </pre>

        <p>
          The simulator then normalises weights across the selected positions so
          they sum to one "max-positions worth" of equity, capped at 99% of cash
          to leave a slippage buffer:
        </p>
        <pre className="markov-explain__formula">
{`allocation_per_pick = total_deployable × (weight / Σ weights)`}
        </pre>

        <table className="markov-explain__table">
          <thead>
            <tr>
              <th>P(Bull 5d)</th>
              <th className="num">Raw weight</th>
              <th>Interpretation</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>50%</td><td className="num">1.0×</td><td>Baseline — same as equal-weight</td></tr>
            <tr><td>60%</td><td className="num">2.0×</td><td>Small conviction lift</td></tr>
            <tr><td>70%</td><td className="num">3.0×</td><td>Moderate lift</td></tr>
            <tr><td>80%</td><td className="num">4.0×</td><td>Heavy lift</td></tr>
            <tr><td>90%</td><td className="num">5.0×</td><td>Maximum — concentrate dollars here</td></tr>
          </tbody>
        </table>

        <p className="markov-explain__hint">
          <strong>Worked example.</strong> If today's picks are
          {' '}AAPL (95% bull), MSFT (75% bull), and NVDA (52% bull) — weights
          are 5.5×, 3.5×, 1.2× → AAPL gets ~54% of the deployable dollars,
          MSFT gets ~34%, NVDA gets ~12%. The same three names equal-weighted
          would each get ~33%.
        </p>

        <p>
          <strong>If fewer than 10 tickers clear the buy bar</strong>, the
          remaining slots stay in cash — the strategy never reaches for marginal
          picks just to stay fully invested.
        </p>
      </section>

      <section className="markov-explain__section">
        <h3 className="markov-explain__title">5. How the Backtest Avoids Look-Ahead Bias</h3>
        <p>
          A naïve backtest would build the transition matrix from <em>all</em>
          available history at every decision — letting tomorrow's data leak into
          today's signal. The Markov backtest instead walks forward and
          <strong> rebuilds the matrix at each rebalance using only data through
          that date</strong>:
        </p>
        <ul className="markov-explain__list">
          <li>Per-ticker cumulative transition counts are precomputed once</li>
          <li>At each rebalance date, the matrix is built from counts <em>up to that bar only</em></li>
          <li>The forecast P<sup>5</sup> uses that historically-valid matrix</li>
          <li>Buy/sell decisions are made against that snapshot, then time advances</li>
        </ul>
        <p>
          This means the matrix is <em>noisier</em> early in a backtest (fewer
          transitions observed) and stabilises as more history accumulates — a
          realistic picture of how the strategy would have actually performed.
        </p>
      </section>

      <section className="markov-explain__section markov-explain__section--caveat">
        <h3 className="markov-explain__title">Caveats &amp; Limitations</h3>
        <ul className="markov-explain__list">
          <li>
            <strong>Markov assumption.</strong> The model assumes the future
            depends only on today's regime, not on the path that got us here.
            Real markets show momentum and mean-reversion that violate this. The
            5-day forecast is a useful summary, not a probability you should
            size positions against blindly.
          </li>
          <li>
            <strong>Regime smoothing.</strong> Each bar's regime is already a
            20-day log-return label — so a "5 day forecast" is really
            "5 days of a 20-day-smoothed signal." Short-horizon predictions are
            heavily overlapped with the present.
          </li>
          <li>
            <strong>Survivorship bias in the backtest.</strong> Uses today's
            S&amp;P 500 constituents. Stocks delisted before today won't appear
            in older windows — measured returns may be modestly inflated.
          </li>
          <li>
            <strong>Transaction costs.</strong> Only a 5-bps slippage is modelled
            on each fill. Real-world commissions, market impact, and rebalance
            timing all matter and aren't simulated.
          </li>
        </ul>
      </section>
    </div>
  );
}
