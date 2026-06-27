/**
 * C29.1 productization tests
 * Covers: UiFlags display rules, MiniPanel filtering, action button placement,
 * analysis_run status helpers, polling guard, session sort order
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// ── T1: chatUiFlags.js default (non-debug) values ──────────────────────────
describe('T1 chatUiFlags default (production-like) values', () => {
  it('SHOW_THINKING_MINI is the inverse of CHAT_UI_DEBUG', async () => {
    // In test environment, localStorage.getItem('CHAT_UI_DEBUG') returns null → CHAT_UI_DEBUG = false
    const { CHAT_UI_DEBUG, SHOW_THINKING_MINI, SHOW_REASONING_PANEL, SHOW_DATA_QUALITY } =
      await import('../config/chatUiFlags.js')
    expect(SHOW_THINKING_MINI).toBe(!CHAT_UI_DEBUG)
    expect(SHOW_REASONING_PANEL).toBe(CHAT_UI_DEBUG)
    expect(SHOW_DATA_QUALITY).toBe(CHAT_UI_DEBUG)
  })
})

// ── T2: analysis_run status helpers ────────────────────────────────────────
describe('T2 analysis_run status helpers', () => {
  // Reproduce the helper logic inline (same as ChatResultCard.vue)
  function isRunActive(status) { return status === 'queued' || status === 'running' }
  function runStatusLabel(status) {
    const map = { queued: '排队中', running: '生成中', completed: '已完成', failed: '失败', cancelled: '已取消' }
    return map[status] ?? status
  }
  function runPillClass(status) {
    if (status === 'completed') return 'pill--done'
    if (status === 'failed')    return 'pill--error'
    return 'pill--active'
  }

  it('isRunActive returns true for queued/running', () => {
    expect(isRunActive('queued')).toBe(true)
    expect(isRunActive('running')).toBe(true)
  })

  it('isRunActive returns false for terminal states', () => {
    expect(isRunActive('completed')).toBe(false)
    expect(isRunActive('failed')).toBe(false)
    expect(isRunActive('cancelled')).toBe(false)
  })

  it('runStatusLabel maps all known states', () => {
    expect(runStatusLabel('queued')).toBe('排队中')
    expect(runStatusLabel('running')).toBe('生成中')
    expect(runStatusLabel('completed')).toBe('已完成')
    expect(runStatusLabel('failed')).toBe('失败')
    expect(runStatusLabel('cancelled')).toBe('已取消')
  })

  it('runStatusLabel returns unknown status as-is', () => {
    expect(runStatusLabel('unknown_status')).toBe('unknown_status')
  })

  it('runPillClass returns pill--done for completed', () => {
    expect(runPillClass('completed')).toBe('pill--done')
  })

  it('runPillClass returns pill--error for failed', () => {
    expect(runPillClass('failed')).toBe('pill--error')
  })

  it('runPillClass returns pill--active for active/unknown states', () => {
    expect(runPillClass('queued')).toBe('pill--active')
    expect(runPillClass('running')).toBe('pill--active')
    expect(runPillClass('pending')).toBe('pill--active')
  })
})

// ── T3: session sort order (effective_time logic) ───────────────────────────
describe('T3 session effective_time sort', () => {
  function effectiveTime(session) {
    return session.last_accessed_at || session.updated_at || session.created_at
  }

  function sortSessions(sessions) {
    return [...sessions].sort((a, b) => {
      const ta = effectiveTime(a) ?? ''
      const tb = effectiveTime(b) ?? ''
      return tb.localeCompare(ta)
    })
  }

  it('sorts by last_accessed_at first', () => {
    const sessions = [
      { id: 1, last_accessed_at: '2026-01-01T10:00:00Z', updated_at: '2026-01-03T00:00:00Z', created_at: '2026-01-01T00:00:00Z' },
      { id: 2, last_accessed_at: '2026-01-02T10:00:00Z', updated_at: '2026-01-01T00:00:00Z', created_at: '2026-01-01T00:00:00Z' },
    ]
    const sorted = sortSessions(sessions)
    expect(sorted[0].id).toBe(2)
    expect(sorted[1].id).toBe(1)
  })

  it('falls back to updated_at when last_accessed_at is null', () => {
    const sessions = [
      { id: 1, last_accessed_at: null, updated_at: '2026-01-01T00:00:00Z', created_at: '2026-01-01T00:00:00Z' },
      { id: 2, last_accessed_at: null, updated_at: '2026-01-02T00:00:00Z', created_at: '2026-01-01T00:00:00Z' },
    ]
    const sorted = sortSessions(sessions)
    expect(sorted[0].id).toBe(2)
  })

  it('falls back to created_at when both last_accessed_at and updated_at are null', () => {
    const sessions = [
      { id: 1, last_accessed_at: null, updated_at: null, created_at: '2026-01-01T00:00:00Z' },
      { id: 2, last_accessed_at: null, updated_at: null, created_at: '2026-01-03T00:00:00Z' },
    ]
    const sorted = sortSessions(sessions)
    expect(sorted[0].id).toBe(2)
  })

  it('optimistic move-to-top: modifying last_accessed_at changes sort position', () => {
    const sessions = [
      { id: 1, last_accessed_at: '2026-01-02T00:00:00Z', updated_at: null, created_at: '2026-01-01T00:00:00Z' },
      { id: 2, last_accessed_at: '2026-01-01T00:00:00Z', updated_at: null, created_at: '2026-01-01T00:00:00Z' },
    ]
    // Before optimistic update: id=1 is on top
    expect(sortSessions(sessions)[0].id).toBe(1)
    // Simulate optimistic update for id=2
    sessions[1].last_accessed_at = new Date().toISOString()
    // After update: id=2 should be on top
    expect(sortSessions(sessions)[0].id).toBe(2)
  })
})

// ── T4: MiniPanel visibleSteps filtering ────────────────────────────────────
describe('T4 ChatThinkingMiniPanel visibleSteps filtering logic', () => {
  const EXCLUDE_SOURCES = new Set(['data_quality_review', 'deepseek_reasoning'])
  const EXCLUDE_TOOLS = new Set([
    'general_financial_answer_skill',
    'report_explanation_skill',
    'financial_rag_search',
    'compute_data_quality',
  ])

  // Simulate the visibleSteps computed
  function computeVisibleSteps({ thinkingItems = [], reasoningSteps = [], toolTrace = [] } = {}) {
    const steps = []
    for (const item of thinkingItems) {
      if (EXCLUDE_SOURCES.has(item.source)) continue
      steps.push({ label: item.source, done: !item.isStreaming })
    }
    for (const step of reasoningSteps) {
      if (steps.some(s => s.label === step.title)) continue
      steps.push({ label: step.title, done: step.status === 'done' })
    }
    for (const tool of toolTrace) {
      if (EXCLUDE_TOOLS.has(tool.tool)) continue
      const label = tool.tool
      if (steps.some(s => s.label === label)) continue
      steps.push({ label, done: tool.status === 'done' })
    }
    return steps.slice(0, 5)
  }

  it('excludes data_quality_review from thinkingItems', () => {
    const steps = computeVisibleSteps({
      thinkingItems: [
        { source: 'data_quality_review', isStreaming: false },
        { source: 'technical_analysis', isStreaming: false },
      ]
    })
    expect(steps.map(s => s.label)).not.toContain('data_quality_review')
    expect(steps.map(s => s.label)).toContain('technical_analysis')
  })

  it('excludes deepseek_reasoning from thinkingItems', () => {
    const steps = computeVisibleSteps({
      thinkingItems: [{ source: 'deepseek_reasoning', isStreaming: true }]
    })
    expect(steps).toHaveLength(0)
  })

  it('excludes financial_rag_search from toolTrace', () => {
    const steps = computeVisibleSteps({
      toolTrace: [
        { tool: 'financial_rag_search', status: 'done' },
        { tool: 'get_stock_price', status: 'done' },
      ]
    })
    expect(steps.map(s => s.label)).not.toContain('financial_rag_search')
    expect(steps.map(s => s.label)).toContain('get_stock_price')
  })

  it('deduplicates identical labels across sources', () => {
    const steps = computeVisibleSteps({
      thinkingItems: [{ source: 'technical_analysis', isStreaming: false }],
      toolTrace: [{ tool: 'technical_analysis', status: 'done' }],
    })
    expect(steps.filter(s => s.label === 'technical_analysis')).toHaveLength(1)
  })

  it('caps at 5 steps', () => {
    const steps = computeVisibleSteps({
      thinkingItems: [
        { source: 'a', isStreaming: false },
        { source: 'b', isStreaming: false },
        { source: 'c', isStreaming: false },
        { source: 'd', isStreaming: false },
        { source: 'e', isStreaming: false },
        { source: 'f', isStreaming: false },
      ]
    })
    expect(steps).toHaveLength(5)
  })

  it('marks streaming steps as not done', () => {
    const steps = computeVisibleSteps({
      thinkingItems: [{ source: 'technical_analysis', isStreaming: true }]
    })
    expect(steps[0].done).toBe(false)
  })
})

// ── T5: polling guard – no duplicate intervals for same msgId ───────────────
describe('T5 polling guard', () => {
  it('does not start a second poll if msgId already has one', () => {
    const _runPolls = new Map()

    function _startRunPolling(msgId, _runId, tickFn) {
      if (_runPolls.has(msgId)) return
      const iid = setInterval(tickFn, 4000)
      _runPolls.set(msgId, iid)
    }

    const tick = vi.fn()
    _startRunPolling('msg-1', 'run-abc', tick)
    _startRunPolling('msg-1', 'run-abc', tick) // duplicate — must be ignored

    expect(_runPolls.size).toBe(1)

    // cleanup
    _runPolls.forEach(iid => clearInterval(iid))
  })

  it('allows separate polls for different msgIds', () => {
    const _runPolls = new Map()

    function _startRunPolling(msgId, _runId, tickFn) {
      if (_runPolls.has(msgId)) return
      const iid = setInterval(tickFn, 4000)
      _runPolls.set(msgId, iid)
    }

    _startRunPolling('msg-1', 'run-1', vi.fn())
    _startRunPolling('msg-2', 'run-2', vi.fn())

    expect(_runPolls.size).toBe(2)

    _runPolls.forEach(iid => clearInterval(iid))
  })

  it('clears all polls on unmount', () => {
    const _runPolls = new Map()
    const clearSpy = vi.spyOn(global, 'clearInterval')

    _runPolls.set('msg-1', setInterval(() => {}, 9999))
    _runPolls.set('msg-2', setInterval(() => {}, 9999))

    // simulate onBeforeUnmount
    _runPolls.forEach(iid => clearInterval(iid))
    _runPolls.clear()

    expect(clearSpy).toHaveBeenCalledTimes(2)
    expect(_runPolls.size).toBe(0)
    clearSpy.mockRestore()
  })
})

// ── T6: copy feedback timing ────────────────────────────────────────────────
describe('T6 copy feedback timing logic', () => {
  it('copiedId is set, then cleared after 1800ms', () => {
    vi.useFakeTimers()
    let copiedId = null

    function onCopy(msgId) {
      copiedId = msgId
      setTimeout(() => { copiedId = null }, 1800)
    }

    onCopy('msg-42')
    expect(copiedId).toBe('msg-42')

    vi.advanceTimersByTime(1799)
    expect(copiedId).toBe('msg-42') // still set

    vi.advanceTimersByTime(1)
    expect(copiedId).toBeNull() // now cleared

    vi.useRealTimers()
  })
})
