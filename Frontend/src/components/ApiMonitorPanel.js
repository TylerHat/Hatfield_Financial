import React, { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../api';
import './ApiMonitorPanel.css';

export default function ApiMonitorPanel() {
  const [status, setStatus] = useState(null);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState(null);

  // Load metrics status from backend
  const loadStatus = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/admin/metrics/status?t=${Date.now()}`);
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Failed to load metrics');
      }
      setStatus(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  // Start recording
  const handleStartRecording = async (minutes) => {
    setError(null);
    try {
      const res = await apiFetch(`/api/admin/metrics/start/${minutes}`, {
        method: 'POST',
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Failed to start recording');
      }
      // Start polling while recording
      setPolling(true);
      // Immediately load the new status
      await loadStatus();
    } catch (err) {
      setError(err.message);
    }
  };

  // Clear metrics
  const handleClear = async () => {
    setError(null);
    try {
      const res = await apiFetch('/api/admin/metrics/clear', {
        method: 'POST',
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Failed to clear metrics');
      }
      setPolling(false);
      await loadStatus();
    } catch (err) {
      setError(err.message);
    }
  };

  // Initial load on mount
  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  // Polling while recording or done
  useEffect(() => {
    if (!polling && status?.done) {
      // Once recording is done, continue polling for a few seconds then stop
      setPolling(false);
      return;
    }

    if (!polling || (status?.done && status?.recording === false)) {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const res = await apiFetch(`/api/admin/metrics/status?t=${Date.now()}`);
        const data = await res.json();
        if (res.ok) {
          setStatus(data);
          // Stop polling if recording is done
          if (data.done && !data.recording) {
            setPolling(false);
          }
        }
      } catch (err) {
        // Continue polling even if error
      }
    }, 3000); // Poll every 3 seconds

    return () => clearInterval(interval);
  }, [polling, status?.done, status?.recording]);

  // Determine status message
  const getStatusMessage = () => {
    if (!status || (!status.recording && !status.done && status.completed === 0)) {
      return '⚪ Idle';
    }
    if (status.recording && status.completed === 0) {
      return '🔵 Recording minute 1 (collecting data...)';
    }
    if (status.recording && status.completed > 0) {
      return `🔵 Recording minute ${status.completed + 1}/${status.target}...`;
    }
    if (status.done) {
      return `✅ Recording complete (${status.target}/${status.target} minutes)`;
    }
    return 'Unknown state';
  };

  const isRecording = status?.recording || false;
  const isDone = status?.done || false;
  const hasData = status?.data && status.data.length > 0;

  return (
    <div className="api-monitor">
      <div className="api-monitor__header">
        <h2>API Monitor</h2>
        <p className="api-monitor__subtitle">
          Record live API call metrics for diagnostics. Click Record to capture the next N minutes
          of yfinance calls, success/failure rates, and cache performance.
        </p>
      </div>

      {error && <div className="api-monitor__error">{error}</div>}

      <div className="api-monitor__controls">
        <button
          type="button"
          className="api-monitor__btn api-monitor__btn--primary"
          onClick={() => handleStartRecording(5)}
          disabled={isRecording || isDone}
          title={isRecording ? 'Already recording' : isDone ? 'Clear to record again' : 'Start recording for 5 minutes'}
        >
          Record 5 mins
        </button>
        <button
          type="button"
          className="api-monitor__btn api-monitor__btn--primary"
          onClick={() => handleStartRecording(10)}
          disabled={isRecording || isDone}
          title={isRecording ? 'Already recording' : isDone ? 'Clear to record again' : 'Start recording for 10 minutes'}
        >
          Record 10 mins
        </button>
        <button
          type="button"
          className="api-monitor__btn api-monitor__btn--secondary"
          onClick={handleClear}
          title="Clear recorded data and reset"
        >
          Clear
        </button>
      </div>

      <div className="api-monitor__status">
        <span className="api-monitor__status-text">{getStatusMessage()}</span>
      </div>

      {hasData ? (
        <div className="api-monitor__table-wrapper">
          <table className="api-monitor__table">
            <thead>
              <tr>
                <th>Minute</th>
                <th>Total Calls</th>
                <th>Success</th>
                <th>Failure</th>
                <th>Timeout</th>
                <th>Cache Hits</th>
                <th>Cache Misses</th>
                <th>Queue Depth</th>
                <th>yfinance Endpoints</th>
              </tr>
            </thead>
            <tbody>
              {status.data.map((row, idx) => {
                // Format endpoint calls as readable list
                const endpointStr = row.endpoint_calls && Object.keys(row.endpoint_calls).length > 0
                  ? Object.entries(row.endpoint_calls)
                    .map(([name, count]) => `${name}: ${count}`)
                    .join(' | ')
                  : '—';
                return (
                  <tr key={idx}>
                    <td>{row.minute}</td>
                    <td>{row.total_calls}</td>
                    <td className="api-monitor__cell--success">{row.successes}</td>
                    <td className="api-monitor__cell--failure">{row.failures}</td>
                    <td className="api-monitor__cell--timeout">{row.timeouts}</td>
                    <td className="api-monitor__cell--hit">{row.cache_hits}</td>
                    <td className="api-monitor__cell--miss">{row.cache_misses}</td>
                    <td>{row.queue_depth}</td>
                    <td className="api-monitor__cell--endpoints">{endpointStr}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="api-monitor__empty">
          No data yet. Click "Record 5 mins" or "Record 10 mins" to start capturing metrics.
        </div>
      )}
    </div>
  );
}
