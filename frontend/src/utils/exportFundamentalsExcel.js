/**
 * src/utils/exportFundamentalsExcel.js
 * Excel (.xlsx) export utilities for fundamental module data.
 * Uses SheetJS (xlsx) via dynamic import to avoid initial bundle bloat.
 */

// Dynamic import cache
let _xlsxCache = null
async function getXlsx() {
  if (!_xlsxCache) _xlsxCache = await import('xlsx')
  return _xlsxCache
}

// Sanitize sheet name: max 31 chars, strip Excel illegal chars
function sanitizeSheetName(name) {
  return (name || 'Sheet')
    .replace(/[\\\/\?\*\[\]:']/g, '_')
    .slice(0, 31) || 'Sheet'
}

// Deduplicate sheet names across a workbook
function makeSheetNameTracker() {
  const usedNames = new Set()
  return function uniqueSheetName(name) {
    let n = sanitizeSheetName(name)
    if (!usedNames.has(n)) { usedNames.add(n); return n }
    let i = 2
    while (usedNames.has(`${n}_${i}`)) i++
    const unique = `${n}_${i}`
    usedNames.add(unique)
    return unique
  }
}

// Normalize cell value: null/undefined → empty string
function cellValue(v) {
  if (v === null || v === undefined) return ''
  return v
}

// Build metadata rows array [[key, value], ...]
function buildMetaRows(envelope) {
  const rows = []
  if (envelope?.generated_at) rows.push(['更新时间', envelope.generated_at])
  if (envelope?.source?.actual) rows.push(['数据来源', envelope.source.actual])
  if (envelope?.partial) rows.push(['数据完整性', '部分数据（partial）'])
  if (envelope?.stale) rows.push(['缓存状态', '数据来自缓存（stale）'])
  if (envelope?.errors?.length) rows.push(['错误信息', envelope.errors.join('; ')])
  return rows
}

/**
 * Convert a view model + envelope into an array of AOA (array-of-arrays) rows.
 * Layout:
 *   [metadata block]
 *   [blank row]
 *   [metrics as key-value table, if any]
 *   [blank row if both metrics and rows]
 *   [column header row]
 *   [data rows]
 */
function buildSheetAoa(viewModel, envelope, moduleMeta) {
  const fieldLabels = moduleMeta?.field_labels || {}
  const unitHints = moduleMeta?.unit_hints || {}
  const aoa = []

  // Partial data notice at top
  if (envelope?.partial) {
    const reasons = envelope?.data?.reasons || envelope?.errors || []
    const reasonText = reasons.length ? reasons.join('; ') : '数据不完整'
    aoa.push(['数据说明', `部分数据（partial）— ${reasonText}`])
    aoa.push([])
  }

  // Metadata block
  const metaRows = buildMetaRows(envelope)
  metaRows.forEach(([k, v]) => aoa.push([k, v]))
  if (metaRows.length) aoa.push([])

  // Metrics as key-value table
  const metrics = viewModel?.metrics || []
  if (metrics.length) {
    aoa.push(['指标', '值'])
    metrics.forEach(m => {
      // Use raw number (not formatted "—" string); null → empty cell
      const raw = m.raw !== null && m.raw !== undefined ? m.raw : null
      aoa.push([m.label, raw])
    })
    aoa.push([])
  }

  // Table rows
  const rows = viewModel?.rows || []
  const columns = viewModel?.columns || []

  // If no rows but chart series exist, export xAxis + series as table
  if (!rows.length && viewModel?.series?.length && viewModel?.xAxis?.length) {
    const xAxis = viewModel.xAxis
    const series = viewModel.series
    // Header: Date | SeriesName1 | SeriesName2 ...
    const header = ['日期', ...series.map(s => s.name)]
    aoa.push(header)
    xAxis.forEach((label, i) => {
      const rowData = [label, ...series.map(s => {
        const v = s.data?.[i]
        return v !== null && v !== undefined ? v : null
      })]
      aoa.push(rowData)
    })
    return aoa
  }

  if (!rows.length || !columns.length) return aoa

  // Column header row using field_labels
  const headerRow = columns.map(col => fieldLabels[col] || col)
  aoa.push(headerRow)

  // Data rows: null/undefined → '' (empty cell), never export "—"
  rows.forEach(row => {
    const dataRow = columns.map(col => {
      const v = row[col]
      if (v === null || v === undefined) return ''
      // Apply unit hints for numeric fields
      const unit = unitHints[col] || ''
      if (unit && typeof v === 'number') {
        if (unit === '%') return v  // keep as number, Excel can format
        return v
      }
      return cellValue(v)
    })
    aoa.push(dataRow)
  })

  return aoa
}

/**
 * Export a single module to .xlsx.
 */
export async function exportModuleToXlsx({ code, moduleKey, moduleName, envelope, viewModel, moduleMeta }) {
  const XLSX = await getXlsx()
  const wb = XLSX.utils.book_new()
  const sheetName = sanitizeSheetName(moduleName || moduleKey)
  const aoa = buildSheetAoa(viewModel, envelope, moduleMeta)
  const ws = XLSX.utils.aoa_to_sheet(aoa)
  XLSX.utils.book_append_sheet(wb, ws, sheetName)

  const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  XLSX.writeFile(wb, `${code}_${moduleKey}_${dateStr}.xlsx`)
}

/**
 * Export a section (multiple modules) to .xlsx, one sheet per module.
 * modules: Array of { moduleKey, moduleName, envelope, viewModel, moduleMeta }
 */
export async function exportSectionToXlsx({ code, sectionKey, sectionName, modules }) {
  const XLSX = await getXlsx()
  const wb = XLSX.utils.book_new()
  const uniqueSheetName = makeSheetNameTracker()

  // 目录 sheet
  const tocAoa = [['模块', '状态', '数据来源', '更新时间']]
  modules.forEach(m => {
    const env = m.envelope
    tocAoa.push([
      m.moduleName || m.moduleKey,
      env?.partial ? '部分' : env ? '完整' : '未加载',
      env?.source?.actual || '—',
      env?.generated_at || '—',
    ])
  })
  const tocWs = XLSX.utils.aoa_to_sheet(tocAoa)
  XLSX.utils.book_append_sheet(wb, tocWs, uniqueSheetName('目录'))

  // One sheet per module
  modules.forEach(m => {
    if (!m.envelope?.data && !m.viewModel) return
    const sheetName = uniqueSheetName(m.moduleName || m.moduleKey)
    const aoa = buildSheetAoa(m.viewModel, m.envelope, m.moduleMeta)
    const ws = XLSX.utils.aoa_to_sheet(aoa)
    XLSX.utils.book_append_sheet(wb, ws, sheetName)
  })

  const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  XLSX.writeFile(wb, `${code}_${sectionKey}_${dateStr}.xlsx`)
}

/**
 * Export all loaded company fundamentals to .xlsx.
 * modules: Array of { moduleKey, moduleName, envelope, viewModel, moduleMeta }
 * overview: { snapshot, financial_summary } (optional)
 */
export async function exportCompanyFundamentalsToXlsx({ code, overview, modules }) {
  const XLSX = await getXlsx()
  const wb = XLSX.utils.book_new()
  const uniqueSheetName = makeSheetNameTracker()

  // 目录 sheet
  const tocAoa = [['模块', '分组', '状态', '数据来源', '更新时间']]
  modules.forEach(m => {
    const env = m.envelope
    tocAoa.push([
      m.moduleName || m.moduleKey,
      m.moduleMeta?.group || '—',
      env?.partial ? '部分' : env ? '完整' : '未加载',
      env?.source?.actual || '—',
      env?.generated_at || '—',
    ])
  })
  const tocWs = XLSX.utils.aoa_to_sheet(tocAoa)
  XLSX.utils.book_append_sheet(wb, tocWs, uniqueSheetName('目录'))

  // Data sheets
  modules.forEach(m => {
    if (!m.envelope?.data && !m.viewModel) return
    const sheetName = uniqueSheetName(m.moduleName || m.moduleKey)
    const aoa = buildSheetAoa(m.viewModel, m.envelope, m.moduleMeta)
    const ws = XLSX.utils.aoa_to_sheet(aoa)
    XLSX.utils.book_append_sheet(wb, ws, sheetName)
  })

  const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  XLSX.writeFile(wb, `${code}_fundamentals_${dateStr}.xlsx`)
}
