import React, { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../api';
import DataTable from './DataTable';
import Badge from './Badge';
import './Watchlist.css';

/* ── Variant helpers (same logic as Recommendations) ──────────────────────── */

function recVariant(recKey) {
  if (!recKey) return 'gray';
  if (recKey === 'strong_buy' || recKey === 'buy') return 'green';
  if (recKey === 'hold') return 'blue';
  if (recKey === 'sell' || recKey === 'strong_sell') return 'red';
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

/* ── Column definitions ───────────────────────────────────────────────────── */

function buildColumns(onRemove) {
  return [
    {
      key: '_remove',
      label: '',
      sortable: false,
      width: '44px',
      render: (_val, row) => (
        <button
          className="wl-remove-btn"
          title={`Remove ${row.ticker}`}
          onClick={(e) => { e.stopPropagation(); onRemove(row.ticker); }}
        >
          ✕
        </button>
      ),
    },
    {
      key: 'ticker',
      label: 'Stock',
      sortable: true,
      width: '180px',
      render: (val, row) => {
        if (row.__skeleton) {
          return (
            <span>
              <strong style={{ color: '#e6edf3' }}>{val}</strong>
              <span style={{ display: 'block', marginTop: 4 }}>
                <span className="wl-skeleton-cell wl-skeleton-cell--sm" />
              </span>
            </span>
          );
        }
        return (
          <span>
            <strong style={{ color: '#e6edf3' }}>{val}</strong>
            <span style={{ color: '#8b949e', marginLeft: 6, fontSize: '0.8rem' }}>
              {row.name && row.name.length > 25 ? row.name.slice(0, 25) + '…' : row.name}
            </span>
          </span>
        );
      },
    },
    {
      key: 'currentPrice',
      label: 'Price',
      numeric: true,
      sortable: true,
      width: '100px',
      render: (val, row) => {
        if (row.__skeleton) return <span className="wl-skeleton-cell wl-skeleton-cell--narrow" />;
        return val != null ? `$${val.toFixed(2)}` : '—';
      },
    },
    {
      key: 'dayChangePct',
      label: 'Day Change',
      numeric: true,
      sortable: true,
      width: '110px',
      render: (val, row) => {
        if (row.__skeleton) return <span className="wl-skeleton-cell wl-skeleton-cell--narrow" />;
        if (val == null) return '—';
        const cls = val > 0 ? 'wl-positive' : val < 0 ? 'wl-negative' : 'wl-neutral';
        return <span className={cls}>{val > 0 ? '+' : ''}{val.toFixed(2)}%</span>;
      },
    },
    {
      key: 'sinceAddedPct',
      label: 'Since Added',
      numeric: true,
      sortable: true,
      width: '115px',
      render: (val, row) => {
        if (row.__skeleton) return <span className="wl-skeleton-cell wl-skeleton-cell--narrow" />;
        if (val == null) return '—';
        const cls = val > 0 ? 'wl-positive' : val < 0 ? 'wl-negative' : 'wl-neutral';
        return <span className={cls}>{val > 0 ? '+' : ''}{val.toFixed(2)}%</span>;
      },
    },
    {
      key: 'analystRecommendation',
      label: 'Analyst Rec',
      sortable: true,
      width: '130px',
      render: (val, row) => {
        if (row.__skeleton) return <span className="wl-skeleton-cell wl-skeleton-cell--sm" />;
        return <Badge variant={recVariant(row.recommendationKey)} size="sm">{val || 'N/A'}</Badge>;
      },
    },
    {
      key: 'priceAction',
      label: 'Price Action',
      sortable: true,
      width: '120px',
      render: (val, row) => {
        if (row.__skeleton) return <span className="wl-skeleton-cell wl-skeleton-cell--sm" />;
        return <Badge variant={priceActionVariant(val)} size="sm">{val || 'N/A'}</Badge>;
      },
    },
    {
      key: 'macdStatus',
      label: 'MACD',
      sortable: true,
      width: '150px',
      render: (val, row) => {
        if (row.__skeleton) return <span className="wl-skeleton-cell wl-skeleton-cell--sm" />;
        return <Badge variant={macdVariant(val)} size="sm">{val || 'N/A'}</Badge>;
      },
    },
    {
      key: 'volatilityStatus',
      label: 'Volatility',
      sortable: true,
      width: '130px',
      render: (val, row) => {
        if (row.__skeleton) return <span className="wl-skeleton-cell wl-skeleton-cell--sm" />;
        return <Badge variant={volVariant(val)} size="sm">{val || 'N/A'}</Badge>;
      },
    },
    {
      key: 'trendAlignment',
      label: 'Trend',
      sortable: true,
      width: '150px',
      render: (val, row) => {
        if (row.__skeleton) return <span className="wl-skeleton-cell wl-skeleton-cell--sm" />;
        return <Badge variant={trendVariant(val)} size="sm">{val || 'N/A'}</Badge>;
      },
    },
    {
      key: 'momentum',
      label: 'Momentum',
      numeric: true,
      sortable: true,
      width: '110px',
      render: (val, row) => {
        if (row.__skeleton) return <span className="wl-skeleton-cell wl-skeleton-cell--narrow" />;
        if (val == null) return '—';
        const cls = val > 0 ? 'wl-positive' : val < 0 ? 'wl-negative' : 'wl-neutral';
        return <span className={cls}>{val > 0 ? '+' : ''}{val.toFixed(2)}%</span>;
      },
    },
  ];
}

/* ── Component ────────────────────────────────────────────────────────────── */

export default function Watchlist({ onNavigateToStock, onWatchlistChange }) {
  const [watchlist, setWatchlist] = useState(null);
  const [stocks, setStocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dataLoading, setDataLoading] = useState(false);
  const [error, setError] = useState(null);
  const [addInput, setAddInput] = useState('');
  const [addMsg, setAddMsg] = useState(null);
  const [adding, setAdding] = useState(false);

  // Fetch enriched stock data for the watchlist
  const fetchData = useCallback((wl) => {
    if (!wl || !wl.items || wl.items.length === 0) {
      setStocks([]);
      setDataLoading(false);
      return;
    }
    setDataLoading(true);
    apiFetch(`/api/user/watchlists/${wl.id}/data`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          setError(data.error);
        } else {
          setStocks(data.stocks || []);
        }
        setDataLoading(false);
      })
      .catch(() => {
        setError('Failed to fetch watchlist data.');
        setDataLoading(false);
      });
  }, []);

  // On mount: load or create the default watchlist
  useEffect(() => {
    let cancelled = false;

    apiFetch('/api/user/watchlists')
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        const lists = data.watchlists || [];
        if (lists.length > 0) {
          setWatchlist(lists[0]);
          setLoading(false);
          fetchData(lists[0]);
        } else {
          // Auto-create default watchlist
          apiFetch('/api/user/watchlists', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: 'My Watchlist' }),
          })
            .then((r) => r.json())
            .then((d) => {
              if (cancelled) return;
              setWatchlist(d.watchlist);
              setLoading(false);
            })
            .catch(() => {
              if (!cancelled) {
                setError('Failed to create watchlist.');
                setLoading(false);
              }
            });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError('Failed to load watchlists.');
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [fetchData]);

  // Add ticker
  const handleAdd = (e) => {
    e.preventDefault();
    const ticker = addInput.trim().toUpperCase();
    if (!ticker || !watchlist) return;

    setAdding(true);
    setAddMsg(null);

    apiFetch(`/api/user/watchlists/${watchlist.id}/items`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker }),
    })
      .then((r) => r.json().then((d) => ({ ok: r.ok, data: d })))
      .then(({ ok, data }) => {
        if (!ok) {
          setAddMsg({ type: 'error', text: data.error || 'Failed to add ticker.' });
          setAdding(false);
        } else {
          setAddInput('');
          const updatedItems = [...(watchlist.items || []), data.item];
          const updatedWl = { ...watchlist, items: updatedItems };
          setWatchlist(updatedWl);
          if (onWatchlistChange) onWatchlistChange(updatedItems);
          // Fetch only the new ticker's data instead of re-fetching all
          const ticker = data.item.ticker;
          setDataLoading(true);
          apiFetch(`/api/user/watchlists/${watchlist.id}/data/${ticker}`)
            .then((r) => r.json())
            .then((d) => {
              if (d.stock) {
                setStocks((prev) => [...prev, d.stock]);
              }
              setDataLoading(false);
              setAdding(false);
            })
            .catch(() => {
              // Fallback: re-fetch all if single fetch fails
              fetchData(updatedWl);
              setAdding(false);
            });
        }
      })
      .catch(() => {
        setAddMsg({ type: 'error', text: 'Network error.' });
        setAdding(false);
      });
  };

  // Remove ticker (optimistic)
  const handleRemove = useCallback((ticker) => {
    if (!watchlist) return;

    // Optimistic removal
    setStocks((prev) => prev.filter((s) => s.ticker !== ticker));
    const updatedItems = (watchlist.items || []).filter((i) => i.ticker !== ticker);
    setWatchlist((prev) => ({ ...prev, items: updatedItems }));
    if (onWatchlistChange) onWatchlistChange(updatedItems);

    apiFetch(`/api/user/watchlists/${watchlist.id}/items/${ticker}`, {
      method: 'DELETE',
    }).catch(() => {
      // Rollback on error — re-fetch
      fetchData(watchlist);
    });
  }, [watchlist, fetchData, onWatchlistChange]);

  const columns = buildColumns(handleRemove);

  // Use skeleton rows while enriched data is still loading
  const displayRows = (dataLoading && stocks.length === 0 && watchlist?.items?.length > 0)
    ? watchlist.items.map(item => ({ ticker: item.ticker, __skeleton: true }))
    : stocks;

  if (loading) {
    return (
      <div className="wl-tab">
        <DataTable columns={columns} rows={[]} loading={true} />
      </div>
    );
  }

  const hasItems = watchlist && watchlist.items && watchlist.items.length > 0;

  return (
    <div className="wl-tab">
      <div className="wl-header">
        <h2 className="wl-header__title">
          {watchlist ? watchlist.name : 'Watchlist'}
        </h2>
        {stocks.length > 0 && (
          <span className="wl-header__count">{stocks.length} stocks</span>
        )}
      </div>

      <form className="wl-add-bar" onSubmit={handleAdd}>
        <input
          className="wl-add-input"
          type="text"
          placeholder="Add ticker (e.g. AAPL)"
          value={addInput}
          onChange={(e) => setAddInput(e.target.value)}
        />
        <button className="wl-add-btn" type="submit" disabled={adding || !addInput.trim()}>
          {adding ? 'Adding…' : 'Add'}
        </button>
        {addMsg && (
          <span className={`wl-msg wl-msg--${addMsg.type}`}>{addMsg.text}</span>
        )}
      </form>

      {error && <div className="wl-msg wl-msg--error" style={{ marginBottom: 16 }}>{error}</div>}

      {!hasItems && !dataLoading ? (
        <div className="wl-empty">
          <div className="wl-empty__title">No stocks in your watchlist</div>
          <div className="wl-empty__subtitle">Add a ticker above to start tracking stocks.</div>
        </div>
      ) : (
        <DataTable
          columns={columns}
          rows={displayRows}
          loading={false}
          error={error && stocks.length === 0 && !dataLoading ? error : null}
          emptyMessage="No data available for watchlist tickers."
          rowKey="ticker"
          defaultSortKey="ticker"
          defaultSortDir="asc"
          onRowDoubleClick={(row) => !row.__skeleton && onNavigateToStock && onNavigateToStock(row.ticker)}
        />
      )}
    </div>
  );
}
