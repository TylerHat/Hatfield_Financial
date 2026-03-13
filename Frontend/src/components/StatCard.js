import React from 'react';
import './StatCard.css';

/**
 * StatCard — single-metric display card for portfolio and stock summary data.
 *
 * Props
 * ─────
 * label     : string   — metric name shown in the header (e.g. "Current Price")
 * value     : string | number | ReactNode
 *             The primary display value. Pass a pre-formatted string for full
 *             control, or a number — the component will not auto-format so the
 *             caller decides decimal places, currency symbols, etc.
 * delta     : string | number | null
 *             Optional change value displayed beneath the primary value.
 *             If a number, the sign determines color (positive → green,
 *             negative → red). If a string beginning with '+' or '-', the
 *             same coloring applies. Pass null or omit to hide.
 * deltaLabel: string | null
 *             Optional suffix after the delta (e.g. "vs prev close").
 * subtext   : string | ReactNode | null
 *             Optional secondary line below the delta (e.g. "20-day avg").
 * accent    : 'default' | 'green' | 'red' | 'blue' | 'yellow'
 *             Draws a colored left border to visually categorize the card.
 * size      : 'sm' | 'md' | 'lg'
 *             Controls value font size. Default 'md'.
 * loading   : bool — shows a skeleton shimmer when true.
 * error     : string | null — shows error text when set.
 */
export default function StatCard({
  label,
  value,
  delta = null,
  deltaLabel = null,
  subtext = null,
  accent = 'default',
  size = 'md',
  loading = false,
  error = null,
}) {
  // Determine delta color based on sign of value.
  function getDeltaClass(d) {
    if (d === null || d === undefined) return '';
    const str = String(d);
    const num = parseFloat(str.replace(/[^0-9.\-]/g, ''));
    if (str.startsWith('+') || (!str.startsWith('-') && num > 0)) return 'stat-card__delta--positive';
    if (str.startsWith('-') || num < 0) return 'stat-card__delta--negative';
    return 'stat-card__delta--neutral';
  }

  return (
    <div className={`stat-card stat-card--accent-${accent}`}>
      <div className="stat-card__label">{label}</div>

      {loading && (
        <div className="stat-card__skeleton">
          <div className="stat-card__skeleton-bar stat-card__skeleton-bar--wide" />
          <div className="stat-card__skeleton-bar stat-card__skeleton-bar--narrow" />
        </div>
      )}

      {!loading && error && (
        <div className="stat-card__error">{error}</div>
      )}

      {!loading && !error && (
        <>
          <div className={`stat-card__value stat-card__value--${size}`}>
            {value ?? 'N/A'}
          </div>

          {delta !== null && delta !== undefined && (
            <div className={`stat-card__delta ${getDeltaClass(delta)}`}>
              {delta}
              {deltaLabel && (
                <span className="stat-card__delta-label"> {deltaLabel}</span>
              )}
            </div>
          )}

          {subtext && (
            <div className="stat-card__subtext">{subtext}</div>
          )}
        </>
      )}
    </div>
  );
}

/**
 * StatCardGrid — convenience wrapper that lays out StatCards in a responsive
 * multi-column grid. Accepts any children, not just StatCards.
 *
 * Props
 * ─────
 * columns : number — minimum column count hint (default 4).
 *           The grid always tries to fill available width.
 */
export function StatCardGrid({ children, columns = 4 }) {
  return (
    <div
      className="stat-card-grid"
      style={{ '--stat-grid-columns': columns }}
    >
      {children}
    </div>
  );
}
