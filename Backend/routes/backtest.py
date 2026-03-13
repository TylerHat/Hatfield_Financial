import pandas as pd
import numpy as np
import yfinance as yf
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

backtest_bp = Blueprint('backtest', __name__)


def _compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float('nan'))
    return 100 - (100 / (1 + rs))


def _get_signals_bollinger(hist, user_start):
    hist = hist.copy()
    hist['MA20'] = hist['Close'].rolling(20).mean()
    hist['STD20'] = hist['Close'].rolling(20).std()
    hist['Upper'] = hist['MA20'] + 2 * hist['STD20']
    hist['Lower'] = hist['MA20'] - 2 * hist['STD20']
    hist['VolMA20'] = hist['Volume'].rolling(20).mean()

    cutoff = pd.Timestamp(user_start).tz_localize('UTC')
    if hist.index.tz is None:
        cutoff = cutoff.tz_localize(None)
    hist = hist[hist.index >= cutoff]

    signals = []
    for i in range(1, len(hist)):
        row = hist.iloc[i]
        prev = hist.iloc[i - 1]
        if pd.isna(row['Upper']) or pd.isna(row['Lower']):
            continue
        band_width = float(row['Upper'] - row['Lower'])
        vol_confirmed = (
            not pd.isna(row['VolMA20']) and float(row['VolMA20']) > 0
            and float(row['Volume']) > 1.3 * float(row['VolMA20'])
        )
        if prev['Close'] >= prev['Lower'] and row['Close'] < row['Lower'] and vol_confirmed:
            signals.append({'date': hist.index[i].strftime('%Y-%m-%d'), 'price': float(row['Close']), 'type': 'BUY'})
        elif prev['Close'] <= prev['Upper'] and row['Close'] > row['Upper'] and vol_confirmed:
            signals.append({'date': hist.index[i].strftime('%Y-%m-%d'), 'price': float(row['Close']), 'type': 'SELL'})
    return signals


def _get_signals_rsi(hist, user_start):
    hist = hist.copy()
    hist['RSI'] = _compute_rsi(hist['Close'])

    cutoff = pd.Timestamp(user_start).tz_localize('UTC')
    if hist.index.tz is None:
        cutoff = cutoff.tz_localize(None)
    hist = hist[hist.index >= cutoff]

    signals = []
    for i in range(1, len(hist)):
        row = hist.iloc[i]
        prev = hist.iloc[i - 1]
        if pd.isna(row['RSI']) or pd.isna(prev['RSI']):
            continue
        rsi = float(row['RSI'])
        prev_rsi = float(prev['RSI'])
        if prev_rsi >= 30 and rsi < 30:
            signals.append({'date': hist.index[i].strftime('%Y-%m-%d'), 'price': float(row['Close']), 'type': 'BUY'})
        elif prev_rsi <= 70 and rsi > 70:
            signals.append({'date': hist.index[i].strftime('%Y-%m-%d'), 'price': float(row['Close']), 'type': 'SELL'})
    return signals


def _get_signals_macd(hist, user_start):
    hist = hist.copy()
    ema12 = hist['Close'].ewm(span=12, adjust=False).mean()
    ema26 = hist['Close'].ewm(span=26, adjust=False).mean()
    hist['MACD'] = ema12 - ema26
    hist['Signal'] = hist['MACD'].ewm(span=9, adjust=False).mean()

    cutoff = pd.Timestamp(user_start).tz_localize('UTC')
    if hist.index.tz is None:
        cutoff = cutoff.tz_localize(None)
    hist = hist[hist.index >= cutoff]

    signals = []
    for i in range(1, len(hist)):
        row = hist.iloc[i]
        prev = hist.iloc[i - 1]
        if pd.isna(row['MACD']) or pd.isna(row['Signal']) or pd.isna(prev['MACD']) or pd.isna(prev['Signal']):
            continue
        if prev['MACD'] <= prev['Signal'] and row['MACD'] > row['Signal']:
            signals.append({'date': hist.index[i].strftime('%Y-%m-%d'), 'price': float(row['Close']), 'type': 'BUY'})
        elif prev['MACD'] >= prev['Signal'] and row['MACD'] < row['Signal']:
            signals.append({'date': hist.index[i].strftime('%Y-%m-%d'), 'price': float(row['Close']), 'type': 'SELL'})
    return signals


def _get_signals_mean_reversion(hist, user_start):
    hist = hist.copy()
    hist['MA200'] = hist['Close'].rolling(200).mean()
    hist['High20'] = hist['Close'].rolling(20).max()
    hist['Drawdown'] = (hist['Close'] - hist['High20']) / hist['High20']

    cutoff = pd.Timestamp(user_start).tz_localize('UTC')
    if hist.index.tz is None:
        cutoff = cutoff.tz_localize(None)
    hist = hist[hist.index >= cutoff]

    signals = []
    in_drawdown = False
    for i in range(len(hist)):
        row = hist.iloc[i]
        if pd.isna(row['Drawdown']):
            continue
        drawdown_pct = float(row['Drawdown'])
        ma200 = row['MA200']
        in_uptrend = not pd.isna(ma200) and float(row['Close']) > float(ma200)
        if not in_drawdown and drawdown_pct <= -0.10 and in_uptrend:
            signals.append({'date': hist.index[i].strftime('%Y-%m-%d'), 'price': float(row['Close']), 'type': 'BUY'})
            in_drawdown = True
        elif in_drawdown and drawdown_pct > -0.03:
            signals.append({'date': hist.index[i].strftime('%Y-%m-%d'), 'price': float(row['Close']), 'type': 'SELL'})
            in_drawdown = False
    return signals


def _get_signals_relative_strength(ticker, hist, user_start, end):
    spy = yf.Ticker('SPY')
    fetch_start = user_start - timedelta(days=20)
    spy_hist = spy.history(start=fetch_start, end=end)

    combined = pd.DataFrame({'stock': hist['Close'], 'spy': spy_hist['Close']}).dropna()
    combined['rs'] = combined['stock'] / combined['spy']
    combined['rs_ma'] = combined['rs'].rolling(10).mean()

    cutoff = pd.Timestamp(user_start).tz_localize('UTC')
    if combined.index.tz is None:
        cutoff = cutoff.tz_localize(None)
    combined = combined[combined.index >= cutoff]

    signals = []
    for i in range(1, len(combined)):
        row = combined.iloc[i]
        prev = combined.iloc[i - 1]
        if pd.isna(row['rs_ma']) or pd.isna(prev['rs_ma']):
            continue
        if prev['rs'] <= prev['rs_ma'] and row['rs'] > row['rs_ma']:
            signals.append({'date': combined.index[i].strftime('%Y-%m-%d'), 'price': float(row['stock']), 'type': 'BUY'})
        elif prev['rs'] >= prev['rs_ma'] and row['rs'] < row['rs_ma']:
            signals.append({'date': combined.index[i].strftime('%Y-%m-%d'), 'price': float(row['stock']), 'type': 'SELL'})
    return signals


def _simulate_trades(signals, hist, starting_capital):
    """Simulate trades based on BUY/SELL signals. Returns trades and equity curve."""
    # Build a price lookup by date string
    price_by_date = {}
    for ts, row in hist.iterrows():
        ds = ts.strftime('%Y-%m-%d') if hasattr(ts, 'strftime') else str(ts)[:10]
        price_by_date[ds] = float(row['Close'])

    trades = []
    cash = float(starting_capital)
    shares = 0
    entry_price = None
    entry_date = None

    for sig in signals:
        sig_date = sig['date']
        sig_price = sig['price']
        sig_type = sig['type']

        if sig_type == 'BUY' and cash > 0 and shares == 0:
            shares = int(cash / sig_price)
            if shares == 0:
                continue
            cost = shares * sig_price
            cash -= cost
            entry_price = sig_price
            entry_date = sig_date

        elif sig_type == 'SELL' and shares > 0:
            value = shares * sig_price
            pnl = value - (shares * entry_price)
            pnl_pct = ((sig_price - entry_price) / entry_price) * 100 if entry_price else 0
            trades.append({
                'date': sig_date,
                'type': 'SELL',
                'entryDate': entry_date,
                'entryPrice': round(entry_price, 2),
                'price': round(sig_price, 2),
                'shares': shares,
                'value': round(value, 2),
                'pnl': round(pnl, 2),
                'pnlPct': round(pnl_pct, 2),
                'status': 'CLOSED',
            })
            cash += value
            shares = 0
            entry_price = None
            entry_date = None

    # Handle unrealized position at end
    unrealized_pnl = 0
    unrealized_pnl_pct = 0
    has_unrealized = False
    if shares > 0 and entry_price is not None:
        # Find last available price
        last_dates = sorted(price_by_date.keys())
        last_price = price_by_date[last_dates[-1]] if last_dates else entry_price
        value = shares * last_price
        pnl = value - (shares * entry_price)
        pnl_pct = ((last_price - entry_price) / entry_price) * 100 if entry_price else 0
        unrealized_pnl = round(pnl, 2)
        unrealized_pnl_pct = round(pnl_pct, 2)
        has_unrealized = True
        trades.append({
            'date': last_dates[-1] if last_dates else entry_date,
            'type': 'SELL',
            'entryDate': entry_date,
            'entryPrice': round(entry_price, 2),
            'price': round(last_price, 2),
            'shares': shares,
            'value': round(value, 2),
            'pnl': round(pnl, 2),
            'pnlPct': round(pnl_pct, 2),
            'status': 'UNREALIZED',
        })
        cash += value

    return trades, cash, unrealized_pnl, unrealized_pnl_pct, has_unrealized


def _build_equity_curve(hist, signals, starting_capital):
    """Build daily portfolio value series."""
    cash = float(starting_capital)
    shares = 0
    entry_price = None

    # Index signals by date for quick lookup
    signal_map = {}
    for sig in signals:
        signal_map[sig['date']] = sig

    curve = []
    for ts, row in hist.iterrows():
        ds = ts.strftime('%Y-%m-%d') if hasattr(ts, 'strftime') else str(ts)[:10]
        price = float(row['Close'])

        sig = signal_map.get(ds)
        if sig:
            if sig['type'] == 'BUY' and cash > 0 and shares == 0:
                new_shares = int(cash / sig['price'])
                if new_shares > 0:
                    cash -= new_shares * sig['price']
                    shares = new_shares
                    entry_price = sig['price']
            elif sig['type'] == 'SELL' and shares > 0:
                cash += shares * sig['price']
                shares = 0
                entry_price = None

        portfolio_value = cash + (shares * price)
        curve.append({'date': ds, 'value': round(portfolio_value, 2)})

    return curve


def _compute_summary(trades, equity_curve, starting_capital, unrealized_pnl, unrealized_pnl_pct, has_unrealized):
    closed = [t for t in trades if t['status'] == 'CLOSED']
    num_wins = sum(1 for t in closed if t['pnl'] > 0)
    num_losses = sum(1 for t in closed if t['pnl'] <= 0)
    num_trades = len(closed)

    win_rate = (num_wins / num_trades * 100) if num_trades > 0 else 0

    wins_pct = [t['pnlPct'] for t in closed if t['pnl'] > 0]
    losses_pct = [t['pnlPct'] for t in closed if t['pnl'] <= 0]

    avg_win_pct = sum(wins_pct) / len(wins_pct) if wins_pct else 0
    avg_loss_pct = sum(losses_pct) / len(losses_pct) if losses_pct else 0

    gross_profit = sum(t['pnl'] for t in closed if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in closed if t['pnl'] <= 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0)

    best_trade = max((t['pnlPct'] for t in closed), default=0)
    worst_trade = min((t['pnlPct'] for t in closed), default=0)

    # Max drawdown from equity curve
    max_drawdown = 0
    if equity_curve:
        values = [p['value'] for p in equity_curve]
        peak = values[0]
        for v in values:
            if v > peak:
                peak = v
            dd = (v - peak) / peak * 100 if peak > 0 else 0
            if dd < max_drawdown:
                max_drawdown = dd

    final_value = equity_curve[-1]['value'] if equity_curve else starting_capital
    # If has unrealized, final value already includes unrealized
    total_return = ((final_value - starting_capital) / starting_capital * 100) if starting_capital > 0 else 0
    total_return_dollar = final_value - starting_capital

    return {
        'startingCapital': round(starting_capital, 2),
        'finalValue': round(final_value, 2),
        'totalReturn': round(total_return, 2),
        'totalReturnDollar': round(total_return_dollar, 2),
        'winRate': round(win_rate, 2),
        'numTrades': num_trades,
        'numWins': num_wins,
        'numLosses': num_losses,
        'avgWinPct': round(avg_win_pct, 2),
        'avgLossPct': round(avg_loss_pct, 2),
        'profitFactor': round(profit_factor, 2) if profit_factor != float('inf') else None,
        'bestTrade': round(best_trade, 2),
        'worstTrade': round(worst_trade, 2),
        'maxDrawdown': round(max_drawdown, 2),
        'unrealizedPnl': round(unrealized_pnl, 2),
        'unrealizedPnlPct': round(unrealized_pnl_pct, 2),
        'hasUnrealized': has_unrealized,
    }


@backtest_bp.route('/api/backtest/<ticker>')
def run_backtest(ticker):
    try:
        strategy = request.args.get('strategy', 'bollinger-bands')
        end_str = request.args.get('end')
        start_str = request.args.get('start')
        capital_str = request.args.get('capital', '10000')

        try:
            starting_capital = float(capital_str)
        except (ValueError, TypeError):
            starting_capital = 10000.0

        end = datetime.strptime(end_str, '%Y-%m-%d') if end_str else datetime.today()
        user_start = datetime.strptime(start_str, '%Y-%m-%d') if start_str else end - timedelta(days=182)

        # Determine warmup based on strategy
        warmup_map = {
            'bollinger-bands': 40,
            'rsi': 60,
            'macd-crossover': 90,
            'mean-reversion': 280,
            'relative-strength': 20,
        }
        warmup_days = warmup_map.get(strategy, 60)
        fetch_start = user_start - timedelta(days=warmup_days)

        stock = yf.Ticker(ticker.upper())
        hist = stock.history(start=fetch_start, end=end)

        if hist.empty:
            return jsonify({'error': f'No price data found for "{ticker.upper()}".'}), 404

        # Generate signals inline for each strategy
        if strategy == 'bollinger-bands':
            signals = _get_signals_bollinger(hist, user_start)
        elif strategy == 'rsi':
            signals = _get_signals_rsi(hist, user_start)
        elif strategy == 'macd-crossover':
            signals = _get_signals_macd(hist, user_start)
        elif strategy == 'mean-reversion':
            signals = _get_signals_mean_reversion(hist, user_start)
        elif strategy == 'relative-strength':
            signals = _get_signals_relative_strength(ticker, hist, user_start, end)
        else:
            return jsonify({'error': f'Unknown strategy: {strategy}'}), 400

        # Trim hist to user window for equity curve and trade simulation
        cutoff = pd.Timestamp(user_start).tz_localize('UTC')
        if hist.index.tz is None:
            cutoff = cutoff.tz_localize(None)
        hist_user = hist[hist.index >= cutoff]

        trades, final_cash, unrealized_pnl, unrealized_pnl_pct, has_unrealized = _simulate_trades(
            signals, hist_user, starting_capital
        )
        equity_curve = _build_equity_curve(hist_user, signals, starting_capital)
        summary = _compute_summary(
            trades, equity_curve, starting_capital,
            unrealized_pnl, unrealized_pnl_pct, has_unrealized
        )

        return jsonify({
            'trades': trades,
            'equityCurve': equity_curve,
            'summary': summary,
        })

    except Exception as e:
        msg = str(e)
        if 'rate' in msg.lower() or '429' in msg:
            msg = 'Yahoo Finance rate limit reached. Wait a moment and try again.'
        elif 'connection' in msg.lower() or 'timeout' in msg.lower():
            msg = 'Could not reach Yahoo Finance. Check your network connection.'
        return jsonify({'error': msg}), 500
