import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { apiFetch } from '../api';
import DataTable from './DataTable';
import Badge from './Badge';
import { recVariant, macdVariant, trendVariant, volVariant, priceActionVariant } from '../utils/colorVariants';
import './Recommendations.css';

const LS_KEY = 'hf_recommendations_cache';
const LS_TTL = 20 * 60 * 1000; // 20 minutes in ms

// Fires every Custom ETF strategy's rebalance after a fresh recommendations
// load. Backend enforces a 24h cooldown, so calling this on every refresh is
// safe — non-admin users will silently 403 and we ignore it.
function triggerCustomEtfRebalance() {
  apiFetch('/api/custom-etf/strategies')
    .then((r) => (r.ok ? r.json() : null))
    .then((data) => {
      if (!data?.strategies) return;
      data.strategies.forEach((s) => {
        apiFetch(`/api/custom-etf/${s.id}/rebalance`, {
          method: 'POST',
          body: JSON.stringify({ force: false }),
        }).catch(() => {});
      });
    })
    .catch(() => {});
}
// Bump when the row shape changes so stale caches don't hide new columns.
const LS_SCHEMA_VERSION = 6;

function loadCache() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed.stocks || !parsed.timestamp) return null;
    if (parsed.schemaVersion !== LS_SCHEMA_VERSION) {
      localStorage.removeItem(LS_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function saveCache(stocks, lastUpdated) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({
      stocks,
      lastUpdated,
      timestamp: Date.now(),
      schemaVersion: LS_SCHEMA_VERSION,
    }));
  } catch { /* storage full or unavailable — ignore */ }
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

// Self-contained "Updated X mins ago" badge. Owning its own 30s tick here
// (instead of in the parent Recommendations component) means only this
// little span re-renders every 30s — not the entire 500-row tab tree.
function TimeAgoLabel({ ts }) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((v) => v + 1), 30000);
    return () => clearInterval(id);
  }, []);
  return <>{formatTimeAgo(ts)}</>;
}

const NONE_STRATEGY = { value: 'none', label: 'None' };

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'strong_buy', label: 'Strong Buy' },
  { key: 'buy', label: 'Buy' },
  { key: 'hold', label: 'Hold' },
  { key: 'sell', label: 'Sell' },
  { key: 'strong_sell', label: 'Strong Sell' },
];

// Variant helpers live in utils/colorVariants.js — see the import at the
// top of this file. The duplicates that used to live here drifted slightly
// from Watchlist.js (e.g. expanded `||` into separate `if`s); the shared
// module is now the single source of truth.

// ── Buy Score helpers ───────────────────────────────────────────────
// All sub-scores return 0–100. Missing data resolves to 50 (neutral) so
// data gaps neither inflate nor deflate the composite.

function _peScore(pe) {
  if (pe == null || pe <= 0) return 50; // negative/missing earnings = neutral
  if (pe < 10) return 100;
  if (pe < 15) return 80;
  if (pe < 20) return 60;
  if (pe < 30) return 40;
  if (pe < 50) return 20;
  return 5;
}

function _fcfYieldScore(y) {
  if (y == null) return 50;
  if (y >= 0.08) return 100;
  if (y >= 0.06) return 80;
  if (y >= 0.04) return 60;
  if (y >= 0.02) return 40;
  if (y >= 0) return 20;
  return 0;
}

function _roeScore(r) {
  if (r == null) return 50;
  if (r >= 0.20) return 100;
  if (r >= 0.15) return 80;
  if (r >= 0.10) return 60;
  if (r >= 0.05) return 40;
  if (r >= 0) return 20;
  return 0;
}

function _debtScore(de) {
  // yfinance debtToEquity is reported as a percent (e.g. 50 = 50%, 200 = 200%).
  if (de == null) return 50;
  if (de < 30) return 100;
  if (de < 60) return 80;
  if (de < 100) return 60;
  if (de < 200) return 40;
  return 20;
}

function _grossMarginScore(g) {
  if (g == null) return 50;
  if (g >= 0.50) return 100;
  if (g >= 0.40) return 80;
  if (g >= 0.30) return 60;
  if (g >= 0.20) return 40;
  if (g >= 0.10) return 20;
  return 0;
}

function _avg(values) {
  const v = values.filter((x) => x != null);
  if (v.length === 0) return 50;
  return v.reduce((s, x) => s + x, 0) / v.length;
}

function _growthScore(g) {
  if (g == null) return null; // signal: missing
  const c = Math.max(-0.5, Math.min(0.5, g));
  return (c + 0.5) / 1.0 * 100;
}

function _volRatioScore(vr) {
  // Lower vol = better risk-adjusted profile, given equal expected return.
  if (vr == null) return 50;
  if (vr < 0.7) return 80;
  if (vr <= 1.5) return 50;
  return 20;
}

function computeBuyScore(row) {
  const components = [];

  // ── Valuation (18%) ─────────────────────────────────────────────────
  // Forward P/E + FCF yield. The single biggest gap in the prior model.
  const valuation = _avg([_peScore(row.forwardPE), _fcfYieldScore(row.fcfYield)]);
  components.push({ w: 0.18, v: valuation });

  // ── Trend Composite (25%) ───────────────────────────────────────────
  // Consolidates the three trend signals (was 37% with triple-counting).
  const trendMap = {
    'Strong Uptrend': 100, 'Bullish (Mixed)': 75, 'Bullish (Short-term)': 75,
    'N/A': 50, 'Bearish (Mixed)': 30, 'Bearish (Short-term)': 30, 'Strong Downtrend': 0,
  };
  const trendVal = trendMap[row.trendAlignment] ?? 50;
  const macdMap = {
    'BULLISH CROSSOVER': 100, 'BULLISH': 65, 'BEARISH': 35, 'BEARISH CROSSOVER': 0,
  };
  const macdVal = macdMap[row.macdStatus] ?? 50;
  let momVal = 50;
  if (row.momentum != null) {
    const clamped = Math.max(-20, Math.min(20, row.momentum));
    momVal = (clamped + 20) / 40 * 100;
  }
  const trendComposite = trendVal * 0.5 + momVal * 0.3 + macdVal * 0.2;
  components.push({ w: 0.25, v: trendComposite });

  // ── Analyst Sentiment (12%) ─────────────────────────────────────────
  // Consensus level (6%) + target upside (6%, clamped −10/+30 — extreme
  // targets historically have negative predictive value).
  const recMap = { strong_buy: 100, buy: 75, hold: 50, sell: 25, strong_sell: 0 };
  components.push({ w: 0.06, v: recMap[row.recommendationKey] ?? 50 });
  let upsideVal = 50;
  if (row.targetUpsidePct != null) {
    const clamped = Math.max(-10, Math.min(30, row.targetUpsidePct));
    upsideVal = (clamped + 10) / 40 * 100;
  }
  components.push({ w: 0.06, v: upsideVal });

  // ── Quality (10%) ───────────────────────────────────────────────────
  // ROE, debt/equity, gross margin — the persistent quality factor.
  const quality = _avg([
    _roeScore(row.returnOnEquity),
    _debtScore(row.debtToEquity),
    _grossMarginScore(row.grossMargins),
  ]);
  components.push({ w: 0.10, v: quality });

  // ── Growth Trajectory (10%) ─────────────────────────────────────────
  // Pragmatic v1 stand-in for analyst earnings revisions: forward
  // earnings + revenue growth (yfinance does not expose revision history).
  const eg = _growthScore(row.epsGrowth);
  const rg = _growthScore(row.revenueGrowth);
  const growth = (eg == null && rg == null) ? 50 : _avg([eg, rg]);
  components.push({ w: 0.10, v: growth });

  // ── 52-Week Position (8%) ───────────────────────────────────────────
  // George/Hwang anomaly — proximity to 52w high persists.
  const pos52 = row.fiftyTwoWeekPosition != null ? row.fiftyTwoWeekPosition : 50;
  components.push({ w: 0.08, v: pos52 });

  // ── Volatility / Risk-Adjusted (7%) ─────────────────────────────────
  components.push({ w: 0.07, v: _volRatioScore(row.volRatio) });

  // ── RSI — regime-conditioned (5%) ───────────────────────────────────
  // In strong trends, RSI is unreliable as a contrarian signal — neutralize.
  let rsiVal = 50;
  const inStrongTrend = row.trendAlignment === 'Strong Uptrend' || row.trendAlignment === 'Strong Downtrend';
  if (row.rsiValue != null && !inStrongTrend) {
    const r = row.rsiValue;
    rsiVal = r < 30 ? 100 : r < 40 ? 85 : r < 55 ? 60 : r < 70 ? 40 : 15;
  }
  components.push({ w: 0.05, v: rsiVal });

  // ── Governance (3%) ─────────────────────────────────────────────────
  let govVal = 50;
  if (row.overallRisk != null) {
    govVal = (11 - row.overallRisk) / 10 * 100;
  }
  components.push({ w: 0.03, v: govVal });

  // ── Analyst Coverage (2%) ───────────────────────────────────────────
  let covVal = 50;
  if (row.numberOfAnalysts != null) {
    covVal = Math.min(100, row.numberOfAnalysts / 20 * 100);
  }
  components.push({ w: 0.02, v: covVal });

  return Math.round(components.reduce((sum, c) => sum + c.w * c.v, 0));
}

const SCORE_INFO_ROWS = [
  { signal: 'Valuation', weight: '18%', logic: 'Avg of Forward P/E score (cheap=100, >50×=5) and FCF yield score (≥8%=100, negative=0)' },
  { signal: 'Trend Composite', weight: '25%', logic: '50% MA 20/50/200 alignment + 30% 1M return vs SPY + 20% MACD — consolidated to stop triple-counting trend' },
  { signal: 'Analyst Sentiment', weight: '12%', logic: '6% consensus level (Strong Buy→100, Strong Sell→0) + 6% target upside (clamped −10% to +30%)' },
  { signal: 'Quality', weight: '10%', logic: 'Avg of ROE, Debt/Equity (inverted), and Gross Margin scores' },
  { signal: 'Growth Trajectory', weight: '10%', logic: 'Avg of forward earnings growth and revenue growth (proxy for analyst revisions), clamped ±50%' },
  { signal: '52-Week Position', weight: '8%', logic: 'Where price sits in the 52w range: at-low=0, at-high=100 (George/Hwang anomaly)' },
  { signal: 'Volatility (Risk-Adj)', weight: '7%', logic: 'ATR ratio: LOW vol (<0.7×)→80, Normal→50, HIGH vol (>1.5×)→20' },
  { signal: 'RSI (regime-conditioned)', weight: '5%', logic: 'Mean-reversion signal — neutralized in strong trends; otherwise oversold→100, overbought→15' },
  { signal: 'Governance Risk', weight: '3%', logic: 'ISS overall risk inverted: risk 1→100, risk 10→10' },
  { signal: 'Analyst Coverage', weight: '2%', logic: '20+ analysts = full score; missing data = 50 neutral' },
];

// REC_COLUMNS is defined inside the component so setShowScoreInfo is in scope.
const _STATIC_COLUMNS = [
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
    key: 'targetUpsidePct',
    label: 'Analyst Target',
    numeric: true,
    sortable: true,
    width: '150px',
    render: (val, row) => {
      if (val == null || row.targetMeanPrice == null) return '—';
      const cls = val > 0 ? 'rec-positive' : val < 0 ? 'rec-negative' : 'rec-neutral';
      const sign = val > 0 ? '+' : '';
      return (
        <span className={cls}>
          {sign}{val.toFixed(2)}% (${row.targetMeanPrice.toFixed(2)})
        </span>
      );
    },
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
  {
    key: 'overallRisk',
    label: 'Gov. Risk',
    numeric: true,
    sortable: true,
    width: '90px',
    render: (val) => {
      if (val == null) return '—';
      const color = val <= 3 ? '#2ea043' : val <= 6 ? '#d2993a' : '#f85149';
      return <span style={{ color, fontWeight: 600 }}>{val}</span>;
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
  const [etfStrategies, setEtfStrategies] = useState([]);
  const [rankings, setRankings] = useState({ strategyId: null, loading: false, error: null, byTicker: {}, buyThreshold: null, sellThreshold: null });
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [lastUpdated, setLastUpdated] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [showScoreInfo, setShowScoreInfo] = useState(false);

  const etfScoreColumn = {
    key: 'etfScore',
    label: 'Strategy Score',
    numeric: true,
    sortable: true,
    width: '140px',
    render: (val, row) => {
      if (val == null) return <span style={{ color: '#484f58' }}>—</span>;
      const color = val >= 70 ? '#2ea043' : val >= 40 ? '#d2993a' : '#f85149';
      return (
        <span style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
          <span style={{ color, fontWeight: 700, fontSize: '0.95rem' }}>{Math.round(val)}</span>
          {row.etfRank != null && (
            <span style={{ color: '#484f58', fontSize: '0.72rem' }}>#{row.etfRank}</span>
          )}
          {row.etfHeld && (
            <span title="Currently held by this strategy" style={{ color: '#58a6ff', fontSize: '0.72rem' }}>●</span>
          )}
        </span>
      );
    },
  };

  const REC_COLUMNS = [
    {
      key: 'buyScore',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          Buy Score
          <button
            className="rec-score-info-btn"
            onClick={(e) => { e.stopPropagation(); setShowScoreInfo(true); }}
            title="How is this score calculated?"
          >ⓘ</button>
        </span>
      ),
      numeric: true,
      sortable: true,
      width: '110px',
      render: (val) => {
        if (val == null) return '—';
        const color = val >= 70 ? '#2ea043' : val >= 40 ? '#d2993a' : '#f85149';
        return <span style={{ color, fontWeight: 700, fontSize: '0.95rem' }}>{val}</span>;
      },
    },
    ...(selectedStrategy !== 'none' ? [etfScoreColumn] : []),
    ..._STATIC_COLUMNS,
  ];

  // (The "X mins ago" tick lives inside <TimeAgoLabel> at the module top
  // so it doesn't force-rerender the whole tab tree every 30 seconds.)

  // Fetch recommendations on mount with localStorage cache
  useEffect(() => {
    let cancelled = false;
    let retryCount = 0;
    const MAX_RETRIES = 60;

    // Check localStorage first
    const cached = loadCache();
    if (cached && (Date.now() - cached.timestamp) < LS_TTL) {
      // Fresh cache — show it and skip backend fetch
      console.log('[Recommendations] fresh localStorage cache — %d stocks', cached.stocks.length);
      setStocks(cached.stocks);
      setLastUpdated(cached.timestamp);
      setLoading(false);
      return () => { cancelled = true; };
    }

    if (cached) {
      // Stale cache — show it immediately, refresh in background
      console.log('[Recommendations] stale localStorage cache — showing while refreshing');
      setStocks(cached.stocks);
      setLastUpdated(cached.timestamp);
      setLoading(false);
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    setError(null);

    function handleFreshData(newStocks, serverLastUpdated) {
      if (cancelled) return;
      setStocks(newStocks);
      setLastUpdated(Date.now());
      setLoading(false);
      setRefreshing(false);
      setProgress({ current: 0, total: 0 });
      // Only cache non-empty results to avoid blocking retries
      if (newStocks.length > 0) {
        saveCache(newStocks, serverLastUpdated);
        triggerCustomEtfRebalance();
      }
    }

    function doFetch() {
      console.log('[Recommendations] fetching (attempt', retryCount + 1, ')');
      apiFetch('/api/recommendations')
        .then((r) => r.json())
        .then((data) => {
          if (cancelled) return;
          if (data.error) {
            console.error('[Recommendations] server error:', data.error);
            if (!cached) setError(data.error);
            setLoading(false);
            setRefreshing(false);
          } else if (data.status === 'loading') {
            console.warn('[Recommendations] backend prewarming — polling progress');
            pollProgress();
          } else {
            console.log('[Recommendations] loaded', (data.stocks || []).length, 'stocks');
            handleFreshData(data.stocks || [], data.lastUpdated);
          }
        })
        .catch((err) => {
          if (!cancelled) {
            console.error('[Recommendations] fetch error:', err);
            if (!cached) setError('Failed to connect to server.');
            setLoading(false);
            setRefreshing(false);
          }
        });
    }

    function pollProgress() {
      if (cancelled) return;
      retryCount++;
      if (retryCount >= MAX_RETRIES) {
        console.error('[Recommendations] max retries reached — giving up');
        if (!cached) setError('Data is taking too long to load. Please refresh and try again.');
        setLoading(false);
        setRefreshing(false);
        return;
      }

      apiFetch('/api/recommendations/progress')
        .then((r) => r.json())
        .then((data) => {
          if (cancelled) return;

          if (data.status === 'complete') {
            handleFreshData(data.stocks || [], null);
            return;
          }

          // Show partial results as they arrive (only if no stale cache shown)
          if (!cached && data.stocks && data.stocks.length > 0) {
            setStocks(data.stocks);
          }
          setProgress({ current: data.progress || 0, total: data.total || 0 });

          setTimeout(pollProgress, 5000);
        })
        .catch(() => {
          if (!cancelled) {
            setTimeout(pollProgress, 5000);
          }
        });
    }

    doFetch();
    return () => { cancelled = true; };
  }, []);

  // Load the registered Custom ETF strategies once on mount
  useEffect(() => {
    apiFetch('/api/custom-etf/strategies')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data?.strategies) setEtfStrategies(data.strategies);
      })
      .catch(() => {});
  }, []);

  // Fetch rankings whenever the selected Custom ETF strategy changes
  useEffect(() => {
    if (selectedStrategy === 'none') {
      setRankings({ strategyId: null, loading: false, error: null, byTicker: {}, buyThreshold: null, sellThreshold: null });
      return;
    }
    let cancelled = false;
    setRankings((prev) => ({ ...prev, strategyId: selectedStrategy, loading: true, error: null }));
    apiFetch(`/api/custom-etf/${selectedStrategy}/rankings`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        if (data.error) {
          setRankings({ strategyId: selectedStrategy, loading: false, error: data.error, byTicker: {}, buyThreshold: null, sellThreshold: null });
          return;
        }
        const byTicker = {};
        (data.rankings || []).forEach((r) => { byTicker[r.ticker] = r; });
        setRankings({
          strategyId: selectedStrategy,
          loading: false,
          error: null,
          byTicker,
          buyThreshold: data.buyThreshold ?? null,
          sellThreshold: data.sellThreshold ?? null,
        });
      })
      .catch(() => {
        if (cancelled) return;
        setRankings({ strategyId: selectedStrategy, loading: false, error: 'Failed to load rankings.', byTicker: {}, buyThreshold: null, sellThreshold: null });
      });
    return () => { cancelled = true; };
  }, [selectedStrategy]);

  // Handle row click
  const handleRowClick = useCallback((row) => {
    const ticker = row.ticker;
    if (expandedTicker === ticker) {
      setExpandedTicker(null);
      return;
    }
    setExpandedTicker(ticker);
  }, [expandedTicker]);

  // Handle row double-click — navigate to Stock Analysis
  const handleRowDoubleClick = useCallback((row) => {
    if (onNavigateToStock) {
      onNavigateToStock(row.ticker);
    }
  }, [onNavigateToStock]);

  // Compute filter counts (one pass over `stocks`, not one per filter)
  const counts = useMemo(() => {
    const out = { all: stocks.length };
    for (const f of FILTERS.slice(1)) out[f.key] = 0;
    for (const s of stocks) {
      if (s.recommendationKey && out[s.recommendationKey] !== undefined) {
        out[s.recommendationKey] += 1;
      }
    }
    return out;
  }, [stocks]);

  // Apply filter
  const filteredStocks = useMemo(
    () => (filter === 'all' ? stocks : stocks.filter((s) => s.recommendationKey === filter)),
    [stocks, filter],
  );

  // Build the rows array — computeBuyScore is ~10 lookups + arithmetic per
  // row, so on a 500-stock universe this is ~5000 ops per render. useMemo
  // keeps it stable across re-renders that only touch unrelated state
  // (filter chip, search box, expanded-row toggling…).
  const strategyActive = selectedStrategy !== 'none';
  const rows = useMemo(() => filteredStocks.map((s) => {
    const r = rankings.byTicker[s.ticker];
    return {
      ...s,
      buyScore: computeBuyScore(s),
      etfScore: r?.score ?? null,
      etfRank: r?.rank ?? null,
      etfHeld: r?.held ?? false,
      _rowClass: s.ticker === expandedTicker ? 'rec-row--selected' : '',
    };
  }), [filteredStocks, rankings.byTicker, expandedTicker]);

  // Get expanded stock data
  const expandedStock = useMemo(
    () => (expandedTicker ? stocks.find((s) => s.ticker === expandedTicker) : null),
    [expandedTicker, stocks],
  );
  const expandedRank = useMemo(
    () => (expandedTicker ? rankings.byTicker[expandedTicker] : null),
    [expandedTicker, rankings.byTicker],
  );
  const activeStrategyMeta = useMemo(
    () => (strategyActive ? etfStrategies.find((es) => es.id === selectedStrategy) : null),
    [strategyActive, etfStrategies, selectedStrategy],
  );

  return (
    <div className="rec-tab">
      {/* Header */}
      <div className="rec-header">
        <h2 className="rec-header__title">S&P 500 Recommendations</h2>
        {!loading && !error && (
          <span className="rec-header__meta">
            {stocks.length} stocks loaded
            {lastUpdated && (
              <span style={{ marginLeft: 8, color: '#8b949e' }}>
                · Updated <TimeAgoLabel ts={lastUpdated} />
                {refreshing && <span className="rec-loading-spinner" style={{ marginLeft: 6, width: 12, height: 12 }} />}
              </span>
            )}
          </span>
        )}
      </div>

      {/* Loading banner with progress */}
      {loading && (
        <div className="rec-loading-banner">
          <div className="rec-loading-banner__title">
            <span className="rec-loading-spinner" />
            {progress.total > 0
              ? `Loading S\u0026P 500 data\u2026 ${progress.current}/${progress.total} (${Math.round((progress.current / progress.total) * 100)}%)`
              : 'Loading S\u0026P 500 data\u2026'}
          </div>
          {progress.total > 0 && (
            <div className="rec-loading-banner__progress-bar">
              <div
                className="rec-loading-banner__progress-fill"
                style={{ width: `${Math.round((progress.current / progress.total) * 100)}%` }}
              />
            </div>
          )}
          <div className="rec-loading-banner__subtitle">
            {stocks.length > 0
              ? `${stocks.length} stocks loaded so far \u2014 showing partial results below.`
              : 'This may take a couple of minutes on first load. Data is cached for 20 minutes.'}
          </div>
        </div>
      )}

      {/* Filter bar — show even during loading if partial results exist */}
      {!error && (stocks.length > 0 || !loading) && (
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
      {!error && (stocks.length > 0 || !loading) && (
        <div className="rec-strategy-bar">
          <span className="rec-strategy-bar__label">Custom ETF Strategies:</span>
          <select
            value={selectedStrategy}
            onChange={(e) => setSelectedStrategy(e.target.value)}
          >
            <option value={NONE_STRATEGY.value}>{NONE_STRATEGY.label}</option>
            {etfStrategies.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          {rankings.loading && (
            <span style={{ fontSize: '0.78rem', color: '#8b949e' }}>
              <span className="rec-loading-spinner" style={{ width: 12, height: 12 }} />
              Scoring universe…
            </span>
          )}
          {rankings.error && (
            <span style={{ fontSize: '0.78rem', color: '#f85149' }}>{rankings.error}</span>
          )}
          {strategyActive && activeStrategyMeta && !rankings.loading && !rankings.error && (
            <span style={{ fontSize: '0.78rem', color: '#8b949e' }} title={activeStrategyMeta.description}>
              Buy ≥ {activeStrategyMeta.buyThreshold} · Sell ≤ {activeStrategyMeta.sellThreshold}
            </span>
          )}
        </div>
      )}

      {/* Data table — show partial results while loading.
          `key` forces a remount when the strategy changes so the default sort
          re-applies (DataTable seeds sortKey/sortDir from props only on mount). */}
      <DataTable
        key={`rec-table-${selectedStrategy}`}
        columns={REC_COLUMNS}
        rows={rows}
        defaultSortKey={strategyActive ? 'etfScore' : 'ticker'}
        defaultSortDir={strategyActive ? 'desc' : 'asc'}
        stickyHeader
        loading={loading && stocks.length === 0}
        error={error}
        emptyMessage="No stocks match the selected filter."
        rowKey="ticker"
        onRowClick={handleRowClick}
        onRowDoubleClick={handleRowDoubleClick}
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

          {!strategyActive && (
            <p className="rec-detail__prompt">
              Select a Custom ETF strategy above to see how {expandedTicker} ranks.
            </p>
          )}

          {strategyActive && rankings.loading && (
            <p className="rec-detail__loading">
              <span className="rec-loading-spinner" />
              Scoring {expandedTicker} under {activeStrategyMeta?.name || selectedStrategy}…
            </p>
          )}

          {strategyActive && rankings.error && (
            <p className="rec-detail__error">{rankings.error}</p>
          )}

          {strategyActive && !rankings.loading && !rankings.error && (
            <div className="rec-detail__signals">
              {!expandedRank || expandedRank.score == null ? (
                <p className="rec-detail__no-signals">
                  {expandedTicker} could not be scored by {activeStrategyMeta?.name || selectedStrategy}
                  {expandedRank && !expandedRank.eligible ? ' (ineligible for this strategy)' : ' (missing required data)'}.
                </p>
              ) : (
                <div className="rec-signal-card">
                  <div className="rec-signal-card__field">
                    <span className="rec-signal-card__label">Strategy</span>
                    <span className="rec-signal-card__value">{activeStrategyMeta?.name || selectedStrategy}</span>
                  </div>
                  <div className="rec-signal-card__field">
                    <span className="rec-signal-card__label">Score</span>
                    <span className="rec-signal-card__value" style={{ fontWeight: 700 }}>
                      {Math.round(expandedRank.score)}
                    </span>
                  </div>
                  <div className="rec-signal-card__field">
                    <span className="rec-signal-card__label">Rank</span>
                    <span className="rec-signal-card__value">
                      #{expandedRank.rank} of {Object.keys(rankings.byTicker).length}
                    </span>
                  </div>
                  <div className="rec-signal-card__field">
                    <span className="rec-signal-card__label">Buy Threshold</span>
                    <span className="rec-signal-card__value">
                      <Badge
                        variant={expandedRank.score >= (rankings.buyThreshold ?? 70) ? 'buy' : 'sell'}
                        size="sm"
                      >
                        {expandedRank.score >= (rankings.buyThreshold ?? 70) ? 'PASSES' : 'BELOW'}
                      </Badge>
                    </span>
                  </div>
                  <div className="rec-signal-card__field">
                    <span className="rec-signal-card__label">Held</span>
                    <span className="rec-signal-card__value">
                      {expandedRank.held ? (
                        <Badge variant="green" size="sm">In Portfolio</Badge>
                      ) : (
                        <Badge variant="gray" size="sm">Not Held</Badge>
                      )}
                    </span>
                  </div>
                  {activeStrategyMeta?.description && (
                    <div className="rec-signal-card__field rec-signal-card__reason">
                      <span className="rec-signal-card__label">Description</span>
                      <span className="rec-signal-card__value">{activeStrategyMeta.description}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Score methodology modal */}
      {showScoreInfo && (
        <div className="rec-score-modal-backdrop" onClick={() => setShowScoreInfo(false)}>
          <div className="rec-score-modal" onClick={(e) => e.stopPropagation()}>
            <button className="rec-score-modal__close" onClick={() => setShowScoreInfo(false)}>✕</button>
            <div className="rec-score-modal__title">Buy Score Methodology</div>
            <div className="rec-score-modal__intro">
              A weighted 0–100 composite that ranks stocks by their combined fundamental, analyst, and technical signals.
              Higher scores indicate a stronger near-term buy case. Missing data defaults to a neutral value and does not inflate or deflate the score.
            </div>
            <table>
              <thead>
                <tr>
                  <th>Signal</th>
                  <th>Weight</th>
                  <th>Scoring Logic</th>
                </tr>
              </thead>
              <tbody>
                {SCORE_INFO_ROWS.map((r) => (
                  <tr key={r.signal}>
                    <td>{r.signal}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>{r.weight}</td>
                    <td>{r.logic}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
