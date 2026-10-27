import { describe, it, expect } from 'vitest'
import { formatCompanyFact, historyEnvelope, companyWebsite } from '../utils/companyPagePresentation.js'
import { translateWarning, agentStatusLabel } from '../utils/warningMap.js'

it('normalizes company websites and rejects executable URLs', () => {
  expect(companyWebsite('www.mylotushealth.com')).toBe('https://www.mylotushealth.com/')
  expect(companyWebsite('javascript:alert(1)')).toBe('')
})

describe('honest report and financial presentation', () => {
  it('formats real financial values with bounded precision and readable units', () => {
    expect(formatCompanyFact(43.7459, 'multiple')).toEqual({ value: '43.75', unit: '倍' })
    expect(formatCompanyFact(-2.2518, '%')).toEqual({ value: '-2.25', unit: '%' })
    expect(formatCompanyFact(0, 'CNY')).toEqual({ value: '0', unit: '元' })
    expect(formatCompanyFact(null, '%').value).toBe('—')
  })
  it('uses history data independently from the debug snapshot without fabricating success', () => {
    const rows = [{ period: '2025-12-31', roe: 12 }]
    const envelope = historyEnvelope({ history: rows, data_success: true })
    expect(envelope.normalized.rows).toBe(rows)
    expect(envelope.render.has_displayable_data).toBe(true)
    expect(historyEnvelope({}).ok).toBe(false)
  })
  it('localizes legacy agent errors without claiming the market data is missing', () => {
    expect(translateWarning('fundamental agent failed.')).toContain('不代表原始数据缺失')
    expect(agentStatusLabel('failed')).toBe('未完成')
  })
})
