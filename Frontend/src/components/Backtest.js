import React, { useState } from 'react';

const API_BASE = 'http://localhost:5000';

const STRATEGIES = [
  { value: 'bollinger-bands', label: 'Bollinger Bands' },
  { value: 'relative-strength', label: 'Relative Strength vs Market' },
  { value: 'mean-reversion', label: 'Mean Reversion After Large Drawdown' },
  { value: 'post-earnings-drift', label: 'Post-Earnings Drift' },
];

function toISODate(d) {
  return d.toISOString().split('T')[0];
}
function defaultDates() {
  const end = new Date();
  const start = new Date(end);
  start.setFullYear(start.getFullYear() - 1);
  return { start: toISODate(start), end: toISODate(end) };
}

function fmt$(n) {
  if (n == null) return '—';
  const abs = Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return (n < 0 ? '-$' : '$') + abs;
}
function fmtPct(n) {
  if (n == null) return '—';
  return (n >= 0 ? '+' : '') + n.toFixed(2) + '%';
}
function fmtShares(n) {
  if (n == null) return '—';
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function PnlCell({ value }) {
  if (value == null) return <td className="bt-td bt-td-right">—</td>;
  const cls = value >= 0 ? 'bt-profit' : 'bt-loss';
  return <td className={`bt-td bt-td-right ${cls}`}>{fmt$(value)}</td>;
}

// ── Single-stock summary card ──────────────────────────────────────────────────
function SummaryCard({ summary, ticker, strategy, start, end }) {
  const stratLabel = STRATEGIES.find((s) => s.value === strategy)?.label ?? strategy;
  const pnlCls = summary.total_pnl >= 0 ? 'bt-profit' : 'bt-loss';
  const bhCls = summary.buy_hold_pnl >= 0 ? 'bt-profit' : 'bt-loss';

  return (
    <div className="bt-summary">
      <div className="bt-summary-header">
        <div>
          <span className="bt-summary-ticker">{ticker}</span>
          <span className="bt-summary-meta">
            {stratLabel} · {start} → {end}
          </span>
        </div>
        <div className={`bt-summary-total ${pnlCls}`}>
          <span className="bt-summary-total-label">Total P&amp;L</span>
          <span className="bt-summary-total-value">{fmt$(summary.total_pnl)}</span>
          <span className="bt-summary-total-pct">{fmtPct(summary.total_return_pct)}</span>
        </div>
      </div>

      <div className="bt-summary-grid">
        <div className="bt-stat-group">
          <div className="bt-stat-label">Starting Capital</div>
          <div className="bt-stat-value">{fmt$(summary.starting_capital)}</div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Ending Capital</div>
          <div className={`bt-stat-value ${pnlCls}`}>{fmt$(summary.ending_capital)}</div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Position Size</div>
          <div className="bt-stat-value">
            {fmt$(summary.position_size)}
            <span className="bt-stat-sub">
              ({((summary.position_size / summary.starting_capital) * 100).toFixed(0)}% per trade)
            </span>
          </div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Realized P&amp;L</div>
          <div className={`bt-stat-value ${summary.realized_pnl >= 0 ? 'bt-profit' : 'bt-loss'}`}>
            {fmt$(summary.realized_pnl)}
          </div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Unrealized P&amp;L</div>
          <div className={`bt-stat-value ${summary.unrealized_pnl >= 0 ? 'bt-profit' : 'bt-loss'}`}>
            {summary.unrealized_pnl !== 0 ? fmt$(summary.unrealized_pnl) : '—'}
          </div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Completed Trades</div>
          <div className="bt-stat-value">{summary.num_completed_trades}</div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Win Rate</div>
          <div className="bt-stat-value">
            {summary.num_completed_trades > 0
              ? `${summary.win_rate}% (${summary.num_wins}W / ${summary.num_losses}L)`
              : '—'}
          </div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Avg P&amp;L / Trade</div>
          <div className={`bt-stat-value ${summary.avg_pnl >= 0 ? 'bt-profit' : 'bt-loss'}`}>
            {summary.num_completed_trades > 0 ? fmt$(summary.avg_pnl) : '—'}
          </div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Best Trade</div>
          <div className="bt-stat-value bt-profit">
            {summary.num_completed_trades > 0 ? fmt$(summary.best_trade) : '—'}
          </div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Worst Trade</div>
          <div className={`bt-stat-value ${summary.worst_trade < 0 ? 'bt-loss' : 'bt-profit'}`}>
            {summary.num_completed_trades > 0 ? fmt$(summary.worst_trade) : '—'}
          </div>
        </div>
        <div className="bt-stat-group bt-bh-group">
          <div className="bt-stat-label">Buy &amp; Hold P&amp;L</div>
          <div className={`bt-stat-value ${bhCls}`}>
            {fmt$(summary.buy_hold_pnl)}
            <span className="bt-stat-sub">{fmtPct(summary.buy_hold_return_pct)}</span>
          </div>
        </div>
      </div>

      {summary.open_position && (
        <div className={`bt-open-pos ${summary.open_position.unrealized_pnl >= 0 ? 'bt-open-profit' : 'bt-open-loss'}`}>
          <span className="bt-open-label">Open Position (Trade #{summary.open_position.trade_num})</span>
          <span>
            Entered {summary.open_position.entry_date} @ ${summary.open_position.entry_price.toFixed(4)} ·{' '}
            {fmtShares(summary.open_position.shares)} shares ·{' '}
            Current ${summary.open_position.current_price.toFixed(4)} ·{' '}
            Unrealized{' '}
            <strong>
              {fmt$(summary.open_position.unrealized_pnl)} ({fmtPct(summary.open_position.unrealized_return_pct)})
            </strong>{' '}
            · {summary.open_position.hold_days}d held
          </span>
        </div>
      )}
    </div>
  );
}

// ── Portfolio summary card ─────────────────────────────────────────────────────
function PortfolioSummaryCard({ summary, strategy, start, end }) {
  const stratLabel = STRATEGIES.find((s) => s.value === strategy)?.label ?? strategy;
  const pnlCls = summary.total_pnl >= 0 ? 'bt-profit' : 'bt-loss';
  const bhCls = summary.buy_hold_pnl >= 0 ? 'bt-profit' : 'bt-loss';
  const [showOpenPos, setShowOpenPos] = useState(false);

  return (
    <div className="bt-summary">
      <div className="bt-summary-header">
        <div>
          <span className="bt-summary-ticker">S&amp;P 500 Portfolio</span>
          <span className="bt-summary-meta">
            {stratLabel} · {start} → {end} · Mon &amp; Wed only
          </span>
        </div>
        <div className={`bt-summary-total ${pnlCls}`}>
          <span className="bt-summary-total-label">Total P&amp;L</span>
          <span className="bt-summary-total-value">{fmt$(summary.total_pnl)}</span>
          <span className="bt-summary-total-pct">{fmtPct(summary.total_return_pct)}</span>
        </div>
      </div>

      <div className="bt-summary-grid">
        <div className="bt-stat-group">
          <div className="bt-stat-label">Starting Capital</div>
          <div className="bt-stat-value">{fmt$(summary.starting_capital)}</div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Ending Portfolio Value</div>
          <div className={`bt-stat-value ${pnlCls}`}>{fmt$(summary.ending_portfolio_value)}</div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Ending Cash</div>
          <div className="bt-stat-value">{fmt$(summary.ending_cash)}</div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Open Positions Value</div>
          <div className="bt-stat-value">{fmt$(summary.open_positions_value)}</div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Position Size / Trade</div>
          <div className="bt-stat-value">
            {fmt$(summary.position_size)}
            <span className="bt-stat-sub">
              ({((summary.position_size / summary.starting_capital) * 100).toFixed(0)}% of capital)
            </span>
          </div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Realized P&amp;L</div>
          <div className={`bt-stat-value ${summary.realized_pnl >= 0 ? 'bt-profit' : 'bt-loss'}`}>
            {fmt$(summary.realized_pnl)}
          </div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Unrealized P&amp;L</div>
          <div className={`bt-stat-value ${summary.unrealized_pnl >= 0 ? 'bt-profit' : 'bt-loss'}`}>
            {summary.unrealized_pnl !== 0 ? fmt$(summary.unrealized_pnl) : '—'}
          </div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Completed Trades</div>
          <div className="bt-stat-value">{summary.num_completed_trades}</div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Win Rate</div>
          <div className="bt-stat-value">
            {summary.num_completed_trades > 0
              ? `${summary.win_rate}% (${summary.num_wins}W / ${summary.num_losses}L)`
              : '—'}
          </div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Avg P&amp;L / Trade</div>
          <div className={`bt-stat-value ${summary.avg_pnl >= 0 ? 'bt-profit' : 'bt-loss'}`}>
            {summary.num_completed_trades > 0 ? fmt$(summary.avg_pnl) : '—'}
          </div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Best Trade</div>
          <div className="bt-stat-value bt-profit">
            {summary.num_completed_trades > 0 ? fmt$(summary.best_trade) : '—'}
          </div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Worst Trade</div>
          <div className={`bt-stat-value ${summary.worst_trade < 0 ? 'bt-loss' : 'bt-profit'}`}>
            {summary.num_completed_trades > 0 ? fmt$(summary.worst_trade) : '—'}
          </div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Unique Tickers Traded</div>
          <div className="bt-stat-value">{summary.num_unique_tickers}</div>
        </div>
        <div className="bt-stat-group">
          <div className="bt-stat-label">Max Simultaneous Positions</div>
          <div className="bt-stat-value">{summary.max_simultaneous_positions}</div>
        </div>
        <div className="bt-stat-group bt-bh-group">
          <div className="bt-stat-label">Buy &amp; Hold SPY P&amp;L</div>
          <div className={`bt-stat-value ${bhCls}`}>
            {fmt$(summary.buy_hold_pnl)}
            <span className="bt-stat-sub">{fmtPct(summary.buy_hold_return_pct)}</span>
          </div>
        </div>
      </div>

      {summary.open_positions && summary.open_positions.length > 0 && (
        <div className="bt-port-open-wrap">
          <button
            className="bt-port-open-toggle"
            onClick={() => setShowOpenPos((v) => !v)}
          >
            {showOpenPos ? '▲' : '▼'} Open Positions ({summary.num_open_positions})
          </button>
          {showOpenPos && (
            <div className="bt-port-open-list">
              {summary.open_positions.map((pos) => (
                <div
                  key={pos.ticker}
                  className={`bt-open-pos ${pos.unrealized_pnl >= 0 ? 'bt-open-profit' : 'bt-open-loss'}`}
                >
                  <span className="bt-open-label">{pos.ticker} (#{pos.trade_num})</span>
                  <span>
                    Entered {pos.entry_date} @ ${pos.entry_price.toFixed(2)} ·{' '}
                    {fmtShares(pos.shares)} shares · Current ${pos.current_price.toFixed(2)} ·{' '}
                    <strong>
                      {fmt$(pos.unrealized_pnl)} ({fmtPct(pos.unrealized_return_pct)})
                    </strong>{' '}
                    · {pos.hold_days}d held
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function Backtest() {
  const { start: defaultStart, end: defaultEnd } = defaultDates();

  const [mode, setMode] = useState('single');
  const [ticker, setTicker] = useState('');
  const [inputTicker, setInputTicker] = useState('');
  const [strategy, setStrategy] = useState('bollinger-bands');
  const [startDate, setStartDate] = useState(defaultStart);
  const [endDate, setEndDate] = useState(defaultEnd);
  const [capital, setCapital] = useState(100000);
  const [positionPct, setPositionPct] = useState(5);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const dateRangeValid = startDate && endDate && startDate < endDate;
  const strategyLabel = STRATEGIES.find((s) => s.value === strategy)?.label ?? strategy;

  const runBacktest = async () => {
    const clean = inputTicker.trim().toUpperCase();
    if (mode === 'single' && !clean) return;

    setLoading(true);
    setError(null);
    setResult(null);
    if (mode === 'single') setTicker(clean);

    try {
      const body = {
        mode,
        strategy,
        start: startDate,
        end: endDate,
        capital: Number(capital),
        position_pct: positionPct / 100,
      };
      if (mode === 'single') body.ticker = clean;

      const res = await fetch(`${API_BASE}/api/backtest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.error) {
        setError(data.error);
      } else {
        setResult(data);
      }
    } catch {
      setError('Backtest request failed. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (dateRangeValid) runBacktest();
  };

  const isPortfolio = mode === 'portfolio';
  const canRun = dateRangeValid && (isPortfolio || inputTicker.trim());

  return (
    <div className="bt-container">
      {/* ── Mode toggle ── */}
      <div className="bt-mode-wrap">
        <span className="bt-mode-label">Mode</span>
        <div className="bt-mode-toggle">
          <button
            type="button"
            className={`toggle-btn ${mode === 'single' ? 'active' : ''}`}
            onClick={() => { setMode('single'); setResult(null); setError(null); }}
          >
            Single Stock
          </button>
          <button
            type="button"
            className={`toggle-btn ${mode === 'portfolio' ? 'active' : ''}`}
            onClick={() => { setMode('portfolio'); setResult(null); setError(null); }}
          >
            S&amp;P 500 Portfolio
          </button>
        </div>
        {isPortfolio && (
          <span className="bt-mode-hint">
            Buys strong-buy signals on Mon &amp; Wed across all S&amp;P 500 stocks
          </span>
        )}
      </div>

      {/* ── Controls ── */}
      <form className="bt-controls" onSubmit={handleSubmit}>
        <div className="bt-control-row">
          {/* Ticker (single mode only) */}
          {!isPortfolio && (
            <div className="bt-control-group">
              <label>Ticker</label>
              <input
                type="text"
                className="bt-input bt-ticker-input"
                placeholder="e.g. AAPL"
                value={inputTicker}
                onChange={(e) => setInputTicker(e.target.value.toUpperCase())}
                spellCheck={false}
                autoComplete="off"
              />
            </div>
          )}

          {/* Strategy */}
          <div className="bt-control-group bt-strategy-group">
            <label>Strategy</label>
            <select
              className="bt-select"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
            >
              {STRATEGIES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>

          {/* Capital */}
          <div className="bt-control-group">
            <label>Starting Capital ($)</label>
            <input
              type="number"
              className="bt-input"
              value={capital}
              min={1000}
              step={1000}
              onChange={(e) => setCapital(e.target.value)}
            />
          </div>

          {/* Position size */}
          <div className="bt-control-group">
            <label>Position Size (%)</label>
            <input
              type="number"
              className="bt-input bt-pct-input"
              value={positionPct}
              min={1}
              max={100}
              step={1}
              onChange={(e) => setPositionPct(e.target.value)}
            />
          </div>
        </div>

        <div className="bt-control-row">
          {/* Date range */}
          <div className="bt-control-group">
            <label>From</label>
            <input
              type="date"
              className="bt-input bt-date-input"
              value={startDate}
              max={endDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>
          <div className="bt-control-group">
            <label>To</label>
            <input
              type="date"
              className="bt-input bt-date-input"
              value={endDate}
              min={startDate}
              max={toISODate(new Date())}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>
          {!dateRangeValid && startDate && endDate && (
            <span className="bt-date-error">Start must be before end</span>
          )}

          <button
            type="submit"
            className="bt-run-btn"
            disabled={loading || !canRun}
          >
            {loading
              ? (isPortfolio ? 'Simulating…' : 'Running…')
              : (isPortfolio ? 'Run Portfolio Simulation' : 'Run Backtest')}
          </button>
        </div>
      </form>

      {/* ── Loading ── */}
      {loading && (
        <div className="bt-loading">
          <div className="bt-spinner" />
          {isPortfolio ? (
            <div>
              <p>Running S&amp;P 500 portfolio simulation using <strong>{strategyLabel}</strong>…</p>
              <p className="bt-loading-sub">Downloading market data for ~500 stocks. This may take 60–90 seconds.</p>
            </div>
          ) : (
            <p>Running backtest for <strong>{inputTicker.trim().toUpperCase()}</strong>…</p>
          )}
        </div>
      )}

      {/* ── Error ── */}
      {error && <div className="bt-error">{error}</div>}

      {/* ── Results ── */}
      {result && (
        <>
          {result.mode === 'portfolio' ? (
            <PortfolioSummaryCard
              summary={result.summary}
              strategy={result.strategy}
              start={result.start}
              end={result.end}
            />
          ) : (
            <SummaryCard
              summary={result.summary}
              ticker={result.ticker}
              strategy={result.strategy}
              start={result.start}
              end={result.end}
            />
          )}

          {result.actions.length === 0 ? (
            <div className="bt-no-trades">
              No signals were generated in this period for the selected strategy.
              Try a longer date range or a different strategy.
            </div>
          ) : (
            <div className="bt-table-wrap">
              <div className="bt-table-title">
                Trade Log
                <span className="bt-table-count">{result.actions.length} actions</span>
              </div>
              <div className="bt-table-scroll">
                <table className="bt-table">
                  <thead>
                    <tr>
                      <th className="bt-th">#</th>
                      <th className="bt-th">Signal</th>
                      {isPortfolio && <th className="bt-th">Ticker</th>}
                      <th className="bt-th">Date</th>
                      <th className="bt-th bt-th-right">Price</th>
                      <th className="bt-th bt-th-right">Shares</th>
                      <th className="bt-th bt-th-right">Value</th>
                      <th className="bt-th bt-th-right">P&amp;L</th>
                      <th className="bt-th bt-th-right">Return</th>
                      <th className="bt-th bt-th-right">Hold Days</th>
                      <th className="bt-th bt-th-right">Cum. P&amp;L</th>
                      {!isPortfolio && <th className="bt-th">Reason</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {result.actions.map((a, i) => {
                      const isBuy = a.action === 'BUY';
                      const rowCls = isBuy ? 'bt-row-buy' : (a.pnl >= 0 ? 'bt-row-win' : 'bt-row-loss');
                      const cumCls = a.cumulative_pnl >= 0 ? 'bt-profit' : 'bt-loss';
                      return (
                        <tr key={i} className={`bt-tr ${rowCls}`}>
                          <td className="bt-td bt-td-num">{a.trade_num}</td>
                          <td className="bt-td">
                            <span className={`bt-signal-badge ${isBuy ? 'bt-badge-buy' : 'bt-badge-sell'}`}>
                              {isBuy ? '▲ BUY' : '▼ SELL'}
                            </span>
                          </td>
                          {isPortfolio && (
                            <td className="bt-td bt-td-ticker">{a.ticker}</td>
                          )}
                          <td className="bt-td bt-td-date">{a.date}</td>
                          <td className="bt-td bt-td-right">${a.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</td>
                          <td className="bt-td bt-td-right">{fmtShares(a.shares)}</td>
                          <td className="bt-td bt-td-right">{fmt$(a.value)}</td>
                          <PnlCell value={a.pnl} />
                          <td className={`bt-td bt-td-right ${a.return_pct != null ? (a.return_pct >= 0 ? 'bt-profit' : 'bt-loss') : ''}`}>
                            {a.return_pct != null ? fmtPct(a.return_pct) : '—'}
                          </td>
                          <td className="bt-td bt-td-right">
                            {a.hold_days != null ? `${a.hold_days}d` : '—'}
                          </td>
                          <td className={`bt-td bt-td-right ${cumCls}`}>
                            {fmt$(a.cumulative_pnl)}
                          </td>
                          {!isPortfolio && (
                            <td className="bt-td bt-td-reason">{a.reason}</td>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Placeholder ── */}
      {!loading && !error && !result && (
        <div className="bt-placeholder">
          {isPortfolio ? (
            <>
              <p>Select a strategy and date range, then click <strong>Run Portfolio Simulation</strong>.</p>
              <p className="bt-placeholder-sub">
                Scans all S&amp;P 500 stocks on every Monday and Wednesday. Buys when a stock is a
                strong buy according to the strategy, sells when it becomes a strong sell.
                Each trade uses a fixed position size (default 5% of starting capital = $5,000).
                Requires 60–90 seconds to download and process market data.
              </p>
            </>
          ) : (
            <>
              <p>Enter a ticker, choose a strategy and date range, then click <strong>Run Backtest</strong>.</p>
              <p className="bt-placeholder-sub">
                The simulation buys when the strategy signals a buy and sells on the opposing signal.
                Each trade uses a fixed position size (default 5% of starting capital = $5,000).
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
