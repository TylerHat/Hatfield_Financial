import React from 'react';
import './Badge.css';

/**
 * Badge — colored status pill for signal types, conviction levels, and
 * arbitrary categorical labels.
 *
 * Props
 * ─────
 * variant  : 'buy' | 'sell' | 'neutral' | 'high' | 'medium' | 'low'
 *            | 'green' | 'red' | 'yellow' | 'blue' | 'gray'
 *            Controls background + text color.
 * size     : 'sm' | 'md' (default 'md')
 *            'sm' is used inside dense table cells; 'md' for standalone display.
 * children : The label text displayed inside the pill.
 *
 * Variant aliases
 * ───────────────
 * 'buy'     → green
 * 'sell'    → red
 * 'neutral' → blue
 * 'high'    → green  (conviction)
 * 'medium'  → yellow (conviction)
 * 'low'     → gray   (conviction)
 *
 * All other strings map directly to a color class. Unknown strings fall back
 * to gray so the component never renders unstyled.
 */

// Map semantic variant names to the underlying color class.
const VARIANT_MAP = {
  buy: 'green',
  sell: 'red',
  neutral: 'blue',
  high: 'green',
  medium: 'yellow',
  low: 'gray',
};

export default function Badge({ variant = 'gray', size = 'md', children }) {
  const colorClass = VARIANT_MAP[variant] ?? variant ?? 'gray';
  return (
    <span className={`hf-badge hf-badge--${colorClass} hf-badge--${size}`}>
      {children}
    </span>
  );
}
