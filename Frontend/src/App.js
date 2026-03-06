import React, { useState } from 'react';
import './App.css';
import StockChart from './components/StockChart';
import StockInfo from './components/StockInfo';
import Screener from './components/Screener';
import Backtest from './components/Backtest';
import StrategyGuide from './components/StrategyGuide';

const STRATEGIES = [
  { value: 'none', label: 'None (Raw Price Chart)' },
  { value: 'post-earnings-drift', label: 'Post-Earnings Drift Strategy' },
  { value: 'relative-strength', label: 'Relative Strength vs Market' },
  { value: 'bollinger-bands', label: 'Bollinger Bands' },
  { value: 'mean-reversion', label: 'Mean Reversion After Large Drawdown' },
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

function App() {
  const [activeTab, setActiveTab] = useState('analysis');
  const [inputValue, setInputValue] = useState('');
  const [submittedTicker, setSubmittedTicker] = useState('');
  const [strategy, setStrategy] = useState('none');
  const { start: defaultStart, end: defaultEnd } = defaultDates();
  const [startDate, setStartDate] = useState(defaultStart);
  const [endDate, setEndDate] = useState(defaultEnd);

  const handleSubmit = (e) => {
    e.preventDefault();
    const clean = inputValue.trim().toUpperCase();
    if (clean) {
      setSubmittedTicker(clean);
      setStrategy('none');
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
          className={`tab-btn ${activeTab === 'screener' ? 'active' : ''}`}
          onClick={() => setActiveTab('screener')}
        >
          Stock Screener
        </button>
        <button
          className={`tab-btn ${activeTab === 'backtest' ? 'active' : ''}`}
          onClick={() => setActiveTab('backtest')}
        >
          Backtesting
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

            {submittedTicker && (
              <div className="controls-row">
                <span className="ticker-label">{submittedTicker}</span>
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
            )}

            {submittedTicker && dateRangeValid && (
              <StockChart
                ticker={submittedTicker}
                strategy={strategy}
                startDate={startDate}
                endDate={endDate}
              />
            )}

            {submittedTicker && <StockInfo ticker={submittedTicker} />}
          </>
        )}

        {activeTab === 'screener' && <Screener />}

        {activeTab === 'backtest' && <Backtest />}

        {activeTab === 'guide' && <StrategyGuide />}
      </main>
    </div>
  );
}

export default App;
