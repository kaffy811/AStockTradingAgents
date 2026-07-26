/**
 * frontend/src/tests/companyV2PerformanceBehavior.test.js
 * Phase 6T-E: 页面加载/交互性能行为验收
 */
import { describe, expect, it } from 'vitest'

describe('Phase 6T-E page profile & payload', () => {
  it('CompanyV2View requests page profile by default (not debug)', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain("'page'")
    expect(raw.default).toContain('profile:')
  })

  it('include_raw defaults to false', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain('includeRaw = ref(false)')
  })

  it('api layer supports profile param and AbortSignal', async () => {
    const raw = await import('../api/companyV2.js?raw')
    expect(raw.default).toContain("params.set('profile'")
    expect(raw.default).toContain('signal')
  })
})

describe('Phase 6T-E request cancellation', () => {
  it('CompanyV2View cancels stale requests on symbol switch', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain('AbortController')
    expect(raw.default).toContain('_loadSeq')
    // 旧请求结果不得覆盖新页面
    expect(raw.default).toContain('seq !== _loadSeq')
    // 卸载时取消进行中的请求
    expect(raw.default).toContain('onUnmounted')
  })

  it('AbortError is silently ignored (no error popup for cancelled request)', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain('AbortError')
  })
})

describe('Phase 6T-E loading behavior', () => {
  it('debug panel is gated behind debug mode', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain('v-if="debugMode" class="cv2-debug-details"')
    expect(raw.default).toContain('VITE_COMPANY_V2_DEBUG')
  })

  it('no automatic PDF download/parse on page load', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).not.toContain('downloadCompanyV2Report')
    expect(raw.default).not.toContain('parseCompanyV2Report')
    // 下载/解析只在 ReportDocuments 组件内由用户点击触发
    const reports = await import('../components/company-v2/CompanyV2ReportDocuments.vue?raw')
    expect(reports.default).toMatch(/@click|onClick/)
  })

  it('module loading is parallel with allSettled (one failure does not block others)', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain('Promise.allSettled')
  })

  it('charts use ResizeObserver instead of window resize storm', async () => {
    const raw = await import('../components/company-v2/charts/CompanyV2GrowthComboChart.vue?raw')
    expect(raw.default).toContain('ResizeObserver')
  })

  it('annual is default; quarterly is lazy-loaded once and cached', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    // 默认 annual，不默认 period=all / 全部季度
    expect(raw.default).toContain("period: 'annual'")
    expect(raw.default).not.toContain("period: 'all'")
    // 已缓存则不重复请求
    expect(raw.default).toContain('if (quarterlyHistoryData.value?.modules || quarterlyLoading.value) return')
    // periodTab 变化不触发全页 load()
    expect(raw.default).not.toMatch(/watch\(\s*periodTab[^)]*load/)
  })
})

describe('Phase 6T-E scroll & no local_path', () => {
  it('bottom sentinel is reachable (exists in template)', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    expect(raw.default).toContain('company-v2-bottom-sentinel')
  })

  it('charts have fixed min-height to prevent layout jump', async () => {
    const raw = await import('../components/company-v2/charts/CompanyV2GrowthComboChart.vue?raw')
    expect(raw.default).toMatch(/height:\s*\d+px|min-height/)
  })

  it('no local_path displayed anywhere in CompanyV2 components', async () => {
    const files = [
      '../views/CompanyV2View.vue?raw',
      '../components/company-v2/CompanyV2Section.vue?raw',
      '../components/company-v2/CompanyV2ReportTimeline.vue?raw',
    ]
    for (const f of files) {
      const raw = await import(/* @vite-ignore */ f)
      expect(raw.default).not.toContain('local_path')
    }
  })

  it('no investment advice wording in CompanyV2 view', async () => {
    const raw = await import('../views/CompanyV2View.vue?raw')
    for (const word of ['买入', '卖出', '目标价', '保证上涨']) {
      expect(raw.default).not.toContain(word)
    }
    expect(raw.default).toContain('不构成投资建议')
  })
})
