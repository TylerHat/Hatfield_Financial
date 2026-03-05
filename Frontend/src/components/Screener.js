import React, { useState, useRef } from 'react';

const API_BASE = 'http://localhost:5000';

const STRATEGIES = [
  { value: 'bollinger-bands', label: 'Bollinger Bands' },
  { value: 'relative-strength', label: 'Relative Strength vs Market' },
  { value: 'mean-reversion', label: 'Mean Reversion After Large Drawdown' },
  { value: 'post-earnings-drift', label: 'Post-Earnings Drift' },
];

const CATEGORIES = [
  { score: 2, label: 'Strong Buy', cls: 'cat-strong-buy' },
  { score: 1, label: 'Buy', cls: 'cat-buy' },
  { score: 0, label: 'Neutral', cls: 'cat-neutral' },
  { score: -1, label: 'Sell', cls: 'cat-sell' },
  { score: -2, label: 'Strong Sell', cls: 'cat-strong-sell' },
];

export default function Screener() {
  const [strategy, setStrategy] = useState('bollinger-bands');
  const [universe, setUniverse] = useState('sp500');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);

  const runScreener = async () => {
    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    setResults(null);
    setMeta(null);

    try {
      const res = await fetch(`${API_BASE}/api/screener`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy, universe }),
        signal: ctrl.signal,
      });
      const data = await res.json();
      if (data.error) {
        setError(data.error);
      } else {
        setResults(data.results);
        setMeta(data.meta);
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setError('Screener request failed. Is the backend running?');
      }
    } finally {
      setLoading(false);
    }
  };

  // Group results by score
  const grouped = results
    ? CATEGORIES.reduce((acc, cat) => {
        acc[cat.score] = results.filter((r) => r.score === cat.score);
        return acc;
      }, {})
    : null;

  const strategyLabel = STRATEGIES.find((s) => s.value === strategy)?.label ?? strategy;

  return (
    <div className="screener-container">
      {/* ── Controls ── */}
      <div className="screener-controls">
        <div className="screener-control-group">
          <label htmlFor="sc-universe">Universe</label>
          <div className="screener-toggle">
            <button
              className={`toggle-btn ${universe === 'sp500' ? 'active' : ''}`}
              onClick={() => setUniverse('sp500')}
            >
              S&amp;P 500
            </button>
            <button
              className={`toggle-btn ${universe === 'crypto' ? 'active' : ''}`}
              onClick={() => setUniverse('crypto')}
            >
              Crypto
            </button>
          </div>
        </div>

        <div className="screener-control-group">
          <label htmlFor="sc-strategy">Strategy</label>
          <select
            id="sc-strategy"
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            className="screener-select"
          >
            {STRATEGIES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        <button
          className="screener-run-btn"
          onClick={runScreener}
          disabled={loading}
        >
          {loading ? 'Scanning…' : 'Run Screener'}
        </button>
      </div>

      {/* ── Loading state ── */}
      {loading && (
        <div className="screener-loading">
          <div className="screener-spinner" />
          <p>
            Scanning {universe === 'sp500' ? 'S&P 500 stocks' : 'crypto assets'} using{' '}
            <strong>{strategyLabel}</strong>…
          </p>
          <p className="screener-loading-sub">
            This may take 15–45 seconds for a full universe scan.
          </p>
        </div>
      )}

      {/* ── Error ── */}
      {error && <div className="screener-error">{error}</div>}

      {/* ── Results ── */}
      {results && meta && (
        <>
          <div className="screener-meta">
            Scanned <strong>{meta.count}</strong> tickers in{' '}
            <strong>{meta.duration}s</strong> using{' '}
            <strong>{strategyLabel}</strong>
            {meta.errors > 0 && (
              <span className="screener-meta-warn">
                {' '}· {meta.errors} skipped (insufficient data)
              </span>
            )}
          </div>

          <div className="screener-board">
            {CATEGORIES.map((cat) => {
              const items = grouped[cat.score] || [];
              return (
                <div key={cat.score} className={`screener-col ${cat.cls}`}>
                  <div className="screener-col-header">
                    <span className="screener-col-title">{cat.label}</span>
                    <span className="screener-col-count">{items.length}</span>
                  </div>
                  <div className="screener-col-body">
                    {items.length === 0 && (
                      <p className="screener-empty">No tickers</p>
                    )}
                    {items.map((item) => (
                      <div key={item.ticker} className="screener-card">
                        <div className="screener-card-top">
                          <span className="screener-card-ticker">{item.ticker}</span>
                          <span className="screener-card-price">
                            ${item.price.toLocaleString(undefined, {
                              minimumFractionDigits: 2,
                              maximumFractionDigits: 4,
                            })}
                          </span>
                        </div>
                        <p className="screener-card-reason">{item.reason}</p>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* ── Placeholder when nothing has been run yet ── */}
      {!loading && !error && !results && (
        <div className="screener-placeholder">
          <p>Select a strategy and universe, then click <strong>Run Screener</strong>.</p>
          <p className="screener-placeholder-sub">
            The screener evaluates every ticker in the selected universe using the
            chosen strategy's current-state signal and groups them from Strong Buy
            to Strong Sell.
          </p>
        </div>
      )}
    </div>
  );
}
