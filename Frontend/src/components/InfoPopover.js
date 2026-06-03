import React, { useState, useEffect, useRef } from 'react';

/**
 * Small "i" button that toggles a popover explaining the surrounding panel.
 *
 * Previously defined verbatim in both InsiderTransactions.js and
 * InstitutionalHoldings.js. Click-outside-to-close lives here so any
 * future panel just imports it.
 *
 * Styles (`panel-info-wrap`, `panel-info-btn`, `panel-info-popover`,
 * `chart-info-close`, `chart-info-content`) are defined in the consumer
 * panels' CSS files for now — kept that way to avoid breaking the existing
 * visual placement.
 */
export default function InfoPopover({ children }) {
  const [show, setShow] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!show) return;
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setShow(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [show]);

  return (
    <div className="panel-info-wrap" ref={ref}>
      <button
        className="panel-info-btn"
        onClick={() => setShow((s) => !s)}
        aria-label="More information"
        title="What is this?"
      >
        i
      </button>
      {show && (
        <div className="panel-info-popover">
          <button className="chart-info-close" onClick={() => setShow(false)}>✕</button>
          <div className="chart-info-content">{children}</div>
        </div>
      )}
    </div>
  );
}
