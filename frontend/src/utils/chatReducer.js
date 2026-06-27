/**
 * chatReducer.js — Phase 2E-3.
 *
 * applyChatUiEvent(message, uiEvent) mutates a reactive Vue message object in place.
 *
 * Expected message fields (add these when constructing a new assistant message):
 *   reasoningSteps: []     ← orchestrator / agent step cards
 *   toolTrace:      []     ← tool call trace rows
 *   thinkingContent: ''    ← DeepSeek reasoning_content (streamed)
 *   answerContent:   ''    ← streaming answer text accumulator
 *   content:         ''    ← rendered text (mirrors answerContent; also final fallback)
 *   finalAnswer:     null  ← structured OrchestratorResponse / FinalAnswer
 *   agentTrace:      []    ← Phase 2E-2 backward compat
 *   status: 'connecting'   ← 'connecting' | 'streaming' | 'done' | 'error'
 *   isStreaming: true
 *   error: null
 */

// ── Internal helpers ───────────────────────────────────────────────────────────

/** findLastIndex polyfill (Safari < 15.4, older Chrome) */
function _findLastIndex(arr, predicate) {
  for (let i = arr.length - 1; i >= 0; i--) {
    if (predicate(arr[i])) return i
  }
  return -1
}

// ── Main reducer ───────────────────────────────────────────────────────────────

/**
 * Apply a single normalized UI event to a reactive message object.
 *
 * @param {object} message  Reactive Vue object (mutated in-place)
 * @param {object} uiEvent  Normalized event from normalizeChatEvent()
 */
export function applyChatUiEvent(message, uiEvent) {
  if (!uiEvent) return

  switch (uiEvent.type) {

    // ── Agent / orchestrator step cards ───────────────────────────────────────
    case 'ui_step_start': {
      if (!message.reasoningSteps) message.reasoningSteps = []

      // avoid duplicate running entry for same stepKey
      const dup = message.reasoningSteps.find(
        s => s.key === uiEvent.stepKey && s.status === 'running'
      )
      if (!dup) {
        message.reasoningSteps.push({
          key:       uiEvent.stepKey,
          title:     uiEvent.title,
          status:    'running',
          summary:   uiEvent.summary ?? '',
          riskFlags: [],
          startedAt: Date.now(),
        })
      }

      // Keep agentTrace in sync for Phase 2E-2 backward compat
      if (!message.agentTrace) message.agentTrace = []
      const adDup = message.agentTrace.find(
        a => a.name === uiEvent.stepKey && a.status === 'running'
      )
      if (!adDup) {
        message.agentTrace.push({
          type:        uiEvent.stepKey.split(':')[0],
          name:        uiEvent.stepKey,
          displayName: uiEvent.title,
          status:      'running',
          summary:     uiEvent.summary ?? '',
          riskFlags:   [],
        })
      }
      break
    }

    case 'ui_step_done': {
      if (!message.reasoningSteps) message.reasoningSteps = []

      const idx = _findLastIndex(
        message.reasoningSteps,
        s => s.key === uiEvent.stepKey && s.status === 'running'
      )
      if (idx >= 0) {
        Object.assign(message.reasoningSteps[idx], {
          status:     uiEvent.status ?? 'success',
          summary:    uiEvent.summary ?? message.reasoningSteps[idx].summary,
          riskFlags:  uiEvent.riskFlags ?? [],
          finishedAt: Date.now(),
        })
      }

      // agentTrace compat
      if (message.agentTrace) {
        const ai = _findLastIndex(
          message.agentTrace,
          a => a.name === uiEvent.stepKey && a.status === 'running'
        )
        if (ai >= 0) {
          Object.assign(message.agentTrace[ai], {
            status:    uiEvent.status ?? 'success',
            summary:   uiEvent.summary ?? '',
            riskFlags: uiEvent.riskFlags ?? [],
          })
        }
      }
      break
    }

    // ── Tool call trace ────────────────────────────────────────────────────────
    case 'ui_tool_start': {
      if (!message.toolTrace) message.toolTrace = []
      if (message.toolTrace.length >= 20) break

      // avoid duplicate running entry
      const running = message.toolTrace.find(
        t => t.key === uiEvent.stepKey && t.status === 'running'
      )
      // C25.13: also skip if this tool key already completed — a second tool_started
      // for the same key (e.g. Phase-5 re-emission or filtered-result event) must not
      // create a second trace entry. The subsequent ui_tool_done will merge the summary.
      const alreadyCompleted = message.toolTrace.find(
        t => t.key === uiEvent.stepKey && t.status !== 'running'
      )
      if (!running && !alreadyCompleted) {
        message.toolTrace.push({
          key:       uiEvent.stepKey,
          name:      uiEvent.stepKey.replace(/^[^:]+:/, ''),
          title:     uiEvent.title,
          status:    'running',
          summary:   '执行中…',
          detail:    uiEvent.detail ?? '',
          startedAt: Date.now(),
        })
      }
      break
    }

    case 'ui_tool_done': {
      if (!message.toolTrace) message.toolTrace = []

      const idx = _findLastIndex(
        message.toolTrace,
        t => t.key === uiEvent.stepKey && t.status === 'running'
      )
      if (idx >= 0) {
        Object.assign(message.toolTrace[idx], {
          status:     uiEvent.status ?? 'success',
          summary:    uiEvent.summary ?? '',
          finishedAt: Date.now(),
        })
      } else if (message.toolTrace.length < 20) {
        // C25.12: if a completed entry already exists for this key, MERGE the summary
        // instead of ignoring — Phase 5 fallback re-emits tool_completed events, and
        // the second emission may carry a more specific summary (filtered result count).
        const doneIdx = message.toolTrace.findIndex(
          t => t.key === uiEvent.stepKey && t.status !== 'running'
        )
        if (doneIdx >= 0) {
          // Update summary only if new summary is non-empty and different
          const newSummary = uiEvent.summary ?? ''
          if (newSummary && newSummary !== message.toolTrace[doneIdx].summary) {
            message.toolTrace[doneIdx].summary = newSummary
          }
          // title update: prefer the newer non-generic title
          if (uiEvent.title && uiEvent.title !== 'tool' && !message.toolTrace[doneIdx].title) {
            message.toolTrace[doneIdx].title = uiEvent.title
          }
        } else {
          // Orphan done entry — no prior start event
          message.toolTrace.push({
            key:       uiEvent.stepKey,
            name:      uiEvent.stepKey.replace(/^[^:]+:/, ''),
            title:     uiEvent.title,
            status:    uiEvent.status ?? 'success',
            summary:   uiEvent.summary ?? '',
            startedAt: Date.now(), // prevents sorting to position 0
          })
        }
      }
      break
    }

    // ── Streaming content ──────────────────────────────────────────────────────
    case 'ui_thinking_delta':
      message.thinkingContent = (message.thinkingContent ?? '') + (uiEvent.content ?? '')
      break

    // C28.5: structured thinking item (agent_step / tool_planning / deepseek_reasoning …)
    case 'ui_thinking_item': {
      if (!message.thinkingItems) message.thinkingItems = []
      const newItem = {
        source:     uiEvent.source,
        stage:      uiEvent.stage      ?? '',
        title:      uiEvent.title      ?? '',
        content:    uiEvent.content    ?? '',
        importance: uiEvent.importance ?? 'medium',
        timestamp:  Date.now(),
      }
      // C28.2: replace same-source+stage item (e.g. data_quality_review re-emitted after
      // final compute_data_quality — prevents optimistic early value staying visible)
      if (newItem.source && newItem.stage) {
        const existIdx = message.thinkingItems.findIndex(
          t => t.source === newItem.source && t.stage === newItem.stage
        )
        if (existIdx >= 0) {
          message.thinkingItems[existIdx] = newItem
        } else {
          message.thinkingItems.push(newItem)
        }
      } else {
        message.thinkingItems.push(newItem)
      }
      // DeepSeek reasoning also feeds the legacy thinkingContent accumulator for the
      // raw thinking panel (backward compat with existing tests / ChatReasoningPanel).
      if (uiEvent.source === 'deepseek_reasoning' && uiEvent.content) {
        message.thinkingContent = (message.thinkingContent ?? '') + uiEvent.content
      }
      break
    }

    case 'ui_answer_delta':
      message.answerContent = (message.answerContent ?? '') + (uiEvent.content ?? '')
      message.content       = message.answerContent
      break

    // ── Final answer ───────────────────────────────────────────────────────────
    case 'ui_final_answer': {
      const fa = uiEvent.data
      if (fa && typeof fa === 'object') {
        message.finalAnswer = fa
        // C28.1: prefer sanitized full_text from backend (preamble-free);
        // falls back to accumulated answerContent or structured fields.
        if (fa.full_text) {
          // full_text is the backend-sanitized, preamble-stripped answer
          message.answerContent = fa.full_text
          message.content       = fa.full_text
        } else if (!message.answerContent && (fa.summary || fa.analysis || fa.disclaimer)) {
          message.content = [fa.summary, fa.analysis].filter(Boolean).join('\n\n')
        }
        // If answerContent already present and no full_text, keep it (streaming path)

        // C28.3/C28.4: sync data_quality_review thinking item with final card level.
        // C28.4: use broad filter (not exact findIndex) — removes ALL stale dq items
        // regardless of source/stage variation, then inserts the authoritative final item.
        const _dq = fa.data_quality
        if (_dq?.level) {
          const _DQ_THINKING_TEXT = {
            high:         '数据质量：数据完整。已获取多维度数据，信息完整度高。',
            medium:       '数据质量：数据部分完整。仍有部分关键数据缺失。',
            low:          '数据质量：数据有限。仅获取到行情或新闻数据，缺少财务及深度研究数据。',
            insufficient: '数据质量：数据不足。当前缺少可靠数据，无法完整判断。',
          }
          const _dqText = _DQ_THINKING_TEXT[_dq.level]
          if (_dqText) {
            if (!message.thinkingItems) message.thinkingItems = []
            // Remove ALL stale data-quality thinking items by any of 4 heuristics
            message.thinkingItems = message.thinkingItems.filter(t =>
              t.source !== 'data_quality_review' &&
              !String(t.stage  ?? '').includes('data_quality') &&
              !String(t.title  ?? '').includes('数据质量') &&
              !String(t.title  ?? '').includes('检查数据质量') &&
              !String(t.content ?? '').startsWith('数据质量：')
            )
            // Insert the authoritative final item
            message.thinkingItems.push({
              source:     'data_quality_review',
              stage:      'data_quality',
              title:      '检查数据质量',
              content:    _dqText,
              importance: (_dq.level === 'low' || _dq.level === 'insufficient') ? 'high' : 'medium',
              timestamp:  Date.now(),
            })
          }
        }
      }
      break
    }

    // ── Terminal: done ─────────────────────────────────────────────────────────
    // Replace arrays (not forEach-mutate) so Vue always detects the change.
    // Also clear "执行中…" summary text and stamp finishedAt.
    case 'ui_done': {
      const _now = Date.now()
      message.status      = 'done'
      message.isStreaming = false
      // C25.11: also recover steps that were marked failed/error+中断 by a transient ui_error
      // (happens when agent_error fires mid-stream but agent_completed follows it).
      // reasoningSteps get status:'failed'; toolTrace gets status:'error' — cover both.
      const _isTransientFailed = s =>
        (s.status === 'failed' || s.status === 'error') && (s.summary === '中断' || !s.summary)
      message.reasoningSteps = (message.reasoningSteps ?? []).map(s =>
        s.status === 'running' || _isTransientFailed(s)
          ? { ...s, status: 'success', summary: s.summary && s.summary !== '中断' ? s.summary : '已完成', finishedAt: _now }
          : s
      )
      message.toolTrace = (message.toolTrace ?? []).map(t =>
        t.status === 'running' || _isTransientFailed(t)
          ? { ...t, status: 'success', summary: (t.summary && t.summary !== '执行中…' && t.summary !== '中断') ? t.summary : '已完成', finishedAt: _now }
          : t
      )
      message.agentTrace = (message.agentTrace ?? []).map(a =>
        a.status === 'running' || _isTransientFailed(a)
          ? { ...a, status: 'success', summary: a.summary && a.summary !== '中断' ? a.summary : '已完成', finishedAt: _now }
          : a
      )
      break
    }

    // ── Terminal: error ────────────────────────────────────────────────────────
    case 'ui_error': {
      const _now2 = Date.now()
      message.status      = 'error'
      message.isStreaming = false
      message.error       = uiEvent.message
      if (!message.content) message.content = uiEvent.message
      message.reasoningSteps = (message.reasoningSteps ?? []).map(s =>
        s.status === 'running'
          ? { ...s, status: 'failed', summary: s.summary || '中断', finishedAt: _now2 }
          : s
      )
      message.toolTrace = (message.toolTrace ?? []).map(t =>
        t.status === 'running'
          ? { ...t, status: 'error',  summary: (t.summary && t.summary !== '执行中…') ? t.summary : '中断', finishedAt: _now2 }
          : t
      )
      message.agentTrace = (message.agentTrace ?? []).map(a =>
        a.status === 'running'
          ? { ...a, status: 'failed', summary: a.summary || '中断', finishedAt: _now2 }
          : a
      )
      break
    }

    // ── C27: data quality card (skill path) ───────────────────────────────────
    case 'ui_data_quality_update': {
      if (uiEvent.dataQuality) {
        message.dataQuality = uiEvent.dataQuality
      }
      // Merge sources if not already provided by final_answer
      if (uiEvent.sources && uiEvent.sources.length > 0) {
        if (!message.finalAnswer) {
          if (!message.skillSources) message.skillSources = []
          message.skillSources = uiEvent.sources
        }
      }
      break
    }

    // Unknown UI events — silently ignore
    default:
      break
  }
}
