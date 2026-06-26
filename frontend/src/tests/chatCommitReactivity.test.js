/**
 * chatCommitReactivity.test.js
 *
 * Tests for the Vue reactivity fix:
 *   commitAssistantMessage + getLiveAssistantMsg pattern
 *
 * These tests verify that SSE events update the messages array in a way Vue
 * can detect — regardless of whether the Debug panel tick is running.
 *
 * Root cause being tested:
 *   applyChatUiEvent mutates the original plain-JS object. Vue 3 only fires
 *   reactive updates when mutations go through the Proxy returned by
 *   messages.value[i]. Committing replaces the array slot + the array
 *   reference, forcing a re-render on every SSE event.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { ref }               from 'vue'
import { applyChatUiEvent }  from '../utils/chatReducer.js'
import { normalizeChatEvent } from '../utils/chatEventNormalizer.js'

// ── Minimal helpers mirroring ChatCopilotView logic ───────────────────────────

function makeMsg(overrides = {}) {
  return {
    id:              'msg-001',
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
    streamDebug: {
      eventsReceived:   0,
      lastEventType:    null,
      lastEventAt:      null,
      streamSessionId:  'session-abc',
      currentSessionId: 'session-abc',
      requestStartedAt: null,
    },
    ...overrides,
  }
}

function makeMessages() {
  return ref([makeMsg()])
}

/** Mirrors commitAssistantMessage from ChatCopilotView.vue */
function commitAssistantMessage(messages, msg) {
  const idx = messages.value.findIndex(m => m.id === msg.id)
  if (idx < 0) return

  messages.value[idx] = {
    ...msg,
    reasoningSteps: [...(msg.reasoningSteps ?? [])],
    toolTrace:      [...(msg.toolTrace      ?? [])],
    agentTrace:     [...(msg.agentTrace     ?? [])],
    streamDebug:    msg.streamDebug  ? { ...msg.streamDebug  } : msg.streamDebug,
    finalAnswer:    msg.finalAnswer  ? { ...msg.finalAnswer  } : msg.finalAnswer,
  }

  messages.value = [...messages.value]
}

/** Mirrors getLiveAssistantMsg from ChatCopilotView.vue */
function getLiveAssistantMsg(messages, msgId) {
  return messages.value.find(m => m.id === msgId) ?? null
}

// ── Test 1: commit replaces both the array item and array reference ────────────

describe('commitAssistantMessage', () => {
  it('T1: replaces array item reference and array reference after apply + commit', () => {
    const messages   = makeMessages()
    const beforeArr  = messages.value          // snapshot array reference
    const beforeItem = messages.value[0]       // snapshot item reference

    const msg = getLiveAssistantMsg(messages, 'msg-001')
    applyChatUiEvent(msg, normalizeChatEvent('answer_delta', { delta: 'hello' }))
    commitAssistantMessage(messages, msg)

    // Array reference must have changed
    expect(messages.value).not.toBe(beforeArr)

    // Item reference must have changed
    expect(messages.value[0]).not.toBe(beforeItem)

    // Content must be updated
    expect(messages.value[0].content).toBe('hello')
    expect(messages.value[0].answerContent).toBe('hello')
  })

  it('T1b: commit is a no-op when msg id not in array', () => {
    const messages = makeMessages()
    const ghost    = makeMsg({ id: 'ghost-999' })
    const before   = messages.value

    commitAssistantMessage(messages, ghost)   // should not throw

    expect(messages.value).toBe(before)       // array unchanged
  })
})

// ── Test 2: final_answer event updates message and is committable ─────────────

describe('final_answer commit', () => {
  it('T2: final_answer via normalizer populates finalAnswer + commits', () => {
    const messages = makeMessages()

    const msg     = getLiveAssistantMsg(messages, 'msg-001')
    const uiEvent = normalizeChatEvent('final_answer', {
      summary:  'ok',
      analysis: 'analysis text',
    })
    applyChatUiEvent(msg, uiEvent)
    commitAssistantMessage(messages, msg)

    const live = messages.value[0]
    expect(live.finalAnswer).toBeTruthy()
    expect(live.finalAnswer.summary).toBe('ok')
  })
})

// ── Test 3: agent_completed → ui_done → send button state recovers ────────────

describe('agent_completed → ui_done', () => {
  it('T3: after ui_done commit, isStreaming=false and status=done', () => {
    const messages = makeMessages()

    const msg = getLiveAssistantMsg(messages, 'msg-001')
    msg.status     = 'streaming'
    msg.isStreaming = true
    applyChatUiEvent(msg, { type: 'ui_done' })
    commitAssistantMessage(messages, msg)

    const live = messages.value[0]
    expect(live.status).toBe('done')
    expect(live.isStreaming).toBe(false)
  })
})

// ── Test 4: multiple events maintain content accumulation across commits ────────

describe('multiple SSE events across commits', () => {
  it('T4: answer_delta accumulates across commits (debug panel irrelevant)', () => {
    const messages = makeMessages()

    // Simulate two answer_delta events
    for (const delta of ['foo', ' ', 'bar']) {
      // Each event: get live msg from array → apply → commit
      const live = getLiveAssistantMsg(messages, 'msg-001')
      applyChatUiEvent(live, normalizeChatEvent('answer_delta', { delta }))
      commitAssistantMessage(messages, live)
    }

    expect(messages.value[0].content).toBe('foo bar')
    expect(messages.value[0].answerContent).toBe('foo bar')
  })

  it('T4b: getLiveAssistantMsg always returns latest committed object', () => {
    const messages = makeMessages()
    const original = messages.value[0]

    const live1 = getLiveAssistantMsg(messages, 'msg-001')
    applyChatUiEvent(live1, normalizeChatEvent('answer_delta', { delta: 'a' }))
    commitAssistantMessage(messages, live1)

    const live2 = getLiveAssistantMsg(messages, 'msg-001')
    // live2 is a NEW object after commit — not live1 or original
    expect(live2).not.toBe(original)
    expect(live2).not.toBe(live1)
    // But content is correct
    expect(live2.content).toBe('a')
  })
})

// ── Test 5: old assistantMsg reference doesn't pollute the live object ─────────

describe('stale reference isolation', () => {
  it('T5: mutating stale assistantMsg after a commit does NOT affect array item', () => {
    const messages     = makeMessages()
    const assistantMsg = messages.value[0]  // plain object (pre-proxy)

    // Simulate a commit (e.g. from a first SSE event)
    const live1 = getLiveAssistantMsg(messages, 'msg-001')
    applyChatUiEvent(live1, normalizeChatEvent('answer_delta', { delta: 'real' }))
    commitAssistantMessage(messages, live1)

    // Now mutate the stale reference — this should NOT affect messages.value[0]
    assistantMsg.content = 'STALE MUTATION'

    const live2 = getLiveAssistantMsg(messages, 'msg-001')
    // The committed spread copy is at messages.value[0]; it's a different object
    // than assistantMsg, so the stale mutation doesn't propagate
    expect(live2.content).toBe('real')
  })
})

// ── Test 6: tool trace events commit correctly ─────────────────────────────────

describe('tool trace events', () => {
  it('T6: tool_call_start + tool_call_result committed correctly', () => {
    const messages = makeMessages()

    // tool start
    const live1 = getLiveAssistantMsg(messages, 'msg-001')
    applyChatUiEvent(live1, normalizeChatEvent('tool_call_start', {
      tool_name: 'stock_quote_tool',
      display_name: '查询实时行情',
    }))
    commitAssistantMessage(messages, live1)

    expect(messages.value[0].toolTrace).toHaveLength(1)
    expect(messages.value[0].toolTrace[0].status).toBe('running')

    // tool done
    const live2 = getLiveAssistantMsg(messages, 'msg-001')
    applyChatUiEvent(live2, normalizeChatEvent('tool_call_result', {
      tool_name:      'stock_quote_tool',
      status:         'success',
      result_summary: '当前价 1212.1',
    }))
    commitAssistantMessage(messages, live2)

    expect(messages.value[0].toolTrace[0].status).toBe('success')
    expect(messages.value[0].toolTrace[0].summary).toBe('当前价 1212.1')
  })
})

// ── Test 7: error event committed + isStreaming cleared ───────────────────────

describe('error handling', () => {
  it('T7: ui_error sets status=error and isStreaming=false, committed properly', () => {
    const messages = makeMessages()

    const live = getLiveAssistantMsg(messages, 'msg-001')
    live.status     = 'streaming'
    live.isStreaming = true
    applyChatUiEvent(live, { type: 'ui_error', message: '连接中断' })
    commitAssistantMessage(messages, live)

    const result = messages.value[0]
    expect(result.status).toBe('error')
    expect(result.isStreaming).toBe(false)
    expect(result.error).toBe('连接中断')
  })
})
