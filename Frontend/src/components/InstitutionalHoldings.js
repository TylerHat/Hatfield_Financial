import React, { useState, useEffect, useRef } from 'react';

function fmtValue(v) {
  if (v == null) return 'N/A';
  const abs = Math.abs(v);
  const sign = v < 0 ? '-' : '';
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9)  return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6)  return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3)  return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

function fmtShares(s) {
  if (s == null) return 'N/A';
  return Number(s).toLocaleString();
}

function SummaryCard({ label, value }) {
  return (
    <div className="inst-summary-card">
      <span className="inst-summary-label">{label}</span>
      <span className="inst-summary-value">{value ?? 'N/A'}</span>
    </div>
  );
}

function InfoPopover({ children }) {
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
        onClick={() => setShow(s => !s)}
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

export default function InstitutionalHoldings({ holders, major, totalCount }) {
  const [open, setOpen] = useState(true);
  const [sortCol, setSortCol] = useState('value');
  const [sortAsc, setSortAsc] = useState(false);

  const hasData = (holders && holders.length > 0) || major;

  if (!hasData) {
    return (
      <div className="insider-panel">
        <div className="insider-header">
          <span className="insider-title">Institutional Holdings</span>
          <InfoPopover>
            <p className="chart-info-desc">Institutional Holdings</p>
            <p>Shows which major institutions — hedge funds, mutual funds, pension funds, and ETF managers — hold shares in this company, based on their most recent 13F filings with the SEC.</p>
            <p className="chart-info-note">Rising institutional ownership is a classic <strong style={{color:'#3fb950'}}>accumulation</strong> signal. A high institution count with growing % held indicates professional money is building positions.</p>
            <p className="chart-info-desc" style={{marginTop:'10px'}}>Summary Strip</p>
            <p><strong>Insider % Held</strong> — percentage of total shares owned by company insiders (officers and directors). High insider ownership aligns management incentives with shareholders.</p>
            <p><strong>Institutions % Held</strong> — percentage of all outstanding shares held by institutional investors. Above 70% means the stock is heavily owned by professional money managers.</p>
            <p><strong>Float Held by Institutions</strong> — percentage of the publicly tradable float (shares available for anyone to buy) held by institutions. Can exceed 100% due to short selling and timing differences in 13F filings.</p>
            <p><strong>Institution Count</strong> — total number of institutions that have reported a position. More institutions generally means more analyst coverage and liquidity.</p>
            <p className="chart-info-desc" style={{marginTop:'10px'}}>Table Column</p>
            <p><strong>% Out</strong> — the percentage of total outstanding shares held by that specific institution. A single holder above 5% is considered a major shareholder and must file additional disclosures with the SEC.</p>
          </InfoPopover>
        </div>
        <p className="insider-empty">No institutional holdings data available for this ticker.</p>
      </div>
    );
  }

  function handleSort(col) {
    if (sortCol === col) {
      setSortAsc(a => !a);
    } else {
      setSortCol(col);
      setSortAsc(false);
    }
  }

  const sorted = holders ? [...holders].sort((a, b) => {
    let av = a[sortCol] ?? -Infinity;
    let bv = b[sortCol] ?? -Infinity;
    if (typeof av === 'string') av = av.toLowerCase();
    if (typeof bv === 'string') bv = bv.toLowerCase();
    if (av < bv) return sortAsc ? -1 : 1;
    if (av > bv) return sortAsc ? 1 : -1;
    return 0;
  }) : [];

  function SortTh({ col, label, className }) {
    const active = sortCol === col;
    return (
      <th
        className={`sortable${active ? ' sort-active' : ''}${className ? ` ${className}` : ''}`}
        onClick={() => handleSort(col)}
      >
        {label}
        <span className="sort-arrow">{active ? (sortAsc ? ' ▴' : ' ▾') : ' ⇅'}</span>
      </th>
    );
  }

  return (
    <div className="insider-panel">
      <div className="insider-header">
        <button
          className="insider-toggle"
          onClick={() => setOpen(o => !o)}
          aria-expanded={open}
        >
          <span className="insider-title">Institutional Holdings</span>
          <span className="insider-chevron">{open ? '▾' : '▸'}</span>
        </button>
        {totalCount != null && (
          <span className="status-badge status-blue">{totalCount.toLocaleString()} Institutions</span>
        )}
        <InfoPopover>
          <p className="chart-info-desc">Institutional Holdings</p>
          <p>Shows which major institutions — hedge funds, mutual funds, pension funds, and ETF managers — hold shares in this company, based on their most recent 13F filings with the SEC.</p>
          <p className="chart-info-note">Rising institutional ownership is a classic <strong style={{color:'#3fb950'}}>accumulation</strong> signal. A high institution count with growing % held indicates professional money is building positions.</p>
          <p className="chart-info-desc" style={{marginTop:'10px'}}>Summary Strip</p>
          <p><strong>Insider % Held</strong> — percentage of total shares owned by company insiders (officers and directors). High insider ownership aligns management incentives with shareholders.</p>
          <p><strong>Institutions % Held</strong> — percentage of all outstanding shares held by institutional investors. Above 70% means the stock is heavily owned by professional money managers.</p>
          <p><strong>Float Held by Institutions</strong> — percentage of the publicly tradable float (shares available for anyone to buy) held by institutions. Can exceed 100% due to short selling and timing differences in 13F filings.</p>
          <p><strong>Institution Count</strong> — total number of institutions that have reported a position. More institutions generally means more analyst coverage and liquidity.</p>
          <p className="chart-info-desc" style={{marginTop:'10px'}}>Table Column</p>
          <p><strong>% Out</strong> — the percentage of total outstanding shares held by that specific institution. A single holder above 5% is considered a major shareholder and must file additional disclosures with the SEC.</p>
        </InfoPopover>
      </div>

      {open && (
        <>
          {/* Summary row */}
          {major && (
            <div className="inst-summary-row">
              {major.insidersPct != null && (
                <SummaryCard label="Insider % Held" value={`${major.insidersPct.toFixed(2)}%`} />
              )}
              {major.institutionsPct != null && (
                <SummaryCard label="Institutions % Held" value={`${major.institutionsPct.toFixed(2)}%`} />
              )}
              {major.institutionsFloatPct != null && (
                <SummaryCard label="Float Held by Institutions" value={`${major.institutionsFloatPct.toFixed(2)}%`} />
              )}
              {major.institutionsCount != null && (
                <SummaryCard label="Institution Count" value={major.institutionsCount.toLocaleString()} />
              )}
            </div>
          )}

          {/* Holders table */}
          {sorted.length > 0 && (
            <div className="insider-table-wrap">
              <table className="insider-table">
                <thead>
                  <tr>
                    <SortTh col="holder" label="Holder" />
                    <SortTh col="shares" label="Shares" className="right" />
                    <SortTh col="pctOut" label="% Out" className="right" />
                    <SortTh col="value" label="Value" className="right" />
                    <SortTh col="dateReported" label="Date Reported" />
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((row, i) => (
                    <tr key={i}>
                      <td className="insider-filer">{row.holder ?? 'N/A'}</td>
                      <td className="right">{fmtShares(row.shares)}</td>
                      <td className="right">{row.pctOut != null ? `${row.pctOut.toFixed(2)}%` : 'N/A'}</td>
                      <td className="right">{fmtValue(row.value)}</td>
                      <td className="insider-date">{row.dateReported ?? 'N/A'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
