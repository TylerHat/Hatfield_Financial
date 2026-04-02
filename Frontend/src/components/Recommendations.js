import React, { useState, useEffect, useCallback } from 'react';
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
          {row.name && row.name.length > 25 ? row.name.slice(0, 25) + '…' : row.name}
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
    render: (val) => val != null ? `$${val.toFixed(2)}` : '—',
  },
  {
    key: 'dayChangePct',
    label: 'Day Change',
    numeric: true,
    sortable: true,
    width: '110px',
    render: (val) => {
      if (val == null) return '—';
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
      if (val == null) return '—';
      const cls = val > 0 ? 'rec-positive' : val < 0 ? 'rec-negative' : 'rec-neutral';
      return <span className={cls}>{val > 0 ? '+' : ''}{val.toFixed(2)}%</span>;
    },
  },
];

export default function Recommendations({ onNavigateToStock }) {
  const [stocks, setStocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all');
  const [selectedStrategy, setSelectedStrategy] = useState('none');
  const [expandedTicker, setExpandedTicker] = useState(null);
  const [strategySignals, setStrategySignals] = useState({});

  // Fetch recommendations on mount with polling until data is ready
  useEffect(() => {
    let cancelled = false;
    let retryCount = 0;
    const MAX_RETRIES = 18; // up to ~3 minutes at 10s intervals

    setLoading(true);
    setError(null);

    function doFetch() {
      console.log('[Recommendations] fetching (attempt', retryCount + 1, '/', MAX_RETRIES + 1, ')');
      apiFetch('/api/recommendations')
        .then((r) => r.json())
        .then((data) => {
          if (cancelled) return;
          if (data.error) {
            console.error('[Recommendations] server error:', data.error);
            setError(data.error);
            setLoading(false);
          } else if (data.status === 'loading') {
            // Backend is still prewarming — keep polling
            retryCount++;
            console.warn('[Recommendations] backend still prewarming — retry', retryCount, '/', MAX_RETRIES);
            if (retryCount >= MAX_RETRIES) {
              console.error('[Recommendations] max retries reached — giving up');
              setError('Data is taking too long to load. Please refresh and try again.');
              setLoading(false);
            } else {
              setTimeout(() => { if (!cancelled) doFetch(); }, 10000);
            }
          } else {
            console.log('[Recommendations] loaded', (data.stocks || []).length, 'stocks', `(${data.failedCount} failed, updated ${data.lastUpdated})`);
            setStocks(data.stocks || []);
            setLoading(false);
          }
        })
        .catch((err) => {
          if (!cancelled) {
            console.error('[Recommendations] fetch error:', err);
            setError('Failed to connect to server.');
            setLoading(false);
          }
        });
    }

    doFetch();
    return () => { cancelled = true; };
  }, []);

  // Fetch strategy signals when expanded ticker or strategy changes
  const fetchSignals = useCallback((ticker) => {
    if (selectedStrategy === 'none' || !ticker) return;

    console.log('[Recommendations] fetching signals for', ticker, 'strategy:', selectedStrategy);
    setStrategySignals((prev) => ({
      ...prev,
      [ticker]: { loading: true, error: null, signals: [] },
    }));

    apiFetch(`/api/strategy/${selectedStrategy}/${ticker}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          console.error('[Recommendations] signal error for', ticker, ':', data.error);
        } else {
          console.log('[Recommendations] signals for', ticker, ':', (data.signals || []).length, 'signals');
        }
        setStrategySignals((prev) => ({
          ...prev,
          [ticker]: { loading: false, error: data.error || null, signals: data.signals || [] },
        }));
      })
      .catch((err) => {
        console.error('[Recommendations] signal fetch failed for', ticker, ':', err);
        setStrategySignals((prev) => ({
          ...prev,
          [ticker]: { loading: false, error: 'Failed to fetch signals.', signals: [] },
        }));
      });
  }, [selectedStrategy]);

  // Handle row click
  const handleRowClick = useCallback((row) => {
    const ticker = row.ticker;
    if (expandedTicker === ticker) {
      setExpandedTicker(null);
      return;
    }
    setExpandedTicker(ticker);
    if (selectedStrategy !== 'none') {
      fetchSignals(ticker);
    }
  }, [expandedTicker, selectedStrategy, fetchSignals]);

  // Re-fetch signals when strategy changes and a ticker is expanded
  useEffect(() => {
    if (expandedTicker && selectedStrategy !== 'none') {
      fetchSignals(expandedTicker);
    }
  }, [selectedStrategy, expandedTicker, fetchSignals]);

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

  // Add _rowClass for selected row
  const rows = filteredStocks.map((s) => ({
    ...s,
    _rowClass: s.ticker === expandedTicker ? 'rec-row--selected' : '',
  }));

  // Get expanded stock's signal data
  const expandedData = expandedTicker ? strategySignals[expandedTicker] : null;
  const expandedStock = expandedTicker ? stocks.find((s) => s.ticker === expandedTicker) : null;

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
        </div>
      )}

      {/* Data table */}
      <DataTable
        columns={REC_COLUMNS}
        rows={rows}
        defaultSortKey="ticker"
        defaultSortDir="asc"
        stickyHeader
        loading={loading}
        error={error}
        emptyMessage="No stocks match the selected filter."
        rowKey="ticker"
        onRowClick={handleRowClick}
      />

      {/* Detail panel */}
      {expandedTicker && expandedStock && (
        <div className="rec-detail">
          <div className="rec-detail__header">
            <span className="rec-detail__ticker">
              {expandedTicker} — {expandedStock.name}
            </span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {onNavigateToStock && (
                <button
                  className="rec-detail__nav-link"
                  onClick={() => onNavigateToStock(expandedTicker)}
                >
                  Open in Stock Analysis →
                </button>
              )}
              <button
                className="rec-detail__close"
                onClick={() => setExpandedTicker(null)}
              >
                ✕
              </button>
            </div>
          </div>

          {selectedStrategy === 'none' && (
            <p className="rec-detail__prompt">
              Select a strategy above to view signals for {expandedTicker}.
            </p>
          )}

          {selectedStrategy !== 'none' && expandedData?.loading && (
            <p className="rec-detail__loading">
              <span className="rec-loading-spinner" />
              Loading {STRATEGIES.find((s) => s.value === selectedStrategy)?.label} signals…
            </p>
          )}

          {selectedStrategy !== 'none' && expandedData?.error && (
            <p className="rec-detail__error">{expandedData.error}</p>
          )}

          {selectedStrategy !== 'none' && expandedData && !expandedData.loading && !expandedData.error && (
            <div className="rec-detail__signals">
              {expandedData.signals.length === 0 && (
                <p className="rec-detail__no-signals">
                  No signals generated for {expandedTicker} with this strategy.
                </p>
              )}
              {expandedData.signals.slice(-5).reverse().map((sig, i) => (
                <div key={i} className="rec-signal-card">
                  <div className="rec-signal-card__field">
                    <span className="rec-signal-card__label">Date</span>
                    <span className="rec-signal-card__value">{sig.date}</span>
                  </div>
                  <div className="rec-signal-card__field">
                    <span className="rec-signal-card__label">Price</span>
                    <span className="rec-signal-card__value">${sig.price?.toFixed(2)}</span>
                  </div>
                  <div className="rec-signal-card__field">
                    <span className="rec-signal-card__label">Signal</span>
                    <span className="rec-signal-card__value">
                      <Badge variant={sig.type === 'BUY' ? 'buy' : 'sell'} size="sm">
                        {sig.type}
                      </Badge>
                    </span>
                  </div>
                  <div className="rec-signal-card__field">
                    <span className="rec-signal-card__label">Conviction</span>
                    <span className="rec-signal-card__value">
                      <Badge variant={sig.conviction?.toLowerCase()} size="sm">
                        {sig.conviction} ({sig.score})
                      </Badge>
                    </span>
                  </div>
                  <div className="rec-signal-card__field rec-signal-card__reason">
                    <span className="rec-signal-card__label">Reason</span>
                    <span className="rec-signal-card__value">{sig.reason}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
