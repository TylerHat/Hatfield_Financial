import React, { useState, useMemo } from 'react';
import './DataTable.css';

/**
 * DataTable — sortable, scannable data table for screener results, signals,
 * and any tabular financial data in the Hatfield Investments dashboard.
 *
 * Props
 * ─────
 * columns : Array<ColumnDef>
 *   Each column definition object:
 *   {
 *     key      : string         — unique key matching a field in each row object
 *     label    : string         — column header text
 *     numeric  : bool           — right-aligns column and sorts numerically
 *     sortable : bool           — enables click-to-sort on this column (default true)
 *     width    : string | null  — optional CSS width (e.g. '120px')
 *     render   : (value, row) => ReactNode | null
 *                Optional custom cell renderer. Receives the raw cell value and
 *                the full row object. If omitted, the raw value is rendered.
 *   }
 *
 * rows : Array<object>
 *   Array of data objects. Each object must have keys matching column.key values.
 *   An optional `_rowClass` string on each row appends a CSS class to <tr>.
 *
 * defaultSortKey   : string | null  — column key to sort by on first render
 * defaultSortDir   : 'asc' | 'desc' — initial sort direction (default 'asc')
 * stickyHeader     : bool — makes the thead stick during scroll (default true)
 * emptyMessage     : string — text shown when rows is empty (default generic)
 * loading          : bool — shows a skeleton when true
 * error            : string | null — shows error state when set
 * caption          : string | null — accessible table caption (screen readers)
 * rowKey           : string | ((row, i) => string)
 *                    Key field name or function for React key prop. Falls back
 *                    to row index if not set.
 * onRowClick       : (row, index) => void
 *                    Optional callback fired when a body row is clicked.
 * onRowDoubleClick  : (row, index) => void
 *                    Optional callback fired when a body row is double-clicked.
 */
export default function DataTable({
  columns = [],
  rows = [],
  defaultSortKey = null,
  defaultSortDir = 'asc',
  stickyHeader = true,
  emptyMessage = 'No data to display.',
  loading = false,
  error = null,
  caption = null,
  rowKey = null,
  onRowClick = null,
  onRowDoubleClick = null,
}) {
  const [sortKey, setSortKey] = useState(defaultSortKey);
  const [sortDir, setSortDir] = useState(defaultSortDir);

  // Handle header click: toggle direction if same column, else new column asc.
  function handleSort(key) {
    const col = columns.find((c) => c.key === key);
    if (!col || col.sortable === false) return;

    if (sortKey === key) {
      setSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  }

  // Sort rows. Numeric columns compare as floats; others compare as strings.
  const sortedRows = useMemo(() => {
    if (!sortKey) return rows;

    const col = columns.find((c) => c.key === sortKey);
    const numeric = col?.numeric ?? false;

    return [...rows].sort((a, b) => {
      let aVal = a[sortKey];
      let bVal = b[sortKey];

      if (numeric) {
        aVal = parseFloat(aVal) || 0;
        bVal = parseFloat(bVal) || 0;
        return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
      }

      // String comparison — treat null/undefined as empty string for sort stability.
      aVal = aVal == null ? '' : String(aVal).toLowerCase();
      bVal = bVal == null ? '' : String(bVal).toLowerCase();
      if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  }, [rows, sortKey, sortDir, columns]);

  // Derive a stable React key for each row.
  function getRowKey(row, i) {
    if (!rowKey) return i;
    if (typeof rowKey === 'function') return rowKey(row, i);
    return row[rowKey] ?? i;
  }

  // Sort indicator arrow glyph.
  function SortArrow({ columnKey }) {
    if (sortKey !== columnKey) {
      return <span className="dt-sort-arrow dt-sort-arrow--inactive">↕</span>;
    }
    return (
      <span className="dt-sort-arrow dt-sort-arrow--active">
        {sortDir === 'asc' ? '↑' : '↓'}
      </span>
    );
  }

  // ── Render states ────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="dt-wrapper">
        <div className="dt-state dt-state--loading">
          {/* Skeleton rows */}
          <div className="dt-skeleton">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="dt-skeleton-row">
                {columns.map((col) => (
                  <div
                    key={col.key}
                    className="dt-skeleton-cell"
                    style={{ width: col.width || undefined }}
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dt-wrapper">
        <div className="dt-state dt-state--error">{error}</div>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="dt-wrapper">
        <div className="dt-state dt-state--empty">{emptyMessage}</div>
      </div>
    );
  }

  // ── Main table ───────────────────────────────────────────────────────────────

  return (
    <div className="dt-wrapper">
      <div className="dt-scroll">
        <table className={`dt-table ${stickyHeader ? 'dt-table--sticky-header' : ''}`}>
          {caption && <caption className="dt-caption">{caption}</caption>}

          <thead className="dt-thead">
            <tr>
              {columns.map((col) => {
                const isSortable = col.sortable !== false;
                const isActive = sortKey === col.key;
                return (
                  <th
                    key={col.key}
                    className={[
                      'dt-th',
                      col.numeric ? 'dt-th--numeric' : '',
                      isSortable ? 'dt-th--sortable' : '',
                      isActive ? 'dt-th--sorted' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    style={col.width ? { width: col.width } : undefined}
                    onClick={isSortable ? () => handleSort(col.key) : undefined}
                    aria-sort={
                      isActive
                        ? sortDir === 'asc'
                          ? 'ascending'
                          : 'descending'
                        : undefined
                    }
                  >
                    {col.label}
                    {isSortable && <SortArrow columnKey={col.key} />}
                  </th>
                );
              })}
            </tr>
          </thead>

          <tbody className="dt-tbody">
            {sortedRows.map((row, i) => (
              <tr
                key={getRowKey(row, i)}
                className={['dt-tr', row._rowClass].filter(Boolean).join(' ')}
                onClick={onRowClick ? () => onRowClick(row, i) : undefined}
                onDoubleClick={onRowDoubleClick ? () => onRowDoubleClick(row, i) : undefined}
                style={onRowClick || onRowDoubleClick ? { cursor: 'pointer' } : undefined}
              >
                {columns.map((col) => {
                  const raw = row[col.key];
                  const cell = col.render ? col.render(raw, row) : raw;
                  return (
                    <td
                      key={col.key}
                      className={['dt-td', col.numeric ? 'dt-td--numeric' : '']
                        .filter(Boolean)
                        .join(' ')}
                    >
                      {cell ?? <span className="dt-null">—</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="dt-footer">
        {sortedRows.length} {sortedRows.length === 1 ? 'row' : 'rows'}
        {sortKey && (
          <span className="dt-footer__sort-info">
            {' '}· sorted by <strong>{columns.find((c) => c.key === sortKey)?.label ?? sortKey}</strong>{' '}
            {sortDir === 'asc' ? '(asc)' : '(desc)'}
          </span>
        )}
      </div>
    </div>
  );
}
