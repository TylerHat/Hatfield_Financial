import React from 'react';
import Badge from './Badge';
import DataTable from './DataTable';
import './AnalystPanel.css';

/* ── helpers ─────────────────────────────────────────────────────────────── */

function recColor(rec) {
  if (!rec || rec === 'N/A') return 'gray';
  const r = rec.toLowerCase();
  if (r.includes('strong buy') || r.includes('buy')) return 'green';
  if (r.includes('strong sell') || r.includes('sell')) return 'red';
  if (r.includes('hold') || r.includes('neutral')) return 'yellow';
  return 'gray';
}

function actionColor(action) {
  if (!action) return 'gray';
  const a = action.toLowerCase();
  if (a === 'upgrade' || a === 'init' || a === 'initiated') return 'green';
  if (a === 'downgrade') return 'red';
  if (a === 'reiterated' || a === 'main' || a === 'maintains') return 'blue';
  return 'gray';
}

function fmtLarge(val) {
  if (val == null) return 'N/A';
  const abs = Math.abs(val);
  const sign = val < 0 ? '-' : '';
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  return `${sign}$${abs.toLocaleString()}`;
}

function fmtNum(val, prefix = '', suffix = '') {
  if (val == null) return 'N/A';
  return `${prefix}${val}${suffix}`;
}

/* ── Period labels ───────────────────────────────────────────────────────── */

const PERIOD_LABELS = {
  '0q': 'Current Qtr',
  '+1q': 'Next Qtr',
  '0y': 'Current Year',
  '+1y': 'Next Year',
};

/* ── Sub-components ──────────────────────────────────────────────────────── */

function PriceTargetBar({ targets, currentPrice }) {
  if (!targets || targets.low == null || targets.high == null) return null;

  const low = targets.low;
  const high = targets.high;
  const range = high - low;
  if (range <= 0) return null;

  // Inverted: high on left (0%), low on right (100%)
  const pricePct = currentPrice
    ? Math.max(0, Math.min(100, ((high - currentPrice) / range) * 100))
    : null;
  const meanPct = targets.mean != null
    ? Math.max(0, Math.min(100, ((high - targets.mean) / range) * 100))
    : null;
  const medianPct = targets.median != null
    ? Math.max(0, Math.min(100, ((high - targets.median) / range) * 100))
    : null;

  return (
    <div className="ap-target-bar-wrap">
      <div className="ap-target-labels">
        <span className="ap-target-hi">${high.toFixed(2)}</span>
        <span className="ap-target-lo">${low.toFixed(2)}</span>
      </div>
      <div className="ap-target-bar">
        {pricePct != null && (
          <div className="ap-marker ap-marker--price" style={{ left: `${pricePct}%` }}
               title={`Current: $${currentPrice.toFixed(2)}`}>
            <div className="ap-marker-line" />
            <span className="ap-marker-label">Current</span>
          </div>
        )}
        {meanPct != null && (
          <div className="ap-marker ap-marker--mean" style={{ left: `${meanPct}%` }}
               title={`Mean: $${targets.mean.toFixed(2)}`}>
            <div className="ap-marker-line" />
            <span className="ap-marker-label">Mean ${targets.mean.toFixed(0)}</span>
          </div>
        )}
        {medianPct != null && meanPct != null && Math.abs(medianPct - meanPct) > 5 && (
          <div className="ap-marker ap-marker--median" style={{ left: `${medianPct}%` }}
               title={`Median: $${targets.median.toFixed(2)}`}>
            <div className="ap-marker-line" />
            <span className="ap-marker-label">Med ${targets.median.toFixed(0)}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function RecBreakdownBar({ counts }) {
  if (!counts || !counts.total) return null;

  const segments = [
    { key: 'strongBuy', label: 'Strong Buy', color: '#2ea043' },
    { key: 'buy', label: 'Buy', color: '#3fb950' },
    { key: 'hold', label: 'Hold', color: '#d2993a' },
    { key: 'sell', label: 'Sell', color: '#f85149' },
    { key: 'strongSell', label: 'Strong Sell', color: '#da3633' },
  ];

  return (
    <div className="ap-rec-bar-wrap">
      <div className="ap-rec-bar">
        {segments.map((s) => {
          const val = counts[s.key] || 0;
          if (val === 0) return null;
          const pct = (val / counts.total) * 100;
          return (
            <div key={s.key} className="ap-rec-segment"
                 style={{ width: `${pct}%`, backgroundColor: s.color }}
                 title={`${s.label}: ${val}`}>
              {pct > 8 && <span className="ap-rec-segment-label">{val}</span>}
            </div>
          );
        })}
      </div>
      <div className="ap-rec-legend">
        {segments.map((s) => {
          const val = counts[s.key] || 0;
          if (val === 0) return null;
          return (
            <span key={s.key} className="ap-rec-legend-item">
              <span className="ap-rec-dot" style={{ backgroundColor: s.color }} />
              {s.label} ({val})
            </span>
          );
        })}
      </div>
    </div>
  );
}

function RecTrendTable({ trend }) {
  if (!trend || trend.length === 0) return null;

  const periodLabels = ['Current', '1M Ago', '2M Ago', '3M Ago'];

  return (
    <div className="ap-trend-table-wrap">
      <table className="ap-trend-table">
        <thead>
          <tr>
            <th>Period</th>
            <th>Strong Buy</th>
            <th>Buy</th>
            <th>Hold</th>
            <th>Sell</th>
            <th>Strong Sell</th>
          </tr>
        </thead>
        <tbody>
          {trend.slice(0, 4).map((row, i) => (
            <tr key={i}>
              <td>{periodLabels[i] || row.period}</td>
              <td className="ap-trend-green">{row.strongBuy ?? '-'}</td>
              <td className="ap-trend-green">{row.buy ?? '-'}</td>
              <td className="ap-trend-yellow">{row.hold ?? '-'}</td>
              <td className="ap-trend-red">{row.sell ?? '-'}</td>
              <td className="ap-trend-red">{row.strongSell ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EstimatesSection({ title, estimates, isRevenue }) {
  if (!estimates || Object.keys(estimates).length === 0) return null;

  const periods = ['0q', '+1q', '0y', '+1y'];
  const available = periods.filter((p) => estimates[p]);
  if (available.length === 0) return null;

  return (
    <div className="ap-estimates-section">
      <div className="ap-subsection-title">{title}</div>
      <div className="ap-estimates-grid">
        {available.map((p) => {
          const est = estimates[p];
          const avg = isRevenue ? fmtLarge(est.avg) : fmtNum(est.avg, '$');
          const lo = isRevenue ? fmtLarge(est.low) : fmtNum(est.low, '$');
          const hi = isRevenue ? fmtLarge(est.high) : fmtNum(est.high, '$');
          return (
            <div key={p} className="ap-estimate-card">
              <div className="ap-estimate-period">{PERIOD_LABELS[p] || p}</div>
              <div className="ap-estimate-avg">{avg}</div>
              <div className="ap-estimate-range">Range: {lo} &ndash; {hi}</div>
              {est.numberOfAnalysts != null && (
                <div className="ap-estimate-analysts">{est.numberOfAnalysts} analysts</div>
              )}
              {est.growth != null && (
                <div className={`ap-estimate-growth ${est.growth >= 0 ? 'positive' : 'negative'}`}>
                  {est.growth >= 0 ? '+' : ''}{(est.growth * 100).toFixed(1)}% YoY
                </div>
              )}
              {!isRevenue && est.yearAgoEps != null && (
                <div className="ap-estimate-yago">Year Ago: ${est.yearAgoEps}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Upgrades/Downgrades columns ─────────────────────────────────────────── */

const UD_COLUMNS = [
  { key: 'date', label: 'Date', sortable: true, width: '110px' },
  { key: 'firm', label: 'Firm', sortable: true },
  {
    key: 'action', label: 'Action', sortable: true, width: '120px',
    render: (val) => <Badge variant={actionColor(val)} size="sm">{val || 'N/A'}</Badge>,
  },
  { key: 'fromGrade', label: 'From', sortable: false, width: '110px' },
  { key: 'toGrade', label: 'To', sortable: false, width: '110px' },
];

/* ── Main component ──────────────────────────────────────────────────────── */

export default function AnalystPanel({ data, ticker, currentPrice, loading }) {
  if (loading) {
    return (
      <div className="ap-panel">
        <div className="metrics-title">Analyst Coverage</div>
        <p className="ap-loading">Loading analyst data...</p>
      </div>
    );
  }

  if (!data || data.error) {
    return null;
  }

  const hasData = data.priceTargets || data.recommendationCounts ||
    data.upgradesDowngrades || data.earningsEstimate || data.revenueEstimate;

  if (!hasData) {
    return (
      <div className="ap-panel">
        <div className="metrics-title">Analyst Coverage</div>
        <p className="ap-empty">No analyst coverage available for {ticker}.</p>
      </div>
    );
  }

  const pt = data.priceTargets;
  const upside = pt && pt.mean && currentPrice
    ? ((pt.mean / currentPrice - 1) * 100).toFixed(1)
    : null;

  return (
    <div className="ap-panel">
      <div className="metrics-title">Analyst Coverage</div>

      {/* ── Overview row ── */}
      <div className="ap-overview-row">
        {data.consensusRecommendation && data.consensusRecommendation !== 'N/A' && (
          <div className="ap-overview-card">
            <span className="ap-overview-label">Consensus</span>
            <Badge variant={recColor(data.consensusRecommendation)} size="md">
              {data.consensusRecommendation}
            </Badge>
          </div>
        )}
        {data.numberOfAnalysts != null && (
          <div className="ap-overview-card">
            <span className="ap-overview-label">Analysts</span>
            <span className="ap-overview-value">{data.numberOfAnalysts}</span>
          </div>
        )}
        {pt && pt.mean != null && (
          <div className="ap-overview-card">
            <span className="ap-overview-label">Mean Target</span>
            <span className="ap-overview-value">
              ${pt.mean.toFixed(2)}
              {upside && (
                <span className={`ap-upside ${parseFloat(upside) >= 0 ? 'positive' : 'negative'}`}>
                  {' '}({upside > 0 ? '+' : ''}{upside}%)
                </span>
              )}
            </span>
          </div>
        )}
      </div>

      {/* ── Price target range bar ── */}
      {pt && <PriceTargetBar targets={pt} currentPrice={currentPrice} />}

      {/* ── Recommendation breakdown ── */}
      {data.recommendationCounts && (
        <div className="ap-section">
          <div className="ap-subsection-title">Recommendation Breakdown</div>
          <RecBreakdownBar counts={data.recommendationCounts} />
        </div>
      )}

      {/* ── Recommendation trend ── */}
      {data.recommendationTrend && data.recommendationTrend.length > 1 && (
        <div className="ap-section">
          <div className="ap-subsection-title">Recommendation Trend</div>
          <RecTrendTable trend={data.recommendationTrend} />
        </div>
      )}

      {/* ── Upgrades & Downgrades ── */}
      {data.upgradesDowngrades && data.upgradesDowngrades.length > 0 && (
        <div className="ap-section">
          <div className="ap-subsection-title">Recent Upgrades & Downgrades</div>
          <DataTable
            columns={UD_COLUMNS}
            rows={data.upgradesDowngrades}
            defaultSortKey="date"
            defaultSortDir="desc"
            stickyHeader={false}
            emptyMessage="No recent upgrades or downgrades."
          />
        </div>
      )}

      {/* ── Earnings estimates ── */}
      <EstimatesSection
        title="Earnings Estimates (EPS)"
        estimates={data.earningsEstimate}
        isRevenue={false}
      />

      {/* ── Revenue estimates ── */}
      <EstimatesSection
        title="Revenue Estimates"
        estimates={data.revenueEstimate}
        isRevenue={true}
      />
    </div>
  );
}
