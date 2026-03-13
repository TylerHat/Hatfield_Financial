import React, { useEffect, useRef, useState } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import { Line, Bar } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend
);

const API_BASE = 'http://localhost:5000';

// Build an array the same length as `dates` with the signal price at matching
// indices and null everywhere else.
function buildSignalArray(dates, signals, type) {
  const lookup = {};
  signals.forEach((s) => {
    if (s.type === type) lookup[s.date] = s.price;
  });
  return dates.map((d) => (lookup[d] !== undefined ? lookup[d] : null));
}

export default function StockChart({ ticker, strategy, startDate, endDate, onSignals }) {
  const [stockData, setStockData] = useState(null);
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [strategyLoading, setStrategyLoading] = useState(false);
  const [error, setError] = useState(null);

  // Keep signal reasons accessible inside Chart.js tooltip callbacks
  const signalReasonRef = useRef({});

  // Fetch price data whenever ticker or date range changes
  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    setStockData(null);
    setSignals([]);

    const params = new URLSearchParams({ start: startDate, end: endDate });
    fetch(`${API_BASE}/api/stock/${ticker}?${params}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.error) {
          setError(data.error);
        } else {
          setStockData(data);
        }
        setLoading(false);
      })
      .catch(() => {
        setError('Could not connect to the backend. Make sure the Flask server is running on port 5000.');
        setLoading(false);
      });
  }, [ticker, startDate, endDate]);

  // Fetch strategy signals whenever ticker, strategy, or date range changes
  useEffect(() => {
    if (!ticker || !stockData || strategy === 'none') {
      setSignals([]);
      signalReasonRef.current = {};
      if (onSignals) onSignals([]);
      return;
    }

    setStrategyLoading(true);

    const params = new URLSearchParams({ start: startDate, end: endDate });
    fetch(`${API_BASE}/api/strategy/${strategy}/${ticker}?${params}`)
      .then((res) => res.json())
      .then((data) => {
        const sigs = data.signals || [];
        setSignals(sigs);

        // Lift signals to parent (App.js) so other tabs can consume them.
        if (onSignals) onSignals(sigs);

        // Build date → {reason, type, conviction, score} lookup for tooltips
        const lookup = {};
        sigs.forEach((s) => {
          lookup[s.date] = { reason: s.reason, type: s.type, conviction: s.conviction, score: s.score };
        });
        signalReasonRef.current = lookup;
        setStrategyLoading(false);
      })
      .catch(() => {
        setSignals([]);
        setStrategyLoading(false);
      });
  }, [ticker, strategy, startDate, endDate, stockData]);

  if (loading) {
    return <div className="chart-status">Loading {ticker}…</div>;
  }
  if (error) {
    return <div className="chart-status error">{error}</div>;
  }
  if (!stockData) return null;

  const { dates, close, volume, ma20, ma50, macd, macd_signal, macd_hist, rsi } = stockData;

  // Strategies where RSI context panel adds value
  const RSI_PANEL_STRATEGIES = new Set(['bollinger-bands', 'mean-reversion', 'rsi', 'macd-crossover']);
  const showRsiPanel = RSI_PANEL_STRATEGIES.has(strategy);

  const buyData = buildSignalArray(dates, signals, 'BUY');
  const sellData = buildSignalArray(dates, signals, 'SELL');

  // ── Price chart ──────────────────────────────────────────────────────────────
  const priceData = {
    labels: dates,
    datasets: [
      {
        label: `${ticker} Close`,
        data: close,
        borderColor: '#58a6ff',
        backgroundColor: 'rgba(88,166,255,0.07)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.15,
        fill: false,
        order: 3,
      },
      {
        label: 'MA 20',
        data: ma20,
        borderColor: '#f0883e',
        borderWidth: 1.5,
        borderDash: [4, 3],
        pointRadius: 0,
        tension: 0.15,
        fill: false,
        order: 2,
      },
      {
        label: 'MA 50',
        data: ma50,
        borderColor: '#bc8cff',
        borderWidth: 1.5,
        borderDash: [8, 4],
        pointRadius: 0,
        tension: 0.15,
        fill: false,
        order: 1,
      },
      {
        label: 'BUY',
        data: buyData,
        showLine: false,
        fill: false,
        pointStyle: 'triangle',
        pointRotation: 0,
        pointRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 11 : 0),
        pointHoverRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 13 : 0),
        pointBackgroundColor: '#3fb950',
        pointBorderColor: '#1a7f37',
        pointBorderWidth: 1.5,
        order: 0,
      },
      {
        label: 'SELL',
        data: sellData,
        showLine: false,
        fill: false,
        pointStyle: 'triangle',
        pointRotation: 180,
        pointRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 11 : 0),
        pointHoverRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 13 : 0),
        pointBackgroundColor: '#f85149',
        pointBorderColor: '#b62324',
        pointBorderWidth: 1.5,
        order: 0,
      },
    ],
  };

  const priceOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        position: 'top',
        labels: {
          color: '#8b949e',
          usePointStyle: true,
          filter: (item) => {
            if (strategy === 'none' && (item.text === 'BUY' || item.text === 'SELL')) {
              return false;
            }
            return true;
          },
        },
      },
      title: {
        display: true,
        text: `${ticker} — ${startDate} to ${endDate}`,
        color: '#e6edf3',
        font: { size: 15, weight: '600' },
        padding: { bottom: 12 },
      },
      tooltip: {
        backgroundColor: '#161b22',
        borderColor: '#30363d',
        borderWidth: 1,
        titleColor: '#e6edf3',
        bodyColor: '#8b949e',
        callbacks: {
          label: (ctx) => {
            if (ctx.dataset.label === 'BUY' || ctx.dataset.label === 'SELL') {
              const val = ctx.dataset.data[ctx.dataIndex];
              if (val === null) return null;
              return `${ctx.dataset.label}: $${val.toFixed(2)}`;
            }
            if (ctx.parsed.y === null) return null;
            return `${ctx.dataset.label}: $${ctx.parsed.y.toFixed(2)}`;
          },
          afterBody: (items) => {
            const date = items[0]?.label;
            const info = signalReasonRef.current[date];
            if (!info) return [];
            const lines = ['', `Signal: ${info.type}`, `Reason: ${info.reason}`];
            if (info.conviction) lines.push(`Conviction: ${info.conviction} (Score: ${info.score})`);
            return lines;
          },
        },
      },
    },
    scales: {
      x: {
        ticks: { color: '#8b949e', maxTicksLimit: 8, maxRotation: 0 },
        grid: { color: '#21262d', display: true },
      },
      y: {
        position: 'left',
        ticks: {
          color: '#8b949e',
          callback: (v) => `$${v.toFixed(0)}`,
        },
        grid: { color: '#21262d' },
      },
    },
  };

  // ── Volume chart ─────────────────────────────────────────────────────────────
  const volumeData = {
    labels: dates,
    datasets: [
      {
        label: 'Volume',
        data: volume,
        backgroundColor: 'rgba(88,166,255,0.35)',
        borderColor: 'rgba(88,166,255,0.6)',
        borderWidth: 1,
        borderRadius: 1,
      },
    ],
  };

  const volumeOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: { display: false },
      title: {
        display: true,
        text: 'Volume',
        color: '#8b949e',
        font: { size: 12 },
        padding: { bottom: 6 },
      },
      tooltip: {
        backgroundColor: '#161b22',
        borderColor: '#30363d',
        borderWidth: 1,
        titleColor: '#e6edf3',
        bodyColor: '#8b949e',
        callbacks: {
          label: (ctx) => {
            const v = ctx.parsed.y;
            if (v >= 1e9) return `Volume: ${(v / 1e9).toFixed(2)}B`;
            if (v >= 1e6) return `Volume: ${(v / 1e6).toFixed(2)}M`;
            if (v >= 1e3) return `Volume: ${(v / 1e3).toFixed(0)}K`;
            return `Volume: ${v}`;
          },
        },
      },
    },
    scales: {
      x: {
        ticks: { color: '#8b949e', maxTicksLimit: 8, maxRotation: 0 },
        grid: { display: false },
      },
      y: {
        ticks: {
          color: '#8b949e',
          callback: (v) => {
            if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
            if (v >= 1e6) return `${(v / 1e6).toFixed(0)}M`;
            if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
            return v;
          },
        },
        grid: { color: '#21262d' },
      },
    },
  };

  // ── MACD chart ───────────────────────────────────────────────────────────────
  const macdData = {
    labels: dates,
    datasets: [
      {
        type: 'bar',
        label: 'Histogram',
        data: macd_hist,
        backgroundColor: (macd_hist || []).map((v) => (v >= 0 ? 'rgba(63,185,80,0.5)' : 'rgba(248,81,73,0.5)')),
        borderColor: (macd_hist || []).map((v) => (v >= 0 ? '#3fb950' : '#f85149')),
        borderWidth: 1,
        order: 2,
      },
      {
        type: 'line',
        label: 'MACD',
        data: macd,
        borderColor: '#58a6ff',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.15,
        fill: false,
        order: 1,
      },
      {
        type: 'line',
        label: 'Signal',
        data: macd_signal,
        borderColor: '#f0883e',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.15,
        fill: false,
        order: 0,
      },
    ],
  };

  const macdOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: {
        display: true,
        position: 'top',
        labels: { color: '#8b949e', usePointStyle: true, boxWidth: 8, font: { size: 11 } },
      },
      title: {
        display: true,
        text: 'MACD (12, 26, 9)',
        color: '#8b949e',
        font: { size: 12 },
        padding: { bottom: 6 },
      },
      tooltip: {
        backgroundColor: '#161b22',
        borderColor: '#30363d',
        borderWidth: 1,
        titleColor: '#e6edf3',
        bodyColor: '#8b949e',
        callbacks: {
          label: (ctx) => {
            if (ctx.parsed.y === null) return null;
            return `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(4)}`;
          },
        },
      },
    },
    scales: {
      x: {
        ticks: { color: '#8b949e', maxTicksLimit: 8, maxRotation: 0 },
        grid: { display: false },
      },
      y: {
        ticks: { color: '#8b949e', callback: (v) => v.toFixed(2) },
        grid: { color: '#21262d' },
      },
    },
  };

  // ── RSI context panel ────────────────────────────────────────────────────────
  const flat70 = dates.map(() => 70);
  const flat30 = dates.map(() => 30);

  const rsiData = {
    labels: dates,
    datasets: [
      {
        label: 'RSI (14)',
        data: rsi,
        borderColor: '#e6edf3',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.15,
        fill: false,
        order: 0,
      },
      {
        label: 'Overbought (70)',
        data: flat70,
        borderColor: 'rgba(248,81,73,0.6)',
        borderWidth: 1,
        borderDash: [4, 3],
        pointRadius: 0,
        fill: false,
        order: 1,
      },
      {
        label: 'Oversold (30)',
        data: flat30,
        borderColor: 'rgba(63,185,80,0.6)',
        borderWidth: 1,
        borderDash: [4, 3],
        pointRadius: 0,
        fill: false,
        order: 1,
      },
    ],
  };

  const rsiOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: {
        display: true,
        position: 'top',
        labels: { color: '#8b949e', usePointStyle: true, boxWidth: 8, font: { size: 11 } },
      },
      title: {
        display: true,
        text: 'RSI (14)  ·  Overbought > 70  ·  Oversold < 30',
        color: '#8b949e',
        font: { size: 12 },
        padding: { bottom: 6 },
      },
      tooltip: {
        backgroundColor: '#161b22',
        borderColor: '#30363d',
        borderWidth: 1,
        titleColor: '#e6edf3',
        bodyColor: '#8b949e',
        callbacks: {
          label: (ctx) => {
            if (ctx.parsed.y === null) return null;
            return `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}`;
          },
        },
      },
    },
    scales: {
      x: {
        ticks: { color: '#8b949e', maxTicksLimit: 8, maxRotation: 0 },
        grid: { display: false },
      },
      y: {
        min: 0,
        max: 100,
        ticks: {
          color: '#8b949e',
          callback: (v) => v.toFixed(0),
          stepSize: 25,
        },
        grid: { color: '#21262d' },
      },
    },
  };

  const buySignals = signals.filter((s) => s.type === 'BUY');
  const sellSignals = signals.filter((s) => s.type === 'SELL');

  return (
    <div className="chart-container">
      {strategyLoading && (
        <div className="strategy-loading">Loading strategy signals…</div>
      )}

      <div className="price-chart">
        <Line data={priceData} options={priceOptions} />
      </div>

      <div className="volume-chart">
        <Bar data={volumeData} options={volumeOptions} />
      </div>

      <div className="macd-chart">
        <Bar data={macdData} options={macdOptions} />
      </div>

      {showRsiPanel && (
        <div className="rsi-chart">
          <Line data={rsiData} options={rsiOptions} />
        </div>
      )}

      {signals.length > 0 && (
        <div className="signals-summary">
          <h3>
            Strategy Signals — {signals.length} total &nbsp;
            <span className="badge buy">{buySignals.length} BUY</span>
            <span className="badge sell">{sellSignals.length} SELL</span>
          </h3>
          <div className="signals-table-wrapper">
            <table className="signals-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Price</th>
                  <th>Signal</th>
                  <th>Conviction</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {[...signals].reverse().map((s, i) => (
                  <tr key={i} className={s.type === 'BUY' ? 'buy-row' : 'sell-row'}>
                    <td>{s.date}</td>
                    <td>${s.price.toFixed(2)}</td>
                    <td>
                      <span className={`signal-badge ${s.type.toLowerCase()}`}>
                        {s.type}
                      </span>
                    </td>
                    <td>
                      <span className={`conviction-badge conviction-${(s.conviction || 'low').toLowerCase()}`}>
                        {s.conviction || 'N/A'} {s.score !== undefined ? `(${s.score})` : ''}
                      </span>
                    </td>
                    <td>{s.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {strategy !== 'none' && !strategyLoading && signals.length === 0 && (
        <div className="no-signals">
          No signals generated for {ticker} with this strategy from {startDate} to {endDate}.
        </div>
      )}
    </div>
  );
}
