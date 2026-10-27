import { createApp } from 'vue'
import { describe, it, expect } from 'vitest'
import ReportVisualSummary from '../components/ReportVisualSummary.vue'

function render(visuals) {
  const el=document.createElement('div'), app=createApp(ReportVisualSummary,{visuals})
  app.mount(el)
  return {el,close:()=>app.unmount()}
}

describe('report data pictures',()=>{
  it('omits absent panels instead of creating placeholder scores',()=>{
    const view=render({})
    try { expect(view.el.querySelector('section')).toBeNull() } finally {view.close()}
  })
  it('shows only supplied values, real reporting dates and a zero-centered growth bar',()=>{
    const view=render({
      prices:[{date:'2026-10-25',close:11.2},{date:'2026-10-26',close:11.3}],
      growth:[{label:'营业收入',value:0,as_of:'2026-09-30'},{label:'净利润',value:-2.21,as_of:'2026-09-30'}],
    })
    try {
      expect(view.el.textContent).toContain('2026-09-30')
      expect(view.el.textContent).toContain('0%')
      expect(view.el.textContent).toContain('-2.21%')
      expect(view.el.textContent).not.toContain('/100')
      expect(view.el.querySelector('svg')).not.toBeNull()
      expect(view.el.querySelector('.growth-bar.negative').style.left).toBe('2%')
    } finally {view.close()}
  })
  it('rejects malformed numbers and does not invent missing growth items',()=>{
    const view=render({growth:[{label:'营业收入',value:2.42,as_of:'2026-09-30'}, {label:'净利润',value:null,as_of:'2026-09-30'}]})
    try {
      expect(view.el.querySelectorAll('.growth-row')).toHaveLength(1)
      expect(view.el.textContent).not.toContain('净利润')
    } finally {view.close()}
  })
})
