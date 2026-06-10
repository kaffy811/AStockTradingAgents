import { baseFetch } from './http.js'
import { useAuthStore } from '../stores/auth.js'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1'

/**
 * POST /analysis/comprehensive  (legacy — kept for backward compat)
 */
export async function getComprehensive(market, symbol, options = {}) {
  return baseFetch('/analysis/comprehensive', {
    method: 'POST',
    body: JSON.stringify({ market, symbol }),
    signal: options.signal,
  })
}

/**
 * POST /analysis/comprehensive-v2  (M4-a: analysis_scope; M4-b.6: optional engine)
 */
export function runComprehensiveAnalysisV2(payload, options = {}) {
  const body = {
    market:          payload.market,
    symbol:          payload.symbol,
    analysis_scope:  payload.analysis_scope || 'comprehensive',
    output_language: payload.output_language || 'zh-CN',
  }
  if (payload.engine) {
    body.engine = payload.engine
  }
  return baseFetch('/analysis/comprehensive-v2', {
    method: 'POST',
    body:   JSON.stringify(body),
    signal: options.signal,
  })
}

// ── M25-a SSE Analysis Runs ───────────────────────────────────────────────────

/**
 * POST /analysis/runs — create a new SSE-backed analysis run.
 * M25-c: optional engine field ("custom_coordinator" | "langgraph")
 */
export function createAnalysisRun(payload, options = {}) {
  const body = {
    market:          payload.market,
    symbol:          payload.symbol,
    analysis_scope:  payload.analysis_scope || 'comprehensive',
    output_language: payload.output_language || 'zh-CN',
  }
  if (payload.engine) {
    body.engine = payload.engine
  }
  return baseFetch('/analysis/runs', {
    method: 'POST',
    body:   JSON.stringify(body),
    signal: options.signal,
  })
}

/**
 * GET /analysis/runs/{runId} — poll run status / result.
 */
export function getAnalysisRun(runId, options = {}) {
  return baseFetch(`/analysis/runs/${encodeURIComponent(runId)}`, {
    signal: options.signal,
  })
}

/**
 * POST /analysis/runs/{runId}/cancel — cancel a running analysis.
 */
export function cancelAnalysisRun(runId) {
  return baseFetch(`/analysis/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
  })
}

// ── M25-b: subscribeAnalysisEvents with reconnect ────────────────────────────

const _TERMINAL_EVENTS = new Set(['report_ready', 'analysis_failed', 'cancelled'])

/**
 * Subscribe to SSE progress events for a run.
 *
 * Uses fetch + ReadableStream (NOT EventSource) to support Authorization header.
 *
 * M25-b reconnect strategy:
 *   - Tracks lastEventId from SSE id: fields
 *   - On unexpected stream drop (not abort, not terminal event):
 *     waits 500 ms, reconnects once with ?after_event_id=lastEventId
 *   - If reconnect also fails: calls handlers.onError
 *
 * @param {string} runId
 * @param {{
 *   onEvent:  (event: object) => void,
 *   onDone?:  () => void,
 *   onError?: (err: Error) => void,
 * }} handlers
 * @param {AbortSignal} [signal]
 */
export async function subscribeAnalysisEvents(runId, handlers, signal) {
  let lastEventId      = -1
  let terminalReceived = false

  /**
   * Execute one SSE connection attempt.
   * @param {number|null} afterEventId  If ≥ 0, appended as ?after_event_id=N
   * @returns {'done'|'dropped'|'abort'|'error'}
   */
  async function _connect(afterEventId) {
    if (signal?.aborted) return 'abort'

    const authStore = useAuthStore()
    const qs  = (afterEventId !== null && afterEventId >= 0)
      ? `?after_event_id=${afterEventId}`
      : ''
    const url = `${API_BASE}/analysis/runs/${encodeURIComponent(runId)}/events${qs}`

    let response
    try {
      response = await fetch(url, {
        headers: {
          'Accept':        'text/event-stream',
          'Cache-Control': 'no-cache',
          ...(authStore.token ? { 'Authorization': `Bearer ${authStore.token}` } : {}),
        },
        signal,
      })
    } catch (err) {
      return err?.name === 'AbortError' ? 'abort' : 'error'
    }

    if (!response.ok) return 'error'

    const reader  = response.body.getReader()
    const decoder = new TextDecoder()
    let   buffer  = ''
    let   currentEvent = {}
    let   streamEndSeen = false

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) return streamEndSeen ? 'done' : 'dropped'

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          // SSE comment — heartbeat or stream-end marker
          if (line.startsWith(':')) {
            if (line.includes('stream-end')) streamEndSeen = true
            currentEvent = {}
            continue
          }

          // Empty line → dispatch event
          if (line === '') {
            if (currentEvent.data !== undefined) {
              try {
                const parsed = JSON.parse(currentEvent.data)
                // Update lastEventId from SSE id: field
                if (currentEvent.id !== undefined) {
                  const n = parseInt(currentEvent.id, 10)
                  if (!isNaN(n)) lastEventId = n
                }
                handlers.onEvent(parsed)
                if (_TERMINAL_EVENTS.has(parsed.event)) {
                  terminalReceived = true
                  streamEndSeen    = true
                }
              } catch { /* ignore malformed JSON */ }
            }
            currentEvent = {}
            continue
          }

          if      (line.startsWith('event:')) currentEvent.event = line.slice(6).trim()
          else if (line.startsWith('data:'))  currentEvent.data  = line.slice(5).trim()
          else if (line.startsWith('id:'))    currentEvent.id    = line.slice(3).trim()
        }
      }
    } catch (err) {
      return err?.name === 'AbortError' ? 'abort' : 'dropped'
    } finally {
      reader.releaseLock()
    }
  }

  // ── First connection ───────────────────────────────────────────────────────
  const reason1 = await _connect(null)
  if (signal?.aborted || terminalReceived || reason1 === 'done' || reason1 === 'abort') {
    handlers.onDone?.()
    return
  }

  // ── One reconnect attempt on unexpected drop ───────────────────────────────
  if (reason1 === 'dropped' || reason1 === 'error') {
    // Brief pause before reconnect
    await new Promise(r => setTimeout(r, 500))
    if (signal?.aborted || terminalReceived) {
      handlers.onDone?.()
      return
    }

    const reason2 = await _connect(lastEventId >= 0 ? lastEventId : null)
    if (signal?.aborted || terminalReceived || reason2 === 'done' || reason2 === 'abort') {
      handlers.onDone?.()
      return
    }

    // Reconnect also failed
    handlers.onError?.(new Error('SSE 连接中断，重连失败'))
    handlers.onDone?.()
    return
  }

  handlers.onDone?.()
}
