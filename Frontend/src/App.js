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
import InsiderTransactions from './components/InsiderTransactions';
import InstitutionalHoldings from './components/InstitutionalHoldings';
import Watchlist from './components/Watchlist';
import AdminPanel from './components/AdminPanel';
import AccountPanel from './components/AccountPanel';
import ApiMonitorPanel from './components/ApiMonitorPanel';

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
  // Backend always fetches a trailing 1-year window; filters below slice it in memory.
  const [fetchRange] = useState(defaultDates);
  const [startDate, setStartDate] = useState(fetchRange.start);
  const [endDate, setEndDate] = useState(fetchRange.end);
  const [pendingStart, setPendingStart] = useState(fetchRange.start);
  const [pendingEnd, setPendingEnd] = useState(fetchRange.end);
  const [activePreset, setActivePreset] = useState('1Y');
  const [rangePerf, setRangePerf] = useState(null);

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

  // Refresh data state
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState(null);
  const [refreshCount, setRefreshCount] = useState(0);

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

  const handleRefreshData = () => {
    if (!submittedTicker) return;
    setRefreshing(true);
    setStockInfoLoading(true);
    setRefreshError(null);
    setStockInfoError(null);

    // Trigger chart refresh by incrementing refresh count
    setRefreshCount((prev) => prev + 1);

    apiFetch(`/api/stock-info/${submittedTicker}`, {
      method: 'POST',
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          setRefreshError(data.error);
        } else {
          setStockInfo(data);
          setRefreshError(null);
          setStockInfoError(null);
        }
        setRefreshing(false);
        setStockInfoLoading(false);
      })
      .catch(() => {
        setRefreshError('Could not refresh stock data.');
        setRefreshing(false);
        setStockInfoLoading(false);
      });
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

  const dateRangeValid = startDate && endDate && startDate <= endDate;

  // ── Chart-range presets (slice already-fetched 1-year window) ───────────────
  function commitFilter(s, e, presetKey) {
    setStartDate(s);
    setEndDate(e);
    setPendingStart(s);
    setPendingEnd(e);
    setActivePreset(presetKey);
  }

  function applyPreset(key) {
    const today = new Date();
    const fetchStartDate = new Date(fetchRange.start);
    let start;
    let end = today;
    if (key === '1W') {
      start = new Date(today);
      start.setDate(start.getDate() - 7);
    } else if (key === '1M') {
      start = new Date(today);
      start.setMonth(start.getMonth() - 1);
    } else if (key === '6M') {
      start = new Date(today);
      start.setMonth(start.getMonth() - 6);
    } else if (key === '1Y') {
      start = new Date(fetchRange.start);
      end = new Date(fetchRange.end);
    } else {
      return;
    }
    // Clamp to fetch window
    if (start < fetchStartDate) start = fetchStartDate;
    if (end > today) end = today;
    if (start > end) return;
    commitFilter(toISODate(start), toISODate(end), key);
  }

  function handleLoadCustomRange() {
    if (!pendingStart || !pendingEnd || pendingStart > pendingEnd) return;
    commitFilter(pendingStart, pendingEnd, null);
  }

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
        <button
          className={`tab-btn ${activeTab === 'account' ? 'active' : ''}`}
          onClick={() => setActiveTab('account')}
        >
          Account
        </button>
        {user?.is_admin && (
          <button
            className={`tab-btn tab-btn--admin ${activeTab === 'administration' ? 'active' : ''}`}
            onClick={() => setActiveTab('administration')}
          >
            Administration
          </button>
        )}
        {user?.is_admin && (
          <button
            className={`tab-btn tab-btn--admin ${activeTab === 'api-monitor' ? 'active' : ''}`}
            onClick={() => setActiveTab('api-monitor')}
          >
            API Monitor
          </button>
        )}
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

            {submittedTicker && (
              <div className="info-overview">
                <div className="overview-name">
                  <span className="overview-ticker">{stockInfo?.ticker || submittedTicker}</span>
                  {stockInfo?.name && (
                    <span className="overview-company">{stockInfo.name}</span>
                  )}
                </div>
                <div className="overview-actions">
                  <div className="overview-meta">
                    {stockInfo?.sector && stockInfo.sector !== 'N/A' && (
                      <span className="overview-pill">{stockInfo.sector}</span>
                    )}
                    {stockInfo?.industry && stockInfo.industry !== 'N/A' && (
                      <span className="overview-pill">{stockInfo.industry}</span>
                    )}
                    {stockInfo?.marketCap && (
                      <span className="overview-pill">Mkt Cap: {stockInfo.marketCap}</span>
                    )}
                  </div>
                  <div className="overview-buttons">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <button
                        className="refresh-data-btn"
                        disabled={refreshing || !submittedTicker}
                        onClick={handleRefreshData}
                        title="Clear cache and fetch fresh data"
                      >
                        {refreshing ? 'Refreshing...' : '↻ Refresh'}
                      </button>
                      {refreshError && (
                        <span style={{ color: '#f85149', fontSize: '12px' }}>
                          {refreshError}
                        </span>
                      )}
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
                  className={`subtab-btn ${analysisSubTab === 'insider' ? 'active' : ''}`}
                  onClick={() => setAnalysisSubTab('insider')}
                >
                  Insider Transactions
                </button>
                <button
                  className={`subtab-btn ${analysisSubTab === 'institutional' ? 'active' : ''}`}
                  onClick={() => setAnalysisSubTab('institutional')}
                >
                  Institutional Holdings
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

            {submittedTicker && analysisSubTab === 'insider' && (
              <InsiderTransactions
                transactions={stockInfo?.insiderTransactions}
                net90d={stockInfo?.insiderNet90d}
                net90dValue={stockInfo?.insiderNet90dValue}
              />
            )}

            {submittedTicker && analysisSubTab === 'institutional' && (
              <InstitutionalHoldings
                holders={stockInfo?.institutionalHolders}
                major={stockInfo?.institutionalMajor}
                totalCount={stockInfo?.institutionalCount}
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
                  <div className="chart-range-controls">
                    <div className="range-presets">
                      {[
                        { key: '1W', label: '1W' },
                        { key: '1M', label: '1M' },
                        { key: '6M', label: '6M' },
                        { key: '1Y', label: '1Y' },
                      ].map(({ key, label }) => (
                        <button
                          key={key}
                          type="button"
                          className={`range-btn ${activePreset === key ? 'active' : ''}`}
                          onClick={() => applyPreset(key)}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <div className="range-custom">
                      <input
                        type="date"
                        className="date-input"
                        value={pendingStart}
                        min={fetchRange.start}
                        max={fetchRange.end}
                        onChange={(e) => setPendingStart(e.target.value)}
                      />
                      <span className="range-sep">–</span>
                      <input
                        type="date"
                        className="date-input"
                        value={pendingEnd}
                        min={fetchRange.start}
                        max={fetchRange.end}
                        onChange={(e) => setPendingEnd(e.target.value)}
                      />
                      <button
                        type="button"
                        className="range-load-btn"
                        onClick={handleLoadCustomRange}
                        disabled={!pendingStart || !pendingEnd || pendingStart > pendingEnd}
                      >
                        Load
                      </button>
                      {rangePerf !== null && (
                        <span className={`range-perf range-perf--${rangePerf.up ? 'up' : 'down'}`}>
                          {rangePerf.up ? '▲' : '▼'} {Math.abs(rangePerf.pct).toFixed(2)}%
                        </span>
                      )}
                    </div>
                  </div>
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
                  fetchStart={fetchRange.start}
                  fetchEnd={fetchRange.end}
                  startDate={startDate}
                  endDate={endDate}
                  onRangePerformance={setRangePerf}
                  refreshKey={refreshCount}
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

        {activeTab === 'account' && <AccountPanel />}

        {activeTab === 'administration' && user?.is_admin && <AdminPanel />}

        {activeTab === 'api-monitor' && user?.is_admin && <ApiMonitorPanel />}
      </main>
    </div>
  );
}

export default App;
