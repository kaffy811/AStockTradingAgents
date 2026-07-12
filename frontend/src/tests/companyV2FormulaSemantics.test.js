import { describe, expect, it } from 'vitest'
import debugRaw from '../components/company-v2/CompanyV2DebugPanel.vue?raw'
import sectionRaw from '../components/company-v2/CompanyV2Section.vue?raw'

describe('CompanyV2 formula semantics calibration UI', () => {
  it('renders semantic warning text for weak formula checks', () => {
    expect(debugRaw).toContain('该指标存在口径差异')
    expect(sectionRaw).toContain('该指标存在口径差异')
    expect(sectionRaw).toContain('报告期间')
    expect(sectionRaw).toContain('累计/单季')
  })

  it('renders Dupont provider-defined and net margin context warnings', () => {
    expect(sectionRaw).toContain('杜邦拆解字段来自供应商定义口径')
    expect(sectionRaw).toContain('净利率校验需要营收、净利润和净利率处于同一期间与同一口径')
    expect(sectionRaw).toContain('DUPONT_PROVIDER_DEFINED')
    expect(sectionRaw).toContain('net_margin_formula')
  })

  it('keeps pass warning fail classes and schema compatibility', () => {
    expect(debugRaw).toContain('cv2-validation-status.pass')
    expect(debugRaw).toContain('cv2-validation-status.warning')
    expect(debugRaw).toContain('cv2-validation-status.fail')
    expect(sectionRaw).toContain('props.envelope.validation_checks || []')
  })

  it('does not contain prohibited recommendation wording', () => {
    const raw = `${debugRaw}\n${sectionRaw}`
    expect(raw).not.toContain('该公司财务异常')
    expect(raw).not.toContain('建议买入')
    expect(raw).not.toContain('建议卖出')
    expect(raw).not.toContain('目标价')
    expect(raw).not.toContain('高风险股票')
    expect(raw).not.toContain('保证上涨')
  })
})
