/**
 * sseParser.test.js — SSE parser robustness tests (C25 fix).
 *
 * Tests parseSseStream() in isolation using a fake ReadableStream reader.
 * No fetch / auth mocking required — the parser is a pure async function.
 *
 * Covers:
 *   T1  same-chunk event + data
 *   T2  cross-chunk split (event in chunk N, data in chunk N+1)
 *   T3  no "event:" line — parsed.event_type used instead of "message"
 *   T4  multi-line data lines — no crash
 *   T5  CRLF line endings
 *   T6  SSE comment / keepalive ignored
 *   T7  EOF without trailing blank line — EOF fallback dispatches
 *   T8  malformed JSON — no crash, subsequent events still arrive
 *   T9  agent_completed normalizes to ui_done via chatEventNormalizer
 *   T10 multiple events in one stream
 *   T11 data: line without space after colon (data:foo)
 *   T12 event: field split exactly at chunk boundary (mid-line)
 */

import { describe, it, expect } from 'vitest'
import { parseSseStream } from '../api/chat.js'
import { normalizeChatEvent } from '../utils/chatEventNormalizer.js'

// ── Helper ────────────────────────────────────────────────────────────────────

/**
 * Build a fake ReadableStreamDefaultReader from an array of string chunks.
 * Each string is encoded to Uint8Array and yielded in order.
 */
function makeReader(chunks) {
  const encoder = new TextEncoder()
  let   idx     = 0
  const stream  = new ReadableStream({
    pull(controller) {
      if (idx < chunks.length) {
        controller.enqueue(encoder.encode(chunks[idx++]))
      } else {
        controller.close()
      }
    },
  })
  return stream.getReader()
}

/** Run parseSseStream and collect all (eventType, payload) pairs. */
async function collect(chunks) {
  const events = []
  await parseSseStream(
    makeReader(chunks),
    (eventType, payload) => events.push({ eventType, payload }),
  )
  return events
}

// ── T1: event + data in the same chunk ───────────────────────────────────────

describe('T1 — same-chunk event and data', () => {
  it('dispatches agent_completed with correct type and payload', async () => {
    const events = await collect([
      'event: agent_completed\n' +
      'data: {"event_type":"agent_completed","payload":{}}\n\n',
    ])
    expect(events).toHaveLength(1)
    expect(events[0].eventType).toBe('agent_completed')
    expect(events[0].payload).toEqual({})
  })
})

// ── T2: event and data split across two chunks ────────────────────────────────

describe('T2 — cross-chunk: event in chunk 1, data in chunk 2', () => {
  it('dispatches final_answer with merged state', async () => {
    const events = await collect([
      'event: final_answer\n',
      'data: {"event_type":"final_answer","payload":{"summary":"ok"}}\n\n',
    ])
    expect(events).toHaveLength(1)
    expect(events[0].eventType).toBe('final_answer')
    expect(events[0].payload).toEqual({ summary: 'ok' })
  })

  it('also works when the blank line is in a third chunk', async () => {
    const events = await collect([
      'event: agent_completed\n',
      'data: {"event_type":"agent_completed","payload":{}}\n',
      '\n',
    ])
    expect(events).toHaveLength(1)
    expect(events[0].eventType).toBe('agent_completed')
  })

  it('works when a single line is split mid-character across chunks', async () => {
    // Split the data: line itself across two chunks
    const full = 'event: agent_completed\ndata: {"event_type":"agent_completed","payload":{}}\n\n'
    const mid  = Math.floor(full.length / 2)
    const events = await collect([full.slice(0, mid), full.slice(mid)])
    expect(events).toHaveLength(1)
    expect(events[0].eventType).toBe('agent_completed')
  })
})

// ── T3: no "event:" line — must use parsed.event_type, NOT "message" ─────────

describe('T3 — no event: line, only data with event_type in JSON', () => {
  it('uses parsed.event_type instead of default "message"', async () => {
    const events = await collect([
      'data: {"event_type":"agent_completed","payload":{}}\n\n',
    ])
    expect(events).toHaveLength(1)
    expect(events[0].eventType).toBe('agent_completed')  // NOT 'message'
  })

  it('uses parsed.event_type for final_answer without SSE event: line', async () => {
    const events = await collect([
      'data: {"event_type":"final_answer","payload":{"summary":"done"}}\n\n',
    ])
    expect(events[0].eventType).toBe('final_answer')
    expect(events[0].payload.summary).toBe('done')
  })
})

// ── T4: multi-line data: lines ────────────────────────────────────────────────

describe('T4 — multi-line data: lines', () => {
  it('joins data lines with newline and does not crash on invalid JSON', async () => {
    // Each "data:" line is a separate SSE data field; joined → may be invalid JSON
    const events = await collect([
      'event: answer_delta\n' +
      'data: {"event_type":"answer_delta",\n' +    // line 1 of data (invalid JSON alone)
      'data: "payload":{"delta":"你好"}}\n\n',     // line 2 of data
    ])
    // Result may be 0 (invalid JSON) or 1 (if join is valid) — either is acceptable.
    // The critical guarantee: no exception thrown.
    expect(Array.isArray(events)).toBe(true)
  })

  it('handles valid multi-line data by joining correctly', async () => {
    // Valid JSON split across two data: lines (JSON doesn't care about embedded newlines)
    const events = await collect([
      'event: agent_completed\n' +
      'data: {"event_type":"agent_completed",\n' +
      'data: "payload":{}}\n\n',
    ])
    // JSON.parse('{"event_type":"agent_completed",\n"payload":{}}') IS valid
    expect(events).toHaveLength(1)
    expect(events[0].eventType).toBe('agent_completed')
  })
})

// ── T5: CRLF line endings ─────────────────────────────────────────────────────

describe('T5 — CRLF line endings', () => {
  it('strips \\r and parses correctly', async () => {
    const events = await collect([
      'event: agent_completed\r\n' +
      'data: {"event_type":"agent_completed","payload":{}}\r\n' +
      '\r\n',
    ])
    expect(events).toHaveLength(1)
    expect(events[0].eventType).toBe('agent_completed')
  })

  it('handles mixed CRLF and LF in the same stream', async () => {
    const events = await collect([
      'event: agent_completed\r\n' +
      'data: {"event_type":"agent_completed","payload":{}}\n' +
      '\n',
    ])
    expect(events).toHaveLength(1)
    expect(events[0].eventType).toBe('agent_completed')
  })
})

// ── T6: SSE comment / keepalive ───────────────────────────────────────────────

describe('T6 — SSE comment / keepalive ignored', () => {
  it('does not dispatch on ":" comment line', async () => {
    const events = await collect([': keepalive\n\n'])
    expect(events).toHaveLength(0)
  })

  it('ignores keepalives between events; other events still arrive', async () => {
    const events = await collect([
      ': keepalive\n\n',
      'event: agent_completed\n' +
      'data: {"event_type":"agent_completed","payload":{}}\n\n',
      ': keepalive\n\n',
    ])
    expect(events).toHaveLength(1)
    expect(events[0].eventType).toBe('agent_completed')
  })
})

// ── T7: EOF without trailing blank line ───────────────────────────────────────

describe('T7 — EOF fallback: stream ends without trailing blank line', () => {
  it('still dispatches the pending event', async () => {
    const events = await collect([
      // No trailing \n\n
      'event: agent_completed\n' +
      'data: {"event_type":"agent_completed","payload":{}}',
    ])
    expect(events).toHaveLength(1)
    expect(events[0].eventType).toBe('agent_completed')
  })

  it('works for final_answer too', async () => {
    const events = await collect([
      'data: {"event_type":"final_answer","payload":{"summary":"test"}}',
    ])
    expect(events).toHaveLength(1)
    expect(events[0].eventType).toBe('final_answer')
  })
})

// ── T8: malformed JSON ────────────────────────────────────────────────────────

describe('T8 — malformed JSON does not crash or block subsequent events', () => {
  it('skips bad JSON and processes following valid event', async () => {
    const events = await collect([
      'event: answer_delta\ndata: {bad json}\n\n',
      'event: agent_completed\ndata: {"event_type":"agent_completed","payload":{}}\n\n',
    ])
    // First event skipped (bad JSON), second received
    expect(events).toHaveLength(1)
    expect(events[0].eventType).toBe('agent_completed')
  })

  it('does not throw on completely empty data line', async () => {
    const events = await collect(['data: \n\n'])
    expect(events).toHaveLength(0)  // empty body, _flush exits early
  })
})

// ── T9: agent_completed → ui_done in normalizer ───────────────────────────────

describe('T9 — chatEventNormalizer: agent_completed → ui_done', () => {
  it('maps agent_completed to ui_done', () => {
    const r = normalizeChatEvent('agent_completed', {})
    expect(r).not.toBeNull()
    expect(r.type).toBe('ui_done')
  })

  it('maps done alias to ui_done (C25)', () => {
    const r = normalizeChatEvent('done', {})
    expect(r?.type).toBe('ui_done')
  })

  it('maps completed alias to ui_done (C25)', () => {
    const r = normalizeChatEvent('completed', {})
    expect(r?.type).toBe('ui_done')
  })

  it('maps stream_done alias to ui_done (C25)', () => {
    const r = normalizeChatEvent('stream_done', {})
    expect(r?.type).toBe('ui_done')
  })
})

// ── T10: multiple events in one stream ────────────────────────────────────────

describe('T10 — multiple events in a single stream', () => {
  it('dispatches all events in order', async () => {
    const events = await collect([
      'event: tool_call_start\ndata: {"event_type":"tool_call_start","payload":{"tool_name":"stock_quote_tool"}}\n\n' +
      'event: tool_call_result\ndata: {"event_type":"tool_call_result","payload":{"tool_name":"stock_quote_tool","status":"success"}}\n\n' +
      'event: agent_completed\ndata: {"event_type":"agent_completed","payload":{}}\n\n',
    ])
    expect(events).toHaveLength(3)
    expect(events[0].eventType).toBe('tool_call_start')
    expect(events[1].eventType).toBe('tool_call_result')
    expect(events[2].eventType).toBe('agent_completed')
  })
})

// ── T11: data: without space after colon ─────────────────────────────────────

describe('T11 — data: field with and without space after colon', () => {
  it('handles "data:foo" (no space)', async () => {
    const events = await collect([
      'data:{"event_type":"agent_completed","payload":{}}\n\n',
    ])
    expect(events).toHaveLength(1)
    expect(events[0].eventType).toBe('agent_completed')
  })

  it('handles "data: foo" (one space)', async () => {
    const events = await collect([
      'data: {"event_type":"agent_completed","payload":{}}\n\n',
    ])
    expect(events).toHaveLength(1)
    expect(events[0].eventType).toBe('agent_completed')
  })
})

// ── T12: event: field split at chunk boundary (mid-line) ─────────────────────

describe('T12 — event: line split mid-character across two chunks', () => {
  it('correctly reads the full event type name', async () => {
    // Split: "event: agent_" in chunk1, "completed\n..." in chunk2
    const events = await collect([
      'event: agent_',
      'completed\ndata: {"event_type":"agent_completed","payload":{}}\n\n',
    ])
    expect(events).toHaveLength(1)
    expect(events[0].eventType).toBe('agent_completed')
  })
})
