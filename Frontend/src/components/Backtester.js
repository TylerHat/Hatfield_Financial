import React, { useState } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import StatCard from './StatCard';
import DataTable from './DataTable';
import Badge from './Badge';
import './Backtester.css';
import { apiFetch } from '../api';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

const TRADE_COLUMNS = [
  { key: 'entryDate', label: 'Entry Date', sortable: true, width: '110px' },
  { key: 'date', label: 'Exit Date', sortable: true, width: '110px' },
  {
    key: 'type',
    label: 'Type',
    sortable: false,
    width: '70px',
    render: () => <Badge variant="sell" size="sm">SELL</Badge>,
  },
  {
    key: 'entryPrice',
    label: 'Entry $',
    numeric: true,
    sortable: true,
    width: '90px',
    render: (v) => (v != null ? `$${Number(v).toFixed(2)}` : 'N/A'),
  },
  {
    key: 'price',
    label: 'Exit $',
    numeric: true,
    sortable: true,
    width: '90px',
    render: (v) => (v != null ? `$${Number(v).toFixed(2)}` : 'N/A'),
  },
  { key: 'shares', label: 'Shares', numeric: true, sortable: true, width: '80px' },
  {
    key: 'pnl',
    label: 'P&L $',
    numeric: true,
    sortable: true,
    width: '100px',
    render: (v) => {
      if (v == null) return 'N/A';
      const color = v >= 0 ? '#3fb950' : '#f85149';
      return <span style={{ color }}>{v >= 0 ? '+' : ''}{Number(v).toFixed(2)}</span>;
    },
  },
  {
    key: 'pnlPct',
    label: 'P&L %',
    numeric: true,
    sortable: true,
    width: '90px',
    render: (v) => {
      if (v == null) return 'N/A';
      const color = v >= 0 ? '#3fb950' : '#f85149';
      return <span style={{ color }}>{v >= 0 ? '+' : ''}{Number(v).toFixed(2)}%</span>;
    },
  },
  {
    key: 'status',
    label: 'Status',
    sortable: true,
    width: '110px',
    render: (v) => {
      if (!v) return null;
      const variant = v === 'UNREALIZED' ? 'yellow' : 'gray';
      return <Badge variant={variant} size="sm">{v}</Badge>;
    },
  },
];

export default function Backtester({ ticker, strategy, startDate, endDate }) {
  const [capital, setCapital] = useState('10000');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  if (!ticker) {
    return (
      <div className="backtester__empty">
        Enter a ticker on the Stock Analysis tab first.
      </div>
    );
  }

  function handleRun() {
    const cap = parseFloat(capital);
    if (isNaN(cap) || cap <= 0) {
      setError('Please enter a valid starting capital amount.');
      return;
    }
    if (!strategy || strategy === 'none') {
      setError('Please select a strategy on the Stock Analysis tab first.');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    const params = new URLSearchParams();
    params.set('strategy', strategy);
    if (startDate) params.set('start', startDate);
    if (endDate) params.set('end', endDate);
    params.set('capital', cap);

    console.log('[Backtester] run:', { ticker, strategy, startDate, endDate, capital: cap });
    apiFetch(`/api/backtest/${ticker}?${params.toString()}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          console.warn('[Backtester] server error:', data.error);
          setError(data.error);
        } else {
          console.log('[Backtester] result:', {
            trades: data.trades?.length,
            equityPoints: data.equityCurve?.length,
            finalValue: data.summary?.finalValue,
          });
          setResult(data);
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error('[Backtester] network error:', err);
        setError('Could not connect to the backend. Make sure the server is running.');
        setLoading(false);
      });
  }

  const s = result?.summary;

  // Equity curve chart data
  const chartData = result
    ? {
        labels: result.equityCurve.map((p) => p.date),
        datasets: [
          {
            label: 'Portfolio Value',
            data: result.equityCurve.map((p) => p.value),
            borderColor: '#58a6ff',
            backgroundColor: 'rgba(88,166,255,0.08)',
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.2,
            fill: true,
          },
          {
            label: 'Starting Capital',
            data: result.equityCurve.map(() => s?.startingCapital),
            borderColor: '#30363d',
            borderWidth: 1,
            borderDash: [6, 4],
            pointRadius: 0,
            fill: false,
          },
        ],
      }
    : null;

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: { color: '#8b949e', boxWidth: 14, font: { size: 11 } },
      },
      tooltip: {
        backgroundColor: '#161b22',
        borderColor: '#30363d',
        borderWidth: 1,
        titleColor: '#e6edf3',
        bodyColor: '#8b949e',
        callbacks: {
          label: (ctx) => ` $${Number(ctx.parsed.y).toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
        },
      },
    },
    scales: {
      x: {
        ticks: {
          color: '#8b949e',
          font: { size: 10 },
          maxTicksLimit: 8,
          maxRotation: 0,
        },
        grid: { color: '#21262d' },
      },
      y: {
        ticks: {
          color: '#8b949e',
          font: { size: 10 },
          callback: (v) => `$${Number(v).toLocaleString()}`,
        },
        grid: { color: '#21262d' },
      },
    },
  };

  const returnAccent = s
    ? s.totalReturn >= 0 ? 'green' : 'red'
    : 'default';

  const tradeRows = result?.trades?.map((t) => ({
    ...t,
    _rowClass: t.pnl > 0 ? 'buy-row' : t.pnl < 0 ? 'sell-row' : '',
  })) || [];

  return (
    <div className="backtester">
      {/* Controls */}
      <div className="backtester__controls">
        <span className="backtester__controls-label">Starting Capital ($):</span>
        <input
          type="number"
          className="backtester__capital-input"
          value={capital}
          onChange={(e) => setCapital(e.target.value)}
          min="100"
          step="100"
        />
        <button
          className="backtester__run-btn"
          onClick={handleRun}
          disabled={loading}
        >
          {loading ? 'Running…' : 'Run Backtest'}
        </button>
        {loading && <span className="backtester__loading">Fetching data and simulating trades…</span>}
      </div>

      {error && <div className="backtester__error">{error}</div>}

      {result && s && (
        <>
          {/* Summary stat cards */}
          <div>
            <div className="backtester__section-title">Performance Summary</div>
            <div className="backtester__summary-grid">
              <StatCard
                label="Total Return"
                value={`${s.totalReturn >= 0 ? '+' : ''}${s.totalReturn}%`}
                subtext={`${s.totalReturnDollar >= 0 ? '+' : ''}$${Math.abs(s.totalReturnDollar).toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
                accent={returnAccent}
              />
              <StatCard
                label="Final Value"
                value={`$${s.finalValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
                subtext={`Started with $${s.startingCapital.toLocaleString()}`}
              />
              <StatCard
                label="Win Rate"
                value={`${s.winRate}%`}
                subtext={`${s.numWins}W / ${s.numLosses}L of ${s.numTrades} trades`}
                accent={s.winRate >= 50 ? 'green' : 'red'}
              />
              <StatCard
                label="Max Drawdown"
                value={`${s.maxDrawdown}%`}
                accent={s.maxDrawdown < -20 ? 'red' : s.maxDrawdown < -10 ? 'yellow' : 'default'}
              />
            </div>
          </div>

          {/* Equity curve chart */}
          <div className="backtester__chart-wrap">
            <div className="backtester__section-title">Equity Curve</div>
            <div className="backtester__chart">
              <Line data={chartData} options={chartOptions} />
            </div>
          </div>

          {/* Trades table */}
          <div>
            <div className="backtester__section-title">Trade History</div>
            <DataTable
              columns={TRADE_COLUMNS}
              rows={tradeRows}
              defaultSortKey="entryDate"
              defaultSortDir="desc"
              rowKey="entryDate"
              emptyMessage="No trades were executed in this date range."
              caption={`Backtest trades for ${ticker} using ${strategy}`}
            />
          </div>

          {s.hasUnrealized && (
            <div style={{
              background: 'rgba(240,136,62,0.1)',
              border: '1px solid #f0883e',
              borderRadius: '6px',
              padding: '10px 14px',
              fontSize: '0.85rem',
              color: '#f0883e',
            }}>
              Note: The last trade is marked UNREALIZED — an open position at the end of the date range.
              Unrealized P&L: {s.unrealizedPnlPct >= 0 ? '+' : ''}{s.unrealizedPnlPct}%
              (${s.unrealizedPnl >= 0 ? '+' : ''}{s.unrealizedPnl.toFixed(2)}).
            </div>
          )}
        </>
      )}
    </div>
  );
}
