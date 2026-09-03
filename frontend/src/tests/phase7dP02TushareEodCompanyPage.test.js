import { describe, expect, it } from 'vitest'

describe('Phase 7D-P0.2 grounded EOD company page', () => {
  it('loads EOD independently and labels it as non-real-time', async () => {
    const view = await import('../views/CompanyV2View.vue?raw')
    expect(view.default).toContain('getCompanyV2Eod')
    expect(view.default).toContain('Promise.allSettled')
    expect(view.default).toContain('debugMode.value ? getCompanyV2FullDebug')
    expect(view.default).toContain(': Promise.resolve({})')
    expect(view.default).toContain('最近交易日盘后数据')
    expect(view.default).toContain('盘后数据可能延迟，不代表实时行情')
    expect(view.default).toContain('数据截至 {{ eodData.as_of }}')
  })

  it('keeps profile and shows a module-level EOD unavailable state', async () => {
    const view = await import('../views/CompanyV2View.vue?raw')
    expect(view.default).toContain('CompanyV2CompanyProfileCard')
    expect(view.default).toContain('data-testid="eod-unavailable"')
    expect(view.default).toContain('暂缺已验证的盘后数据')
    expect(view.default).toContain("eodResult.status === 'rejected'")
  })

  it('uses only normalized fact fields and not raw provider data', async () => {
    const view = await import('../views/CompanyV2View.vue?raw')
    expect(view.default).toContain("modules[moduleKey]?.fields?.[fieldKey]")
    expect(view.default).not.toContain('raw_payload')
    expect(view.default).not.toContain('Eastmoney')
  })
})
