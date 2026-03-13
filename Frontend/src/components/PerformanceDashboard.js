import React, { useEffect, useState } from 'react';
import StatCard from './StatCard';
import './PerformanceDashboard.css';

const API_BASE = 'http://localhost:5000';

export default function PerformanceDashboard({ ticker, strategy, startDate, endDate }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (!ticker || !strategy || strategy === 'none') {
      setResult(null);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    const params = new URLSearchParams();
    params.set('strategy', strategy);
    if (startDate) params.set('start', startDate);
    if (endDate) params.set('end', endDate);
    params.set('capital', '10000');

    fetch(`${API_BASE}/api/backtest/${ticker}?${params.toString()}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          setError(data.error);
        } else {
          setResult(data);
        }
        setLoading(false);
      })
      .catch(() => {
        setError('Could not connect to the backend. Make sure the server is running.');
        setLoading(false);
      });
  }, [ticker, strategy, startDate, endDate]);

  if (!ticker || !strategy || strategy === 'none') {
    return (
      <div className="perf-dashboard__empty">
        {!ticker
          ? 'Enter a ticker on the Stock Analysis tab first.'
          : 'Select a strategy on the Stock Analysis tab to view performance metrics.'}
      </div>
    );
  }

  if (loading) {
    return <div className="perf-dashboard__loading">Loading performance data for {ticker}…</div>;
  }

  if (error) {
    return <div className="perf-dashboard__error">{error}</div>;
  }

  if (!result) return null;

  const s = result.summary;
  const closed = result.trades.filter((t) => t.status === 'CLOSED');
  const totalClosed = closed.length;
  const winPct = s.numTrades > 0 ? (s.numWins / s.numTrades) * 100 : 0;

  const returnAccent = s.totalReturn >= 0 ? 'green' : 'red';
  const winRateAccent = s.winRate >= 50 ? 'green' : 'red';
  const pfAccent = s.profitFactor != null
    ? (s.profitFactor >= 1.5 ? 'green' : s.profitFactor >= 1 ? 'yellow' : 'red')
    : 'default';
  const ddAccent = s.maxDrawdown < -20 ? 'red' : s.maxDrawdown < -10 ? 'yellow' : 'default';

  return (
    <div className="perf-dashboard">
      {/* Row 1: Core performance */}
      <div>
        <div className="perf-dashboard__section-title">Returns & Risk</div>
        <div className="perf-dashboard__cards-grid">
          <StatCard
            label="Total Return"
            value={`${s.totalReturn >= 0 ? '+' : ''}${s.totalReturn}%`}
            subtext={`$${s.startingCapital.toLocaleString()} → $${s.finalValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
            accent={returnAccent}
          />
          <StatCard
            label="Win Rate"
            value={`${s.winRate}%`}
            subtext={`${s.numWins} wins, ${s.numLosses} losses`}
            accent={winRateAccent}
          />
          <StatCard
            label="Profit Factor"
            value={s.profitFactor != null ? s.profitFactor : '∞'}
            subtext="Gross profit ÷ gross loss"
            accent={pfAccent}
          />
          <StatCard
            label="Max Drawdown"
            value={`${s.maxDrawdown}%`}
            subtext="Peak-to-trough portfolio decline"
            accent={ddAccent}
          />
        </div>
      </div>

      {/* Row 2: Trade metrics */}
      <div>
        <div className="perf-dashboard__section-title">Trade Metrics</div>
        <div className="perf-dashboard__cards-grid">
          <StatCard
            label="Avg Win"
            value={`+${s.avgWinPct}%`}
            accent="green"
          />
          <StatCard
            label="Avg Loss"
            value={`${s.avgLossPct}%`}
            accent="red"
          />
          <StatCard
            label="Best Trade"
            value={`+${s.bestTrade}%`}
            accent="green"
          />
          <StatCard
            label="Worst Trade"
            value={`${s.worstTrade}%`}
            accent="red"
          />
        </div>
      </div>

      {/* Win/Loss bar */}
      <div className="perf-dashboard__winloss-wrap">
        <div className="perf-dashboard__winloss-header">
          <span className="perf-dashboard__winloss-label">Win vs Loss Distribution</span>
          <span className="perf-dashboard__winloss-counts">
            <span style={{ color: '#3fb950' }}>{s.numWins} wins</span>
            {' · '}
            <span style={{ color: '#f85149' }}>{s.numLosses} losses</span>
          </span>
        </div>
        <div className="perf-dashboard__winloss-track">
          <div
            className="perf-dashboard__winloss-fill"
            style={{ width: s.numTrades > 0 ? `${winPct}%` : '0%' }}
          />
        </div>
        <div className="perf-dashboard__accuracy-note">
          {totalClosed > 0
            ? `${s.numWins} of ${totalClosed} closed trade${totalClosed !== 1 ? 's' : ''} were profitable`
            : 'No closed trades in this date range.'}
        </div>
      </div>

      {/* Unrealized notice */}
      {s.hasUnrealized && (
        <div className="perf-dashboard__unrealized-notice">
          Open position at end of period — unrealized P&L:{' '}
          {s.unrealizedPnlPct >= 0 ? '+' : ''}{s.unrealizedPnlPct}%
          (${s.unrealizedPnl >= 0 ? '+' : ''}{Number(s.unrealizedPnl).toFixed(2)}).
          Final value includes this unrealized gain/loss.
        </div>
      )}
    </div>
  );
}
