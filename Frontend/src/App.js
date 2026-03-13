import React, { useState, useEffect } from 'react';
import './App.css';
import StockChart from './components/StockChart';
import StockInfo from './components/StockInfo';
import StrategyGuide from './components/StrategyGuide';
import StatCard, { StatCardGrid } from './components/StatCard';
import DataTable from './components/DataTable';
import Badge from './components/Badge';

const API_BASE = 'http://localhost:5000';

const STRATEGIES = [
  { value: 'none', label: 'None (Raw Price Chart)' },
  { value: 'post-earnings-drift', label: 'Post-Earnings Drift Strategy' },
  { value: 'relative-strength', label: 'Relative Strength vs Market' },
  { value: 'bollinger-bands', label: 'Bollinger Bands' },
  { value: 'mean-reversion', label: 'Mean Reversion After Large Drawdown' },
  { value: 'macd-crossover', label: 'MACD Crossover' },
];

function toISODate(d) {
  return d.toISOString().split('T')[0];
}

function defaultDates() {
  const end = new Date();
  const start = new Date(end);
  start.setMonth(start.getMonth() - 6);
  return { start: toISODate(start), end: toISODate(end) };
}

// ── Signals DataTable column definitions ────────────────────────────────────
// Defined outside the component so the reference is stable across renders.
const SIGNAL_COLUMNS = [
  {
    key: 'date',
    label: 'Date',
    sortable: true,
    width: '120px',
  },
  {
    key: 'price',
    label: 'Price',
    numeric: true,
    sortable: true,
    width: '100px',
    render: (v) => (v != null ? `$${Number(v).toFixed(2)}` : null),
  },
  {
    key: 'type',
    label: 'Signal',
    sortable: true,
    width: '90px',
    render: (v) => {
      if (!v) return null;
      const variant = v.toLowerCase() === 'buy' ? 'buy' : 'sell';
      return <Badge variant={variant} size="sm">{v}</Badge>;
    },
  },
  {
    key: 'conviction',
    label: 'Conviction',
    sortable: true,
    width: '130px',
    render: (v, row) => {
      if (!v) return <Badge variant="gray" size="sm">N/A</Badge>;
      const variant =
        v.toLowerCase() === 'high'
          ? 'high'
          : v.toLowerCase() === 'medium'
          ? 'medium'
          : 'low';
      const score = row.score !== undefined ? ` (${row.score})` : '';
      return <Badge variant={variant} size="sm">{v}{score}</Badge>;
    },
  },
  {
    key: 'reason',
    label: 'Reason',
    sortable: false,
    // Allow this column to wrap — long strategy reason strings need room.
    render: (v) => <span style={{ whiteSpace: 'normal', lineHeight: '1.45' }}>{v}</span>,
  },
];

// ── Stock snapshot panel: StatCards driven by /api/stock-info/:ticker ────────
function StockSnapshot({ ticker }) {
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    setInfo(null);

    fetch(`${API_BASE}/api/stock-info/${ticker}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) setError(data.error);
        else setInfo(data);
        setLoading(false);
      })
      .catch(() => {
        setError('Could not load snapshot data.');
        setLoading(false);
      });
  }, [ticker]);

  // Determine accent color for price-change card based on sign.
  function priceAccent() {
    if (!info?.dayChange) return 'default';
    return info.dayChange > 0 ? 'green' : 'red';
  }

  // Format large numbers (market cap already pre-formatted by backend).
  function fmtPct(v) {
    if (v == null) return null;
    const sign = v >= 0 ? '+' : '';
    return `${sign}${Number(v).toFixed(2)}%`;
  }

  if (!ticker) return null;

  return (
    <div className="snapshot-section">
      <StatCardGrid columns={2}>
        <StatCard
          label="Current Price"
          value={info?.currentPrice != null ? `$${Number(info.currentPrice).toFixed(2)}` : null}
          accent={priceAccent()}
          loading={loading}
          error={error}
        />
        <StatCard
          label="Day Change"
          value={info?.dayChange != null ? fmtPct(info.dayChange) : null}
          accent={priceAccent()}
          loading={loading}
          error={error}
        />
      </StatCardGrid>
    </div>
  );
}

// ── Badge showcase: illustrates all variants in one place ────────────────────
function BadgeShowcase() {
  return (
    <div className="badge-showcase">
      <div className="badge-showcase__header">Badge Variants</div>
      <div className="badge-showcase__row">
        <div className="badge-showcase__group">
          <div className="badge-showcase__group-label">Signal</div>
          <Badge variant="buy">BUY</Badge>
          <Badge variant="sell">SELL</Badge>
          <Badge variant="neutral">NEUTRAL</Badge>
        </div>
        <div className="badge-showcase__group">
          <div className="badge-showcase__group-label">Conviction</div>
          <Badge variant="high">HIGH</Badge>
          <Badge variant="medium">MEDIUM</Badge>
          <Badge variant="low">LOW</Badge>
        </div>
        <div className="badge-showcase__group">
          <div className="badge-showcase__group-label">Colors</div>
          <Badge variant="green">Green</Badge>
          <Badge variant="red">Red</Badge>
          <Badge variant="blue">Blue</Badge>
          <Badge variant="yellow">Yellow</Badge>
          <Badge variant="gray">Gray</Badge>
        </div>
        <div className="badge-showcase__group">
          <div className="badge-showcase__group-label">Sizes</div>
          <Badge variant="buy" size="md">BUY (md)</Badge>
          <Badge variant="sell" size="sm">SELL (sm)</Badge>
        </div>
      </div>
    </div>
  );
}

// ── Components demo tab ──────────────────────────────────────────────────────
function ComponentsTab({ ticker, signals }) {
  // Build rows for the DataTable from the signals array passed from the
  // analysis tab. If no signals exist yet, show an empty + instructive state.
  const rows = signals.map((s) => ({
    ...s,
    _rowClass: s.type === 'BUY' ? 'buy-row' : 'sell-row',
  }));

  return (
    <div className="components-tab">
      <div className="components-tab__section">
        <div className="components-tab__title">Badge</div>
        <p className="components-tab__desc">
          Unified status pill. Use <code>variant</code> to control color and{' '}
          <code>size</code> for density.
        </p>
        <BadgeShowcase />
      </div>

      <div className="components-tab__section">
        <div className="components-tab__title">DataTable</div>
        <p className="components-tab__desc">
          Sortable table. Click any column header to sort. Run a strategy on the
          Stock Analysis tab to populate signals below.
        </p>
        <DataTable
          columns={SIGNAL_COLUMNS}
          rows={rows}
          defaultSortKey="date"
          defaultSortDir="desc"
          caption={
            ticker && rows.length > 0
              ? `Strategy signals for ${ticker}`
              : undefined
          }
          emptyMessage={
            ticker
              ? 'No signals yet. Select a strategy on the Stock Analysis tab.'
              : 'Enter a ticker and select a strategy on the Stock Analysis tab.'
          }
          rowKey="date"
        />
      </div>
    </div>
  );
}

// ── Root App ─────────────────────────────────────────────────────────────────
function App() {
  const [activeTab, setActiveTab] = useState('analysis');
  const [inputValue, setInputValue] = useState('');
  const [submittedTicker, setSubmittedTicker] = useState('');
  const [strategy, setStrategy] = useState('none');
  const { start: defaultStart, end: defaultEnd } = defaultDates();
  const [startDate, setStartDate] = useState(defaultStart);
  const [endDate, setEndDate] = useState(defaultEnd);

  // Signals are lifted to App so the Components tab can display them in
  // DataTable without a second fetch. StockChart passes them up via onSignals.
  const [liveSignals, setLiveSignals] = useState([]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const clean = inputValue.trim().toUpperCase();
    if (clean) {
      setSubmittedTicker(clean);
      setStrategy('none');
      setLiveSignals([]);
    }
  };

  const dateRangeValid = startDate && endDate && startDate < endDate;

  return (
    <div className="app">
      <header className="app-header">
        <h1>Hatfield Financial</h1>
        <p>Stock Analysis Dashboard</p>
      </header>

      {/* ── Tab navigation ── */}
      <nav className="tab-nav">
        <button
          className={`tab-btn ${activeTab === 'analysis' ? 'active' : ''}`}
          onClick={() => setActiveTab('analysis')}
        >
          Stock Analysis
        </button>
        <button
          className={`tab-btn ${activeTab === 'components' ? 'active' : ''}`}
          onClick={() => setActiveTab('components')}
        >
          Components
        </button>
        <button
          className={`tab-btn ${activeTab === 'guide' ? 'active' : ''}`}
          onClick={() => setActiveTab('guide')}
        >
          Strategy Guide
        </button>
      </nav>

      <main className="app-main">
        {activeTab === 'analysis' && (
          <>
            <form className="search-form" onSubmit={handleSubmit}>
              <input
                type="text"
                placeholder="Enter ticker symbol (e.g. AAPL)"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value.toUpperCase())}
                className="ticker-input"
                spellCheck={false}
                autoComplete="off"
              />
              <button type="submit" className="search-btn">
                Load
              </button>
            </form>

            <div className="date-range-row">
              <div className="date-group">
                <label htmlFor="start-date">From:</label>
                <input
                  id="start-date"
                  type="date"
                  value={startDate}
                  max={endDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="date-input"
                />
              </div>
              <div className="date-group">
                <label htmlFor="end-date">To:</label>
                <input
                  id="end-date"
                  type="date"
                  value={endDate}
                  min={startDate}
                  max={toISODate(new Date())}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="date-input"
                />
              </div>
              {!dateRangeValid && startDate && endDate && (
                <span className="date-error">Start date must be before end date</span>
              )}
            </div>

            {submittedTicker && <StockSnapshot ticker={submittedTicker} />}

            {submittedTicker && (
              <div className="controls-row">
                <span className="ticker-label">{submittedTicker}</span>
                <div className="strategy-group">
                  <label htmlFor="strategy-select">Strategy:</label>
                  <select
                    id="strategy-select"
                    value={strategy}
                    onChange={(e) => {
                      setStrategy(e.target.value);
                      setLiveSignals([]);
                    }}
                    className="strategy-select"
                  >
                    {STRATEGIES.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {submittedTicker && <StockInfo ticker={submittedTicker} />}

            {submittedTicker && dateRangeValid && (
              <StockChart
                ticker={submittedTicker}
                strategy={strategy}
                startDate={startDate}
                endDate={endDate}
                onSignals={setLiveSignals}
              />
            )}
          </>
        )}

        {activeTab === 'components' && (
          <ComponentsTab ticker={submittedTicker} signals={liveSignals} />
        )}

        {activeTab === 'guide' && <StrategyGuide />}
      </main>
    </div>
  );
}

export default App;
