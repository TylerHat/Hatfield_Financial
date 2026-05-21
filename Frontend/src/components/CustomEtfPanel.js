import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { apiFetch } from '../api';
import { useAuth } from '../AuthContext';
import MarkovBacktestPanel from './MarkovBacktestPanel';
import './CustomEtfPanel.css';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler);

function fmtMoney(n) {
  if (n == null) return '—';
  return `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(n) {
  if (n == null) return '—';
  const sign = n > 0 ? '+' : '';
  return `${sign}${Number(n).toFixed(2)}%`;
}

function fmtDateTime(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

// ── Auto-rebalance schedule helpers ────────────────────────────────
// Mirrors the EventBridge Scheduler config: 9:30 AM America/New_York,
// MON-FRI. Computed entirely client-side; no backend round trip needed.

const ET_FMT = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  weekday: 'short', year: 'numeric', month: 'numeric', day: 'numeric',
  hour: 'numeric', minute: 'numeric', second: 'numeric', hour12: false,
});

function etParts(d) {
  const o = {};
  for (const p of ET_FMT.formatToParts(d)) o[p.type] = p.value;
  return o;
}

// Construct a real UTC Date for "9:30 AM ET on (year, month, day)".
// Tries both EDT (UTC-4) and EST (UTC-5) and returns whichever round-trips
// to 9:30 in ET wall time — handles DST transitions automatically.
function build930ET(year, month, day) {
  for (const utcHour of [13, 14]) {
    const cand = new Date(Date.UTC(year, month - 1, day, utcHour, 30, 0));
    const p = etParts(cand);
    if (parseInt(p.hour, 10) === 9 && parseInt(p.minute, 10) === 30) return cand;
  }
  return null;
}

function nextAutoRebalance() {
  const now = new Date();
  const today = etParts(now);
  let y = parseInt(today.year, 10);
  let m = parseInt(today.month, 10);
  let d = parseInt(today.day, 10);

  for (let i = 0; i < 7; i++) {
    const cand = build930ET(y, m, d);
    if (cand && cand > now) {
      const wd = etParts(cand).weekday;
      if (wd !== 'Sat' && wd !== 'Sun') return cand;
    }
    const next = new Date(Date.UTC(y, m - 1, d + 1));
    y = next.getUTCFullYear(); m = next.getUTCMonth() + 1; d = next.getUTCDate();
  }
  return null;
}

function fmtCountdown(ms) {
  if (ms <= 0) return 'imminent';
  const s = Math.floor(ms / 1000);
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  if (days > 0) return `${days}d ${hours}h ${mins}m`;
  if (hours > 0) return `${hours}h ${mins}m ${secs}s`;
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}

function NextRebalanceTimer() {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const next = useMemo(nextAutoRebalance, [Math.floor(now / 60000)]); // recompute each minute
  if (!next) return null;
  const remaining = next.getTime() - now;
  const whenET = next.toLocaleString(undefined, {
    timeZone: 'America/New_York',
    weekday: 'short', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });

  return (
    <span className="cetf-next-run" title={`Auto-rebalance fires at 9:30 AM ET, MON-FRI. Next: ${whenET} ET`}>
      <span className="cetf-next-run__dot" />
      Next auto-rebalance in <strong>{fmtCountdown(remaining)}</strong>
      <span className="cetf-next-run__when"> · {whenET} ET</span>
    </span>
  );
}

function ScoreBadge({ score }) {
  if (score == null) return <span className="cetf-score cetf-score--na">—</span>;
  const cls = score >= 70 ? 'cetf-score--green' : score >= 40 ? 'cetf-score--amber' : 'cetf-score--red';
  return <span className={`cetf-score ${cls}`}>{Math.round(score)}</span>;
}

export default function CustomEtfPanel({ onNavigateToStock }) {
  const { user } = useAuth();
  const isAdmin = !!user?.is_admin;
  const [summaries, setSummaries] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [flash, setFlash] = useState(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [detailView, setDetailView] = useState('live');   // 'live' | 'backtest' (markov only)

  // ── Load summary list (lightweight, drives the sidebar) ───────────
  const loadSummaries = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/custom-etf/summary?t=${Date.now()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to load strategies');
      setSummaries(data.strategies || []);
      setActiveId((curr) => curr || data.strategies?.[0]?.id || null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    loadSummaries();
  }, [loadSummaries]);

  // ── Load state for the active strategy ────────────────────────────
  const loadState = useCallback(async (id) => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/custom-etf/${id}/state?t=${Date.now()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to load state');
      setState(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadState(activeId);
    // Reset to Live whenever the active strategy changes — only markov-regime
    // exposes a Backtest sub-tab, so any other strategy should start on Live.
    setDetailView('live');
  }, [activeId, loadState]);

  // ── Manual rebalance (force=true skips cooldown) ──────────────────
  const handleRebalance = async (force = false) => {
    if (!activeId) return;
    setBusy(true);
    setError(null);
    setFlash(null);
    try {
      const res = await apiFetch(`/api/custom-etf/${activeId}/rebalance`, {
        method: 'POST',
        body: JSON.stringify({ force }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Rebalance failed');
      if (data.status === 'cooldown') {
        setFlash({ kind: 'info', text: data.message });
      } else if (data.status === 'no_data') {
        setFlash({ kind: 'error', text: data.message });
      } else {
        const s = data.actions || {};
        setFlash({
          kind: 'success',
          text: `Rebalanced — ${s.sells?.length || 0} sells, ${s.buys?.length || 0} buys, ${s.kept?.length || 0} held.`,
        });
        if (data.state) setState(data.state);
        loadSummaries();  // refresh sidebar stats
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleReset = async () => {
    if (!activeId) return;
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/custom-etf/${activeId}/reset`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Reset failed');
      setState(data.state);
      setFlash({ kind: 'success', text: 'Simulation reset to starting capital.' });
      setConfirmReset(false);
      loadSummaries();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  // ── Chart data ────────────────────────────────────────────────────
  const chartData = useMemo(() => {
    const series = state?.equitySeries || [];
    if (series.length === 0) return null;
    const labels = series.map((p) => new Date(p.recordedAt).toLocaleDateString(undefined, {
      month: 'short', day: 'numeric',
    }));
    const datasets = [
      {
        label: 'Portfolio',
        data: series.map((p) => p.totalValue),
        borderColor: '#2ea043',
        backgroundColor: 'rgba(46,160,67,0.12)',
        fill: true,
        pointRadius: 3,
        tension: 0.25,
      },
    ];
    if (series.some((p) => p.spyValue != null)) {
      datasets.push({
        label: 'SPY (same $100k)',
        data: series.map((p) => p.spyValue),
        borderColor: '#58a6ff',
        backgroundColor: 'transparent',
        borderDash: [6, 4],
        fill: false,
        pointRadius: 2,
        tension: 0.25,
      });
    }
    return { labels, datasets };
  }, [state]);

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: '#e6edf3' } },
      tooltip: {
        callbacks: {
          label: (ctx) => `${ctx.dataset.label}: ${fmtMoney(ctx.parsed.y)}`,
        },
      },
    },
    scales: {
      x: { ticks: { color: '#8b949e' }, grid: { color: '#21262d' } },
      y: {
        ticks: { color: '#8b949e', callback: (v) => `$${(v / 1000).toFixed(0)}k` },
        grid: { color: '#21262d' },
      },
    },
  };

  const cfg = state?.strategy;
  const port = state?.portfolio;
  const holdings = state?.holdings || [];
  const trades = state?.trades || [];

  return (
    <div className="cetf-panel">
      <div className="cetf-panel__header">
        <h2>Custom ETF Simulator</h2>
        <p className="cetf-panel__subtitle">
          Live paper-trading sandbox. Each strategy holds up to 10 positions, rebalances when the
          Recommendations universe refreshes (24h cooldown), and is benchmarked against SPY.
        </p>
      </div>

      <div className="cetf-layout">
        {/* ── Left rail: every registered strategy with live stats ── */}
        <aside className="cetf-rail">
          <div className="cetf-rail__header">
            Strategies <span className="cetf-rail__count">{summaries.length}</span>
          </div>
          {summaries.length === 0 && (
            <div className="cetf-rail__empty">No strategies registered.</div>
          )}
          {summaries.map((s) => {
            const ret = s.totalReturnPct;
            const retCls = ret > 0 ? 'pos' : ret < 0 ? 'neg' : '';
            const vsSpy = s.vsSpyPct;
            const vsSpyCls = vsSpy == null ? '' : vsSpy > 0 ? 'bull' : vsSpy < 0 ? 'bear' : '';
            return (
              <button
                key={s.id}
                className={`cetf-rail__item ${s.id === activeId ? 'active' : ''}`}
                onClick={() => setActiveId(s.id)}
                title={s.description}
              >
                <div className="cetf-rail__name">{s.name}</div>
                <div className="cetf-rail__stats">
                  <span className="cetf-rail__value">{fmtMoney(s.totalValue)}</span>
                  <span className={`cetf-rail__return ${retCls}`}>{fmtPct(ret)}</span>
                </div>
                {vsSpy != null && (
                  <div className={`cetf-rail__vs-spy ${vsSpyCls}`}>
                    vs SPY {fmtPct(vsSpy)}
                  </div>
                )}
                <div className="cetf-rail__meta">
                  {s.holdingsCount}/{s.maxPositions} held
                  {s.lastRebalanceAt && ' · ' + new Date(s.lastRebalanceAt).toLocaleDateString()}
                </div>
              </button>
            );
          })}
        </aside>

        {/* ── Detail pane for active strategy ── */}
        <div className="cetf-detail">
          {activeId === 'markov-regime' && (
            <nav className="cetf-detail-tabs">
              <button
                type="button"
                className={`cetf-detail-tab ${detailView === 'live' ? 'active' : ''}`}
                onClick={() => setDetailView('live')}
              >
                Live Simulation
              </button>
              <button
                type="button"
                className={`cetf-detail-tab ${detailView === 'backtest' ? 'active' : ''}`}
                onClick={() => setDetailView('backtest')}
              >
                Backtest
              </button>
            </nav>
          )}

          {detailView === 'backtest' && activeId === 'markov-regime' && (
            <MarkovBacktestPanel />
          )}

          {detailView === 'live' && flash && <div className={`cetf-flash cetf-flash--${flash.kind}`}>{flash.text}</div>}
          {detailView === 'live' && error && <div className="cetf-flash cetf-flash--error">{error}</div>}

          {detailView === 'live' && loading && <div className="cetf-loading">Loading simulation…</div>}

          {detailView === 'live' && !loading && state && (
            <>
          <div className="cetf-summary-row">
            <SummaryCard label="Total Value" value={fmtMoney(port.totalValue)} />
            <SummaryCard label="Cash" value={fmtMoney(port.cash)} sub={fmtMoney(port.positionsValue) + ' invested'} />
            <SummaryCard
              label="Total Return"
              value={fmtPct(port.totalReturnPct)}
              accent={port.totalReturnPct >= 0 ? 'pos' : 'neg'}
            />
            <SummaryCard label="Holdings" value={`${holdings.length} / ${cfg.maxPositions}`} />
            <SummaryCard
              label="Last Rebalance"
              value={fmtDateTime(port.lastRebalanceAt)}
              sub={`Started ${fmtDateTime(port.createdAt)}`}
            />
          </div>

          <div className="cetf-actions">
            {isAdmin && (
              <>
                <button className="cetf-btn" onClick={() => handleRebalance(false)} disabled={busy}>
                  Run Rebalance
                </button>
                <button className="cetf-btn cetf-btn--ghost" onClick={() => handleRebalance(true)} disabled={busy}>
                  Force Rebalance (skip cooldown)
                </button>
                <button className="cetf-btn cetf-btn--danger" onClick={() => setConfirmReset(true)} disabled={busy}>
                  Reset Simulation
                </button>
              </>
            )}
            <span className="cetf-meta">
              Buy ≥ {cfg.buyThreshold} · Sell ≤ {cfg.sellThreshold} · Slippage {cfg.slippageBps} bps
            </span>
          </div>

          <NextRebalanceTimer />


          {/* ── Equity Curve ───────────────────────────────────────── */}
          <section className="cetf-section">
            <h3>Equity Curve</h3>
            {chartData ? (
              <div className="cetf-chart-wrap">
                <Line data={chartData} options={chartOptions} />
              </div>
            ) : (
              <div className="cetf-empty">No snapshots yet — run a rebalance to record the first data point.</div>
            )}
          </section>

          {/* ── Holdings ───────────────────────────────────────────── */}
          <section className="cetf-section">
            <h3>Current Holdings ({holdings.length})</h3>
            {holdings.length === 0 ? (
              <div className="cetf-empty">No open positions.</div>
            ) : (
              <table className="cetf-table cetf-table--clickable">
                <thead>
                  <tr>
                    <th>Ticker</th>
                    <th className="num">Shares</th>
                    <th className="num">Avg Cost</th>
                    <th className="num">Current</th>
                    <th className="num">Market Value</th>
                    <th className="num">P/L</th>
                    <th className="num">P/L %</th>
                    <th className="num">Entry Score</th>
                    <th className="num">Current Score</th>
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((h) => (
                    <tr
                      key={h.ticker}
                      onDoubleClick={() => onNavigateToStock && onNavigateToStock(h.ticker)}
                      title="Double-click to view in Stock Analysis"
                    >
                      <td>
                        <strong>{h.ticker}</strong>
                        {h.name && <span className="cetf-name">{h.name.length > 24 ? h.name.slice(0, 24) + '…' : h.name}</span>}
                      </td>
                      <td className="num">{h.shares.toFixed(3)}</td>
                      <td className="num">{fmtMoney(h.avgCost)}</td>
                      <td className="num">{fmtMoney(h.currentPrice)}</td>
                      <td className="num">{fmtMoney(h.marketValue)}</td>
                      <td className={`num ${h.unrealizedPnl >= 0 ? 'pos' : 'neg'}`}>{fmtMoney(h.unrealizedPnl)}</td>
                      <td className={`num ${h.unrealizedPnlPct >= 0 ? 'pos' : 'neg'}`}>{fmtPct(h.unrealizedPnlPct)}</td>
                      <td className="num"><ScoreBadge score={h.entryScore} /></td>
                      <td className="num"><ScoreBadge score={h.currentScore} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {/* ── Trade History ──────────────────────────────────────── */}
          <section className="cetf-section">
            <h3>Trade History ({trades.length})</h3>
            {trades.length === 0 ? (
              <div className="cetf-empty">No trades recorded yet.</div>
            ) : (
              <div className="cetf-trades-scroll">
                <table className="cetf-table">
                  <thead>
                    <tr>
                      <th>When</th>
                      <th>Action</th>
                      <th>Ticker</th>
                      <th className="num">Shares</th>
                      <th className="num">Price</th>
                      <th className="num">Value</th>
                      <th className="num">Score</th>
                      <th>Reason</th>
                      <th className="num">Cash After</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((t, i) => (
                      <tr key={i}>
                        <td>{fmtDateTime(t.executedAt)}</td>
                        <td>
                          <span className={`cetf-action cetf-action--${t.action.toLowerCase()}`}>{t.action}</span>
                        </td>
                        <td><strong>{t.ticker}</strong></td>
                        <td className="num">{t.shares.toFixed(3)}</td>
                        <td className="num">{fmtMoney(t.price)}</td>
                        <td className="num">{fmtMoney(t.value)}</td>
                        <td className="num"><ScoreBadge score={t.score} /></td>
                        <td><span className="cetf-reason">{t.reason || '—'}</span></td>
                        <td className="num">{fmtMoney(t.cashAfter)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
            </>
          )}
        </div>
      </div>

      {confirmReset && (
        <div className="cetf-modal-backdrop" onClick={() => setConfirmReset(false)}>
          <div className="cetf-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Reset simulation?</h3>
            <p>
              This wipes all positions, trades, and equity history for
              <strong> {cfg?.name || 'this strategy'} </strong>
              and restores cash to {fmtMoney(cfg?.startingCapital)}. This cannot be undone.
            </p>
            <div className="cetf-modal__actions">
              <button className="cetf-btn cetf-btn--ghost" onClick={() => setConfirmReset(false)}>Cancel</button>
              <button className="cetf-btn cetf-btn--danger" onClick={handleReset} disabled={busy}>
                Reset
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryCard({ label, value, sub, accent }) {
  return (
    <div className="cetf-card">
      <div className="cetf-card__label">{label}</div>
      <div className={`cetf-card__value ${accent === 'pos' ? 'pos' : accent === 'neg' ? 'neg' : ''}`}>{value}</div>
      {sub && <div className="cetf-card__sub">{sub}</div>}
    </div>
  );
}
