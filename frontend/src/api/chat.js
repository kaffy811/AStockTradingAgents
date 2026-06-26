/**
 * chat.js — Chat Copilot API wrapper (Phase C3).
 *
 * Wraps POST /chat/sessions, GET /chat/sessions, etc.
 * All calls auto-inject Bearer token via baseFetch.
 */

import { baseFetch } from './http.js'
import { useAuthStore } from '../stores/auth.js'

const _API_BASE = () =>
  import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1'

// ── Session ────────────────────────────────────────────────────────────────────

/**
 * Create a new chat session.
 * @param {string|null} title
 * @returns {Promise<{session_id, title, status, created_at}>}
 */
export function createChatSession(title = null) {
  return baseFetch('/chat/sessions', {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
}

/**
 * List current user's chat sessions.
 * @param {number} limit
 * @param {number} offset
 * @returns {Promise<{items, total}>}
 */
export function listChatSessions(limit = 20, offset = 0) {
  return baseFetch(`/chat/sessions?limit=${limit}&offset=${offset}`)
}

/**
 * Get session detail with all messages.
 * @param {string} sessionId
 * @returns {Promise<{session_id, title, status, messages}>}
 */
export function getChatSession(sessionId) {
  return baseFetch(`/chat/sessions/${sessionId}`)
}

// ── Messages ───────────────────────────────────────────────────────────────────

/**
 * Send a user message and get the assistant response.
 * @param {string} sessionId
 * @param {string} content
 * @param {string} outputLanguage  e.g. "zh-CN"
 * @returns {Promise<{message_id, assistant_message_id, status, answer, tool_events, cards, confirmation}>}
 */
export function sendChatMessage(sessionId, content, outputLanguage = 'zh-CN') {
  return baseFetch(`/chat/sessions/${sessionId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content, output_language: outputLanguage }),
  })
}

// ── Confirm ────────────────────────────────────────────────────────────────────

/**
 * Confirm or cancel a pending action.
 * @param {string} sessionId
 * @param {string} confirmationId
 * @param {boolean} confirmed
 * @returns {Promise<{status, answer, tool_events, cards}>}
 */
export function confirmChatAction(sessionId, confirmationId, confirmed) {
  return baseFetch(`/chat/sessions/${sessionId}/confirm`, {
    method: 'POST',
    body: JSON.stringify({ confirmation_id: confirmationId, confirmed }),
  })
}

// ── Skills (C9) ───────────────────────────────────────────────────────────────

/**
 * List available Agent skills (C9 Skill Discovery).
 * @returns {Promise<{items: Array}>}
 */
export function getChatSkills() {
  return baseFetch('/chat/skills')
}

// ── Memory (C8) ───────────────────────────────────────────────────────────────

/**
 * Get the structured memory for a session.
 * @param {string} sessionId
 * @returns {Promise<{session_id, memory}>}
 */
export function getChatSessionMemory(sessionId) {
  return baseFetch(`/chat/sessions/${sessionId}/memory`)
}

/**
 * Clear the structured memory for a session.
 * @param {string} sessionId
 * @returns {Promise<{session_id, cleared}>}
 */
export function clearChatSessionMemory(sessionId) {
  return baseFetch(`/chat/sessions/${sessionId}/memory/clear`, { method: 'POST' })
}

// ── Delete ─────────────────────────────────────────────────────────────────────

/**
 * Soft-delete a chat session.
 * @param {string} sessionId
 * @returns {Promise<null>}
 */
export function deleteChatSession(sessionId) {
  return baseFetch(`/chat/sessions/${sessionId}`, { method: 'DELETE' })
}

// ── SSE Streaming (C13-a, C25 passthrough refactor) ───────────────────────────

/**
 * Send a chat message and receive an SSE stream of Agent events.
 *
 * C25 refactor: replaced the closed static dispatch table with a universal
 * passthrough.  Every SSE event now reaches the caller via:
 *
 *   handlers.onEvent(eventType, payload)   ← fires for EVERY event (new API)
 *
 * Backward-compat named callbacks are still supported as an optional overlay:
 *   handlers.onAgentStarted, handlers.onCompleted, handlers.onError, etc.
 *
 * Why: the old static map silently dropped any event type not listed in it.
 * Adding a new backend event type required touching THREE files in lockstep
 * (chat.js, ChatCopilotView.vue, chatEventNormalizer.js).  Now only the
 * normalizer needs updating.
 *
 * @param {string}   sessionId
 * @param {string}   content
 * @param {string}   outputLanguage   e.g. "zh-CN"
 * @param {object}   handlers
 *   {
 *     onEvent(eventType, payload),   // universal — fires for every event
 *     // ── Legacy named handlers (optional, kept for backward compat) ──────
 *     onUserSaved, onSessionTitleUpdated, onAgentStarted, onPlaceholderCreated,
 *     onIntentDetected, onPlannerStarted, onPlannerStepStarted, onPlannerStepCompleted,
 *     onSkillStarted, onSkillCompleted, onToolStarted, onToolCompleted,
 *     onRagRetrieveStarted, onRagRetrieveCompleted, onRagReviewStarted, onRagReviewCompleted,
 *     onConfirmationRequired, onCardsDelta, onAnswerDelta, onCompleted, onError,
 *     onThinking, onToolCallStart, onToolCallResult, onFinalAnswer,
 *     onOrchestratorStart, onSubagentStart, onSubagentResult,
 *     onRiskReviewStart, onRiskReviewResult, onSynthesisStart,
 *   }
 * @param {AbortSignal} signal   AbortController signal for stop/timeout
 * @returns {Promise<void>}      Resolves when stream ends
 */
export async function sendChatMessageStream(
  sessionId,
  content,
  outputLanguage = 'zh-CN',
  handlers = {},
  signal = null,
) {
  const authStore = useAuthStore()

  const url = `${_API_BASE()}/chat/sessions/${sessionId}/messages/stream`
  const fetchOpts = {
    method: 'POST',
    headers: {
      'Content-Type':  'application/json',
      'Authorization': authStore.token ? `Bearer ${authStore.token}` : '',
    },
    body: JSON.stringify({ content, output_language: outputLanguage }),
  }
  if (signal) fetchOpts.signal = signal

  // Section VI: log request details so browser Network tab details are mirrored in console
  if (import.meta.env.DEV) {
    console.debug('[sse] fetch start', { url, sessionId, outputLanguage })
  }

  const res = await fetch(url, fetchOpts)

  if (import.meta.env.DEV) {
    console.debug('[sse] response received', {
      status:      res.status,
      contentType: res.headers.get('content-type'),
      hasBody:     !!res.body,
    })
  }

  if (res.status === 401) {
    authStore.logout()
    throw Object.assign(new Error('登录已过期，请重新登录'), { status: 401 })
  }
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw Object.assign(new Error(text || `HTTP ${res.status}`), { status: res.status })
  }

  // Section VI: body must exist — null body means SSE can't stream
  if (!res.body) {
    throw Object.assign(
      new Error('SSE response has no body — proxy may be buffering or endpoint is wrong'),
      { status: res.status },
    )
  }

  // ── Legacy named-handler lookup table (backward compat) ────────────────────
  // C25: only used as fallback after onEvent fires.  New code should use onEvent.
  const _legacyMap = {
    user_message_saved:            handlers.onUserSaved,
    session_title_updated:         handlers.onSessionTitleUpdated,
    agent_started:                 handlers.onAgentStarted,
    assistant_placeholder_created: handlers.onPlaceholderCreated,
    intent_detected:               handlers.onIntentDetected,
    planner_started:               handlers.onPlannerStarted,
    planner_step_started:          handlers.onPlannerStepStarted,
    planner_step_completed:        handlers.onPlannerStepCompleted,
    skill_started:                 handlers.onSkillStarted,
    skill_completed:               handlers.onSkillCompleted,
    tool_started:                  handlers.onToolStarted,
    tool_completed:                handlers.onToolCompleted,
    rag_retrieve_started:          handlers.onRagRetrieveStarted,
    rag_retrieve_completed:        handlers.onRagRetrieveCompleted,
    rag_review_started:            handlers.onRagReviewStarted,
    rag_review_completed:          handlers.onRagReviewCompleted,
    confirmation_required:         handlers.onConfirmationRequired,
    cards_delta:                   handlers.onCardsDelta,
    answer_delta:                  handlers.onAnswerDelta,
    agent_completed:               handlers.onCompleted,
    agent_error:                   handlers.onError,
    thinking:                      handlers.onThinking,
    tool_call_start:               handlers.onToolCallStart,
    tool_call_result:              handlers.onToolCallResult,
    final_answer:                  handlers.onFinalAnswer,
    orchestrator_start:            handlers.onOrchestratorStart,
    subagent_start:                handlers.onSubagentStart,
    subagent_result:               handlers.onSubagentResult,
    risk_review_start:             handlers.onRiskReviewStart,
    risk_review_result:            handlers.onRiskReviewResult,
    synthesis_start:               handlers.onSynthesisStart,
  }

  /**
   * C25: universal dispatch — every event reaches onEvent first, then the
   * legacy named callback (if provided).  Unknown event types are no longer
   * silently dropped.
   *
   * Section I fix: handler errors are logged (not silently swallowed).
   * onEventError(err, eventType, payload) is called when onEvent throws.
   */
  const _dispatch = (eventType, payload) => {
    // 1. Universal handler — receives ALL events regardless of type
    if (handlers.onEvent) {
      try {
        handlers.onEvent(eventType, payload)
      } catch (err) {
        console.error('[chat stream] onEvent handler error', { eventType, payload, err })
        if (handlers.onEventError) {
          try { handlers.onEventError(err, eventType, payload) } catch { /* ignore */ }
        }
      }
    }
    // 2. Legacy named handler (backward compat)
    const fn = _legacyMap[eventType]
    if (fn) {
      try { fn(payload) } catch (err) {
        console.warn('[chat stream] legacy handler error', { eventType, err })
      }
    }
  }

  // ── Parse SSE from ReadableStream ──────────────────────────────────────────
  // C25 parser rewrite — fixes cross-chunk state loss and event_type priority.
  // See parseSseStream() below (exported for unit testing).
  await parseSseStream(res.body.getReader(), _dispatch)
}

/**
 * Parse an SSE ReadableStream and call dispatch(eventType, payload) for each
 * complete SSE event.  Exported for unit testing.
 *
 * Fixes vs. the previous inline parser:
 *
 *  1. Parser state (sseType, sseData, leftover) lives OUTSIDE the read() loop
 *     so it survives across chunk boundaries.  Previously curEventType was reset
 *     to 'message' on every reader.read(), causing cross-chunk events to lose
 *     their event: field and be dispatched as the wrong type.
 *
 *  2. Multi-line data: multiple consecutive "data:" lines are accumulated in an
 *     array and joined with '\n' before JSON.parse (SSE spec §9.2.6).
 *
 *  3. CRLF: trailing \r stripped from each line.
 *
 *  4. SSE comments (lines starting with ':') are silently ignored.
 *
 *  5. Event type priority: parsed.event_type > SSE "event:" field > 'message'.
 *     The old code used `curEventType || parsed.event_type`, which meant the
 *     truthy default 'message' always won over parsed.event_type.
 *
 *  6. EOF fallback: pending data is dispatched even without a trailing blank line.
 *
 *  7. Malformed JSON: skipped silently; subsequent events are unaffected.
 *
 * @param {ReadableStreamDefaultReader} reader  from res.body.getReader()
 * @param {function(string, any): void}  dispatch  called with (eventType, payload)
 */
export async function parseSseStream(reader, dispatch) {
  const decoder  = new TextDecoder()
  let   leftover = ''   // incomplete line fragment from previous chunk
  let   sseType  = ''   // current SSE "event:" field value (empty = not set)
  let   sseData  = []   // accumulated "data:" lines for current event
  const _dev     = typeof import.meta !== 'undefined' && !!import.meta.env?.DEV

  /** Flush the current accumulated event to dispatch. */
  const _flush = () => {
    if (sseData.length === 0) return
    const raw       = sseData.join('\n')
    const savedType = sseType
    sseType = ''
    sseData = []
    if (!raw.trim()) return
    try {
      const parsed    = JSON.parse(raw)
      // Priority: JSON-embedded event_type > SSE event: field > 'message'
      const eventType = parsed.event_type || savedType || 'message'
      if (_dev) console.debug('[sse dispatch]', eventType, parsed.payload ?? parsed)
      dispatch(eventType, parsed.payload ?? parsed)
    } catch (err) {
      // Section II: malformed JSON must warn — not silently skip
      if (_dev) console.warn('[sse malformed json]', { raw: raw.slice(0, 300), err: err?.message })
    }
  }

  /**
   * Process a decoded text chunk: split into lines, update parser state,
   * flush on blank line.
   *
   * @param {string}  text    Decoded string from the current chunk.
   * @param {boolean} isEof   When true (stream ended), do NOT hold the last
   *                          line as leftover — treat it as a complete line so
   *                          events without a trailing blank line are flushed.
   */
  const _processText = (text, isEof = false) => {
    // Section VII: log raw chunk for deep debugging
    if (_dev && text) console.debug('[sse chunk]', text.slice(0, 500))

    const rawLines = (leftover + text).split('\n')
    // On EOF: the last fragment IS the final line — process it.
    // During streaming: the last fragment may be incomplete — keep as leftover.
    leftover = isEof ? '' : (rawLines.pop() ?? '')

    for (const rawLine of rawLines) {
      const line = rawLine.replace(/\r$/, '')  // CRLF → LF

      if (_dev && line) console.debug('[sse raw line]', line)

      if (line === '') {
        _flush()                              // blank line → end of SSE event
      } else if (line.startsWith(':')) {
        /* SSE comment / keepalive — intentionally ignored */
      } else if (line.startsWith('event:')) {
        sseType = line.slice(6).trim()        // "event: foo" or "event:foo"
      } else if (line.startsWith('data:')) {
        // Strip exactly one leading space per SSE spec
        sseData.push(line.slice(5).replace(/^ /, ''))
      }
      // id:, retry: fields intentionally ignored
    }
  }

  if (_dev) console.debug('[sse] stream opened')
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        // Flush TextDecoder's internal buffer (handles multi-byte chars at boundary),
        // then process with isEof=true so the last line isn't held as leftover.
        _processText(decoder.decode(), true)
        // EOF fallback: dispatch any event that arrived without a trailing blank line.
        _flush()
        if (_dev) console.debug('[sse] stream closed (EOF)')
        break
      }
      _processText(decoder.decode(value, { stream: true }))
    }
  } catch (err) {
    if (err?.name === 'AbortError') {
      if (_dev) console.debug('[sse] stream aborted')
    } else {
      if (_dev) console.debug('[sse] stream error', err)
    }
    throw err
  }
}
