import React, { useState, useEffect, useMemo } from 'react';
import { apiFetch } from '../api';
import DataTable from './DataTable';
import Badge from './Badge';
import './Recommendations.css';

const STRATEGIES = [
  { value: 'none', label: 'None' },
  { value: 'post-earnings-drift', label: 'Post-Earnings Drift' },
  { value: 'relative-strength', label: 'Relative Strength vs Market' },
  { value: 'bollinger-bands', label: 'Bollinger Bands' },
  { value: 'mean-reversion', label: 'Mean Reversion' },
  { value: 'macd-crossover', label: 'MACD Crossover' },
  { value: 'rsi', label: 'RSI Overbought / Oversold' },
  { value: 'volatility-squeeze', label: 'Volatility Squeeze' },
  { value: '52-week-breakout', label: '52-Week Breakout' },
  { value: 'ma-confluence', label: 'MA Confluence' },
];

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'strong_buy', label: 'Strong Buy' },
  { key: 'buy', label: 'Buy' },
  { key: 'hold', label: 'Hold' },
  { key: 'sell', label: 'Sell' },
  { key: 'strong_sell', label: 'Strong Sell' },
];

function recVariant(recKey) {
  if (!recKey) return 'gray';
  if (recKey === 'strong_buy') return 'green';
  if (recKey === 'buy') return 'green';
  if (recKey === 'hold') return 'blue';
  if (recKey === 'sell') return 'red';
  if (recKey === 'strong_sell') return 'red';
  return 'gray';
}

function macdVariant(status) {
  if (!status) return 'gray';
  if (status.includes('BULLISH')) return 'green';
  if (status.includes('BEARISH')) return 'red';
  return 'gray';
}

function trendVariant(trend) {
  if (!trend) return 'gray';
  if (trend.includes('Uptrend') || trend.includes('Bullish')) return 'green';
  if (trend.includes('Downtrend') || trend.includes('Bearish')) return 'red';
  return 'yellow';
}

function volVariant(vol) {
  if (!vol) return 'gray';
  if (vol.includes('HIGH')) return 'red';
  if (vol.includes('LOW')) return 'green';
  return 'yellow';
}

function priceActionVariant(pa) {
  if (!pa) return 'gray';
  if (pa === 'Overbought') return 'red';
  if (pa === 'Oversold') return 'green';
  if (pa === 'Trending') return 'blue';
  if (pa === 'Consolidating') return 'yellow';
  return 'gray';
}

const REC_COLUMNS = [
  {
    key: 'ticker',
    label: 'Stock',
    sortable: true,
    width: '180px',
    render: (val, row) => (
      <span>
        <strong style={{ color: '#e6edf3' }}>{val}</strong>
        <span style={{ color: '#8b949e', marginLeft: 6, fontSize: '0.8rem' }}>
          {row.name && row.name.length > 25 ? row.name.slice(0, 25) + '\u2026' : row.name}
        </span>
      </span>
    ),
  },
  {
    key: 'currentPrice',
    label: 'Price',
    numeric: true,
    sortable: true,
    width: '100px',
    render: (val) => val != null ? `$${val.toFixed(2)}` : '\u2014',
  },
  {
    key: 'dayChangePct',
    label: 'Day Change',
    numeric: true,
    sortable: true,
    width: '110px',
    render: (val) => {
      if (val == null) return '\u2014';
      const cls = val > 0 ? 'rec-positive' : val < 0 ? 'rec-negative' : 'rec-neutral';
      return <span className={cls}>{val > 0 ? '+' : ''}{val.toFixed(2)}%</span>;
    },
  },
  {
    key: 'analystRecommendation',
    label: 'Analyst Rec',
    sortable: true,
    width: '130px',
    render: (val, row) => (
      <Badge variant={recVariant(row.recommendationKey)} size="sm">{val || 'N/A'}</Badge>
    ),
  },
  {
    key: 'priceAction',
    label: 'Price Action',
    sortable: true,
    width: '120px',
    render: (val) => <Badge variant={priceActionVariant(val)} size="sm">{val || 'N/A'}</Badge>,
  },
  {
    key: 'macdStatus',
    label: 'MACD',
    sortable: true,
    width: '150px',
    render: (val) => <Badge variant={macdVariant(val)} size="sm">{val || 'N/A'}</Badge>,
  },
  {
    key: 'volatilityStatus',
    label: 'Volatility',
    sortable: true,
    width: '130px',
    render: (val) => <Badge variant={volVariant(val)} size="sm">{val || 'N/A'}</Badge>,
  },
  {
    key: 'trendAlignment',
    label: 'Trend',
    sortable: true,
    width: '150px',
    render: (val) => <Badge variant={trendVariant(val)} size="sm">{val || 'N/A'}</Badge>,
  },
  {
    key: 'momentum',
    label: 'Momentum',
    numeric: true,
    sortable: true,
    width: '110px',
    render: (val) => {
      if (val == null) return '\u2014';
      const cls = val > 0 ? 'rec-positive' : val < 0 ? 'rec-negative' : 'rec-neutral';
      return <span className={cls}>{val > 0 ? '+' : ''}{val.toFixed(2)}%</span>;
    },
  },
];

const SIGNAL_COLUMNS = [
  {
    key: 'signalType',
    label: 'Signal',
    sortable: true,
    width: '90px',
    render: (val) => {
      if (!val) return <span className="rec-neutral">None</span>;
      return <Badge variant={val === 'BUY' ? 'buy' : 'sell'} size="sm">{val}</Badge>;
    },
  },
  {
    key: 'signalDate',
    label: 'Signal Date',
    sortable: true,
    width: '110px',
    render: (val) => val || '',
  },
  {
    key: 'signalConviction',
    label: 'Conviction',
    sortable: true,
    width: '100px',
    render: (val) => {
      if (!val) return '';
      return <Badge variant={val.toLowerCase()} size="sm">{val}</Badge>;
    },
  },
  {
    key: 'signalScore',
    label: 'Score',
    numeric: true,
    sortable: true,
    width: '80px',
    render: (val) => val != null ? val : '',
  },
];

export default function Recommendations({ onNavigateToStock }) {
  const [stocks, setStocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all');
  const [selectedStrategy, setSelectedStrategy] = useState('none');
  const [batchSignals, setBatchSignals] = useState({ loading: false, error: null, data: {} });

  // Fetch recommendations on mount
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    apiFetch('/api/recommendations')
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        if (data.error) {
          setError(data.error);
        } else if (data.status === 'loading') {
          setTimeout(() => {
            if (!cancelled) {
              setLoading(true);
              apiFetch('/api/recommendations')
                .then((r2) => r2.json())
                .then((data2) => {
                  if (cancelled) return;
                  if (data2.error) setError(data2.error);
                  else setStocks(data2.stocks || []);
                  setLoading(false);
                })
                .catch(() => { if (!cancelled) { setError('Failed to load data.'); setLoading(false); } });
            }
          }, 10000);
          return;
        } else {
          setStocks(data.stocks || []);
        }
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) { setError('Failed to connect to server.'); setLoading(false); }
      });

    return () => { cancelled = true; };
  }, []);

  // Fetch batch signals when strategy changes
  useEffect(() => {
    if (selectedStrategy === 'none') {
      setBatchSignals({ loading: false, error: null, data: {} });
      return;
    }

    let cancelled = false;
    setBatchSignals({ loading: true, error: null, data: {} });

    apiFetch(`/api/strategy/${selectedStrategy}/batch`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        if (data.error) {
          setBatchSignals({ loading: false, error: data.error, data: {} });
        } else if (data.status === 'loading') {
          setBatchSignals({ loading: false, error: 'S&P 500 data not yet loaded. Please wait for the table to load first.', data: {} });
        } else {
          setBatchSignals({ loading: false, error: null, data: data.signals || {} });
        }
      })
      .catch(() => {
        if (!cancelled) setBatchSignals({ loading: false, error: 'Failed to fetch signals.', data: {} });
      });

    return () => { cancelled = true; };
  }, [selectedStrategy]);

  // Dynamic columns: add signal columns when a strategy is selected
  const activeColumns = useMemo(() => {
    if (selectedStrategy === 'none') return REC_COLUMNS;
    return [...REC_COLUMNS, ...SIGNAL_COLUMNS];
  }, [selectedStrategy]);

  // Compute filter counts
  const counts = {};
  counts.all = stocks.length;
  FILTERS.slice(1).forEach((f) => {
    counts[f.key] = stocks.filter((s) => s.recommendationKey === f.key).length;
  });

  // Apply filter
  const filteredStocks = filter === 'all'
    ? stocks
    : stocks.filter((s) => s.recommendationKey === filter);

  // Merge signal data into rows
  const rows = useMemo(() => {
    return filteredStocks.map((s) => {
      const sig = batchSignals.data[s.ticker] || null;
      return {
        ...s,
        signalType: sig?.type || null,
        signalDate: sig?.date || null,
        signalConviction: sig?.conviction || null,
        signalScore: sig?.score ?? null,
      };
    });
  }, [filteredStocks, batchSignals.data]);

  return (
    <div className="rec-tab">
      {/* Header */}
      <div className="rec-header">
        <h2 className="rec-header__title">S&P 500 Recommendations</h2>
        {!loading && !error && (
          <span className="rec-header__meta">
            {stocks.length} stocks loaded
          </span>
        )}
      </div>

      {/* Loading banner */}
      {loading && (
        <div className="rec-loading-banner">
          <div className="rec-loading-banner__title">
            <span className="rec-loading-spinner" />
            Loading S&P 500 data…
          </div>
          <div className="rec-loading-banner__subtitle">
            This may take up to a minute on first load. Data is cached for 30 minutes.
          </div>
        </div>
      )}

      {/* Filter bar */}
      {!loading && !error && (
        <div className="rec-filter-bar">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              className={`rec-filter-btn ${filter === f.key ? 'rec-filter-btn--active' : ''}`}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
              <span className="rec-filter-btn__count">{counts[f.key] || 0}</span>
            </button>
          ))}
        </div>
      )}

      {/* Strategy selector */}
      {!loading && !error && (
        <div className="rec-strategy-bar">
          <span className="rec-strategy-bar__label">Strategy signal:</span>
          <select
            value={selectedStrategy}
            onChange={(e) => setSelectedStrategy(e.target.value)}
          >
            {STRATEGIES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
          {batchSignals.loading && (
            <span className="rec-strategy-bar__loading">
              <span className="rec-loading-spinner" />
              Computing signals for all stocks…
            </span>
          )}
          {batchSignals.error && (
            <span className="rec-strategy-bar__error">{batchSignals.error}</span>
          )}
        </div>
      )}

      {/* Data table */}
      <DataTable
        columns={activeColumns}
        rows={rows}
        defaultSortKey="ticker"
        defaultSortDir="asc"
        stickyHeader
        loading={loading}
        error={error}
        emptyMessage="No stocks match the selected filter."
        rowKey="ticker"
        onRowClick={onNavigateToStock ? (row) => onNavigateToStock(row.ticker) : undefined}
      />
    </div>
  );
}
