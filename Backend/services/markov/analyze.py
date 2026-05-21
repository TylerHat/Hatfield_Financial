"""Markov regime analysis primitives.

Pure functions — no Flask, no I/O. Shared by:
  - /api/markov/<ticker>          (full per-ticker analysis for the UI)
  - recommendations prewarm        (per-row markov* fields for ETF scoring)
  - markov backtest signal gen     (rolling/expanding matrix without lookahead)

Mirrors the Pine script `theory.pine` (Lewis Jackson / Roan). Defaults match
the script: 20-bar log-return lookback, ±5% thresholds, 50-step stationary
power, 4-bar minimum hold for debounced transition labels.
"""

from __future__ import annotations

import numpy as np

# Pine defaults — kept as module-level constants so all three callers stay
# in sync. Override per-call if you need to.
LOOKBACK = 20
BULL_PCT = 5.0
BEAR_PCT = 5.0
STATIONARY_POWER = 50
MIN_HOLD = 4

# Internal regime codes: 0=Side, 1=Bull, 2=Bear (matches Pine spec §3).
REGIME_FULL = {0: 'Sideways', 1: 'Bull', 2: 'Bear'}

# Display order in tables and the JSON response is Bull/Bear/Side.
# INTERNAL_ORDER[i] gives the internal regime index for display row/col i.
INTERNAL_ORDER = [1, 2, 0]
DISPLAY_LABELS = ['Bull', 'Bear', 'Side']


def classify_regimes(close, lookback=LOOKBACK, bull_pct=BULL_PCT, bear_pct=BEAR_PCT):
    """Label every bar with a regime code from the rolling log-return rule.

    Parameters
    ----------
    close : array-like of float
        Closing prices, ordered oldest → newest.
    lookback : int
        Bars used for the rolling log-return.
    bull_pct, bear_pct : float
        Thresholds in percent (e.g. 5.0 → 0.05 in log-return space).

    Returns
    -------
    np.ndarray[int]
        Same length as `close`. Values are -1 (warmup, undefined log_ret),
        0 (Sideways), 1 (Bull), or 2 (Bear).
    """
    close = np.asarray(close, dtype=float)
    n = len(close)
    log_ret = np.full(n, np.nan)
    if n > lookback:
        log_ret[lookback:] = np.log(close[lookback:] / close[:-lookback])

    regime = np.where(np.isnan(log_ret), -1,
             np.where(log_ret > bull_pct / 100.0, 1,
             np.where(log_ret < -bear_pct / 100.0, 2, 0))).astype(int)
    return regime


def build_transition_matrix(regime):
    """Build the row-normalised 3×3 transition matrix from a regime sequence.

    Warmup bars (-1) are skipped. Empty rows fall back to uniform 1/3 to
    avoid NaN propagation in subsequent matrix operations.

    Returns
    -------
    np.ndarray[float] of shape (3, 3)
        Internal-order stochastic matrix (rows: Side/Bull/Bear).
    """
    counts = np.zeros((3, 3), dtype=int)
    valid = regime[regime != -1]
    if len(valid) >= 2:
        for prev, curr in zip(valid[:-1], valid[1:]):
            counts[prev, curr] += 1

    row_sums = counts.sum(axis=1, keepdims=True)
    with np.errstate(divide='ignore', invalid='ignore'):
        P = np.where(row_sums > 0, counts / np.maximum(row_sums, 1), 1.0 / 3.0)
    return P


def forecast_from_regime(P_internal, current_regime, horizons=(1, 3, 5, 10)):
    """Compute P^n[current_regime, :] for each horizon, remapping to display order.

    Returns
    -------
    dict[str, dict[str, float]]
        e.g. {'1d': {'bull': .., 'bear': .., 'side': ..}, '3d': {...}, ...}
        Empty dict if `current_regime` is -1 (warmup).
    """
    if current_regime is None or current_regime == -1:
        return {}

    out = {}
    for n in horizons:
        Pn = np.linalg.matrix_power(P_internal, n)
        row = Pn[current_regime]   # [side, bull, bear] in internal order
        out[f'{n}d'] = {
            'bull': float(row[1]),
            'bear': float(row[2]),
            'side': float(row[0]),
        }
    return out


def stationary_from_matrix(P_internal, power=STATIONARY_POWER):
    """Stationary distribution via repeated matrix multiplication.

    Returns
    -------
    dict[str, float]
        {'bull', 'bear', 'side'} probabilities summing to ~1.0.
    """
    M = np.linalg.matrix_power(P_internal, power)
    stat = M[0]   # [side, bull, bear]
    return {
        'bull': float(stat[1]),
        'bear': float(stat[2]),
        'side': float(stat[0]),
    }


def debounced_flips(regime, dates, min_hold=MIN_HOLD):
    """Walk the regime sequence and emit transition events where a new regime
    has held for at least `min_hold` consecutive confirmed bars.

    Parameters
    ----------
    regime : np.ndarray[int]
        From classify_regimes().
    dates : sequence
        Same length as `regime`; entries with a .strftime() method preferred,
        else stringified.
    min_hold : int

    Returns
    -------
    list[dict]
        [{'date': 'YYYY-MM-DD', 'from': 'Bull', 'to': 'Bear'}, ...]
    """
    flips = []
    last_labelled = None
    for i in range(min_hold - 1, len(regime)):
        r = int(regime[i])
        if r == -1:
            continue
        window = regime[i - min_hold + 1: i + 1]
        if np.all(window == r) and r != last_labelled:
            if last_labelled is not None:
                flip_idx = i - (min_hold - 1)
                d = dates[flip_idx]
                date_str = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10]
                flips.append({
                    'date': date_str,
                    'from': REGIME_FULL[int(last_labelled)],
                    'to': REGIME_FULL[r],
                })
            last_labelled = r
    return flips


def analyze_markov(close, dates=None, lookback=LOOKBACK, bull_pct=BULL_PCT,
                   bear_pct=BEAR_PCT, stationary_power=STATIONARY_POWER,
                   min_hold=MIN_HOLD, forecast_horizons=(1, 3, 5, 10)):
    """End-to-end analysis: classify, build matrix, forecast, stationary, flips.

    Returns a dict with keys:
        current_regime           : 'Bull' | 'Bear' | 'Sideways' | None
        current_regime_code      : 0 | 1 | 2 | None
        transition_matrix_internal : np.ndarray (3,3) — Side/Bull/Bear order
        transition_matrix_display  : list[list[float]] — Bull/Bear/Side order
        stationary               : {'bull', 'bear', 'side'}
        forecast                 : {'1d': {'bull','bear','side'}, ...}
        transitions              : list of debounced flip dicts (if dates given)
        bars_analyzed            : int (count of non-warmup bars)
    """
    regime = classify_regimes(close, lookback, bull_pct, bear_pct)

    if len(regime) == 0 or np.all(regime == -1):
        return None

    P_internal = build_transition_matrix(regime)
    P_display = P_internal[np.ix_(INTERNAL_ORDER, INTERNAL_ORDER)]
    stationary = stationary_from_matrix(P_internal, stationary_power)

    current = int(regime[-1])
    current_name = REGIME_FULL[current] if current != -1 else None
    forecast = forecast_from_regime(P_internal, current, forecast_horizons)
    transitions = debounced_flips(regime, dates, min_hold) if dates is not None else []

    return {
        'current_regime': current_name,
        'current_regime_code': current if current != -1 else None,
        'transition_matrix_internal': P_internal,
        'transition_matrix_display': [[float(v) for v in row] for row in P_display],
        'stationary': stationary,
        'forecast': forecast,
        'transitions': transitions,
        'bars_analyzed': int((regime != -1).sum()),
    }
