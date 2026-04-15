import React from 'react';

function fmt(val, prefix = '', suffix = '', fallback = 'N/A') {
  if (val === null || val === undefined) return fallback;
  return `${prefix}${val}${suffix}`;
}

function MetricRow({ label, value }) {
  return (
    <div className="metric-row">
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value ?? 'N/A'}</span>
    </div>
  );
}

function StatusBadge({ text, color }) {
  // color: 'green' | 'yellow' | 'red' | 'blue' | 'gray'
  return <span className={`status-badge status-${color}`}>{text}</span>;
}

function valuationColor(v) {
  if (!v || v === 'N/A') return 'gray';
  if (v === 'Potentially Undervalued' || v === 'Fairly Valued') return 'green';
  if (v === 'Slightly Overvalued') return 'yellow';
  if (v === 'Potentially Overvalued' || v === 'Not Profitable') return 'red';
  return 'gray';
}

function rsiColor(sig) {
  if (sig === 'Overbought') return 'red';
  if (sig === 'Oversold') return 'green';
  if (sig === 'Neutral') return 'blue';
  return 'gray';
}

function consolidationColor(status) {
  if (status === 'Strong Consolidation' || status === 'Consolidating') return 'yellow';
  if (status === 'Expanding / Trending') return 'blue';
  if (status === 'Neutral') return 'gray';
  return 'gray';
}

function recColor(rec) {
  if (!rec || rec === 'N/A') return 'gray';
  const r = rec.toLowerCase();
  if (r.includes('strong buy') || r.includes('buy')) return 'green';
  if (r.includes('strong sell') || r.includes('sell')) return 'red';
  if (r.includes('hold') || r.includes('neutral')) return 'yellow';
  return 'gray';
}

function macdColor(status) {
  if (!status) return 'gray';
  if (status === 'BULLISH CROSSOVER' || status === 'BULLISH') return 'green';
  if (status === 'BEARISH CROSSOVER' || status === 'BEARISH') return 'red';
  return 'gray';
}

function volatilityColor(status) {
  if (!status) return 'gray';
  if (status === 'HIGH Volatility') return 'red';
  if (status === 'LOW Volatility') return 'green';
  return 'yellow';
}

function trendColor(status) {
  if (!status) return 'gray';
  if (status === 'Strong Uptrend') return 'green';
  if (status === 'Strong Downtrend') return 'red';
  if (status.includes('Bullish')) return 'green';
  if (status.includes('Bearish')) return 'red';
  return 'gray';
}

function relStrengthColor(val) {
  if (val == null) return 'gray';
  if (val > 5) return 'green';
  if (val < -5) return 'red';
  return 'yellow';
}

function divHealthColor(health) {
  if (!health) return 'gray';
  if (health === 'Very Healthy' || health === 'Healthy') return 'green';
  if (health === 'Moderate') return 'yellow';
  if (health === 'Stretched' || health === 'Unsustainable') return 'red';
  return 'gray';
}

export default function StockInfo({ ticker, stockInfoData, stockInfoLoading, stockInfoError, hideOverview = false }) {
  const info = stockInfoData;
  const loading = stockInfoLoading;
  const error = stockInfoError;

  if (error) return <div className="info-error">{error}</div>;
  if (!info) return null;

  const rsiPct = info.rsi !== null ? Math.min(Math.max(info.rsi, 0), 100) : null;

  return (
    <div className="stock-info" style={{ opacity: loading ? 0.6 : 1, transition: 'opacity 0.2s' }}>
      {loading && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          backgroundColor: '#238636',
          color: '#fff',
          padding: '8px 16px',
          textAlign: 'center',
          fontSize: '13px',
          fontWeight: 500,
          zIndex: 1000,
        }}>
          Refreshing data for {ticker}…
        </div>
      )}
      {/* ── Company overview ─────────────────────────────────────── */}
      {!hideOverview && (
        <div className="info-overview">
          <div className="overview-name">
            <span className="overview-ticker">{info.ticker}</span>
            <span className="overview-company">{info.name}</span>
          </div>
          <div className="overview-meta">
            {info.sector !== 'N/A' && <span className="overview-pill">{info.sector}</span>}
            {info.industry !== 'N/A' && <span className="overview-pill">{info.industry}</span>}
            {info.marketCap && <span className="overview-pill">Mkt Cap: {info.marketCap}</span>}
          </div>
        </div>
      )}

      {/* ── Analysis cards ───────────────────────────────────────── */}
      {/* Row 1: Valuation, Momentum, 52-Week Range */}
      <div className="info-cards-row info-cards-row--top">

        {/* Valuation */}
        <div className="info-card">
          <div className="card-title">Valuation</div>
          <StatusBadge text={info.valuation} color={valuationColor(info.valuation)} />
          <p className="card-detail">{info.valuationDetail}</p>
          {info.targetMeanPrice && info.currentPrice && (
            <p className="card-detail">
              Analyst target: <strong>${info.targetMeanPrice}</strong>
              {' '}({((info.targetMeanPrice / info.currentPrice - 1) * 100).toFixed(1)}% vs current)
            </p>
          )}
        </div>

        {/* RSI / Momentum */}
        <div className="info-card">
          <div className="card-title">Momentum (RSI 14)</div>
          {rsiPct !== null ? (
            <>
              <div className="rsi-row">
                <span className="rsi-value">{info.rsi}</span>
                <StatusBadge text={info.rsiSignal} color={rsiColor(info.rsiSignal)} />
              </div>
              <div className="rsi-track">
                <div
                  className="rsi-fill"
                  style={{
                    width: `${rsiPct}%`,
                    background:
                      rsiPct >= 70 ? '#f85149' : rsiPct <= 30 ? '#3fb950' : '#58a6ff',
                  }}
                />
                <div className="rsi-zone-markers">
                  <span style={{ left: '30%' }} />
                  <span style={{ left: '70%' }} />
                </div>
              </div>
              <p className="card-detail">
                {info.rsiSignal === 'Overbought' && 'RSI above 70 — price may be stretched; watch for pullback.'}
                {info.rsiSignal === 'Oversold' && 'RSI below 30 — potential bounce opportunity; confirm with other signals.'}
                {info.rsiSignal === 'Neutral' && 'RSI between 30–70 — no extreme momentum reading.'}
              </p>
            </>
          ) : (
            <p className="card-detail">RSI not available.</p>
          )}
        </div>

        {/* 52-Week Range */}
        <div className="info-card">
          <div className="card-title">52-Week Range</div>
          {info.positionInRange !== null ? (
            <>
              <div className="range-labels">
                <span>${info.fiftyTwoWeekLow}</span>
                <span className="range-current">${info.currentPrice}</span>
                <span>${info.fiftyTwoWeekHigh}</span>
              </div>
              <div className="range-track">
                <div
                  className="range-thumb"
                  style={{ left: `calc(${info.positionInRange}% - 5px)` }}
                />
              </div>
              <p className="card-detail">
                {info.pctFromHigh < 0
                  ? `${Math.abs(info.pctFromHigh)}% below 52-week high`
                  : 'At or above 52-week high'}
                {' · '}
                {info.pctFromLow > 0
                  ? `${info.pctFromLow}% above 52-week low`
                  : 'At or below 52-week low'}
              </p>
            </>
          ) : (
            <p className="card-detail">Range data not available.</p>
          )}
        </div>

      </div>

      {/* Row 2: Price Action, MACD, Volatility, Volume */}
      <div className="info-cards-row info-cards-row--bottom">

        {/* Consolidation */}
        <div className="info-card">
          <div className="card-title">Price Action</div>
          <StatusBadge
            text={info.consolidationStatus}
            color={consolidationColor(info.consolidationStatus)}
          />
          <p className="card-detail">{info.consolidationDetail}</p>
          {info.consolidationStatus === 'Strong Consolidation' ||
          info.consolidationStatus === 'Consolidating' ? (
            <p className="card-detail">
              Tight ranges often precede significant moves. A strategy breakout signal can
              confirm direction.
            </p>
          ) : null}
        </div>

        {/* MACD */}
        {info.macdStatus && (
          <div className="info-card">
            <div className="card-title">MACD (12, 26, 9)</div>
            <StatusBadge text={info.macdStatus} color={macdColor(info.macdStatus)} />
            <p className="card-detail">{info.macdMomentum}</p>
            <p className="card-detail">
              MACD: <strong>{info.macdValue}</strong> · Signal: <strong>{info.macdSignalValue}</strong>
            </p>
            <p className="card-detail">
              {info.macdStatus === 'BULLISH CROSSOVER' && 'MACD just crossed above signal line — potential upward momentum beginning.'}
              {info.macdStatus === 'BEARISH CROSSOVER' && 'MACD just crossed below signal line — potential downward momentum beginning.'}
              {info.macdStatus === 'BULLISH' && 'MACD is above signal line — upward momentum is active.'}
              {info.macdStatus === 'BEARISH' && 'MACD is below signal line — downward momentum is active.'}
            </p>
          </div>
        )}

        {/* Volatility */}
        {info.volatilityStatus && (
          <div className="info-card">
            <div className="card-title">Volatility (ATR 14)</div>
            <StatusBadge text={info.volatilityStatus} color={volatilityColor(info.volatilityStatus)} />
            <p className="card-detail">
              ATR ratio vs average: <strong>{info.atrRatio}x</strong>
            </p>
            <p className="card-detail">
              {info.volatilityStatus === 'HIGH Volatility' && 'Price swings are larger than normal — higher risk, wider stops advised.'}
              {info.volatilityStatus === 'LOW Volatility' && 'Price swings are compressed — may precede a breakout in either direction.'}
              {info.volatilityStatus === 'Normal Volatility' && 'Volatility is within normal historical range.'}
            </p>
          </div>
        )}

        {/* Volume */}
        {info.volumeStatus && (
          <div className="info-card">
            <div className="card-title">Volume</div>
            <StatusBadge text={info.volumeStatus} color="blue" />
            <p className="card-detail">
              {info.volumeRelative}% of 20-day average · {info.volumeTrend}
            </p>
            <p className="card-detail">
              {info.volumeRelative > 150 && 'Above-average volume — strong conviction behind current price move.'}
              {info.volumeRelative < 50 && 'Below-average volume — move may lack conviction; watch for confirmation.'}
              {info.volumeRelative >= 50 && info.volumeRelative <= 150 && 'Volume is in a normal range relative to recent history.'}
            </p>
          </div>
        )}

      </div>

      {/* Row 3: Trend Alignment, Earnings Proximity, Relative Strength vs SPY, Dividend Health */}
      <div className="info-cards-row info-cards-row--third">

        {/* Trend Alignment */}
        {info.trendAlignment && (
          <div className="info-card">
            <div className="card-title">Trend Alignment</div>
            <StatusBadge text={info.trendAlignment} color={trendColor(info.trendAlignment)} />
            <p className="card-detail">{info.trendDetail}</p>
            <p className="card-detail">
              {info.trendAlignment === 'Strong Uptrend' && 'All moving averages aligned bullishly — strong trend confirmation.'}
              {info.trendAlignment === 'Strong Downtrend' && 'All moving averages aligned bearishly — strong downward pressure.'}
              {info.trendAlignment && info.trendAlignment.includes('Mixed') && 'Moving averages are not fully aligned — trend direction is uncertain.'}
            </p>
          </div>
        )}

        {/* Earnings Proximity */}
        {info.earningsProximity && (
          <div className="info-card">
            <div className="card-title">Earnings Proximity</div>
            <StatusBadge
              text={info.earningsProximity}
              color={info.earningsWarning ? 'red' : 'blue'}
            />
            {info.earningsDate && (
              <p className="card-detail">Next report: <strong>{info.earningsDate}</strong></p>
            )}
            {info.earningsWarning && (
              <p className="card-detail" style={{ color: '#f0883e' }}>
                Earnings within 14 days — increased volatility likely. Consider position sizing.
              </p>
            )}
            {!info.earningsWarning && info.earningsProximityDays > 0 && (
              <p className="card-detail">No imminent earnings catalyst — normal volatility expected.</p>
            )}
          </div>
        )}

        {/* Relative Strength vs SPY */}
        {info.relStrength1M != null && (
          <div className="info-card">
            <div className="card-title">Relative Strength vs SPY</div>
            <div style={{ display: 'flex', gap: '8px', marginBottom: '6px' }}>
              <StatusBadge
                text={`1M: ${info.relStrength1M > 0 ? '+' : ''}${info.relStrength1M}%`}
                color={relStrengthColor(info.relStrength1M)}
              />
              <StatusBadge
                text={`3M: ${info.relStrength3M > 0 ? '+' : ''}${info.relStrength3M}%`}
                color={relStrengthColor(info.relStrength3M)}
              />
            </div>
            <p className="card-detail">
              1M — Stock: {info.stock1MReturn > 0 ? '+' : ''}{info.stock1MReturn}% vs SPY: {info.spy1MReturn > 0 ? '+' : ''}{info.spy1MReturn}%
            </p>
            <p className="card-detail">
              3M — Stock: {info.stock3MReturn > 0 ? '+' : ''}{info.stock3MReturn}% vs SPY: {info.spy3MReturn > 0 ? '+' : ''}{info.spy3MReturn}%
            </p>
            <p className="card-detail">
              {info.relStrength3M > 5 && 'Significantly outperforming the broad market — relative momentum is strong.'}
              {info.relStrength3M < -5 && 'Underperforming the broad market — relative weakness may signal further downside.'}
              {info.relStrength3M >= -5 && info.relStrength3M <= 5 && 'Tracking roughly in line with the S&P 500.'}
            </p>
          </div>
        )}

        {/* Dividend Health */}
        {(info.dividendHealth || info.dividendRate) && (
          <div className="info-card">
            <div className="card-title">Dividend Health</div>
            {info.dividendHealth ? (
              <>
                <StatusBadge text={info.dividendHealth} color={divHealthColor(info.dividendHealth)} />
                <p className="card-detail">{info.dividendHealthDetail}</p>
              </>
            ) : (
              <p className="card-detail">No payout ratio data available.</p>
            )}
            {info.dividendRate && (
              <p className="card-detail">Annual rate: <strong>${info.dividendRate}</strong></p>
            )}
            {info.dividendYield && (
              <p className="card-detail">Yield: <strong>{(info.dividendYield * 100).toFixed(2)}%</strong></p>
            )}
          </div>
        )}

      </div>

      {/* ── Key metrics table ────────────────────────────────────── */}
      <div className="info-metrics">
        <div className="metrics-title">Key Metrics</div>
        <div className="metrics-grid">
          <MetricRow label="P/E Ratio (Trailing)" value={fmt(info.trailingPE, '', 'x')} />
          <MetricRow label="P/E Ratio (Forward)" value={fmt(info.forwardPE, '', 'x')} />
          <MetricRow label="Price / Book" value={fmt(info.priceToBook, '', 'x')} />
          <MetricRow label="Price / Sales" value={fmt(info.priceToSales, '', 'x')} />
          <MetricRow label="Beta (5Y Monthly)" value={info.beta ?? 'N/A'} />
          <MetricRow
            label="Dividend Yield"
            value={
              info.dividendYield != null
                ? `${(info.dividendYield * 100).toFixed(2)}%`
                : 'N/A'
            }
          />
          <MetricRow label="EPS (Trailing)" value={fmt(info.eps, '$')} />
          <MetricRow label="Revenue / Share" value={info.revenuePerShare != null ? `$${info.revenuePerShare}` : 'N/A'} />
          <MetricRow label="Current Price" value={fmt(info.currentPrice, '$')} />
          <MetricRow
            label="Analyst Recommendation"
            value={
              <StatusBadge
                text={info.analystRecommendation}
                color={recColor(info.analystRecommendation)}
              />
            }
          />
          <MetricRow
            label="Analyst Mean Target"
            value={info.targetMeanPrice != null ? `$${info.targetMeanPrice}` : 'N/A'}
          />
          <MetricRow label="EV / EBITDA" value={fmt(info.evToEbitda, '', 'x')} />
          <MetricRow label="PEG Ratio" value={fmt(info.pegRatio, '', 'x')} />
          <MetricRow label="Dividend Rate" value={info.dividendRate != null ? `$${info.dividendRate}` : 'N/A'} />
          <MetricRow label="Ex-Dividend Date" value={info.exDividendDate ?? 'N/A'} />
          <MetricRow label="Earnings Date" value={info.earningsDate ?? 'N/A'} />
          <MetricRow label="50-Day MA" value={info.fiftyDayAverage != null ? `$${info.fiftyDayAverage}` : 'N/A'} />
          <MetricRow label="200-Day MA" value={info.twoHundredDayAverage != null ? `$${info.twoHundredDayAverage}` : 'N/A'} />
        </div>
      </div>

      {/* ── Fundamentals card ────────────────────────────────────── */}
      {(info.revenueGrowth != null || info.earningsGrowth != null ||
        info.grossMargins != null || info.operatingMargins != null ||
        info.profitMargins != null || info.returnOnEquity != null ||
        info.returnOnAssets != null || info.debtToEquity != null ||
        info.currentRatio != null || info.freeCashflow != null ||
        info.shortPercentOfFloat != null || info.quickRatio != null ||
        info.totalCash != null || info.totalDebt != null ||
        info.operatingCashflow != null || info.ebitda != null ||
        info.revenueTTM != null || info.insiderPctHeld != null ||
        info.institutionalPctHeld != null) && (
        <div className="info-metrics">
          <div className="metrics-title">Fundamentals</div>
          <div className="metrics-grid">
            {/* Growth */}
            {info.revenueGrowth != null && (
              <MetricRow
                label="Revenue Growth (YoY)"
                value={`${(info.revenueGrowth * 100).toFixed(1)}%`}
              />
            )}
            {info.earningsGrowth != null && (
              <MetricRow
                label="Earnings Growth (YoY)"
                value={`${(info.earningsGrowth * 100).toFixed(1)}%`}
              />
            )}
            {/* Profitability */}
            {info.grossMargins != null && (
              <MetricRow
                label="Gross Margin"
                value={`${(info.grossMargins * 100).toFixed(1)}%`}
              />
            )}
            {info.operatingMargins != null && (
              <MetricRow
                label="Operating Margin"
                value={`${(info.operatingMargins * 100).toFixed(1)}%`}
              />
            )}
            {info.profitMargins != null && (
              <MetricRow
                label="Net Margin"
                value={`${(info.profitMargins * 100).toFixed(1)}%`}
              />
            )}
            {info.returnOnEquity != null && (
              <MetricRow
                label="Return on Equity (ROE)"
                value={`${(info.returnOnEquity * 100).toFixed(1)}%`}
              />
            )}
            {info.returnOnAssets != null && (
              <MetricRow
                label="Return on Assets (ROA)"
                value={`${(info.returnOnAssets * 100).toFixed(1)}%`}
              />
            )}
            {/* Financial Health */}
            {info.debtToEquity != null && (
              <MetricRow
                label="Debt / Equity"
                value={`${info.debtToEquity}x`}
              />
            )}
            {info.currentRatio != null && (
              <MetricRow
                label="Current Ratio"
                value={`${info.currentRatio}x`}
              />
            )}
            {info.freeCashflow != null && (
              <MetricRow
                label="Free Cash Flow"
                value={info.freeCashflow}
              />
            )}
            {info.shortPercentOfFloat != null && (
              <MetricRow
                label="Short % of Float"
                value={`${(info.shortPercentOfFloat * 100).toFixed(1)}%`}
              />
            )}
            {info.quickRatio != null && (
              <MetricRow label="Quick Ratio" value={`${info.quickRatio}x`} />
            )}
            {info.totalCash != null && (
              <MetricRow label="Total Cash" value={info.totalCash} />
            )}
            {info.totalDebt != null && (
              <MetricRow label="Total Debt" value={info.totalDebt} />
            )}
            {info.operatingCashflow != null && (
              <MetricRow label="Operating Cash Flow" value={info.operatingCashflow} />
            )}
            {info.ebitda != null && (
              <MetricRow label="EBITDA" value={info.ebitda} />
            )}
            {info.revenueTTM != null && (
              <MetricRow label="Revenue (TTM)" value={info.revenueTTM} />
            )}
            {info.insiderPctHeld != null && (
              <MetricRow
                label="Insider % Held"
                value={`${(info.insiderPctHeld * 100).toFixed(1)}%`}
              />
            )}
            {info.institutionalPctHeld != null && (
              <MetricRow
                label="Institutional % Held"
                value={`${(info.institutionalPctHeld * 100).toFixed(1)}%`}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
