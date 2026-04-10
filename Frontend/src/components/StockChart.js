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
import { apiFetch } from '../api';

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
  const [strategyError, setStrategyError] = useState(null);

  // Track which chart is expanded (null = none)
  const [expandedChart, setExpandedChart] = useState(null);
  // Track which chart info popover is open
  const [infoOpen, setInfoOpen] = useState(null);

  // Keep signal reasons accessible inside Chart.js tooltip callbacks
  const signalReasonRef = useRef({});

  // Fetch price data whenever ticker or date range changes
  useEffect(() => {
    if (!ticker) return;
    console.log('[StockChart] fetching price data', { ticker, startDate, endDate });
    setLoading(true);
    setError(null);
    setStockData(null);
    setSignals([]);

    const params = new URLSearchParams({ start: startDate, end: endDate });
    apiFetch(`/api/stock/${ticker}?${params}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.error) {
          console.warn('[StockChart] price data error:', data.error);
          setError(data.error);
        } else {
          console.log(`[StockChart] loaded ${data.dates?.length || 0} price points for ${ticker}`);
          setStockData(data);
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error('[StockChart] price fetch failed:', err);
        setError('Could not connect to the backend. Make sure the Flask server is running on port 5000.');
        setLoading(false);
      });
  }, [ticker, startDate, endDate]);

  // Fetch strategy signals whenever ticker, strategy, or date range changes
  useEffect(() => {
    if (!ticker || !stockData || strategy === 'none') {
      setSignals([]);
      setStrategyError(null);
      signalReasonRef.current = {};
      if (onSignals) onSignals([]);
      return;
    }

    console.log('[StockChart] fetching signals', { ticker, strategy, startDate, endDate });
    setStrategyLoading(true);
    setStrategyError(null);

    const params = new URLSearchParams({ start: startDate, end: endDate });
    apiFetch(`/api/strategy/${strategy}/${ticker}?${params}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.error) {
          console.warn('[StockChart] strategy error:', data.error);
          setStrategyError(data.error);
          setSignals([]);
          if (onSignals) onSignals([]);
        } else {
          const sigs = data.signals || [];
          console.log(`[StockChart] loaded ${sigs.length} signal(s) for ${strategy}/${ticker}`);
          setSignals(sigs);

          // Lift signals to parent (App.js) so other tabs can consume them.
          if (onSignals) onSignals(sigs);

          // Build date → {reason, type, conviction, score} lookup for tooltips
          const lookup = {};
          sigs.forEach((s) => {
            lookup[s.date] = { reason: s.reason, type: s.type, conviction: s.conviction, score: s.score };
          });
          signalReasonRef.current = lookup;
        }
        setStrategyLoading(false);
      })
      .catch((err) => {
        console.error('[StockChart] strategy fetch failed:', err);
        setStrategyError('Could not load strategy signals. Make sure the Flask server is running on port 5000.');
        setSignals([]);
        setStrategyLoading(false);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker, strategy, startDate, endDate, stockData]);

  if (loading) {
    return <div className="chart-status">Loading {ticker}…</div>;
  }
  if (error) {
    return <div className="chart-status error">{error}</div>;
  }
  if (!stockData) return null;

  const { dates, close, volume, ma20, ma50, macd, macd_signal, macd_hist, rsi, bb_upper, bb_lower, vol_ma20, atr, stoch_k, stoch_d, obv, obv_signal, fifty_two_week_high, fifty_two_week_low, earnings_dates } = stockData;

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
        label: 'BB Upper',
        data: bb_upper,
        borderColor: 'rgba(136,198,255,0.4)',
        borderWidth: 1,
        borderDash: [3, 3],
        pointRadius: 0,
        tension: 0.15,
        fill: false,
        order: 4,
      },
      {
        label: 'BB Lower',
        data: bb_lower,
        borderColor: 'rgba(136,198,255,0.4)',
        borderWidth: 1,
        borderDash: [3, 3],
        pointRadius: 0,
        tension: 0.15,
        fill: '-1',
        backgroundColor: 'rgba(136,198,255,0.06)',
        order: 4,
      },
      // 52-Week High reference line
      ...(fifty_two_week_high ? [{
        label: `52W High ($${fifty_two_week_high})`,
        data: dates.map(() => fifty_two_week_high),
        borderColor: 'rgba(63,185,80,0.5)',
        borderWidth: 1,
        borderDash: [10, 5],
        pointRadius: 0,
        pointHitRadius: 0,
        fill: false,
        order: 5,
      }] : []),
      // 52-Week Low reference line
      ...(fifty_two_week_low ? [{
        label: `52W Low ($${fifty_two_week_low})`,
        data: dates.map(() => fifty_two_week_low),
        borderColor: 'rgba(248,81,73,0.5)',
        borderWidth: 1,
        borderDash: [10, 5],
        pointRadius: 0,
        pointHitRadius: 0,
        fill: false,
        order: 5,
      }] : []),
      // Earnings date markers — vertical spikes at earnings dates
      ...(() => {
        if (!earnings_dates || earnings_dates.length === 0) return [];
        const earningsSet = new Set(earnings_dates);
        const earningsData = dates.map((d) => earningsSet.has(d) ? close[dates.indexOf(d)] : null);
        const hasAny = earningsData.some((v) => v !== null);
        if (!hasAny) return [];
        return [{
          label: 'Earnings',
          data: earningsData,
          showLine: false,
          pointStyle: 'line',
          pointRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 14 : 0),
          pointHoverRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 16 : 0),
          pointBorderColor: '#d2a8ff',
          pointBackgroundColor: '#d2a8ff',
          pointBorderWidth: 2,
          order: 0,
        }];
      })(),
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
            if (ctx.dataset.label === 'Earnings') {
              if (ctx.dataset.data[ctx.dataIndex] === null) return null;
              return '📅 Earnings Report';
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
        order: 1,
      },
      {
        type: 'line',
        label: 'Vol MA 20',
        data: vol_ma20,
        borderColor: '#f0883e',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.15,
        fill: false,
        order: 0,
      },
    ],
  };

  const volumeOptions = {
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
            if (ctx.parsed.y === null) return null;
            const v = ctx.parsed.y;
            const prefix = ctx.dataset.label === 'Vol MA 20' ? 'Vol MA 20: ' : 'Volume: ';
            if (v >= 1e9) return `${prefix}${(v / 1e9).toFixed(2)}B`;
            if (v >= 1e6) return `${prefix}${(v / 1e6).toFixed(2)}M`;
            if (v >= 1e3) return `${prefix}${(v / 1e3).toFixed(0)}K`;
            return `${prefix}${v}`;
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

  // (3) Histogram gradient intensity — scale opacity by magnitude
  const histArr = macd_hist || [];
  const histMax = Math.max(...histArr.map((v) => Math.abs(v || 0)), 0.001);
  const histBg = histArr.map((v) => {
    const intensity = Math.max(0.2, Math.abs(v || 0) / histMax);
    return v >= 0
      ? `rgba(63,185,80,${intensity.toFixed(2)})`
      : `rgba(248,81,73,${intensity.toFixed(2)})`;
  });
  const histBorder = histArr.map((v) => (v >= 0 ? '#3fb950' : '#f85149'));

  // (2) Crossover markers — find where MACD crosses the signal line
  const macdArr = macd || [];
  const sigArr = macd_signal || [];
  const crossoverBullish = dates.map(() => null);
  const crossoverBearish = dates.map(() => null);
  for (let i = 1; i < macdArr.length; i++) {
    if (macdArr[i] == null || macdArr[i - 1] == null || sigArr[i] == null || sigArr[i - 1] == null) continue;
    const prevDiff = macdArr[i - 1] - sigArr[i - 1];
    const currDiff = macdArr[i] - sigArr[i];
    if (prevDiff <= 0 && currDiff > 0) crossoverBullish[i] = macdArr[i]; // bullish crossover
    if (prevDiff >= 0 && currDiff < 0) crossoverBearish[i] = macdArr[i]; // bearish crossover
  }

  // (4) Divergence detection — price vs MACD divergence
  // Find local peaks/troughs in 10-bar windows and compare price vs MACD direction
  const divergenceBullish = dates.map(() => null);
  const divergenceBearish = dates.map(() => null);
  const divWindow = 10;
  const closeArr = close || [];
  if (macdArr.length > divWindow * 3) {
    // Find local highs and lows
    const localHighs = [];
    const localLows = [];
    for (let i = divWindow; i < macdArr.length - divWindow; i++) {
      if (closeArr[i] == null || macdArr[i] == null) continue;
      let isHigh = true;
      let isLow = true;
      for (let j = i - divWindow; j <= i + divWindow; j++) {
        if (j === i || closeArr[j] == null) continue;
        if (closeArr[j] >= closeArr[i]) isHigh = false;
        if (closeArr[j] <= closeArr[i]) isLow = false;
      }
      if (isHigh) localHighs.push(i);
      if (isLow) localLows.push(i);
    }
    // Bearish divergence: price makes higher high but MACD makes lower high
    for (let k = 1; k < localHighs.length; k++) {
      const prev = localHighs[k - 1];
      const curr = localHighs[k];
      if (closeArr[curr] > closeArr[prev] && macdArr[curr] < macdArr[prev]) {
        divergenceBearish[curr] = macdArr[curr];
      }
    }
    // Bullish divergence: price makes lower low but MACD makes higher low
    for (let k = 1; k < localLows.length; k++) {
      const prev = localLows[k - 1];
      const curr = localLows[k];
      if (closeArr[curr] < closeArr[prev] && macdArr[curr] > macdArr[prev]) {
        divergenceBullish[curr] = macdArr[curr];
      }
    }
  }

  const macdData = {
    labels: dates,
    datasets: [
      {
        type: 'bar',
        label: 'Histogram',
        data: macd_hist,
        backgroundColor: histBg,
        borderColor: histBorder,
        borderWidth: 1,
        order: 5,
      },
      // (1) Zero line
      {
        type: 'line',
        label: 'Zero',
        data: dates.map(() => 0),
        borderColor: 'rgba(139,148,158,0.5)',
        borderWidth: 1,
        borderDash: [6, 4],
        pointRadius: 0,
        pointHitRadius: 0,
        fill: false,
        order: 4,
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
        order: 2,
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
        order: 1,
      },
      // (2) Crossover markers
      {
        type: 'line',
        label: '▲ Bullish Cross',
        data: crossoverBullish,
        showLine: false,
        pointStyle: 'triangle',
        pointRotation: 0,
        pointRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 8 : 0),
        pointHoverRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 10 : 0),
        pointBackgroundColor: '#3fb950',
        pointBorderColor: '#1a7f37',
        pointBorderWidth: 1.5,
        order: 0,
      },
      {
        type: 'line',
        label: '▼ Bearish Cross',
        data: crossoverBearish,
        showLine: false,
        pointStyle: 'triangle',
        pointRotation: 180,
        pointRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 8 : 0),
        pointHoverRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 10 : 0),
        pointBackgroundColor: '#f85149',
        pointBorderColor: '#b62324',
        pointBorderWidth: 1.5,
        order: 0,
      },
      // (4) Divergence callouts
      {
        type: 'line',
        label: '◆ Bull Divergence',
        data: divergenceBullish,
        showLine: false,
        pointStyle: 'rectRot',
        pointRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 7 : 0),
        pointHoverRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 9 : 0),
        pointBackgroundColor: '#3fb950',
        pointBorderColor: '#e6edf3',
        pointBorderWidth: 2,
        order: 0,
      },
      {
        type: 'line',
        label: '◆ Bear Divergence',
        data: divergenceBearish,
        showLine: false,
        pointStyle: 'rectRot',
        pointRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 7 : 0),
        pointHoverRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 9 : 0),
        pointBackgroundColor: '#f85149',
        pointBorderColor: '#e6edf3',
        pointBorderWidth: 2,
        order: 0,
      },
    ],
  };

  const macdOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        display: true,
        position: 'top',
        labels: {
          color: '#8b949e',
          usePointStyle: true,
          boxWidth: 8,
          font: { size: 11 },
          filter: (item) => item.text !== 'Zero',
        },
      },
      title: {
        display: true,
        text: 'MACD (12, 26, 9)',
        color: '#8b949e',
        font: { size: 12 },
        padding: { bottom: 6 },
      },
      // (5) Enhanced tooltip with momentum context
      tooltip: {
        backgroundColor: '#161b22',
        borderColor: '#30363d',
        borderWidth: 1,
        titleColor: '#e6edf3',
        bodyColor: '#8b949e',
        callbacks: {
          label: (ctx) => {
            if (ctx.dataset.label === 'Zero') return null;
            if (ctx.parsed.y === null) return null;
            const label = ctx.dataset.label;
            if (label === '▲ Bullish Cross') return `▲ Bullish Crossover: ${ctx.parsed.y.toFixed(4)}`;
            if (label === '▼ Bearish Cross') return `▼ Bearish Crossover: ${ctx.parsed.y.toFixed(4)}`;
            if (label === '◆ Bull Divergence') return `◆ Bullish Divergence — price lower low but MACD higher low`;
            if (label === '◆ Bear Divergence') return `◆ Bearish Divergence — price higher high but MACD lower high`;
            return `${label}: ${ctx.parsed.y.toFixed(4)}`;
          },
          afterBody: (items) => {
            const idx = items[0]?.dataIndex;
            if (idx == null || !histArr[idx]) return [];
            const lines = [];
            const curr = histArr[idx];
            const prev = idx > 0 ? histArr[idx - 1] : null;
            if (prev != null) {
              const growing = Math.abs(curr) > Math.abs(prev);
              const positive = curr >= 0;
              if (positive && growing) lines.push('📈 Momentum building (bullish)');
              else if (positive && !growing) lines.push('📉 Momentum fading (bullish weakening)');
              else if (!positive && growing) lines.push('📉 Momentum building (bearish)');
              else lines.push('📈 Momentum fading (bearish weakening)');
            }
            return lines;
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

  // (5) RSI divergence detection — same approach as MACD divergences
  const rsiArr = rsi || [];
  const rsiDivBullish = dates.map(() => null);
  const rsiDivBearish = dates.map(() => null);
  const rsiDivWindow = 10;
  if (rsiArr.length > rsiDivWindow * 3) {
    const rsiLocalHighs = [];
    const rsiLocalLows = [];
    for (let i = rsiDivWindow; i < rsiArr.length - rsiDivWindow; i++) {
      if (closeArr[i] == null || rsiArr[i] == null) continue;
      let isHigh = true;
      let isLow = true;
      for (let j = i - rsiDivWindow; j <= i + rsiDivWindow; j++) {
        if (j === i || closeArr[j] == null) continue;
        if (closeArr[j] >= closeArr[i]) isHigh = false;
        if (closeArr[j] <= closeArr[i]) isLow = false;
      }
      if (isHigh) rsiLocalHighs.push(i);
      if (isLow) rsiLocalLows.push(i);
    }
    // Bearish divergence: price higher high, RSI lower high
    for (let k = 1; k < rsiLocalHighs.length; k++) {
      const prev = rsiLocalHighs[k - 1];
      const curr = rsiLocalHighs[k];
      if (closeArr[curr] > closeArr[prev] && rsiArr[curr] < rsiArr[prev]) {
        rsiDivBearish[curr] = rsiArr[curr];
      }
    }
    // Bullish divergence: price lower low, RSI higher low
    for (let k = 1; k < rsiLocalLows.length; k++) {
      const prev = rsiLocalLows[k - 1];
      const curr = rsiLocalLows[k];
      if (closeArr[curr] < closeArr[prev] && rsiArr[curr] > rsiArr[prev]) {
        rsiDivBullish[curr] = rsiArr[curr];
      }
    }
  }

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
        order: 2,
      },
      {
        label: 'Oversold (30)',
        data: flat30,
        borderColor: 'rgba(63,185,80,0.6)',
        borderWidth: 1,
        borderDash: [4, 3],
        pointRadius: 0,
        fill: false,
        order: 2,
      },
      {
        label: '◆ Bull Divergence',
        data: rsiDivBullish,
        showLine: false,
        pointStyle: 'rectRot',
        pointRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 7 : 0),
        pointHoverRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 9 : 0),
        pointBackgroundColor: '#3fb950',
        pointBorderColor: '#e6edf3',
        pointBorderWidth: 2,
        order: 0,
      },
      {
        label: '◆ Bear Divergence',
        data: rsiDivBearish,
        showLine: false,
        pointStyle: 'rectRot',
        pointRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 7 : 0),
        pointHoverRadius: (ctx) => (ctx.dataset.data[ctx.dataIndex] !== null ? 9 : 0),
        pointBackgroundColor: '#f85149',
        pointBorderColor: '#e6edf3',
        pointBorderWidth: 2,
        order: 0,
      },
    ],
  };

  const rsiOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: 'index', intersect: false },
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
            const label = ctx.dataset.label;
            if (label === '◆ Bull Divergence') return '◆ Bullish Divergence — price lower low but RSI higher low';
            if (label === '◆ Bear Divergence') return '◆ Bearish Divergence — price higher high but RSI lower high';
            return `${label}: ${ctx.parsed.y.toFixed(1)}`;
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

  // ── ATR chart ───────────────────────────────────────────────────────────────
  const atrData = {
    labels: dates,
    datasets: [
      {
        label: 'ATR (14)',
        data: atr,
        borderColor: '#f0883e',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.15,
        fill: true,
        backgroundColor: 'rgba(240,136,62,0.08)',
      },
    ],
  };

  const atrOptions = {
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
        text: 'Average True Range (14)  ·  Volatility in $ terms',
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
            return `ATR: $${ctx.parsed.y.toFixed(2)}`;
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
          callback: (v) => `$${v.toFixed(2)}`,
        },
        grid: { color: '#21262d' },
      },
    },
  };

  // ── Stochastic Oscillator chart ────────────────────────────────────────────
  const flat80 = dates.map(() => 80);
  const flat20 = dates.map(() => 20);

  const stochData = {
    labels: dates,
    datasets: [
      {
        label: '%K (9)',
        data: stoch_k,
        borderColor: '#58a6ff',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.15,
        fill: false,
        order: 0,
      },
      {
        label: '%D (3)',
        data: stoch_d,
        borderColor: '#f0883e',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.15,
        fill: false,
        order: 0,
      },
      {
        label: 'Overbought (80)',
        data: flat80,
        borderColor: 'rgba(248,81,73,0.5)',
        borderWidth: 1,
        borderDash: [4, 3],
        pointRadius: 0,
        fill: false,
        order: 1,
      },
      {
        label: 'Oversold (20)',
        data: flat20,
        borderColor: 'rgba(63,185,80,0.5)',
        borderWidth: 1,
        borderDash: [4, 3],
        pointRadius: 0,
        fill: false,
        order: 1,
      },
    ],
  };

  const stochOptions = {
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
        text: 'Stochastic (9, 3, 3)  ·  Overbought > 80  ·  Oversold < 20',
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
          stepSize: 20,
        },
        grid: { color: '#21262d' },
      },
    },
  };

  // ── OBV chart ───────────────────────────────────────────────────────────────
  const obvData = {
    labels: dates,
    datasets: [
      {
        label: 'OBV',
        data: obv,
        borderColor: '#58a6ff',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.15,
        fill: false,
        order: 0,
      },
      {
        label: 'Signal (20)',
        data: obv_signal,
        borderColor: '#f0883e',
        borderWidth: 1.5,
        borderDash: [4, 3],
        pointRadius: 0,
        tension: 0.15,
        fill: false,
        order: 1,
      },
    ],
  };

  const fmtObv = (v) => {
    if (v >= 1e9 || v <= -1e9) return `${(v / 1e9).toFixed(2)}B`;
    if (v >= 1e6 || v <= -1e6) return `${(v / 1e6).toFixed(1)}M`;
    if (v >= 1e3 || v <= -1e3) return `${(v / 1e3).toFixed(0)}K`;
    return `${v}`;
  };

  const obvOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        display: true,
        position: 'top',
        labels: { color: '#8b949e', usePointStyle: true, boxWidth: 8, font: { size: 11 } },
      },
      title: {
        display: true,
        text: 'On-Balance Volume (OBV)  ·  Accumulation / Distribution',
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
            return `${ctx.dataset.label}: ${fmtObv(ctx.parsed.y)}`;
          },
          afterBody: (items) => {
            const idx = items[0]?.dataIndex;
            if (idx == null || !obv || !obv_signal) return [];
            const obvVal = obv[idx];
            const sigVal = obv_signal[idx];
            if (obvVal == null || sigVal == null) return [];
            const lines = [];
            if (obvVal > sigVal) lines.push('OBV above signal — accumulation (buying pressure)');
            else lines.push('OBV below signal — distribution (selling pressure)');
            return lines;
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
          callback: (v) => fmtObv(v),
        },
        grid: { color: '#21262d' },
      },
    },
  };

  const buySignals = signals.filter((s) => s.type === 'BUY');
  const sellSignals = signals.filter((s) => s.type === 'SELL');

  // Helper to render a colored legend line in info popovers
  function L({ color, dashed, children }) {
    return (
      <div className="chart-info-line">
        <span
          className="chart-info-swatch"
          style={{
            background: dashed ? 'none' : color,
            borderBottom: dashed ? `2px dashed ${color}` : 'none',
          }}
        />
        <span>{children}</span>
      </div>
    );
  }
  function S({ color, symbol, children }) {
    return (
      <div className="chart-info-line">
        <span className="chart-info-symbol" style={{ color }}>{symbol}</span>
        <span>{children}</span>
      </div>
    );
  }

  // Chart info descriptions with colored legends
  const CHART_INFO = {
    price: (
      <>
        <p className="chart-info-desc">Price chart with closing price, moving averages, and Bollinger Bands.</p>
        <L color="#58a6ff">Close price</L>
        <L color="#f0883e" dashed>20-day MA</L>
        <L color="#bc8cff" dashed>50-day MA</L>
        <L color="rgba(136,198,255,0.6)" dashed>Bollinger Bands (2 std dev)</L>
        <L color="rgba(63,185,80,0.5)" dashed>52-week high</L>
        <L color="rgba(248,81,73,0.5)" dashed>52-week low</L>
        <S color="#d2a8ff" symbol="|">Earnings date</S>
        <S color="#3fb950" symbol={'\u25B2'}>BUY signal</S>
        <S color="#f85149" symbol={'\u25BC'}>SELL signal</S>
      </>
    ),
    volume: (
      <>
        <p className="chart-info-desc">Trading volume with 20-day moving average.</p>
        <L color="rgba(88,166,255,0.6)">Daily volume</L>
        <L color="#f0883e">20-day avg volume</L>
        <p className="chart-info-note">Above-average volume confirms price moves. Below-average suggests weak conviction.</p>
      </>
    ),
    macd: (
      <>
        <p className="chart-info-desc">MACD measures momentum via two EMA crossovers.</p>
        <L color="#58a6ff">MACD (12-EMA minus 26-EMA)</L>
        <L color="#f0883e">Signal (9-EMA of MACD)</L>
        <L color="rgba(63,185,80,0.5)">Histogram (positive)</L>
        <L color="rgba(248,81,73,0.5)">Histogram (negative)</L>
        <L color="rgba(139,148,158,0.5)" dashed>Zero line</L>
        <S color="#3fb950" symbol={'\u25B2'}>Bullish crossover</S>
        <S color="#f85149" symbol={'\u25BC'}>Bearish crossover</S>
        <S color="#3fb950" symbol={'\u25C6'}>Bullish divergence</S>
        <S color="#f85149" symbol={'\u25C6'}>Bearish divergence</S>
        <p className="chart-info-note">Bar opacity indicates momentum strength.</p>
      </>
    ),
    atr: (
      <>
        <p className="chart-info-desc">Average True Range measures volatility in dollar terms.</p>
        <L color="#f0883e">14-period ATR</L>
        <p className="chart-info-note">Higher ATR = larger price swings, wider stops needed. Lower ATR = tighter range, possible breakout ahead.</p>
      </>
    ),
    stoch: (
      <>
        <p className="chart-info-desc">Stochastic Oscillator measures price position within recent range.</p>
        <L color="#58a6ff">%K (9-period)</L>
        <L color="#f0883e">%D (3-period avg of %K)</L>
        <L color="rgba(248,81,73,0.5)" dashed>Overbought (80)</L>
        <L color="rgba(63,185,80,0.5)" dashed>Oversold (20)</L>
        <p className="chart-info-note">Buy when %K crosses above %D below 20. Sell when %K crosses below %D above 80.</p>
      </>
    ),
    obv: (
      <>
        <p className="chart-info-desc">On-Balance Volume tracks cumulative buying/selling pressure.</p>
        <L color="#58a6ff">OBV</L>
        <L color="#f0883e" dashed>20-day signal</L>
        <p className="chart-info-note">OBV above signal = accumulation (buying). Below signal = distribution (selling). OBV diverging from price warns of reversal.</p>
      </>
    ),
    rsi: (
      <>
        <p className="chart-info-desc">Relative Strength Index measures momentum on a 0-100 scale.</p>
        <L color="#e6edf3">RSI (14-period)</L>
        <L color="rgba(248,81,73,0.6)" dashed>Overbought (70)</L>
        <L color="rgba(63,185,80,0.6)" dashed>Oversold (30)</L>
        <S color="#3fb950" symbol={'\u25C6'}>Bullish divergence</S>
        <S color="#f85149" symbol={'\u25C6'}>Bearish divergence</S>
        <p className="chart-info-note">Above 70 = stretched, watch for pullback. Below 30 = potential bounce.</p>
      </>
    ),
  };

  function InfoBtn({ chartKey }) {
    const isOpen = infoOpen === chartKey;
    return (
      <>
        <button
          className="chart-info-btn"
          onClick={() => setInfoOpen(isOpen ? null : chartKey)}
          title="Chart info"
        >
          i
        </button>
        {isOpen && (
          <div className="chart-info-popover">
            <button className="chart-info-close" onClick={() => setInfoOpen(null)}>✕</button>
            <div className="chart-info-content">{CHART_INFO[chartKey]}</div>
          </div>
        )}
      </>
    );
  }

  function ExpandBtn({ chartKey }) {
    return (
      <button
        className="chart-expand-btn"
        onClick={() => setExpandedChart(chartKey)}
        title="Expand chart"
      >
        ⛶
      </button>
    );
  }

  // Render a chart in expanded mode — fills the content area, pushes everything else down
  if (expandedChart) {
    const chartMap = {
      price: { className: 'price-chart', node: <Line data={priceData} options={priceOptions} /> },
      volume: { className: 'volume-chart', node: <Bar data={volumeData} options={volumeOptions} /> },
      macd: { className: 'macd-chart', node: <Bar data={macdData} options={macdOptions} /> },
      atr: { className: 'atr-chart', node: <Line data={atrData} options={atrOptions} /> },
      stoch: { className: 'stoch-chart', node: <Line data={stochData} options={stochOptions} /> },
      obv: { className: 'obv-chart', node: <Line data={obvData} options={obvOptions} /> },
      rsi: { className: 'rsi-chart', node: <Line data={rsiData} options={rsiOptions} /> },
    };
    const expanded = chartMap[expandedChart];
    if (expanded) {
      return (
        <div className="chart-container">
          <div className={`${expanded.className} chart-expanded`}>
            <InfoBtn chartKey={expandedChart} />
            <button
              className="chart-close-btn"
              onClick={() => setExpandedChart(null)}
              title="Close expanded view"
            >
              ✕
            </button>
            {expanded.node}
          </div>
        </div>
      );
    }
  }

  return (
    <div className="chart-container">
      {strategyLoading && (
        <div className="strategy-loading">Loading strategy signals…</div>
      )}

      {strategyError && !strategyLoading && (
        <div className="chart-status error">{strategyError}</div>
      )}

      <div className="price-chart chart-expandable">
        <InfoBtn chartKey="price" />
        <ExpandBtn chartKey="price" />
        <Line data={priceData} options={priceOptions} />
      </div>

      <div className="volume-chart chart-expandable">
        <InfoBtn chartKey="volume" />
        <ExpandBtn chartKey="volume" />
        <Bar data={volumeData} options={volumeOptions} />
      </div>

      <div className="macd-chart chart-expandable">
        <InfoBtn chartKey="macd" />
        <ExpandBtn chartKey="macd" />
        <Bar data={macdData} options={macdOptions} />
      </div>

      <div className="atr-chart chart-expandable">
        <InfoBtn chartKey="atr" />
        <ExpandBtn chartKey="atr" />
        <Line data={atrData} options={atrOptions} />
      </div>

      <div className="stoch-chart chart-expandable">
        <InfoBtn chartKey="stoch" />
        <ExpandBtn chartKey="stoch" />
        <Line data={stochData} options={stochOptions} />
      </div>

      <div className="obv-chart chart-expandable">
        <InfoBtn chartKey="obv" />
        <ExpandBtn chartKey="obv" />
        <Line data={obvData} options={obvOptions} />
      </div>

      {showRsiPanel && (
        <div className="rsi-chart chart-expandable">
          <InfoBtn chartKey="rsi" />
          <ExpandBtn chartKey="rsi" />
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

      {strategy !== 'none' && !strategyLoading && !strategyError && signals.length === 0 && (
        <div className="no-signals">
          No signals generated for {ticker} with this strategy from {startDate} to {endDate}.
        </div>
      )}
    </div>
  );
}
