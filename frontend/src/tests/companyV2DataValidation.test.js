import { describe, expect, it } from 'vitest'
import debugRaw from '../components/company-v2/CompanyV2DebugPanel.vue?raw'
import sectionRaw from '../components/company-v2/CompanyV2Section.vue?raw'

describe('CompanyV2 data validation UI', () => {
  it('renders Data Quality summary and expandable checks', () => {
    expect(debugRaw).toContain('Data Quality')
    expect(debugRaw).toContain('validation_summary')
    expect(debugRaw).toContain('validation_checks')
    expect(debugRaw).toContain('topValidationChecks')
    expect(sectionRaw).toContain('validation_checks')
  })

  it('defines pass warning fail and skipped visual states', () => {
    expect(debugRaw).toContain('cv2-validation-status.pass')
    expect(debugRaw).toContain('cv2-validation-status.warning')
    expect(debugRaw).toContain('cv2-validation-status.fail')
    expect(sectionRaw).toContain('cv2-validation-pill.pass')
    expect(sectionRaw).toContain('cv2-validation-pill.warning')
    expect(sectionRaw).toContain('cv2-validation-pill.fail')
    expect(sectionRaw).toContain('cv2-validation-pill.skipped')
  })

  it('frames validation as data quality and tolerates schema 1.x missing fields', () => {
    expect(debugRaw).toContain('数据质量校验')
    expect(sectionRaw).toContain('数据质量校验')
    expect(debugRaw).toContain('props.data.validation_summary || {}')
    expect(debugRaw).toContain('props.data.validation_checks || []')
    expect(sectionRaw).toContain('props.envelope.validation_summary || {}')
    expect(sectionRaw).toContain('props.envelope.validation_checks || []')
  })
})
