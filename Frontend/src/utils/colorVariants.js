/**
 * Shared color-variant helpers for Badge / status displays.
 *
 * Previously duplicated verbatim across Recommendations.js and Watchlist.js
 * (and with subtle "Color" vs "Variant" naming divergence in StockInfo.js
 * for its own display strings).
 *
 * All exports take canonical lower_snake or upper-case-status inputs
 * matching what `/api/recommendations` and `/api/stock-info` return, and
 * resolve to one of: 'green' | 'red' | 'blue' | 'yellow' | 'gray'.
 */

export function recVariant(recKey) {
  if (!recKey) return 'gray';
  if (recKey === 'strong_buy' || recKey === 'buy') return 'green';
  if (recKey === 'hold') return 'blue';
  if (recKey === 'sell' || recKey === 'strong_sell') return 'red';
  return 'gray';
}

export function macdVariant(status) {
  if (!status) return 'gray';
  if (status.includes('BULLISH')) return 'green';
  if (status.includes('BEARISH')) return 'red';
  return 'gray';
}

export function trendVariant(trend) {
  if (!trend) return 'gray';
  if (trend.includes('Uptrend') || trend.includes('Bullish')) return 'green';
  if (trend.includes('Downtrend') || trend.includes('Bearish')) return 'red';
  return 'yellow';
}

export function volVariant(vol) {
  if (!vol) return 'gray';
  if (vol.includes('HIGH')) return 'red';
  if (vol.includes('LOW')) return 'green';
  return 'yellow';
}

export function priceActionVariant(pa) {
  if (!pa) return 'gray';
  if (pa === 'Overbought') return 'red';
  if (pa === 'Oversold') return 'green';
  if (pa === 'Trending') return 'blue';
  if (pa === 'Consolidating') return 'yellow';
  return 'gray';
}
