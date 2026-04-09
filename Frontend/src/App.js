import React, { useState, useEffect } from 'react';
import './App.css';
import { useAuth } from './AuthContext';
import { apiFetch } from './api';
import AuthPage from './components/AuthPage';
import StockChart from './components/StockChart';
import StockInfo from './components/StockInfo';
import StrategyGuide from './components/StrategyGuide';
import StatCard, { StatCardGrid } from './components/StatCard';
import Recommendations from './components/Recommendations';
import AnalystPanel from './components/AnalystPanel';
import Watchlist from './components/Watchlist';

const STRATEGIES = [
  { value: 'none', label: 'None (Raw Price Chart)' },
  { value: 'post-earnings-drift', label: 'Post-Earnings Drift Strategy' },
  { value: 'relative-strength', label: 'Relative Strength vs Market' },
  { value: 'bollinger-bands', label: 'Bollinger Bands' },
  { value: 'mean-reversion', label: 'Mean Reversion After Large Drawdown' },
  { value: 'macd-crossover', label: 'MACD Crossover' },
  { value: 'rsi', label: 'RSI Overbought / Oversold' },
  { value: 'volatility-squeeze', label: 'Volatility Squeeze' },
  { value: '52-week-breakout', label: '52-Week Breakout' },
  { value: 'ma-confluence', label: 'MA Confluence' },
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

// ── Stock snapshot panel: StatCards driven by shared stock-info data ─────────
function StockSnapshot({ info, loading, error }) {
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

// ── Root App ─────────────────────────────────────────────────────────────────
function App() {
  const { user, loading: authLoading, logout } = useAuth();
  const [activeTab, setActiveTab] = useState('analysis');
  const [analysisSubTab, setAnalysisSubTab] = useState('overview');
  const [inputValue, setInputValue] = useState('');
  const [submittedTicker, setSubmittedTicker] = useState('');
  const [strategy, setStrategy] = useState('none');
  const { start: defaultStart, end: defaultEnd } = defaultDates();
  const [startDate, setStartDate] = useState(defaultStart);
  const [endDate, setEndDate] = useState(defaultEnd);

  // Shared stock-info data — one fetch feeds both StockSnapshot and StockInfo.
  const [stockInfo, setStockInfo] = useState(null);
  const [stockInfoLoading, setStockInfoLoading] = useState(false);
  const [stockInfoError, setStockInfoError] = useState(null);

  // Analyst coverage data — fetched alongside stock-info.
  const [analystData, setAnalystData] = useState(null);
  const [analystLoading, setAnalystLoading] = useState(false);

  // Watchlist state — for "Add to Watchlist" button on analysis tab
  const [defaultWatchlist, setDefaultWatchlist] = useState(null);
  const [watchlistTickers, setWatchlistTickers] = useState(new Set());
  const [watchlistAdding, setWatchlistAdding] = useState(false);

  useEffect(() => {
    apiFetch('/api/user/watchlists')
      .then((r) => r.json())
      .then((data) => {
        const lists = data.watchlists || [];
        if (lists.length > 0) {
          setDefaultWatchlist(lists[0]);
          setWatchlistTickers(new Set((lists[0].items || []).map((i) => i.ticker)));
        }
      })
      .catch(() => {});
  }, []);

  const handleAddToWatchlist = (ticker) => {
    if (!defaultWatchlist || watchlistTickers.has(ticker)) return;
    setWatchlistAdding(true);
    apiFetch(`/api/user/watchlists/${defaultWatchlist.id}/items`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker }),
    })
      .then((r) => r.json().then((d) => ({ ok: r.ok, data: d })))
      .then(({ ok, data }) => {
        if (ok && data.item) {
          setWatchlistTickers((prev) => new Set([...prev, data.item.ticker]));
          setDefaultWatchlist((prev) => ({
            ...prev,
            items: [...(prev.items || []), data.item],
          }));
        }
        setWatchlistAdding(false);
      })
      .catch(() => setWatchlistAdding(false));
  };

  useEffect(() => {
    if (!submittedTicker) return;
    setStockInfoLoading(true);
    setStockInfoError(null);
    setStockInfo(null);

    apiFetch(`/api/stock-info/${submittedTicker}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) setStockInfoError(data.error);
        else setStockInfo(data);
        setStockInfoLoading(false);
      })
      .catch(() => {
        setStockInfoError('Could not load stock info.');
        setStockInfoLoading(false);
      });

    // Fetch analyst data in parallel
    setAnalystLoading(true);
    setAnalystData(null);
    apiFetch(`/api/analyst-data/${submittedTicker}`)
      .then((r) => r.json())
      .then((data) => {
        if (!data.error) setAnalystData(data);
        setAnalystLoading(false);
      })
      .catch(() => setAnalystLoading(false));
  }, [submittedTicker]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const clean = inputValue.trim().toUpperCase();
    if (clean) {
      setSubmittedTicker(clean);
      setStrategy('none');
    }
  };

  const dateRangeValid = startDate && endDate && startDate < endDate;

  if (authLoading) {
    return (
      <div className="app">
        <div className="auth-loading">Loading...</div>
      </div>
    );
  }

  if (!user) {
    return <AuthPage />;
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header__top">
          <h1>Hatfield Financial</h1>
          <div className="app-header__user">
            <span className="app-header__username">{user.username}</span>
            <button className="app-header__logout" onClick={logout}>Log out</button>
          </div>
        </div>
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
          className={`tab-btn ${activeTab === 'recommendations' ? 'active' : ''}`}
          onClick={() => setActiveTab('recommendations')}
        >
          Recommendations
        </button>
        <button
          className={`tab-btn ${activeTab === 'watchlist' ? 'active' : ''}`}
          onClick={() => setActiveTab('watchlist')}
        >
          Watchlist
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

            {submittedTicker && stockInfo && (
              <div className="info-overview">
                <div className="overview-name">
                  <span className="overview-ticker">{stockInfo.ticker}</span>
                  <span className="overview-company">{stockInfo.name}</span>
                </div>
                <div className="overview-actions">
                  <div className="overview-meta">
                    {stockInfo.sector !== 'N/A' && <span className="overview-pill">{stockInfo.sector}</span>}
                    {stockInfo.industry !== 'N/A' && <span className="overview-pill">{stockInfo.industry}</span>}
                    {stockInfo.marketCap && <span className="overview-pill">Mkt Cap: {stockInfo.marketCap}</span>}
                  </div>
                  {defaultWatchlist && (
                    <button
                      className={`wl-add-stock-btn ${watchlistTickers.has(submittedTicker) ? 'wl-add-stock-btn--added' : ''}`}
                      disabled={watchlistAdding || watchlistTickers.has(submittedTicker)}
                      onClick={() => handleAddToWatchlist(submittedTicker)}
                    >
                      {watchlistTickers.has(submittedTicker)
                        ? 'In Watchlist'
                        : watchlistAdding
                          ? 'Adding...'
                          : '+ Watchlist'}
                    </button>
                  )}
                </div>
              </div>
            )}

            {submittedTicker && (
              <StockSnapshot info={stockInfo} loading={stockInfoLoading} error={stockInfoError} />
            )}

            {submittedTicker && stockInfo && (
              <nav className="subtab-nav">
                <button
                  className={`subtab-btn ${analysisSubTab === 'overview' ? 'active' : ''}`}
                  onClick={() => setAnalysisSubTab('overview')}
                >
                  Overview
                </button>
                <button
                  className={`subtab-btn ${analysisSubTab === 'analyst' ? 'active' : ''}`}
                  onClick={() => setAnalysisSubTab('analyst')}
                >
                  Analyst Coverage
                </button>
                <button
                  className={`subtab-btn ${analysisSubTab === 'charts' ? 'active' : ''}`}
                  onClick={() => setAnalysisSubTab('charts')}
                >
                  Technical Charts
                </button>
              </nav>
            )}

            {submittedTicker && analysisSubTab === 'overview' && (
              <StockInfo
                ticker={submittedTicker}
                stockInfoData={stockInfo}
                stockInfoLoading={stockInfoLoading}
                stockInfoError={stockInfoError}
                hideOverview
              />
            )}

            {submittedTicker && analysisSubTab === 'analyst' && (
              <AnalystPanel
                data={analystData}
                ticker={submittedTicker}
                currentPrice={stockInfo?.currentPrice}
                loading={analystLoading}
              />
            )}

            {submittedTicker && analysisSubTab === 'charts' && dateRangeValid && stockInfo && (
              <>
                <div className="chart-controls-bar">
                  <span className="chart-controls-title">Technical Charts</span>
                  <div className="strategy-group">
                    <label htmlFor="strategy-select">Strategy:</label>
                    <select
                      id="strategy-select"
                      value={strategy}
                      onChange={(e) => setStrategy(e.target.value)}
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
                <StockChart
                  ticker={submittedTicker}
                  strategy={strategy}
                  startDate={startDate}
                  endDate={endDate}
                />
              </>
            )}
          </>
        )}

        {activeTab === 'recommendations' && (
          <Recommendations
            onNavigateToStock={(ticker) => {
              setInputValue(ticker);
              setSubmittedTicker(ticker);
              setActiveTab('analysis');
            }}
          />
        )}

        {activeTab === 'watchlist' && (
          <Watchlist
            onNavigateToStock={(ticker) => {
              setInputValue(ticker);
              setSubmittedTicker(ticker);
              setActiveTab('analysis');
            }}
            onWatchlistChange={(items) => {
              setWatchlistTickers(new Set(items.map((i) => i.ticker)));
            }}
          />
        )}

        {activeTab === 'guide' && <StrategyGuide />}
      </main>
    </div>
  );
}

export default App;
