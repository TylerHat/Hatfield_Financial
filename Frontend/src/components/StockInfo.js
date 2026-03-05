import React, { useEffect, useState } from 'react';

const API_BASE = 'http://localhost:5000';

function fmt(val, prefix = '', suffix = '', fallback = 'N/A') {
  if (val === null || val === undefined) return fallback;
  return `${prefix}${val}${suffix}`;
}

function MetricRow({ label, value }) {
  return (
    <div className="metric-row">
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value ?? 'N/A'}</span>
    </div>
  );
}

function StatusBadge({ text, color }) {
  // color: 'green' | 'yellow' | 'red' | 'blue' | 'gray'
  return <span className={`status-badge status-${color}`}>{text}</span>;
}

function valuationColor(v) {
  if (!v || v === 'N/A') return 'gray';
  if (v === 'Potentially Undervalued' || v === 'Fairly Valued') return 'green';
  if (v === 'Slightly Overvalued') return 'yellow';
  if (v === 'Potentially Overvalued' || v === 'Not Profitable') return 'red';
  return 'gray';
}

function rsiColor(sig) {
  if (sig === 'Overbought') return 'red';
  if (sig === 'Oversold') return 'green';
  if (sig === 'Neutral') return 'blue';
  return 'gray';
}

function consolidationColor(status) {
  if (status === 'Strong Consolidation' || status === 'Consolidating') return 'yellow';
  if (status === 'Expanding / Trending') return 'blue';
  if (status === 'Neutral') return 'gray';
  return 'gray';
}

function recColor(rec) {
  if (!rec || rec === 'N/A') return 'gray';
  const r = rec.toLowerCase();
  if (r.includes('strong buy') || r.includes('buy')) return 'green';
  if (r.includes('strong sell') || r.includes('sell')) return 'red';
  if (r.includes('hold') || r.includes('neutral')) return 'yellow';
  return 'gray';
}

export default function StockInfo({ ticker }) {
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    setInfo(null);

    fetch(`${API_BASE}/api/stock-info/${ticker}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.error) setError(data.error);
        else setInfo(data);
        setLoading(false);
      })
      .catch(() => {
        setError('Could not load stock info.');
        setLoading(false);
      });
  }, [ticker]);

  if (loading) return <div className="info-loading">Loading analysis for {ticker}…</div>;
  if (error) return <div className="info-error">{error}</div>;
  if (!info) return null;

  const rsiPct = info.rsi !== null ? Math.min(Math.max(info.rsi, 0), 100) : null;

  return (
    <div className="stock-info">
      {/* ── Company overview ─────────────────────────────────────── */}
      <div className="info-overview">
        <div className="overview-name">
          <span className="overview-ticker">{info.ticker}</span>
          <span className="overview-company">{info.name}</span>
        </div>
        <div className="overview-meta">
          {info.sector !== 'N/A' && <span className="overview-pill">{info.sector}</span>}
          {info.industry !== 'N/A' && <span className="overview-pill">{info.industry}</span>}
          {info.marketCap && <span className="overview-pill">Mkt Cap: {info.marketCap}</span>}
        </div>
      </div>

      {/* ── Analysis cards ───────────────────────────────────────── */}
      <div className="info-cards">

        {/* Valuation */}
        <div className="info-card">
          <div className="card-title">Valuation</div>
          <StatusBadge text={info.valuation} color={valuationColor(info.valuation)} />
          <p className="card-detail">{info.valuationDetail}</p>
          {info.targetMeanPrice && info.currentPrice && (
            <p className="card-detail">
              Analyst target: <strong>${info.targetMeanPrice}</strong>
              {' '}({((info.targetMeanPrice / info.currentPrice - 1) * 100).toFixed(1)}% vs current)
            </p>
          )}
        </div>

        {/* RSI / Momentum */}
        <div className="info-card">
          <div className="card-title">Momentum (RSI 14)</div>
          {rsiPct !== null ? (
            <>
              <div className="rsi-row">
                <span className="rsi-value">{info.rsi}</span>
                <StatusBadge text={info.rsiSignal} color={rsiColor(info.rsiSignal)} />
              </div>
              <div className="rsi-track">
                <div
                  className="rsi-fill"
                  style={{
                    width: `${rsiPct}%`,
                    background:
                      rsiPct >= 70 ? '#f85149' : rsiPct <= 30 ? '#3fb950' : '#58a6ff',
                  }}
                />
                <div className="rsi-zone-markers">
                  <span style={{ left: '30%' }} />
                  <span style={{ left: '70%' }} />
                </div>
              </div>
              <p className="card-detail">
                {info.rsiSignal === 'Overbought' && 'RSI above 70 — price may be stretched; watch for pullback.'}
                {info.rsiSignal === 'Oversold' && 'RSI below 30 — potential bounce opportunity; confirm with other signals.'}
                {info.rsiSignal === 'Neutral' && 'RSI between 30–70 — no extreme momentum reading.'}
              </p>
            </>
          ) : (
            <p className="card-detail">RSI not available.</p>
          )}
        </div>

        {/* 52-Week Range */}
        <div className="info-card">
          <div className="card-title">52-Week Range</div>
          {info.positionInRange !== null ? (
            <>
              <div className="range-labels">
                <span>${info.fiftyTwoWeekLow}</span>
                <span className="range-current">${info.currentPrice}</span>
                <span>${info.fiftyTwoWeekHigh}</span>
              </div>
              <div className="range-track">
                <div
                  className="range-thumb"
                  style={{ left: `calc(${info.positionInRange}% - 5px)` }}
                />
              </div>
              <p className="card-detail">
                {info.pctFromHigh < 0
                  ? `${Math.abs(info.pctFromHigh)}% below 52-week high`
                  : 'At or above 52-week high'}
                {' · '}
                {info.pctFromLow > 0
                  ? `${info.pctFromLow}% above 52-week low`
                  : 'At or below 52-week low'}
              </p>
            </>
          ) : (
            <p className="card-detail">Range data not available.</p>
          )}
        </div>

        {/* Consolidation */}
        <div className="info-card">
          <div className="card-title">Price Action</div>
          <StatusBadge
            text={info.consolidationStatus}
            color={consolidationColor(info.consolidationStatus)}
          />
          <p className="card-detail">{info.consolidationDetail}</p>
          {info.consolidationStatus === 'Strong Consolidation' ||
          info.consolidationStatus === 'Consolidating' ? (
            <p className="card-detail">
              Tight ranges often precede significant moves. A strategy breakout signal can
              confirm direction.
            </p>
          ) : null}
        </div>

      </div>

      {/* ── Key metrics table ────────────────────────────────────── */}
      <div className="info-metrics">
        <div className="metrics-title">Key Metrics</div>
        <div className="metrics-grid">
          <MetricRow label="P/E Ratio (Trailing)" value={fmt(info.trailingPE, '', 'x')} />
          <MetricRow label="P/E Ratio (Forward)" value={fmt(info.forwardPE, '', 'x')} />
          <MetricRow label="Price / Book" value={fmt(info.priceToBook, '', 'x')} />
          <MetricRow label="Price / Sales" value={fmt(info.priceToSales, '', 'x')} />
          <MetricRow label="Beta (5Y Monthly)" value={info.beta ?? 'N/A'} />
          <MetricRow
            label="Dividend Yield"
            value={
              info.dividendYield
                ? `${(info.dividendYield * 100).toFixed(2)}%`
                : 'N/A'
            }
          />
          <MetricRow label="EPS (Trailing)" value={fmt(info.eps, '$')} />
          <MetricRow label="Current Price" value={fmt(info.currentPrice, '$')} />
          <MetricRow
            label="Analyst Recommendation"
            value={
              <StatusBadge
                text={info.analystRecommendation}
                color={recColor(info.analystRecommendation)}
              />
            }
          />
          <MetricRow
            label="Analyst Mean Target"
            value={info.targetMeanPrice ? `$${info.targetMeanPrice}` : 'N/A'}
          />
        </div>
      </div>
    </div>
  );
}
