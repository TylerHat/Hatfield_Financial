import time
import numpy as np
import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request

from data.sp500_tickers import SP500_TICKERS, CRYPTO_TICKERS

screener_bp = Blueprint('screener', __name__)

SCORE_LABELS = {
    2: 'Strong Buy',
    1: 'Buy',
    0: 'Neutral',
    -1: 'Sell',
    -2: 'Strong Sell',
}


# ── Scoring functions ────────────────────────────────────────────────────────

def score_bollinger(close):
    """Score based on current %B position within Bollinger Bands."""
    if len(close) < 22:
        return None, 'Not enough data'
    sma = close.rolling(20).mean().iloc[-1]
    std = close.rolling(20).std().iloc[-1]
    if std == 0 or np.isnan(std):
        return 0, 'No volatility'
    upper = sma + 2 * std
    lower = sma - 2 * std
    price = close.iloc[-1]
    band_width = upper - lower
    pct_b = (price - lower) / band_width if band_width != 0 else 0.5
    if pct_b < 0:
        return 2, f'Below lower band (%B={pct_b:.2f}) — oversold'
    elif pct_b < 0.25:
        return 1, f'Near lower band (%B={pct_b:.2f}) — approaching oversold'
    elif pct_b <= 0.75:
        return 0, f'Mid-band (%B={pct_b:.2f}) — neutral'
    elif pct_b <= 1.0:
        return -1, f'Near upper band (%B={pct_b:.2f}) — approaching overbought'
    else:
        return -2, f'Above upper band (%B={pct_b:.2f}) — overbought'


def score_relative_strength(close, spy_close):
    """Score based on RS ratio vs its 10-day MA and recent slope."""
    aligned = pd.DataFrame({'stock': close, 'spy': spy_close}).dropna()
    if len(aligned) < 15:
        return None, 'Not enough aligned data'
    rs = aligned['stock'] / aligned['spy']
    rs_ma = rs.rolling(10).mean()
    if rs_ma.dropna().empty:
        return None, 'Not enough data for MA'
    current_rs = rs.iloc[-1]
    current_ma = rs_ma.iloc[-1]
    if np.isnan(current_ma) or current_ma == 0:
        return None, 'MA not available'
    pct_diff = (current_rs - current_ma) / current_ma
    # Slope: compare today's MA vs 5 days ago
    ma_valid = rs_ma.dropna()
    slope = (ma_valid.iloc[-1] - ma_valid.iloc[-5]) if len(ma_valid) >= 5 else 0
    if pct_diff > 0.005 and slope > 0:
        return 2, f'RS above MA & rising — strong outperformance'
    elif pct_diff > 0:
        return 1, f'RS above 10d MA — outperforming market'
    elif abs(pct_diff) <= 0.005:
        return 0, f'RS near 10d MA — in line with market'
    elif pct_diff < -0.005 and slope < 0:
        return -2, f'RS below MA & falling — strong underperformance'
    else:
        return -1, f'RS below 10d MA — underperforming market'


def score_mean_reversion(close):
    """Score based on current drawdown from 20-day trailing high."""
    if len(close) < 22:
        return None, 'Not enough data'
    rolling_high = close.rolling(20).max()
    price = close.iloc[-1]
    high = rolling_high.iloc[-1]
    if high == 0 or np.isnan(high):
        return None, 'Invalid high'
    drawdown = (price - high) / high  # negative value
    pct = drawdown * 100
    if drawdown <= -0.15:
        return 2, f'Deep drawdown: {pct:.1f}% from 20d high — strong reversion candidate'
    elif drawdown <= -0.10:
        return 1, f'Significant pullback: {pct:.1f}% from 20d high'
    elif drawdown <= -0.05:
        return 0, f'Moderate pullback: {pct:.1f}% from 20d high'
    elif drawdown <= -0.02:
        return -1, f'Minor pullback: {pct:.1f}% from 20d high'
    else:
        return -2, f'Near 20d high: {pct:.1f}% — no reversion opportunity'


def score_pead(close):
    """
    Post-Earnings Drift: detect recent large gaps (proxy for earnings) and
    score based on 2-day follow-through after the gap.
    A gap day is identified as a close-to-close move > 3%.
    """
    if len(close) < 10:
        return None, 'Not enough data'
    returns = close.pct_change()
    # Look at last 15 trading days for a significant gap event
    recent = returns.iloc[-15:]
    gap_threshold = 0.03
    gap_idx = None
    gap_dir = 0
    for i in range(len(recent) - 3, -1, -1):  # find most recent gap (not in last 2 days)
        if abs(recent.iloc[i]) >= gap_threshold:
            gap_idx = i
            gap_dir = 1 if recent.iloc[i] > 0 else -1
            break
    if gap_idx is None:
        return 0, 'No recent earnings-like gap detected'
    # Check 2-day follow-through after the gap
    if gap_idx + 2 >= len(recent):
        return 0, 'Gap too recent to confirm drift'
    day1 = recent.iloc[gap_idx + 1]
    day2 = recent.iloc[gap_idx + 2]
    if gap_dir == 1 and day1 > 0 and day2 > 0:
        return 2, f'Upward gap with 2-day positive drift — Strong Buy'
    elif gap_dir == 1 and (day1 > 0 or day2 > 0):
        return 1, f'Upward gap with partial drift confirmation'
    elif gap_dir == -1 and day1 < 0 and day2 < 0:
        return -2, f'Downward gap with 2-day negative drift — Strong Sell'
    elif gap_dir == -1 and (day1 < 0 or day2 < 0):
        return -1, f'Downward gap with partial negative drift'
    else:
        return 0, f'Gap detected but no clear drift follow-through'


# ── Main screener endpoint ───────────────────────────────────────────────────

@screener_bp.route('/api/screener', methods=['POST'])
def run_screener():
    body = request.get_json(force=True, silent=True) or {}
    strategy = body.get('strategy', 'bollinger-bands')
    universe = body.get('universe', 'sp500')

    tickers = CRYPTO_TICKERS if universe == 'crypto' else SP500_TICKERS

    t0 = time.time()

    # Download price data in one batch call.
    # group_by='column' → MultiIndex (field, ticker), so raw['Close'][ticker] works.
    try:
        raw = yf.download(
            tickers=' '.join(tickers),
            period='3mo',
            interval='1d',
            group_by='column',
            auto_adjust=True,
            threads=True,
            progress=False,
        )
    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

    # Pull the Close sub-frame once (DataFrame with one column per ticker)
    try:
        if isinstance(raw.columns, pd.MultiIndex):
            close_frame = raw['Close']      # (date, ticker)
        else:
            # Fallback: single-ticker or already flat
            close_frame = raw[['Close']].rename(columns={'Close': tickers[0]})
    except Exception as e:
        return jsonify({'error': f'Could not extract Close prices: {str(e)}'}), 500

    # Also need SPY for relative-strength strategy
    spy_close = None
    if strategy == 'relative-strength':
        try:
            spy_raw = yf.download('SPY', period='3mo', interval='1d',
                                  auto_adjust=True, progress=False)
            # Single-ticker download returns flat columns
            if isinstance(spy_raw.columns, pd.MultiIndex):
                spy_close = spy_raw['Close'].iloc[:, 0]
            else:
                spy_close = spy_raw['Close']
        except Exception:
            pass

    results = []
    errors = []

    for ticker in tickers:
        try:
            # Extract this ticker's close series
            if ticker in close_frame.columns:
                close = close_frame[ticker].dropna()
            else:
                errors.append(ticker)
                continue

            if len(close) < 10:
                errors.append(ticker)
                continue

            price = float(close.iloc[-1])

            if strategy == 'bollinger-bands':
                score, reason = score_bollinger(close)
            elif strategy == 'relative-strength':
                if spy_close is None:
                    score, reason = None, 'SPY data unavailable'
                else:
                    score, reason = score_relative_strength(close, spy_close)
            elif strategy == 'mean-reversion':
                score, reason = score_mean_reversion(close)
            elif strategy == 'post-earnings-drift':
                score, reason = score_pead(close)
            else:
                score, reason = 0, 'Unknown strategy'

            if score is None:
                errors.append(ticker)
                continue

            results.append({
                'ticker': ticker,
                'score': score,
                'label': SCORE_LABELS[score],
                'reason': reason,
                'price': round(price, 4),
            })

        except Exception:
            errors.append(ticker)
            continue

    # Sort within each category by ticker name
    results.sort(key=lambda x: (x['score'] * -1, x['ticker']))

    duration = round(time.time() - t0, 1)

    return jsonify({
        'results': results,
        'meta': {
            'count': len(results),
            'errors': len(errors),
            'duration': duration,
            'strategy': strategy,
            'universe': universe,
        },
    })
