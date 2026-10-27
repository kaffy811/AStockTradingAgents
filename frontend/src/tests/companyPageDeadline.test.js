import { createApp, nextTick } from 'vue'
import { describe, it, expect, vi, afterEach } from 'vitest'
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { market: 'CN', symbol: '600186' }, query: {} }),
  useRouter: () => ({ back: vi.fn() }),
}))
vi.mock('../api/companyV2.js', () => ({
  getCompanyV2Profile: vi.fn(), getCompanyV2History: vi.fn(), getCompanyV2Eod: vi.fn(),
  getCompanyV2FullDebug: vi.fn(), refreshCompanyV2Debug: vi.fn(),
}))
vi.mock('../components/company-v2/CompanyV2Section.vue', () => ({ default: {
  props: ['title'], template: '<section class="history-test-module">{{title}}</section>',
} }))
import * as api from '../api/companyV2.js'
import CompanyPage from '../views/CompanyV2View.vue'
let app
async function flush() { for (let i = 0; i < 6; i++) await Promise.resolve(); await nextTick() }
afterEach(() => { app?.unmount(); vi.useRealTimers(); window.__COMPANY_V2_PAGE_CACHE__?.clear() })
function mount() { const el = document.createElement('div'); app = createApp(CompanyPage); app.mount(el); return el }

describe('company page progressive loading', () => {
  it('ends skeletons and keeps profile when history never responds', async () => {
    vi.useFakeTimers()
    api.getCompanyV2Profile.mockResolvedValue({ company_name: '测试公司' })
    let finishHistory
    api.getCompanyV2History.mockImplementation(() => new Promise(resolve => { finishHistory = resolve }))
    api.getCompanyV2Eod.mockResolvedValue({})
    const el = mount()
    await flush()
    expect(el.textContent).toContain('测试公司')
    await vi.advanceTimersByTimeAsync(30001)
    expect(el.textContent).toContain('部分数据加载超时')
    expect(el.textContent).not.toContain('正在刷新数据')
    expect(el.querySelector('[data-testid="financial-module-skeletons"]')).toBeNull()
    finishHistory({ modules: { profitability: { data_success: true } } })
    await flush()
    expect(el.querySelector('.history-test-module')).toBeNull()
  })
  it('renders successful history modules without requiring the debug endpoint', async () => {
    api.getCompanyV2Profile.mockResolvedValue({ company_name: '测试公司' })
    api.getCompanyV2History.mockResolvedValue({ ok: true, modules: {
      profitability: { data_success: true, latest: { roe: 12 }, history: [{ period: '2025-12-31', roe: 12 }] },
    } })
    api.getCompanyV2Eod.mockResolvedValue({})
    const el = mount()
    await flush()
    expect(el.querySelector('.history-test-module')?.textContent).toBe('盈利能力')
    expect(el.textContent).not.toContain('加载超时')
  })
})
