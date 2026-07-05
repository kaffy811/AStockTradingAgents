/**
 * src/utils/exportFundamentals.js
 * CSV export utilities for fundamental module data.
 * No external dependencies — uses browser's built-in download mechanism.
 */

/**
 * Export rows to a CSV file and trigger browser download.
 * @param {string} filename - base filename (without .csv)
 * @param {Array<Object>} rows - data rows
 * @param {Array<string>} columns - column keys to include
 * @param {Object} fieldLabels - column key → display label
 */
export function exportRowsToCsv(filename, rows, columns, fieldLabels = {}) {
  if (!rows || !rows.length || !columns.length) return

  // Build header row
  const header = columns.map(col => `"${(fieldLabels[col] || col).replace(/"/g, '""')}"`)

  // Build data rows: null → empty string, string escaping
  const dataRows = rows.map(row =>
    columns.map(col => {
      const v = row[col]
      if (v === null || v === undefined) return ''
      const s = String(v).replace(/"/g, '""')
      return `"${s}"`
    })
  )

  const csv = [header, ...dataRows].map(r => r.join(',')).join('\n')
  const bom = '\uFEFF'  // UTF-8 BOM for Excel compatibility
  const blob = new Blob([bom + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${filename}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/**
 * Export a single module's data to CSV.
 * @param {string} stockCode - e.g. "600519"
 * @param {string} moduleKey - e.g. "growth"
 * @param {Object} viewModel - output of adaptModuleData()
 * @param {Object} fieldLabels - from moduleMeta
 */
export function exportModuleCsv(stockCode, moduleKey, viewModel, fieldLabels = {}) {
  if (!viewModel || !viewModel.rows || !viewModel.rows.length) return
  const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  const filename = `${stockCode}_${moduleKey}_${dateStr}`
  exportRowsToCsv(filename, viewModel.rows, viewModel.columns || [], fieldLabels)
}
