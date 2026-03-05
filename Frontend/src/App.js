import React, { useState } from 'react';
import './App.css';
import StockChart from './components/StockChart';

const STRATEGIES = [
  { value: 'none', label: 'None (Raw Price Chart)' },
  { value: 'post-earnings-drift', label: 'Post-Earnings Drift Strategy' },
  { value: 'relative-strength', label: 'Relative Strength vs Market' },
  { value: 'bollinger-bands', label: 'Bollinger Bands' },
  { value: 'mean-reversion', label: 'Mean Reversion After Large Drawdown' },
];

function App() {
  const [inputValue, setInputValue] = useState('');
  const [submittedTicker, setSubmittedTicker] = useState('');
  const [strategy, setStrategy] = useState('none');

  const handleSubmit = (e) => {
    e.preventDefault();
    const clean = inputValue.trim().toUpperCase();
    if (clean) {
      setSubmittedTicker(clean);
      setStrategy('none');
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>Hatfield Financial</h1>
        <p>6-Month Stock Analysis Dashboard</p>
      </header>

      <main className="app-main">
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

        {submittedTicker && (
          <StockChart ticker={submittedTicker} strategy={strategy} />
        )}
      </main>
    </div>
  );
}

export default App;
