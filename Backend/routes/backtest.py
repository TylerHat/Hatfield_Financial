from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request

backtest_bp = Blueprint('backtest', __name__)


# ── Signal generators ─────────────────────────────────────────────────────────

def signals_bollinger(close):
    """BUY when price crosses below lower band; SELL when crosses above upper."""
    sma = close.rolling(20).mean()
    std = close.rolling(20).std()
    lower = sma - 2 * std
    upper = sma + 2 * std

    signals = []
    prev_below = prev_above = None

    for i in range(len(close)):
        lb = lower.iloc[i]
        ub = upper.iloc[i]
        if pd.isna(lb) or pd.isna(ub):
            continue
        price = float(close.iloc[i])
        date = close.index[i]
        curr_below = price < lb
        curr_above = price > ub

        if prev_below is not None:
            if curr_below and not prev_below:
                signals.append({'date': date, 'type': 'BUY', 'price': price,
                                'reason': f'Price crossed below lower band (${lb:.2f})'})
            elif curr_above and not prev_above:
                signals.append({'date': date, 'type': 'SELL', 'price': price,
                                'reason': f'Price crossed above upper band (${ub:.2f})'})
        prev_below = curr_below
        prev_above = curr_above

    return signals


def signals_relative_strength(close, spy_close):
    """BUY when RS ratio crosses above its 10-day MA; SELL when crosses below."""
    aligned = pd.DataFrame({'stock': close, 'spy': spy_close}).dropna()
    if aligned.empty:
        return []

    rs = aligned['stock'] / aligned['spy']
    rs_ma = rs.rolling(10).mean()

    signals = []
    prev_above = None

    for i in range(len(rs)):
        if pd.isna(rs_ma.iloc[i]):
            continue
        curr_above = rs.iloc[i] > rs_ma.iloc[i]
        date = aligned.index[i]
        price = float(aligned['stock'].iloc[i])

        if prev_above is not None:
            if curr_above and not prev_above:
                signals.append({'date': date, 'type': 'BUY', 'price': price,
                                'reason': 'RS ratio crossed above 10-day MA — outperforming market'})
            elif not curr_above and prev_above:
                signals.append({'date': date, 'type': 'SELL', 'price': price,
                                'reason': 'RS ratio crossed below 10-day MA — underperforming market'})
        prev_above = curr_above

    return signals


def signals_mean_reversion(close):
    """BUY at ≥10% drawdown from 20-day high; SELL when within 3% of high."""
    rolling_high = close.rolling(20).max()
    signals = []
    in_drawdown = False

    for i in range(len(close)):
        if pd.isna(rolling_high.iloc[i]):
            continue
        price = float(close.iloc[i])
        high = float(rolling_high.iloc[i])
        dd = (price - high) / high
        date = close.index[i]

        if not in_drawdown and dd <= -0.10:
            signals.append({'date': date, 'type': 'BUY', 'price': price,
                            'reason': f'Drawdown {dd*100:.1f}% from 20-day high (${high:.2f})'})
            in_drawdown = True
        elif in_drawdown and dd >= -0.03:
            signals.append({'date': date, 'type': 'SELL', 'price': price,
                            'reason': f'Recovered to within {abs(dd)*100:.1f}% of 20-day high (${high:.2f})'})
            in_drawdown = False

    return signals


def signals_pead(ticker, close, start_dt, end_dt):
    """
    Post-Earnings Drift: BUY on confirmed 2-day upward drift after earnings;
    SELL on confirmed 2-day downward drift.
    """
    signals = []
    try:
        t = yf.Ticker(ticker)
        ed = t.earnings_dates
        if ed is None or ed.empty:
            return signals

        # Normalize timezone
        idx = ed.index
        if hasattr(idx, 'tz') and idx.tz is not None:
            idx = idx.tz_convert(None)

        c_idx = close.index
        if hasattr(c_idx, 'tz') and c_idx.tz is not None:
            c_idx = c_idx.tz_convert(None)
        close_plain = close.copy()
        close_plain.index = c_idx

        start_ts = pd.Timestamp(start_dt)
        end_ts = pd.Timestamp(end_dt)
        earn_dates = sorted(
            [d for d in idx if start_ts <= d <= end_ts],
            key=lambda d: d
        )

        for earn_ts in earn_dates:
            try:
                before = close_plain[close_plain.index < earn_ts]
                after = close_plain[close_plain.index >= earn_ts]
                if len(before) < 1 or len(after) < 2:
                    continue
                pre_close = float(before.iloc[-1])
                day1 = float(after.iloc[0])
                day2 = float(after.iloc[1])
                day2_date = after.index[1]

                if day1 > pre_close and day2 > pre_close:
                    pct = (day2 - pre_close) / pre_close * 100
                    signals.append({'date': day2_date, 'type': 'BUY', 'price': day2,
                                    'reason': f'Earnings upward drift +{pct:.1f}% over 2 days'})
                elif day1 < pre_close and day2 < pre_close:
                    pct = (day2 - pre_close) / pre_close * 100
                    signals.append({'date': day2_date, 'type': 'SELL', 'price': day2,
                                    'reason': f'Earnings downward drift {pct:.1f}% over 2 days'})
            except Exception:
                continue
    except Exception:
        pass

    return signals


# ── Simulation engine ─────────────────────────────────────────────────────────

def run_simulation(signals, close, start_dt, end_dt, capital, position_size):
    """
    Execute trades based on signals (one open position at a time).
    BUY signal → enter if no position.
    SELL signal → exit if position open.
    End of period → mark any open position to market.
    """
    start_ts = pd.Timestamp(start_dt)
    end_ts = pd.Timestamp(end_dt)

    # Filter and sort signals to the user date range
    in_range = sorted(
        [s for s in signals if start_ts <= pd.Timestamp(s['date']) <= end_ts],
        key=lambda s: pd.Timestamp(s['date'])
    )

    actions = []
    trade_count = 0
    open_pos = None      # dict: trade_num, date, price, shares
    cumulative_pnl = 0.0

    for sig in in_range:
        sig_ts = pd.Timestamp(sig['date'])
        sig_price = sig['price']

        if sig['type'] == 'BUY' and open_pos is None:
            trade_count += 1
            shares = position_size / sig_price
            open_pos = {
                'trade_num': trade_count,
                'date': sig_ts,
                'price': sig_price,
                'shares': shares,
            }
            actions.append({
                'trade_num': trade_count,
                'action': 'BUY',
                'date': sig_ts.strftime('%Y-%m-%d'),
                'price': round(sig_price, 4),
                'shares': round(shares, 6),
                'value': round(position_size, 2),
                'pnl': None,
                'return_pct': None,
                'hold_days': None,
                'cumulative_pnl': round(cumulative_pnl, 2),
                'reason': sig['reason'],
            })

        elif sig['type'] == 'SELL' and open_pos is not None:
            shares = open_pos['shares']
            entry_price = open_pos['price']
            pnl = shares * (sig_price - entry_price)
            ret_pct = (sig_price - entry_price) / entry_price * 100
            hold_days = (sig_ts - open_pos['date']).days
            cumulative_pnl += pnl

            actions.append({
                'trade_num': open_pos['trade_num'],
                'action': 'SELL',
                'date': sig_ts.strftime('%Y-%m-%d'),
                'price': round(sig_price, 4),
                'shares': round(shares, 6),
                'value': round(shares * sig_price, 2),
                'pnl': round(pnl, 2),
                'return_pct': round(ret_pct, 2),
                'hold_days': hold_days,
                'cumulative_pnl': round(cumulative_pnl, 2),
                'reason': sig['reason'],
            })
            open_pos = None

    # Mark open position to last available price
    open_pos_out = None
    if open_pos is not None:
        last_price = float(close.iloc[-1])
        last_date = close.index[-1]
        shares = open_pos['shares']
        entry_price = open_pos['price']
        pnl = shares * (last_price - entry_price)
        ret_pct = (last_price - entry_price) / entry_price * 100
        hold_days = (last_date - open_pos['date']).days

        open_pos_out = {
            'trade_num': open_pos['trade_num'],
            'entry_date': open_pos['date'].strftime('%Y-%m-%d'),
            'entry_price': round(entry_price, 4),
            'current_price': round(last_price, 4),
            'shares': round(shares, 6),
            'unrealized_pnl': round(pnl, 2),
            'unrealized_return_pct': round(ret_pct, 2),
            'hold_days': hold_days,
        }

    # Summary
    sells = [a for a in actions if a['action'] == 'SELL']
    wins = [a for a in sells if a['pnl'] > 0]
    losses = [a for a in sells if a['pnl'] <= 0]

    realized_pnl = cumulative_pnl
    unrealized_pnl = open_pos_out['unrealized_pnl'] if open_pos_out else 0
    total_pnl = realized_pnl + unrealized_pnl

    # Buy-and-hold: invest same position_size at first available price, hold to last
    try:
        bh_start_price = float(close.iloc[0])
        bh_end_price = float(close.iloc[-1])
        bh_shares = position_size / bh_start_price
        bh_pnl = bh_shares * (bh_end_price - bh_start_price)
        bh_ret = (bh_end_price - bh_start_price) / bh_start_price * 100
    except Exception:
        bh_pnl = bh_ret = 0

    summary = {
        'starting_capital': round(capital, 2),
        'position_size': round(position_size, 2),
        'ending_capital': round(capital + total_pnl, 2),
        'realized_pnl': round(realized_pnl, 2),
        'unrealized_pnl': round(unrealized_pnl, 2),
        'total_pnl': round(total_pnl, 2),
        'total_return_pct': round(total_pnl / capital * 100, 2),
        'num_completed_trades': len(sells),
        'num_wins': len(wins),
        'num_losses': len(losses),
        'win_rate': round(len(wins) / len(sells) * 100, 1) if sells else 0,
        'avg_pnl': round(sum(a['pnl'] for a in sells) / len(sells), 2) if sells else 0,
        'best_trade': round(max((a['pnl'] for a in sells), default=0), 2),
        'worst_trade': round(min((a['pnl'] for a in sells), default=0), 2),
        'buy_hold_pnl': round(bh_pnl, 2),
        'buy_hold_return_pct': round(bh_ret, 2),
        'open_position': open_pos_out,
    }

    return actions, summary


# ── Route ─────────────────────────────────────────────────────────────────────

@backtest_bp.route('/api/backtest', methods=['POST'])
def run_backtest():
    body = request.get_json(force=True, silent=True) or {}
    ticker = body.get('ticker', '').strip().upper()
    strategy = body.get('strategy', 'bollinger-bands')
    start_str = body.get('start', '')
    end_str = body.get('end', '')
    capital = float(body.get('capital', 100000))
    position_pct = float(body.get('position_pct', 0.05))

    if not ticker:
        return jsonify({'error': 'Ticker is required'}), 400
    if not (0 < position_pct <= 1):
        return jsonify({'error': 'position_pct must be between 0 and 1'}), 400

    try:
        end_dt = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else datetime.today().date()
        start_dt = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else (end_dt - timedelta(days=365))
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    if start_dt >= end_dt:
        return jsonify({'error': 'Start date must be before end date'}), 400

    position_size = capital * position_pct

    # Fetch with warmup (90 days before start covers all rolling windows)
    fetch_start = start_dt - timedelta(days=90)

    try:
        raw = yf.download(ticker, start=fetch_start,
                          end=end_dt + timedelta(days=1),
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw['Close'].iloc[:, 0]
        else:
            close = raw['Close']
        close = close.dropna()
    except Exception as e:
        return jsonify({'error': f'Failed to download data for {ticker}: {str(e)}'}), 500

    if len(close) < 20:
        return jsonify({'error': f'Insufficient price data for {ticker}'}), 400

    # Compute signals
    if strategy == 'bollinger-bands':
        sigs = signals_bollinger(close)
    elif strategy == 'relative-strength':
        try:
            spy_raw = yf.download('SPY', start=fetch_start,
                                  end=end_dt + timedelta(days=1),
                                  auto_adjust=True, progress=False)
            if isinstance(spy_raw.columns, pd.MultiIndex):
                spy_close = spy_raw['Close'].iloc[:, 0]
            else:
                spy_close = spy_raw['Close']
            spy_close = spy_close.dropna()
        except Exception as e:
            return jsonify({'error': f'Failed to download SPY: {str(e)}'}), 500
        sigs = signals_relative_strength(close, spy_close)
    elif strategy == 'mean-reversion':
        sigs = signals_mean_reversion(close)
    elif strategy == 'post-earnings-drift':
        sigs = signals_pead(ticker, close, start_dt, end_dt)
    else:
        return jsonify({'error': f'Unknown strategy: {strategy}'}), 400

    # Restrict close series to user date range for simulation
    start_ts = pd.Timestamp(start_dt)
    end_ts = pd.Timestamp(end_dt)
    close_range = close[(close.index >= start_ts) & (close.index <= end_ts)]

    if len(close_range) == 0:
        return jsonify({'error': 'No price data in selected date range'}), 400

    actions, summary = run_simulation(sigs, close_range, start_dt, end_dt,
                                      capital, position_size)

    return jsonify({
        'actions': actions,
        'summary': summary,
        'ticker': ticker,
        'strategy': strategy,
        'start': start_dt.isoformat(),
        'end': end_dt.isoformat(),
    })
