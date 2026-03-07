from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf
from flask import Blueprint, jsonify, request

from data.sp500_tickers import SP500_TICKERS

backtest_bp = Blueprint('backtest', __name__)


# ── Single-stock signal generators ────────────────────────────────────────────

def signals_bollinger(close):
    """BUY when price crosses below lower band; SELL when crosses above upper."""
    sma = close.rolling(20).mean()
    std = close.rolling(20).std()
    lower = sma - 2 * std
    upper = sma + 2 * std

    # Vectorized crossover detection using shift()
    is_below = close < lower
    is_above = close > upper
    valid = lower.notna() & upper.notna()

    # Crossed below today but was not below yesterday -> BUY
    buy_mask = (is_below & ~is_below.shift(1, fill_value=False)) & valid
    # Crossed above today but was not above yesterday -> SELL
    sell_mask = (is_above & ~is_above.shift(1, fill_value=False)) & valid

    signals = []
    for date in close.index[buy_mask]:
        price = float(close.loc[date])
        lb = float(lower.loc[date])
        signals.append({'date': date, 'type': 'BUY', 'price': price,
                        'reason': f'Price crossed below lower band (${lb:.2f})'})

    for date in close.index[sell_mask]:
        price = float(close.loc[date])
        ub = float(upper.loc[date])
        signals.append({'date': date, 'type': 'SELL', 'price': price,
                        'reason': f'Price crossed above upper band (${ub:.2f})'})

    signals.sort(key=lambda s: s['date'])
    return signals

def signals_relative_strength(close, spy_close):
    """BUY when RS ratio crosses above its 10-day MA; SELL when crosses below."""
    aligned = pd.DataFrame({'stock': close, 'spy': spy_close}).dropna()
    if aligned.empty:
        return []

    rs = aligned['stock'] / aligned['spy']
    rs_ma = rs.rolling(10).mean()

    # Vectorized crossover detection
    is_above = rs > rs_ma
    valid = rs_ma.notna()
    # Require previous row also valid (skip first valid row, matching original behavior)
    both_valid = valid & valid.shift(1, fill_value=False)

    # Crossed above today but was not above yesterday -> BUY
    buy_mask = (is_above & ~is_above.shift(1, fill_value=False)) & both_valid
    # Was above yesterday but is not today -> SELL
    sell_mask = (~is_above & is_above.shift(1, fill_value=False)) & both_valid

    signals = []
    for date in aligned.index[buy_mask]:
        price = float(aligned['stock'].loc[date])
        signals.append({'date': date, 'type': 'BUY', 'price': price,
                        'reason': 'RS ratio crossed above 10-day MA — outperforming market'})

    for date in aligned.index[sell_mask]:
        price = float(aligned['stock'].loc[date])
        signals.append({'date': date, 'type': 'SELL', 'price': price,
                        'reason': 'RS ratio crossed below 10-day MA — underperforming market'})

    signals.sort(key=lambda s: s['date'])
    return signals

def signals_mean_reversion(close):
    """BUY at ≥10% drawdown from 20-day high; SELL when within 3% of high."""
    rolling_high = close.rolling(20).max()
    valid = rolling_high.notna()
    dd = (close - rolling_high) / rolling_high

    # Pre-filter: only iterate dates that could trigger a signal
    in_buy_zone = dd <= -0.10
    in_sell_zone = dd >= -0.03
    candidate_mask = (in_buy_zone | in_sell_zone) & valid
    candidates = close.index[candidate_mask]

    signals = []
    in_drawdown = False
    for date in candidates:
        d = float(dd.loc[date])
        price = float(close.loc[date])
        high = float(rolling_high.loc[date])

        if not in_drawdown and d <= -0.10:
            signals.append({'date': date, 'type': 'BUY', 'price': price,
                            'reason': f'Drawdown {d*100:.1f}% from 20-day high (${high:.2f})'})
            in_drawdown = True
        elif in_drawdown and d >= -0.03:
            signals.append({'date': date, 'type': 'SELL', 'price': price,
                            'reason': f'Recovered to within {abs(d)*100:.1f}% of 20-day high (${high:.2f})'})
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


# ── Simulation engine (single stock) ──────────────────────────────────────────

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


# ── Portfolio helpers (vectorized signal computation) ─────────────────────────

def _precompute_bb_signals(close_frame):
    """Vectorized Bollinger Bands: strong buy = below lower band, strong sell = above upper."""
    sma = close_frame.rolling(20).mean()
    std = close_frame.rolling(20).std()
    lower = sma - 2 * std
    upper = sma + 2 * std
    band_width = upper - lower
    pct_b = (close_frame - lower) / band_width
    return (pct_b < 0).fillna(False), (pct_b > 1).fillna(False)


def _precompute_rs_signals(close_frame, spy_close):
    """Vectorized Relative Strength: strong buy = RS above MA & rising, strong sell = below & falling."""
    rs = close_frame.div(spy_close, axis=0)
    rs_ma = rs.rolling(10).mean()
    slope = rs_ma.diff(5)
    ma_safe = rs_ma.abs().where(rs_ma.abs() > 1e-10, np.nan)
    pct_diff = (rs - rs_ma) / ma_safe
    strong_buy = ((pct_diff > 0.005) & (slope > 0)).fillna(False)
    strong_sell = ((pct_diff < -0.005) & (slope < 0)).fillna(False)
    return strong_buy, strong_sell


def _precompute_mr_signals(close_frame):
    """Vectorized Mean Reversion: strong buy = ≥15% drawdown, strong sell = within 2% of high."""
    rolling_high = close_frame.rolling(20).max()
    high_safe = rolling_high.where(rolling_high > 1e-10, np.nan)
    drawdown = (close_frame - rolling_high) / high_safe
    return (drawdown <= -0.15).fillna(False), (drawdown > -0.02).fillna(False)


def _precompute_pead_signals(close_frame):
    """Vectorized PEAD proxy: 3%+ gap + 2-day follow-through in same direction."""
    returns = close_frame.pct_change()
    gap_up = returns >= 0.03
    gap_down = returns <= -0.03
    strong_buy = (gap_up.shift(2) & (returns.shift(1) > 0) & (returns > 0)).fillna(False)
    strong_sell = (gap_down.shift(2) & (returns.shift(1) < 0) & (returns < 0)).fillna(False)
    return strong_buy, strong_sell


def _run_portfolio_sim(strong_buy_df, strong_sell_df, close_frame,
                       start_dt, end_dt, capital, position_size):
    """
    Simulate portfolio across S&P 500.
    On each Monday and Wednesday: sell strong-sell holdings, then buy strong-buy signals.
    One position per ticker at a time; buys limited by available cash.
    """
    start_ts = pd.Timestamp(start_dt)
    end_ts = pd.Timestamp(end_dt)

    mask = (close_frame.index >= start_ts) & (close_frame.index <= end_ts)
    close_range = close_frame[mask]
    sb = strong_buy_df.reindex(close_range.index).fillna(False)
    ss = strong_sell_df.reindex(close_range.index).fillna(False)

    # Only Mondays (0) and Wednesdays (2)
    trading_days = close_range.index[close_range.index.dayofweek.isin([0, 2])]

    actions = []
    trade_count = 0
    positions = {}       # ticker → {trade_num, date, price, shares}
    cash = float(capital)
    cumulative_pnl = 0.0
    max_simultaneous = 0
    unique_tickers = set()

    for date in trading_days:
        # SELLS first (free up cash before buying)
        for ticker in sorted(list(positions.keys())):
            if ticker not in ss.columns:
                continue
            try:
                if not ss.loc[date, ticker]:
                    continue
                price = float(close_range.loc[date, ticker])
            except (KeyError, ValueError, TypeError):
                continue
            if pd.isna(price):
                continue

            pos = positions[ticker]
            shares = pos['shares']
            pnl = shares * (price - pos['price'])
            ret_pct = (price - pos['price']) / pos['price'] * 100
            hold_days = (date - pos['date']).days
            cumulative_pnl += pnl
            cash += shares * price

            actions.append({
                'trade_num': pos['trade_num'],
                'ticker': ticker,
                'action': 'SELL',
                'date': date.strftime('%Y-%m-%d'),
                'price': round(price, 4),
                'shares': round(shares, 6),
                'value': round(shares * price, 2),
                'pnl': round(pnl, 2),
                'return_pct': round(ret_pct, 2),
                'hold_days': hold_days,
                'cumulative_pnl': round(cumulative_pnl, 2),
            })
            del positions[ticker]

        # BUYS (sorted alphabetically for determinism)
        if date in sb.index:
            buy_row = sb.loc[date]
            buy_tickers = sorted(buy_row[buy_row.astype(bool)].index.tolist())
            for ticker in buy_tickers:
                if ticker in positions:
                    continue
                if cash < position_size:
                    break  # insufficient cash
                try:
                    price = float(close_range.loc[date, ticker])
                except (KeyError, ValueError, TypeError):
                    continue
                if pd.isna(price):
                    continue

                trade_count += 1
                shares = position_size / price
                cash -= position_size
                positions[ticker] = {
                    'trade_num': trade_count,
                    'date': date,
                    'price': price,
                    'shares': shares,
                }
                unique_tickers.add(ticker)
                max_simultaneous = max(max_simultaneous, len(positions))

                actions.append({
                    'trade_num': trade_count,
                    'ticker': ticker,
                    'action': 'BUY',
                    'date': date.strftime('%Y-%m-%d'),
                    'price': round(price, 4),
                    'shares': round(shares, 6),
                    'value': round(position_size, 2),
                    'pnl': None,
                    'return_pct': None,
                    'hold_days': None,
                    'cumulative_pnl': round(cumulative_pnl, 2),
                })

    # Mark open positions to last available price
    open_positions_out = []
    unrealized_total = 0.0
    open_market_value = 0.0

    for ticker, pos in positions.items():
        if ticker not in close_range.columns:
            continue
        series = close_range[ticker].dropna()
        if series.empty:
            continue
        last_price = float(series.iloc[-1])
        last_date = series.index[-1]
        shares = pos['shares']
        pnl = shares * (last_price - pos['price'])
        ret_pct = (last_price - pos['price']) / pos['price'] * 100
        hold_days = (last_date - pos['date']).days
        unrealized_total += pnl
        open_market_value += shares * last_price
        unique_tickers.add(ticker)

        open_positions_out.append({
            'trade_num': pos['trade_num'],
            'ticker': ticker,
            'entry_date': pos['date'].strftime('%Y-%m-%d'),
            'entry_price': round(pos['price'], 4),
            'current_price': round(last_price, 4),
            'shares': round(shares, 6),
            'unrealized_pnl': round(pnl, 2),
            'unrealized_return_pct': round(ret_pct, 2),
            'hold_days': hold_days,
        })

    sells = [a for a in actions if a['action'] == 'SELL']
    wins = [a for a in sells if a['pnl'] > 0]
    losses = [a for a in sells if a['pnl'] <= 0]
    realized_pnl = cumulative_pnl
    total_pnl = realized_pnl + unrealized_total

    summary = {
        'starting_capital': round(capital, 2),
        'position_size': round(position_size, 2),
        'ending_cash': round(cash, 2),
        'open_positions_value': round(open_market_value, 2),
        'ending_portfolio_value': round(cash + open_market_value, 2),
        'realized_pnl': round(realized_pnl, 2),
        'unrealized_pnl': round(unrealized_total, 2),
        'total_pnl': round(total_pnl, 2),
        'total_return_pct': round(total_pnl / capital * 100, 2),
        'num_completed_trades': len(sells),
        'num_wins': len(wins),
        'num_losses': len(losses),
        'win_rate': round(len(wins) / len(sells) * 100, 1) if sells else 0,
        'avg_pnl': round(sum(a['pnl'] for a in sells) / len(sells), 2) if sells else 0,
        'best_trade': round(max((a['pnl'] for a in sells), default=0), 2),
        'worst_trade': round(min((a['pnl'] for a in sells), default=0), 2),
        'num_unique_tickers': len(unique_tickers),
        'num_open_positions': len(open_positions_out),
        'max_simultaneous_positions': max_simultaneous,
        'open_positions': open_positions_out,
    }

    return actions, summary


def _handle_portfolio_backtest(body):
    strategy = body.get('strategy', 'bollinger-bands')
    start_str = body.get('start', '')
    end_str = body.get('end', '')
    capital = float(body.get('capital', 100000))
    position_pct = float(body.get('position_pct', 0.05))

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
    fetch_start = start_dt - timedelta(days=90)

    # Download all S&P 500 + SPY in one batch
    all_tickers = SP500_TICKERS + ['SPY']
    try:
        raw = yf.download(
            all_tickers,
            start=fetch_start,
            end=end_dt + timedelta(days=1),
            auto_adjust=True,
            progress=False,
            group_by='column',
            threads=True,
        )
        if isinstance(raw.columns, pd.MultiIndex):
            close_frame = raw['Close']
        else:
            close_frame = raw[['Close']].rename(columns={'Close': all_tickers[0]})
        close_frame = close_frame.dropna(how='all')
    except Exception as e:
        return jsonify({'error': f'Failed to download market data: {str(e)}'}), 500

    if len(close_frame) < 20:
        return jsonify({'error': 'Insufficient price data for the selected date range'}), 400

    # Separate SPY from stock universe
    spy_close = close_frame['SPY'] if 'SPY' in close_frame.columns else None
    stock_frame = close_frame.drop(columns=['SPY'], errors='ignore')

    # Compute vectorized signals
    if strategy == 'bollinger-bands':
        sb_df, ss_df = _precompute_bb_signals(stock_frame)
    elif strategy == 'relative-strength':
        if spy_close is None:
            return jsonify({'error': 'SPY data unavailable for relative strength strategy'}), 500
        sb_df, ss_df = _precompute_rs_signals(stock_frame, spy_close)
    elif strategy == 'mean-reversion':
        sb_df, ss_df = _precompute_mr_signals(stock_frame)
    elif strategy == 'post-earnings-drift':
        sb_df, ss_df = _precompute_pead_signals(stock_frame)
    else:
        return jsonify({'error': f'Unknown strategy: {strategy}'}), 400

    # SPY buy-and-hold comparison (full capital invested at period start)
    spy_bh_pnl = spy_bh_ret = 0.0
    try:
        if spy_close is not None:
            spy_range = spy_close[
                (spy_close.index >= pd.Timestamp(start_dt)) &
                (spy_close.index <= pd.Timestamp(end_dt))
            ].dropna()
            if len(spy_range) >= 2:
                spy_start_price = float(spy_range.iloc[0])
                spy_end_price = float(spy_range.iloc[-1])
                bh_shares = capital / spy_start_price
                spy_bh_pnl = bh_shares * (spy_end_price - spy_start_price)
                spy_bh_ret = (spy_end_price - spy_start_price) / spy_start_price * 100
    except Exception:
        pass

    actions, summary = _run_portfolio_sim(
        sb_df, ss_df, stock_frame, start_dt, end_dt, capital, position_size
    )

    summary['buy_hold_pnl'] = round(spy_bh_pnl, 2)
    summary['buy_hold_return_pct'] = round(spy_bh_ret, 2)

    return jsonify({
        'mode': 'portfolio',
        'actions': actions,
        'summary': summary,
        'strategy': strategy,
        'start': start_dt.isoformat(),
        'end': end_dt.isoformat(),
    })


# ── Route ─────────────────────────────────────────────────────────────────────

@backtest_bp.route('/api/backtest', methods=['POST'])
def run_backtest():
    body = request.get_json(force=True, silent=True) or {}

    # Portfolio mode: simulate across entire S&P 500
    if body.get('mode') == 'portfolio':
        return _handle_portfolio_backtest(body)

    # Single-stock mode (existing logic)
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
        'mode': 'single',
        'actions': actions,
        'summary': summary,
        'ticker': ticker,
        'strategy': strategy,
        'start': start_dt.isoformat(),
        'end': end_dt.isoformat(),
    })
