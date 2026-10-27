import { createApp, nextTick } from 'vue'
import { describe, it, expect, vi } from 'vitest'
import DataQualitySummary from '../components/DataQualitySummary.vue'
import AnalysisProgressPanel from '../components/AnalysisProgressPanel.vue'

function mount(component, props) {
  const el = document.createElement('div')
  const app = createApp(component, props)
  app.mount(el)
  return { el, unmount: () => app.unmount() }
}

describe('analysis failure presentation', () => {
  it('does not call a model timeout missing K-line data', () => {
    const view = mount(DataQualitySummary, { result: {
      sections: { technical: '[technical 模块暂时不可用：PROVIDER_TIMEOUT]' },
      metadata: { agents: { technical: { status: 'failed', message: 'PROVIDER_TIMEOUT' } } },
    } })
    try {
      expect(view.el.querySelector('.dqs-chip').title).toContain('不能据此判断 K 线数据缺失')
    } finally { view.unmount() }
  })

  it('does not promise a stalled task is still running', async () => {
    vi.useFakeTimers()
    const view = mount(AnalysisProgressPanel, { mode: 'realtime', loading: true })
    try {
      await vi.advanceTimersByTimeAsync(16000)
      await nextTick()
      expect(view.el.textContent).toContain('尚不能确认任务是否仍在运行')
      expect(view.el.textContent).not.toContain('系统仍在后台处理中')
    } finally { view.unmount(); vi.useRealTimers() }
  })

  it('labels synthesis fallback as retaining partial reports', () => {
    const view = mount(AnalysisProgressPanel, {
      mode: 'realtime', loading: false,
      latestEvent: { event: 'synthesis_completed', degraded: true },
    })
    try { expect(view.el.textContent).toContain('综合生成失败，已保留分项报告') }
    finally { view.unmount() }
  })
})
