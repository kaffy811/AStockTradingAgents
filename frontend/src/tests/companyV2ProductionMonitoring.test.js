import { describe, expect, it } from 'vitest'
import debugRaw from '../components/company-v2/CompanyV2DebugPanel.vue?raw'

describe('CompanyV2 production monitoring panel', () => {
  it('renders production health summary metrics', () => {
    expect(debugRaw).toContain('Production Health Summary')
    expect(debugRaw).toContain('providers_data_success')
    expect(debugRaw).toContain('modules_renderable')
    expect(debugRaw).toContain('coverage_avg')
    expect(debugRaw).toContain('data_quality_score')
    expect(debugRaw).toContain('strong_failed_count')
    expect(debugRaw).toContain('semantic_warning_count')
    expect(debugRaw).toContain('fallback_to_legacy_count')
  })

  it('renders semantic warnings as口径提示 and strong failures as error', () => {
    expect(debugRaw).toContain('口径提示')
    expect(debugRaw).toContain('semantic warnings 用于观察供应商定义')
    expect(debugRaw).toContain('数据强校验失败')
    expect(debugRaw).toContain('Critical validation failure')
    expect(debugRaw).toContain('cv2-strong-failure')
    expect(debugRaw).toContain('cv2-critical-failure')
  })

  it('keeps schema compatibility and no restricted wording', () => {
    expect(debugRaw).toContain('props.data.validation_summary || {}')
    expect(debugRaw).not.toContain('目标价')
    expect(debugRaw).not.toContain('保证上涨')
    expect(debugRaw).not.toContain('建议买入')
    expect(debugRaw).not.toContain('建议卖出')
  })
})
