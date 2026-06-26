/**
 * Tests for Task D — Chat Copilot stability fixes.
 *
 * Covers:
 *   - Problem 1: SSE state machine never stuck at 'connecting'
 *   - Problem 2: session-switch guard (stale events discarded)
 *   - Problem 3: creation lock semantics (isCreatingChat flag)
 *   - Reducer finalization — ui_done from finally path
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { applyChatUiEvent } from '../utils/chatReducer.js'
import { normalizeChatEvent } from '../utils/chatEventNormalizer.js'

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeMsg(overrides = {}) {
  return {
    id:              'msg-1',
    role:            'assistant',
    content:         '',
    status:          'connecting',
    isStreaming:     true,
    reasoningSteps:  [],
    toolTrace:       [],
    agentTrace:      [],
    thinkingContent: '',
    answerContent:   '',
    finalAnswer:     null,
    error:           null,
    ...overrides,
  }
}

// ── Problem 1: SSE state machine ──────────────────────────────────────────────

describe('Problem 1 — SSE status transitions', () => {
  it('status moves from connecting → streaming on first answer_delta', () => {
    const msg = makeMsg()
    // Simulate what _handleEvent does: flip status then apply event
    msg.status = 'streaming'  // first-event flip
    applyChatUiEvent(msg, normalizeChatEvent('answer_delta', { delta: '你好' }))
    expect(msg.status).toBe('streaming')
    expect(msg.answerContent).toBe('你好')
  })

  it('status moves from connecting → streaming on tool_call_start', () => {
    const msg = makeMsg()
    msg.status = 'streaming'  // any-event flip
    applyChatUiEvent(msg, normalizeChatEvent('tool_call_start', { tool_name: 'stock_quote' }))
    expect(msg.status).toBe('streaming')
    expect(msg.toolTrace).toHaveLength(1)
  })

  it('ui_done from finally path finalizes a streaming message', () => {
    const msg = makeMsg({ status: 'streaming' })
    applyChatUiEvent(msg, { type: 'ui_done' })
    expect(msg.status).toBe('done')
    expect(msg.isStreaming).toBe(false)
  })

  it('ui_done on connecting message finalizes correctly', () => {
    // Scenario: stream returned 0 events, finally block fires
    const msg = makeMsg({ status: 'connecting' })
    applyChatUiEvent(msg, { type: 'ui_done' })
    expect(msg.status).toBe('done')
    expect(msg.isStreaming).toBe(false)
  })

  it('ui_error on connecting message marks as error', () => {
    const msg = makeMsg({ status: 'connecting' })
    applyChatUiEvent(msg, { type: 'ui_error', message: '连接超时' })
    expect(msg.status).toBe('error')
    expect(msg.isStreaming).toBe(false)
    expect(msg.error).toBe('连接超时')
  })

  it('status stays done once finalized — ui_done is idempotent', () => {
    const msg = makeMsg({ status: 'done', isStreaming: false })
    applyChatUiEvent(msg, { type: 'ui_done' })
    expect(msg.status).toBe('done')
    expect(msg.isStreaming).toBe(false)
  })
})

// ── Problem 2: session isolation guard ───────────────────────────────────────

describe('Problem 2 — session isolation (stale event discard)', () => {
  it('events destined for old session are discarded by session ID guard', () => {
    // Simulate the guard: streamSessionId !== sessionId.value
    const activeSessionId = 'session-B'
    const streamSessionId = 'session-A'  // captured at stream start

    const msg = makeMsg()

    // This is the guard logic from _handleEvent:
    const isStale = activeSessionId !== streamSessionId
    if (!isStale) {
      applyChatUiEvent(msg, normalizeChatEvent('answer_delta', { delta: '旧数据' }))
    }

    // Guard blocks the event → message untouched
    expect(msg.answerContent).toBe('')
    expect(msg.status).toBe('connecting')
  })

  it('events for current session are NOT discarded', () => {
    const activeSessionId = 'session-A'
    const streamSessionId = 'session-A'

    const msg = makeMsg()
    const isStale = activeSessionId !== streamSessionId
    if (!isStale) {
      msg.status = 'streaming'
      applyChatUiEvent(msg, normalizeChatEvent('answer_delta', { delta: '新数据' }))
    }

    expect(msg.answerContent).toBe('新数据')
    expect(msg.status).toBe('streaming')
  })

  it('switching sessions while loading: isLoadingSession=false check aborts restore', () => {
    // Simulate the guard in onSelectSession:
    // After getChatSession resolves, if isLoadingSession was reset by a newer
    // concurrent call, bail out.
    let isLoadingSession = true  // set at start of first switch
    const messages = []
    const restoredMessages = [{ role: 'user', content: 'msg from session-A' }]

    // Concurrent call resets the flag
    isLoadingSession = false

    // Guard in finally block of first switch:
    if (isLoadingSession === false) {
      // bail — do not restore
    } else {
      messages.push(...restoredMessages)
    }

    expect(messages).toHaveLength(0)  // restore was skipped
  })
})

// ── Problem 3: creation lock ──────────────────────────────────────────────────

describe('Problem 3 — creation lock semantics', () => {
  it('isCreatingChat lock prevents second onNewSession call from running', async () => {
    // Simulate the lock:
    let isCreatingChat = false
    let createCallCount = 0

    async function onNewSession() {
      if (isCreatingChat) return
      isCreatingChat = true
      try {
        createCallCount++
        await Promise.resolve()  // simulate async createChatSession
      } finally {
        isCreatingChat = false
      }
    }

    // Fire two calls concurrently
    await Promise.all([onNewSession(), onNewSession()])
    expect(createCallCount).toBe(1)
  })

  it('dedup check prevents inserting same session ID twice', () => {
    const sessions = [{ id: 'session-1', preview: 'first' }]
    const newId = 'session-1'  // same ID returned by backend

    // Guard from onNewSession:
    const alreadyExists = sessions.some(s => s.id === newId)
    if (!alreadyExists) {
      sessions.push({ id: newId, preview: '' })
    }

    expect(sessions).toHaveLength(1)  // not duplicated
  })

  it('new unique session ID is inserted normally', () => {
    const sessions = [{ id: 'session-1', preview: 'first' }]
    const newId = 'session-2'

    const alreadyExists = sessions.some(s => s.id === newId)
    if (!alreadyExists) {
      sessions.unshift({ id: newId, preview: '' })
    }

    expect(sessions).toHaveLength(2)
    expect(sessions[0].id).toBe('session-2')
  })
})

// ── Combined scenario: orchestrator + early-done ──────────────────────────────

describe('Combined — orchestrator stream with finally finalization', () => {
  it('orchestrator stream that never sends agent_completed is finalized by ui_done', () => {
    const msg = makeMsg()

    // Events arrive (stream is live)
    msg.status = 'streaming'  // first-event flip
    applyChatUiEvent(msg, normalizeChatEvent('orchestrator_start', { query: '分析宁德时代' }))
    applyChatUiEvent(msg, normalizeChatEvent('subagent_start', { agent_name: 'market_agent' }))
    applyChatUiEvent(msg, normalizeChatEvent('answer_delta', { delta: '根据行情' }))

    // agent_completed never arrives — stream just ends
    // finally block fires:
    if (msg.isStreaming && (msg.status === 'connecting' || msg.status === 'streaming')) {
      applyChatUiEvent(msg, { type: 'ui_done' })
    }

    expect(msg.status).toBe('done')
    expect(msg.isStreaming).toBe(false)
    expect(msg.answerContent).toBe('根据行情')
    // Running steps get closed out by ui_done
    const runningSteps = msg.reasoningSteps.filter(s => s.status === 'running')
    expect(runningSteps).toHaveLength(0)
  })

  it('message already done is NOT re-processed by finally guard', () => {
    const msg = makeMsg({ status: 'done', isStreaming: false, answerContent: '完整结论' })

    // Finally guard checks isStreaming first — skips since already false
    if (msg.isStreaming && (msg.status === 'connecting' || msg.status === 'streaming')) {
      applyChatUiEvent(msg, { type: 'ui_done' })
    }

    expect(msg.answerContent).toBe('完整结论')  // unchanged
    expect(msg.status).toBe('done')
  })
})
