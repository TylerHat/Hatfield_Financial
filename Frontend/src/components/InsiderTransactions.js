import React, { useState } from 'react';

function fmtValue(v) {
  if (v == null) return 'N/A';
  const abs = Math.abs(v);
  const sign = v < 0 ? '-' : '';
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

function fmtShares(s) {
  if (s == null) return 'N/A';
  return Number(s).toLocaleString();
}

function transactionType(text) {
  if (!text) return { label: 'Unknown', color: 'gray' };
  const t = text.toLowerCase();
  if (t.includes('sale') || t.includes('sell') || t.includes('sold')) return { label: 'Sale', color: 'red' };
  if (t.includes('purchase') || t.includes('buy') || t.includes('bought') || t.includes('acquisition')) return { label: 'Purchase', color: 'green' };
  if (t.includes('grant') || t.includes('award') || t.includes('option')) return { label: 'Grant/Award', color: 'blue' };
  return { label: text.length > 24 ? text.slice(0, 24) + '…' : text, color: 'gray' };
}

function net90dColor(value) {
  if (value == null) return 'gray';
  return value > 0 ? 'green' : 'red';
}

export default function InsiderTransactions({ transactions, net90d, net90dValue }) {
  const [open, setOpen] = useState(true);

  if (!transactions || transactions.length === 0) {
    return (
      <div className="insider-panel">
        <div className="insider-header">
          <span className="insider-title">Insider Transactions</span>
        </div>
        <p className="insider-empty">No insider transaction data available for this ticker.</p>
      </div>
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
          <span className="insider-title">Insider Transactions</span>
          <span className="insider-chevron">{open ? '▾' : '▸'}</span>
        </button>
        {net90d && (
          <span className={`status-badge status-${net90dColor(net90dValue)}`}>
            {net90d} <span className="insider-badge-sub">(90d)</span>
          </span>
        )}
      </div>

      {open && (
        <div className="insider-table-wrap">
          <table className="insider-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Insider</th>
                <th>Type</th>
                <th className="right">Shares</th>
                <th className="right">Value</th>
                <th>Ownership</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((txn, i) => {
                const { label, color } = transactionType(txn.text);
                return (
                  <tr key={i}>
                    <td className="insider-date">{txn.date ?? 'N/A'}</td>
                    <td className="insider-filer">{txn.filer ?? 'N/A'}</td>
                    <td>
                      <span className={`status-badge status-${color}`}>{label}</span>
                    </td>
                    <td className="right">{fmtShares(txn.shares)}</td>
                    <td className={`right ${txn.value != null && txn.value < 0 ? 'text-red' : txn.value != null && txn.value > 0 ? 'text-green' : ''}`}>
                      {fmtValue(txn.value)}
                    </td>
                    <td className="insider-ownership">{txn.ownership ?? 'N/A'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
