"""
/api/analyst-data/<ticker>  —  Detailed analyst coverage data.

Returns price targets, recommendation counts & trend, upgrade/downgrade
history (with firm names), and earnings/revenue estimates.
"""

import math

import pandas as pd
from flask import Blueprint, jsonify

from data_fetcher import get_analyst_data, get_ticker_info

analyst_data_bp = Blueprint('analyst_data', __name__)


def _safe(val):
    """Convert NaN / Inf / numpy types to JSON-safe Python scalars."""
    if val is None:
        return None
    try:
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        # numpy int / float → plain Python
        if hasattr(val, 'item'):
            val = val.item()
        if isinstance(val, float):
            return round(val, 4)
        return val
    except Exception:
        return None


def _df_to_records(df):
    """Convert a DataFrame to a list of dicts with NaN → None."""
    if df is None or df.empty:
        return []
    records = []
    for idx, row in df.iterrows():
        rec = {}
        for col in df.columns:
            rec[col] = _safe(row[col])
        # Include the index (often a date or period label)
        if isinstance(idx, pd.Timestamp):
            rec['date'] = idx.strftime('%Y-%m-%d')
        elif isinstance(idx, str):
            rec['period'] = idx
        records.append(rec)
    return records


def _estimates_to_dict(df):
    """Convert earnings/revenue estimate DataFrame to {period: {field: val}}."""
    if df is None or df.empty:
        return {}
    result = {}
    for idx, row in df.iterrows():
        period_key = str(idx)
        result[period_key] = {col: _safe(row[col]) for col in df.columns}
    return result


@analyst_data_bp.route('/api/analyst-data/<ticker>')
def analyst_data(ticker):
    try:
        raw = get_analyst_data(ticker)
        info = get_ticker_info(ticker) or {}

        response = {'ticker': ticker.upper()}

        # ── Price targets ────────────────────────────────────────────
        pt = (raw or {}).get('price_targets')
        if pt and isinstance(pt, dict):
            response['priceTargets'] = {
                'current': _safe(pt.get('current')),
                'low': _safe(pt.get('low')),
                'high': _safe(pt.get('high')),
                'mean': _safe(pt.get('mean')),
                'median': _safe(pt.get('median')),
            }
        else:
            # Fallback to .info fields
            mean = info.get('targetMeanPrice')
            low = info.get('targetLowPrice')
            high = info.get('targetHighPrice')
            if mean is not None:
                response['priceTargets'] = {
                    'current': _safe(mean),
                    'low': _safe(low),
                    'high': _safe(high),
                    'mean': _safe(mean),
                    'median': _safe(info.get('targetMedianPrice')),
                }

        # ── Number of analysts ───────────────────────────────────────
        n = info.get('numberOfAnalystOpinions') or info.get('numberOfAnalystRatings')
        if n is not None:
            response['numberOfAnalysts'] = int(n)

        # ── Recommendation counts (current month) ────────────────────
        rec_summary = (raw or {}).get('recommendations_summary')
        if rec_summary is not None and not rec_summary.empty:
            trend_records = _df_to_records(rec_summary)
            response['recommendationTrend'] = trend_records
            # Current-month counts
            if trend_records:
                current = trend_records[0]
                counts = {
                    'strongBuy': current.get('strongBuy', 0) or 0,
                    'buy': current.get('buy', 0) or 0,
                    'hold': current.get('hold', 0) or 0,
                    'sell': current.get('sell', 0) or 0,
                    'strongSell': current.get('strongSell', 0) or 0,
                }
                counts['total'] = sum(counts.values())
                response['recommendationCounts'] = counts

        # ── Consensus recommendation from info ───────────────────────
        rec_key = info.get('recommendationKey') or ''
        response['consensusRecommendation'] = (
            rec_key.replace('_', ' ').title() if rec_key else 'N/A'
        )

        # ── Upgrades / downgrades ────────────────────────────────────
        ud = (raw or {}).get('upgrades_downgrades')
        if ud is not None and not ud.empty:
            ud_records = []
            for idx, row in ud.head(20).iterrows():
                rec = {
                    'firm': row.get('Firm') or row.get('firm', 'Unknown'),
                    'toGrade': row.get('ToGrade') or row.get('toGrade', ''),
                    'fromGrade': row.get('FromGrade') or row.get('fromGrade', ''),
                    'action': row.get('Action') or row.get('action', ''),
                }
                if isinstance(idx, pd.Timestamp):
                    rec['date'] = idx.strftime('%Y-%m-%d')
                elif hasattr(idx, 'strftime'):
                    rec['date'] = idx.strftime('%Y-%m-%d')
                else:
                    rec['date'] = str(idx)
                ud_records.append(rec)
            response['upgradesDowngrades'] = ud_records

        # ── Earnings estimates ───────────────────────────────────────
        ee = (raw or {}).get('earnings_estimate')
        if ee is not None and not ee.empty:
            response['earningsEstimate'] = _estimates_to_dict(ee)

        # ── Revenue estimates ────────────────────────────────────────
        re_ = (raw or {}).get('revenue_estimate')
        if re_ is not None and not re_.empty:
            response['revenueEstimate'] = _estimates_to_dict(re_)

        return jsonify(response)

    except Exception as e:
        return jsonify({'error': str(e)}), 500
