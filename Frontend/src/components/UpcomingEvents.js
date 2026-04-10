import React, { useState, useEffect, useRef } from 'react';
import { apiFetch } from '../api';
import DataTable from './DataTable';
import Badge from './Badge';
import './UpcomingEvents.css';

const LS_KEY = 'hf_upcoming_events_cache';
const LS_TTL = 20 * 60 * 1000; // 20 minutes

function loadCache() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed.events || !parsed.timestamp) return null;
    return parsed;
  } catch {
    return null;
  }
}

function saveCache(events, lastUpdated) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({
      events,
      lastUpdated,
      timestamp: Date.now(),
    }));
  } catch { /* storage full — ignore */ }
}

function formatTimeAgo(isoOrTimestamp) {
  const ts = typeof isoOrTimestamp === 'number' ? isoOrTimestamp : new Date(isoOrTimestamp).getTime();
  const mins = Math.round((Date.now() - ts) / 60000);
  if (mins < 1) return 'just now';
  if (mins === 1) return '1 min ago';
  if (mins < 60) return `${mins} mins ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs === 1) return '1 hour ago';
  return `${hrs} hours ago`;
}

function recVariant(recKey) {
  if (!recKey) return 'gray';
  if (recKey === 'strong_buy' || recKey === 'buy') return 'green';
  if (recKey === 'hold') return 'blue';
  if (recKey === 'sell' || recKey === 'strong_sell') return 'red';
  return 'gray';
}

function eventTypeVariant(type) {
  if (type === 'Earnings') return 'green';
  if (type === 'Ex-Dividend') return 'blue';
  if (type === 'Stock Split') return 'yellow';
  return 'gray';
}

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'Earnings', label: 'Earnings' },
  { key: 'Ex-Dividend', label: 'Ex-Dividend' },
  { key: 'Stock Split', label: 'Stock Split' },
];

const EVENT_COLUMNS = [
  {
    key: 'ticker',
    label: 'Ticker',
    sortable: true,
    width: '90px',
    render: (val) => <strong style={{ color: '#e6edf3' }}>{val}</strong>,
  },
  {
    key: 'companyName',
    label: 'Company',
    sortable: true,
    width: '180px',
    render: (val) => (
      <span style={{ color: '#8b949e' }}>
        {val && val.length > 28 ? val.slice(0, 28) + '\u2026' : val}
      </span>
    ),
  },
  {
    key: 'eventType',
    label: 'Event',
    sortable: true,
    width: '120px',
    render: (val) => <Badge variant={eventTypeVariant(val)} size="sm">{val}</Badge>,
  },
  {
    key: 'eventDate',
    label: 'Date',
    sortable: true,
    width: '110px',
  },
  {
    key: 'daysUntil',
    label: 'Days Until',
    numeric: true,
    sortable: true,
    width: '95px',
    render: (val) => {
      if (val === 0) return <span style={{ color: '#f0883e', fontWeight: 600 }}>Today</span>;
      if (val === 1) return <span style={{ color: '#d29922' }}>Tomorrow</span>;
      return `${val} days`;
    },
  },
  {
    key: 'analystRecommendation',
    label: 'Analyst Rec',
    sortable: true,
    width: '120px',
    render: (val, row) => (
      <Badge variant={recVariant(row.recommendationKey)} size="sm">{val || 'N/A'}</Badge>
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
    label: 'Day Chg %',
    numeric: true,
    sortable: true,
    width: '100px',
    render: (val) => {
      if (val == null) return '\u2014';
      const cls = val > 0 ? 'ue-positive' : val < 0 ? 'ue-negative' : 'ue-neutral';
      return <span className={cls}>{val > 0 ? '+' : ''}{val.toFixed(2)}%</span>;
    },
  },
  {
    key: 'inWatchlist',
    label: '\u2605',
    sortable: true,
    width: '50px',
    render: (val) => (
      <span className={val ? 'ue-star--active' : 'ue-star--inactive'}>
        {val ? '\u2605' : '\u2606'}
      </span>
    ),
  },
];

export default function UpcomingEvents({ onNavigateToStock, watchlistTickers }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all');
  const [lastUpdated, setLastUpdated] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const tickRef = useRef(null);

  // Re-render "X mins ago" every 30s
  useEffect(() => {
    tickRef.current = setInterval(() => setLastUpdated((v) => v), 30000);
    return () => clearInterval(tickRef.current);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let retryCount = 0;
    const MAX_RETRIES = 60;

    const cached = loadCache();
    if (cached && (Date.now() - cached.timestamp) < LS_TTL) {
      setEvents(cached.events);
      setLastUpdated(cached.timestamp);
      setLoading(false);
      return () => { cancelled = true; };
    }

    if (cached) {
      setEvents(cached.events);
      setLastUpdated(cached.timestamp);
      setLoading(false);
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    setError(null);

    function handleFreshData(newEvents, serverLastUpdated) {
      if (cancelled) return;
      setEvents(newEvents);
      setLastUpdated(Date.now());
      setLoading(false);
      setRefreshing(false);
      if (newEvents.length > 0) {
        saveCache(newEvents, serverLastUpdated);
      }
    }

    function doFetch() {
      apiFetch('/api/upcoming-events')
        .then((r) => r.json())
        .then((data) => {
          if (cancelled) return;
          if (data.error) {
            if (!cached) setError(data.error);
            setLoading(false);
            setRefreshing(false);
          } else if (data.status === 'loading') {
            poll();
          } else {
            handleFreshData(data.events || [], data.lastUpdated);
          }
        })
        .catch((err) => {
          if (!cancelled) {
            if (!cached) setError('Failed to connect to server.');
            setLoading(false);
            setRefreshing(false);
          }
        });
    }

    function poll() {
      if (cancelled) return;
      retryCount++;
      if (retryCount >= MAX_RETRIES) {
        if (!cached) setError('Data is taking too long to load. Please refresh and try again.');
        setLoading(false);
        setRefreshing(false);
        return;
      }
      setTimeout(doFetch, 5000);
    }

    doFetch();
    return () => { cancelled = true; };
  }, []);

  // Recompute daysUntil from eventDate on each render to stay fresh
  const today = new Date().toISOString().slice(0, 10);
  const watchlistSet = watchlistTickers || new Set();

  const enrichedEvents = events.map((e) => {
    const daysUntil = Math.ceil(
      (new Date(e.eventDate) - new Date(today)) / 86400000
    );
    return {
      ...e,
      daysUntil,
      inWatchlist: watchlistSet.has(e.ticker),
    };
  }).filter((e) => e.daysUntil >= 0 && e.daysUntil <= 30);

  // Filter counts
  const counts = {};
  counts.all = enrichedEvents.length;
  FILTERS.slice(1).forEach((f) => {
    counts[f.key] = enrichedEvents.filter((e) => e.eventType === f.key).length;
  });

  const filteredEvents = filter === 'all'
    ? enrichedEvents
    : enrichedEvents.filter((e) => e.eventType === filter);

  return (
    <div className="ue-tab">
      {/* Header */}
      <div className="ue-header">
        <h2 className="ue-header__title">Upcoming Events — S&P 500</h2>
        {!loading && !error && (
          <span className="ue-header__meta">
            {enrichedEvents.length} events in the next 30 days
            {lastUpdated && (
              <span style={{ marginLeft: 8, color: '#8b949e' }}>
                · Updated {formatTimeAgo(lastUpdated)}
                {refreshing && <span className="ue-loading-spinner" style={{ marginLeft: 6, width: 12, height: 12 }} />}
              </span>
            )}
          </span>
        )}
      </div>

      {/* Loading banner */}
      {loading && (
        <div className="ue-loading-banner">
          <div className="ue-loading-banner__title">
            <span className="ue-loading-spinner" />
            Loading upcoming events for S&P 500…
          </div>
          <div className="ue-loading-banner__subtitle">
            This may take a few minutes on first load. Data is cached for 24 hours.
          </div>
        </div>
      )}

      {/* Filter bar */}
      {!error && (enrichedEvents.length > 0 || !loading) && (
        <div className="ue-filter-bar">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              className={`ue-filter-btn ${filter === f.key ? 'ue-filter-btn--active' : ''}`}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
              <span className="ue-filter-btn__count">{counts[f.key] || 0}</span>
            </button>
          ))}
        </div>
      )}

      {/* Data table */}
      <DataTable
        columns={EVENT_COLUMNS}
        rows={filteredEvents}
        defaultSortKey="eventDate"
        defaultSortDir="asc"
        stickyHeader
        loading={loading && events.length === 0}
        error={error}
        emptyMessage="No upcoming events in the next 30 days."
        rowKey={(row) => `${row.ticker}-${row.eventType}-${row.eventDate}`}
        onRowDoubleClick={(row) => onNavigateToStock?.(row.ticker)}
      />
    </div>
  );
}
