/** Presentation only: never invent values or upgrade provider validation. */
export function formatCompanyFact(value, unit) {
  if (value == null || value === '' || !Number.isFinite(Number(value))) return { value: '—', unit: '' }
  return {
    value: new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(Number(value)),
    unit: ({ CNY: '元', HKD: '港元', multiple: '倍', percent: '%' })[unit] || unit || '',
  }
}

export function historyEnvelope(history = {}) {
  const rows = Array.isArray(history.history) ? history.history : []
  return {
    ok: history.data_success === true,
    normalized: { fields: {}, rows },
    render: {
      has_displayable_data: history.data_success === true,
      table_renderable: rows.length > 0,
      reason: history.reason_code || 'DATA_NOT_AVAILABLE',
    },
  }
}

export function companyWebsite(raw) {
  const value = String(raw || '').trim()
  if (!value) return ''
  try {
    const url = new URL(/^[a-z][a-z0-9+.-]*:/i.test(value) ? value : `https://${value}`)
    return ['https:', 'http:'].includes(url.protocol) && url.hostname.includes('.') && !url.username && !url.password ? url.href : ''
  } catch { return '' }
}
