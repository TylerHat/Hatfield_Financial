import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Line } from 'react-chartjs-2';
import { apiFetch } from '../api';

const POLL_MS = 2000;

function fmtMoney(n) {
  if (n == null) return '—';
  const num = Number(n);
  return num.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}
function fmtMoneyFull(n) {
  if (n == null) return '—';
  return Number(n).toLocaleString(undefined, { style: 'currency', currency: 'USD', minimumFractionDigits: 2 });
}
function fmtPct(n, sign = false) {
  if (n == null) return '—';
  const s = sign && n > 0 ? '+' : '';
  return `${s}${Number(n).toFixed(2)}%`;
}

export default function MarkovBacktestPanel() {
  const [years, setYears] = useState(1);
  const [cadence, setCadence] = useState('weekly');
  const [jobId, setJobId] = useState(null);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  // Poll the job endpoint until status is done or error.
  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    async function poll() {
      try {
        // Cache-bust: apiFetch caches GET responses for 2 min and the polling
        // endpoint returns 200 with changing data — without ?t=... every poll
        // after the first would return stale cached progress forever.
        const res = await apiFetch(`/api/custom-etf/backtest/${jobId}`, { skipCache: true });
        const data = await res.json();
        if (cancelled) return;
        if (!res.ok) {
          setError(data.error || `Polling failed (${res.status})`);
          return;
        }
        setJob(data);
        if (data.status === 'done' || data.status === 'error') {
          return; // stop polling
        }
        pollRef.current = setTimeout(poll, POLL_MS);
      } catch (e) {
        if (!cancelled) setError(e.message);
      }
    }

    poll();
    return () => {
      cancelled = true;
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [jobId]);

  async function handleRun() {
    setError(null);
    setJob(null);
    try {
      const res = await apiFetch('/api/custom-etf/markov-regime/backtest', {
        method: 'POST',
        body: JSON.stringify({ years, cadence }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || `Failed to start (${res.status})`);
        return;
      }
      setJobId(data.jobId);
    } catch (e) {
      setError(e.message);
    }
  }

  const isRunning = job && (job.status === 'pending' || job.status === 'running');
  const isDone = job && job.status === 'done';
  const isError = job && job.status === 'error';
  const result = isDone ? job.result : null;
  const s = result?.summary;

  // Equity curve chart
  const chartData = useMemo(() => {
    if (!result?.equityCurve?.length) return null;
    const startingCapital = result.params.startingCapital;
    const hasSpy = result.equityCurve.some((p) => p.spyValue != null);
    const datasets = [
      {
        label: 'Markov Portfolio',
        data: result.equityCurve.map((p) => p.value),
        borderColor: '#3FDE7E',
        backgroundColor: 'rgba(63,222,126,0.10)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.15,
        fill: true,
      },
    ];
    if (hasSpy) {
      datasets.push({
        label: 'SPY (benchmark)',
        // chart.js skips null values when spanGaps is false (default)
        data: result.equityCurve.map((p) => p.spyValue),
        borderColor: '#58a6ff',
        backgroundColor: 'rgba(88,166,255,0.06)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.15,
        fill: false,
      });
    }
    datasets.push({
      label: 'Starting Capital',
      data: result.equityCurve.map(() => startingCapital),
      borderColor: '#30363d',
      borderWidth: 1,
      borderDash: [6, 4],
      pointRadius: 0,
      fill: false,
    });
    return { labels: result.equityCurve.map((p) => p.date), datasets };
  }, [result]);

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: '#8b949e', boxWidth: 14, font: { size: 11 } } },
      tooltip: {
        backgroundColor: '#161b22', borderColor: '#30363d', borderWidth: 1,
        titleColor: '#e6edf3', bodyColor: '#8b949e',
        callbacks: { label: (ctx) => ` ${fmtMoneyFull(ctx.parsed.y)}` },
      },
    },
    scales: {
      x: { ticks: { color: '#8b949e', font: { size: 10 }, maxTicksLimit: 10, maxRotation: 0 }, grid: { color: '#21262d' } },
      y: { ticks: { color: '#8b949e', font: { size: 10 }, callback: (v) => fmtMoney(v) }, grid: { color: '#21262d' } },
    },
  };

  return (
    <div className="markov-bt">
      <div className="markov-bt__intro">
        <h3 className="markov-bt__title">Markov Regime — Portfolio Backtest</h3>
        <p className="markov-bt__desc">
          Walks forward across the S&amp;P 500, rebalancing a $100,000 portfolio on
          the selected cadence. At each rebalance date, picks the top 10 stocks
          ranked by 5-day bull-probability (computed from each ticker's Markov
          transition matrix using only data through that date — no look-ahead).
          Position size scales with conviction; cash is held when fewer than 10
          tickers qualify.
        </p>
      </div>

      <div className="markov-bt__controls">
        <div className="markov-bt__control-group">
          <span className="markov-bt__control-label">Window</span>
          <div className="markov-bt__pill-group">
            {[1, 3].map((y) => (
              <button
                key={y}
                type="button"
                className={`markov-bt__pill ${years === y ? 'active' : ''}`}
                onClick={() => setYears(y)}
                disabled={isRunning}
              >
                {y} year{y > 1 ? 's' : ''}
              </button>
            ))}
          </div>
        </div>
        <div className="markov-bt__control-group">
          <span className="markov-bt__control-label">Cadence</span>
          <div className="markov-bt__pill-group">
            {[{ k: 'weekly', l: 'Weekly' }, { k: 'daily', l: 'Daily' }].map(({ k, l }) => (
              <button
                key={k}
                type="button"
                className={`markov-bt__pill ${cadence === k ? 'active' : ''}`}
                onClick={() => setCadence(k)}
                disabled={isRunning}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
        <button
          className="markov-bt__run-btn"
          onClick={handleRun}
          disabled={isRunning}
        >
          {isRunning ? 'Running…' : 'Run Backtest'}
        </button>
      </div>

      <div className="markov-bt__caveat">
        <strong>Survivorship-bias note:</strong> uses today's S&amp;P 500 constituents.
        Delisted names won't appear in older windows — measured returns may
        be modestly inflated vs. an unbiased universe.
      </div>

      {error && <div className="markov-bt__error">{error}</div>}

      {isRunning && (
        <div className="markov-bt__progress">
          <div className="markov-bt__progress-bar">
            <div
              className="markov-bt__progress-fill"
              style={{ width: `${job?.progress || 0}%` }}
            />
          </div>
          <div className="markov-bt__progress-msg">
            {(job?.progress || 0).toFixed(0)}% · {job?.message || 'Starting…'}
          </div>
          <div className="markov-bt__progress-hint">
            Cold-cache runs can take 2–5 minutes while S&amp;P 500 OHLC downloads.
            Subsequent runs are much faster.
          </div>
        </div>
      )}

      {isError && (
        <div className="markov-bt__error">Backtest failed: {job.error}</div>
      )}

      {isDone && s && (
        <>
          <section className="markov-bt__section">
            <h4 className="markov-bt__section-title">Performance Summary</h4>
            <div className="markov-bt__stat-grid">
              <Stat label="Total Return" value={fmtPct(s.totalReturn, true)} accent={s.totalReturn >= 0 ? 'pos' : 'neg'}
                    sub={`${s.totalReturnDollar >= 0 ? '+' : ''}${fmtMoneyFull(s.totalReturnDollar)}`} />
              <Stat label="vs SPY"
                    value={s.vsSpy == null ? '—' : fmtPct(s.vsSpy, true)}
                    accent={s.vsSpy == null ? '' : s.vsSpy >= 0 ? 'pos' : 'neg'}
                    sub={s.spyReturn == null ? 'SPY benchmark unavailable' : `SPY: ${fmtPct(s.spyReturn, true)}`} />
              <Stat label="Final Value" value={fmtMoneyFull(s.finalValue)} sub={`Started ${fmtMoneyFull(s.startingCapital)}`} />
              <Stat label="Win Rate" value={`${s.winRate.toFixed(1)}%`}
                    accent={s.winRate >= 50 ? 'pos' : 'neg'}
                    sub={`${s.numWins}W / ${s.numLosses}L · ${s.numTrades} closed trades`} />
              <Stat label="Win/Loss Ratio" value={s.winLossRatio == null ? '—' : `${s.winLossRatio.toFixed(2)}×`}
                    accent={s.winLossRatio == null ? '' : s.winLossRatio >= 1 ? 'pos' : 'neg'}
                    sub={`Avg win ${fmtPct(s.avgWinPct, true)} / loss ${fmtPct(s.avgLossPct, true)}`} />
              <Stat label="Max Drawdown" value={fmtPct(s.maxDrawdown)}
                    accent={s.maxDrawdown < -20 ? 'neg' : ''} />
              <Stat label="Best / Worst Trade" value={`${fmtPct(s.bestTrade, true)} / ${fmtPct(s.worstTrade, true)}`} />
              <Stat label="Profit Factor" value={s.profitFactor == null ? '—' : `${s.profitFactor.toFixed(2)}×`}
                    sub="Σ wins / |Σ losses|" />
              <Stat label="Rebalances" value={`${s.rebalances}`}
                    sub={`${result.params.cadence}, ${result.params.years}y · ${s.tickersAnalyzed} tickers`} />
            </div>
          </section>

          <section className="markov-bt__section">
            <h4 className="markov-bt__section-title">Equity Curve</h4>
            <div className="markov-bt__chart-wrap">
              {chartData ? <Line data={chartData} options={chartOptions} /> : <div className="markov-bt__empty">No equity data.</div>}
            </div>
          </section>

          {result.openPositions?.length > 0 && (
            <section className="markov-bt__section">
              <h4 className="markov-bt__section-title">Open Positions at End ({result.openPositions.length})</h4>
              <div className="markov-bt__table-scroll">
                <table className="markov-bt__table">
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th className="num">Shares</th>
                      <th className="num">Avg Cost</th>
                      <th className="num">Last Price</th>
                      <th className="num">Market Value</th>
                      <th className="num">Unrealized P/L</th>
                      <th className="num">Unrealized %</th>
                      <th>Entry Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.openPositions.map((p) => (
                      <tr key={p.ticker}>
                        <td><strong>{p.ticker}</strong></td>
                        <td className="num">{p.shares.toFixed(2)}</td>
                        <td className="num">{fmtMoneyFull(p.avgCost)}</td>
                        <td className="num">{fmtMoneyFull(p.currentPrice)}</td>
                        <td className="num">{fmtMoneyFull(p.marketValue)}</td>
                        <td className={`num ${p.unrealizedPnl >= 0 ? 'pos' : 'neg'}`}>
                          {p.unrealizedPnl >= 0 ? '+' : ''}{fmtMoneyFull(p.unrealizedPnl)}
                        </td>
                        <td className={`num ${p.unrealizedPnlPct >= 0 ? 'pos' : 'neg'}`}>
                          {fmtPct(p.unrealizedPnlPct, true)}
                        </td>
                        <td>{p.entryDate}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="markov-bt__section">
            <h4 className="markov-bt__section-title">Trade Log ({result.trades.length})</h4>
            <div className="markov-bt__table-scroll markov-bt__table-scroll--tall">
              <table className="markov-bt__table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Ticker</th>
                    <th>Action</th>
                    <th className="num">Shares</th>
                    <th className="num">Price</th>
                    <th className="num">Value</th>
                    <th className="num">Entry Date</th>
                    <th className="num">Entry Price</th>
                    <th className="num">P/L</th>
                    <th className="num">P/L %</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((t, i) => (
                    <tr key={`${t.date}-${t.ticker}-${t.action}-${i}`} className={t.action === 'BUY' ? 'buy-row' : t.pnl > 0 ? 'win-row' : t.pnl < 0 ? 'loss-row' : ''}>
                      <td>{t.date}</td>
                      <td><strong>{t.ticker}</strong></td>
                      <td>
                        <span className={`markov-bt__badge markov-bt__badge--${t.action.toLowerCase()}`}>
                          {t.action}
                        </span>
                      </td>
                      <td className="num">{t.shares.toFixed(2)}</td>
                      <td className="num">{fmtMoneyFull(t.price)}</td>
                      <td className="num">{fmtMoneyFull(t.value)}</td>
                      <td className="num">{t.entryDate || '—'}</td>
                      <td className="num">{t.entryPrice ? fmtMoneyFull(t.entryPrice) : '—'}</td>
                      <td className={`num ${t.pnl == null ? '' : t.pnl >= 0 ? 'pos' : 'neg'}`}>
                        {t.pnl == null ? '—' : `${t.pnl >= 0 ? '+' : ''}${fmtMoneyFull(t.pnl)}`}
                      </td>
                      <td className={`num ${t.pnlPct == null ? '' : t.pnlPct >= 0 ? 'pos' : 'neg'}`}>
                        {t.pnlPct == null ? '—' : fmtPct(t.pnlPct, true)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <div className="markov-bt__elapsed">Completed in {result.elapsedSeconds}s</div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, sub, accent }) {
  return (
    <div className={`markov-bt__stat ${accent ? `markov-bt__stat--${accent}` : ''}`}>
      <div className="markov-bt__stat-label">{label}</div>
      <div className="markov-bt__stat-value">{value}</div>
      {sub && <div className="markov-bt__stat-sub">{sub}</div>}
    </div>
  );
}
