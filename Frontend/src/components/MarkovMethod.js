import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api';
import StatCard, { StatCardGrid } from './StatCard';

const REGIME_ACCENT = { Bull: 'green', Bear: 'red', Sideways: 'default', Side: 'default' };
const fmtPct = (p) => `${Math.round(p * 100)}%`;

const FORECAST_OPTIONS = [
  { key: '1d', label: '1 day' },
  { key: '3d', label: '3 days' },
  { key: '5d', label: '5 days' },
  { key: '10d', label: '10 days' },
  { key: 'stationary', label: 'Long-run' },
];

export default function MarkovMethod({ ticker, start, end }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [horizon, setHorizon] = useState('3d');

  useEffect(() => {
    if (!ticker || !start || !end) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    apiFetch(`/api/markov/${ticker}?start=${start}&end=${end}`)
      .then(async (res) => {
        const body = await res.json();
        if (cancelled) return;
        if (!res.ok) {
          setError(body.error || `Request failed (${res.status})`);
          setData(null);
        } else {
          setData(body);
        }
      })
      .catch((err) => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [ticker, start, end]);

  if (loading) {
    return (
      <div className="markov-section">
        <div className="markov-loading">Computing regime matrix…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="markov-section">
        <div className="markov-error">{error}</div>
      </div>
    );
  }

  if (!data) return null;

  const { current_regime, transition_matrix, stationary, forecast, transitions, params, bars_analyzed, date_range } = data;
  const accent = REGIME_ACCENT[current_regime] || 'default';
  const recentFlips = [...transitions].reverse().slice(0, 10);

  const forecastRow = horizon === 'stationary' ? stationary : (forecast && forecast[horizon]);
  const horizonLabel = FORECAST_OPTIONS.find((o) => o.key === horizon)?.label || horizon;

  return (
    <div className="markov-section">
      <div className="markov-header">
        <h3 className="markov-title">Markov Regime Analysis</h3>
        <span className="markov-subtitle">
          {date_range.start} → {date_range.end} · {bars_analyzed} bars analyzed
        </span>
      </div>

      <StatCardGrid columns={4}>
        <StatCard
          label="Current Regime"
          value={current_regime}
          accent={accent}
          size="lg"
        />
        <StatCard
          label="Long-Run Bull"
          value={fmtPct(stationary.bull)}
          accent="green"
          size="lg"
        />
        <StatCard
          label="Long-Run Bear"
          value={fmtPct(stationary.bear)}
          accent="red"
          size="lg"
        />
        <StatCard
          label="Long-Run Sideways"
          value={fmtPct(stationary.side)}
          accent="default"
          size="lg"
        />
      </StatCardGrid>

      <div className="markov-card">
        <div className="markov-card__title">
          <span className="markov-card__title-main">TRANSITION MATRIX</span>
          <span className="markov-card__title-meta">3 × 3 · next-state P</span>
        </div>
        <div className="markov-matrix">
          <div className="markov-matrix__corner" />
          {transition_matrix.cols.map((c) => (
            <div key={`col-${c}`} className="markov-matrix__header">{c.toUpperCase()}</div>
          ))}
          {transition_matrix.rows.map((rLabel, r) => (
            <React.Fragment key={`row-${rLabel}`}>
              <div className="markov-matrix__header markov-matrix__row-header">{rLabel.toUpperCase()}</div>
              {transition_matrix.values[r].map((v, c) => {
                const diag = r === c;
                return (
                  <div
                    key={`cell-${r}-${c}`}
                    className={`markov-matrix__cell ${diag ? 'markov-matrix__cell--diag' : ''}`}
                  >
                    {fmtPct(v)}
                  </div>
                );
              })}
            </React.Fragment>
          ))}
        </div>
        <div className="markov-card__footer">
          Diagonal = persistence (probability today's regime repeats tomorrow)
        </div>
      </div>

      {forecastRow && (
        <div className="markov-card">
          <div className="markov-card__title">
            <span className="markov-card__title-main">FORECAST</span>
            <span className="markov-card__title-meta">
              from current regime ({current_regime}) · P<sup>n</sup> · {horizonLabel}
            </span>
          </div>
          <div className="markov-forecast__controls">
            {FORECAST_OPTIONS.map((o) => (
              <button
                key={o.key}
                type="button"
                className={`markov-forecast__btn ${horizon === o.key ? 'active' : ''}`}
                onClick={() => setHorizon(o.key)}
              >
                {o.label}
              </button>
            ))}
          </div>
          <div className="markov-forecast__tiles">
            <div className="markov-forecast__tile markov-forecast__tile--bull">
              <div className="markov-forecast__tile-label">Bull</div>
              <div className="markov-forecast__tile-value">{fmtPct(forecastRow.bull)}</div>
            </div>
            <div className="markov-forecast__tile markov-forecast__tile--bear">
              <div className="markov-forecast__tile-label">Bear</div>
              <div className="markov-forecast__tile-value">{fmtPct(forecastRow.bear)}</div>
            </div>
            <div className="markov-forecast__tile markov-forecast__tile--side">
              <div className="markov-forecast__tile-label">Sideways</div>
              <div className="markov-forecast__tile-value">{fmtPct(forecastRow.side)}</div>
            </div>
          </div>
          <div className="markov-card__footer">
            Probability distribution over regimes {horizonLabel.toLowerCase()} from now, assuming today is {current_regime}.
            Each "day" is one bar — and a bar's regime is itself a {params.lookback}-bar rolling label, so short horizons are heavily smoothed.
          </div>
        </div>
      )}

      <div className="markov-card">
        <div className="markov-card__title">
          <span className="markov-card__title-main">RECENT REGIME CHANGES</span>
          <span className="markov-card__title-meta">debounced · min {params.min_hold}-bar hold</span>
        </div>
        {recentFlips.length === 0 ? (
          <div className="markov-flips__empty">No durable regime changes in this window.</div>
        ) : (
          <ul className="markov-flips">
            {recentFlips.map((f, i) => (
              <li key={`${f.date}-${i}`} className="markov-flips__item">
                <span className="markov-flips__date">{f.date}</span>
                <span className={`markov-flips__regime markov-flips__regime--${f.from.toLowerCase()}`}>{f.from}</span>
                <span className="markov-flips__arrow">→</span>
                <span className={`markov-flips__regime markov-flips__regime--${f.to.toLowerCase()}`}>{f.to}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="markov-footnote">
        Params (fixed): lookback {params.lookback} bars · bull threshold +{params.bull_pct}% ·
        bear threshold −{params.bear_pct}% · stationary power {params.stationary_power} ·
        min hold {params.min_hold} bars
      </div>
    </div>
  );
}
