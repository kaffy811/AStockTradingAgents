<template>
  <div ref="listRef" class="message-list">

    <!-- Welcome state (empty messages) -->
    <div v-if="messages.length === 0" class="msg-welcome">
      <div class="msg-welcome-icon">💬</div>
      <p class="msg-welcome-text">{{ t('chat_welcome') }}</p>
    </div>

    <!-- Messages -->
    <TransitionGroup name="msg-appear" tag="div" class="msg-items">
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="msg-row"
        :class="`msg-row--${msg.role}`"
      >
        <!-- User bubble -->
        <div v-if="msg.role === 'user'" class="msg-bubble msg-bubble--user">
          <p class="msg-text">{{ msg.content }}</p>
          <!-- C29.4: user message actions -->
          <div class="msg-actions msg-actions--user">
            <button class="msg-action-btn" @click="onCopyUser(msg.content)" :title="t('chat_copy')">⎘</button>
            <button class="msg-action-btn" @click="$emit('edit-user', msg.id, msg.content)" :title="t('chat_edit')">✎</button>
          </div>
        </div>

        <!-- Assistant bubble -->
        <div v-else class="msg-bubble msg-bubble--assistant">
          <!-- Avatar -->
          <div class="msg-avatar">🤖</div>

          <!-- Bubble content -->
          <div class="msg-content">
            <!-- C29.1: Reasoning panel — debug-only; hidden in production -->
            <ChatReasoningPanel
              v-if="SHOW_REASONING_PANEL"
              :isStreaming="msg.isStreaming"
              :status="msg.status ?? (msg.isStreaming ? 'streaming' : 'done')"
              :reasoningSteps="msg.reasoningSteps ?? []"
              :toolTrace="msg.toolTrace ?? []"
              :agentTrace="msg.agentTrace ?? []"
              :thinkingContent="msg.thinkingContent ?? ''"
              :thinkingItems="msg.thinkingItems ?? []"
            />

            <!-- C29.1: Stream debug panel — debug-only -->
            <div
              v-if="SHOW_STREAM_DEBUG && (msg.isStreaming || msg.streamDebug?.eventsReceived > 0)"
              class="stream-debug-panel"
            >
              <div class="sdp-title">[Stream Debug]</div>
              <div class="sdp-grid">
                <span class="sdp-k">status</span>
                <span class="sdp-v">{{ msg.status ?? '–' }}</span>

                <span class="sdp-k">isStreaming</span>
                <span class="sdp-v">{{ msg.isStreaming }}</span>

                <span class="sdp-k">eventsReceived</span>
                <span class="sdp-v" :class="{ 'sdp-warn': msg.isStreaming && !msg.streamDebug?.eventsReceived }">
                  {{ msg.streamDebug?.eventsReceived ?? 0 }}
                </span>

                <span class="sdp-k">lastEventType</span>
                <span class="sdp-v">{{ msg.streamDebug?.lastEventType ?? '–' }}</span>

                <span class="sdp-k">lastEventAt</span>
                <span class="sdp-v">{{ _fmtTs(msg.streamDebug?.lastEventAt) }}</span>

                <span class="sdp-k">handlerErrors</span>
                <span class="sdp-v" :class="{ 'sdp-error': msg.streamDebug?.handlerErrors > 0 }">
                  {{ msg.streamDebug?.handlerErrors ?? 0 }}
                </span>

                <span class="sdp-k">droppedEvents</span>
                <span class="sdp-v" :class="{ 'sdp-error': msg.streamDebug?.droppedEvents > 0 }">
                  {{ msg.streamDebug?.droppedEvents ?? 0 }}
                </span>

                <span class="sdp-k">streamSessionId</span>
                <span class="sdp-v sdp-mono">{{ (msg.streamDebug?.streamSessionId ?? '–').slice(-8) }}</span>

                <span class="sdp-k">currentSessionId</span>
                <span class="sdp-v sdp-mono"
                  :class="{ 'sdp-error': msg.streamDebug?.currentSessionId && msg.streamDebug?.streamSessionId && msg.streamDebug.currentSessionId !== msg.streamDebug.streamSessionId }"
                >
                  {{ (msg.streamDebug?.currentSessionId ?? '–').slice(-8) }}
                </span>

                <span class="sdp-k">requestStartedAt</span>
                <span class="sdp-v">{{ _fmtTs(msg.streamDebug?.requestStartedAt) }}</span>

                <span class="sdp-k">elapsed</span>
                <span class="sdp-v">
                  {{ _fmtMs(msg.streamDebug?.requestStartedAt ? nowTick - msg.streamDebug.requestStartedAt : null) }}
                </span>

                <span class="sdp-k">answerLength</span>
                <span class="sdp-v">{{ msg.answerContent?.length ?? 0 }}</span>

                <span class="sdp-k">contentLength</span>
                <span class="sdp-v">{{ msg.content?.length ?? 0 }}</span>

                <span class="sdp-k">hasFinalAnswer</span>
                <span class="sdp-v">{{ !!msg.finalAnswer }}</span>

                <span class="sdp-k">reasoningSteps</span>
                <span class="sdp-v">{{ msg.reasoningSteps?.length ?? 0 }}</span>

                <span class="sdp-k">toolTrace</span>
                <span class="sdp-v">{{ msg.toolTrace?.length ?? 0 }}</span>

                <span class="sdp-k">agentTrace</span>
                <span class="sdp-v">{{ msg.agentTrace?.length ?? 0 }}</span>
              </div>
              <!-- Red alert: no events after 5s -->
              <div
                v-if="msg.isStreaming && !msg.streamDebug?.eventsReceived && msg.streamDebug?.requestStartedAt && (nowTick - msg.streamDebug.requestStartedAt) > 5000"
                class="sdp-no-events-alert"
              >
                ⚠ No SSE events received yet — check Network EventStream or proxy buffering
              </div>
            </div>

            <!-- Text content -->
            <div v-if="msg.content" class="msg-text-md" v-html="renderMarkdown(msg.content)"></div>

            <!-- Streaming indicator (when no content yet) -->
            <div v-else-if="msg.isStreaming" class="msg-typing">
              <span></span><span></span><span></span>
            </div>

            <!-- Confirmation card -->
            <ChatConfirmationCard
              v-if="msg.confirmation"
              :confirmation="msg.confirmation"
              @confirm="(c) => $emit('confirm', msg.id, c)"
              @cancel="(c) => $emit('cancel', msg.id, c)"
            />

            <!-- Result card -->
            <ChatResultCard
              v-if="msg.resultCard"
              :card="msg.resultCard"
              @action="(link) => $emit('action', msg.id, link)"
            />

            <!-- C29.1: Data quality card — debug-only -->
            <DataQualityCard
              v-if="SHOW_DATA_QUALITY && (msg.dataQuality || msg.finalAnswer?.data_quality)"
              :dq="msg.dataQuality ?? msg.finalAnswer?.data_quality"
            />

            <!-- C29.1: Source list — debug-only -->
            <ChatSourceList
              v-if="SHOW_SOURCES"
              :sources="msg.finalAnswer?.sources?.length
                ? msg.finalAnswer.sources
                : (msg.skillSources ?? [])"
            />

            <!-- C29.5: AI message actions (copy + retry) — shown after streaming ends -->
            <div v-if="!msg.isStreaming && msg.content" class="msg-actions msg-actions--ai">
              <button class="msg-action-btn" @click="onCopyAi(msg.content)" :title="t('chat_copy')">⎘</button>
              <button class="msg-action-btn" @click="$emit('retry-ai', msg.id)" :title="t('chat_retry')">↺</button>
            </div>
          </div>
        </div>
      </div>
    </TransitionGroup>

  </div>
</template>

<script setup>
import { ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { useI18n } from '../../utils/i18n.js'
import ChatReasoningPanel    from './ChatReasoningPanel.vue'
import ChatResultCard        from './ChatResultCard.vue'
import ChatConfirmationCard  from './ChatConfirmationCard.vue'
import DataQualityCard       from './DataQualityCard.vue'
import ChatSourceList        from './ChatSourceList.vue'

// C29.1 — production/debug display flags
import {
  SHOW_DATA_QUALITY,
  SHOW_SOURCES,
  SHOW_REASONING_PANEL,
  SHOW_STREAM_DEBUG,
} from '../../config/chatUiFlags.js'

const props = defineProps({
  messages: { type: Array, default: () => [] },
})

const emit = defineEmits(['confirm', 'cancel', 'action', 'edit-user', 'retry-ai'])

const { t } = useI18n()
const listRef = ref(null)

// Stream debug tick (only active when SHOW_STREAM_DEBUG is on)
const nowTick = ref(Date.now())
let _tickTimer = null
watch(
  () => props.messages.some(m => m.isStreaming),
  (hasStreaming) => {
    if (hasStreaming && !_tickTimer && SHOW_STREAM_DEBUG) {
      _tickTimer = setInterval(() => { nowTick.value = Date.now() }, 500)
    } else if (!hasStreaming && _tickTimer) {
      clearInterval(_tickTimer)
      _tickTimer = null
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => { if (_tickTimer) clearInterval(_tickTimer) })

function _fmtMs(ms) {
  if (ms == null || isNaN(ms)) return '–'
  return (ms / 1000).toFixed(1) + 's'
}
function _fmtTs(ts) {
  if (!ts) return '–'
  return new Date(ts).toLocaleTimeString()
}

// Auto-scroll to bottom when messages change
watch(() => props.messages.length, () => scrollToBottom(), { flush: 'post' })
watch(() => props.messages.map(m => m.toolTrace?.length), () => scrollToBottom(), { flush: 'post' })

function scrollToBottom() {
  nextTick(() => {
    const el = listRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

// C29.4: copy user message
async function onCopyUser(text) {
  try { await navigator.clipboard.writeText(text ?? '') } catch { /* non-fatal */ }
}

// C29.5: copy AI message (strips HTML tags from rendered markdown)
async function onCopyAi(text) {
  try { await navigator.clipboard.writeText(text ?? '') } catch { /* non-fatal */ }
}

// C29.6 — Improved markdown renderer (headings / lists / tables / code / inline)
// Processes line by line to avoid mid-sentence keyword conflicts.
function _inlineMd(text) {
  return text
    .replace(/`([^`\n]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+?)\*/g, '<em>$1</em>')
    .replace(/_([^_\n]+?)_/g, '<em>$1</em>')
}

function renderMarkdown(text) {
  if (!text) return ''

  // HTML-escape the raw text up-front (per-field, before inline processing)
  const esc = s => s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  const lines = text.split('\n')
  const out   = []
  let i       = 0
  let inPara  = false

  const flushPara = () => {
    if (inPara) { out.push('</p>'); inPara = false }
  }
  const openPara = () => {
    if (!inPara) { out.push('<p>'); inPara = true }
  }

  while (i < lines.length) {
    const raw  = lines[i]
    const line = raw.trim()

    // ── Fenced code block ```...``` ───────────────────────────────────────────
    if (line.startsWith('```')) {
      flushPara()
      const codeLines = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(esc(lines[i]))
        i++
      }
      out.push(`<pre class="md-pre"><code>${codeLines.join('\n')}</code></pre>`)
      i++
      continue
    }

    // ── ATX Headings # ## ### ─────────────────────────────────────────────────
    const hMatch = line.match(/^(#{1,3})\s+(.+)$/)
    if (hMatch) {
      flushPara()
      const lvl = hMatch[1].length
      out.push(`<h${lvl} class="md-h">${_inlineMd(esc(hMatch[2]))}</h${lvl}>`)
      i++
      continue
    }

    // ── Unordered list (- or *) ───────────────────────────────────────────────
    if (/^[-*]\s/.test(line)) {
      flushPara()
      out.push('<ul class="md-ul">')
      while (i < lines.length && /^[-*]\s/.test(lines[i].trim())) {
        out.push(`<li>${_inlineMd(esc(lines[i].trim().slice(2).trim()))}</li>`)
        i++
      }
      out.push('</ul>')
      continue
    }

    // ── Ordered list (1. 2. …) ───────────────────────────────────────────────
    if (/^\d+\.\s/.test(line)) {
      flushPara()
      out.push('<ol class="md-ol">')
      while (i < lines.length && /^\d+\.\s/.test(lines[i].trim())) {
        out.push(`<li>${_inlineMd(esc(lines[i].trim().replace(/^\d+\.\s/, '')))}</li>`)
        i++
      }
      out.push('</ol>')
      continue
    }

    // ── Table  | col | col | ─────────────────────────────────────────────────
    if (line.startsWith('|') && line.endsWith('|')) {
      flushPara()
      const tableRows = []
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        tableRows.push(lines[i].trim())
        i++
      }
      // Detect header + separator pattern
      const hasHeader = tableRows.length >= 2 && /^\|[\s|:-]+\|$/.test(tableRows[1])
      out.push('<div class="md-table-wrap"><table class="md-table">')
      tableRows.forEach((row, ri) => {
        if (hasHeader && ri === 1) return  // skip separator row
        const isHead = hasHeader && ri === 0
        const parts  = row.split('|')
        const cells  = parts.slice(1, parts.length - 1).map(c => c.trim())
        const tag    = isHead ? 'th' : 'td'
        out.push('<tr>' + cells.map(c => `<${tag}>${_inlineMd(esc(c))}</${tag}>`).join('') + '</tr>')
      })
      out.push('</table></div>')
      continue
    }

    // ── Horizontal rule ───────────────────────────────────────────────────────
    if (/^---+$/.test(line) || /^\*\*\*+$/.test(line)) {
      flushPara()
      out.push('<hr class="md-hr">')
      i++
      continue
    }

    // ── Blank line → close paragraph ──────────────────────────────────────────
    if (line === '') {
      flushPara()
      i++
      continue
    }

    // ── Normal paragraph line ─────────────────────────────────────────────────
    openPara()
    out.push(_inlineMd(esc(raw)) + '<br>')
    i++
  }

  flushPara()

  return out.join('')
    .replace(/<br><\/p>/g, '</p>')
    .replace(/<p><\/p>/g, '')
}
</script>

<style scoped>
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0 8px;
  display: flex;
  flex-direction: column;
  gap: 0;
  scroll-behavior: smooth;
}

/* ── Welcome ────────────────────────────────────────────────────────────────── */
.msg-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 20px;
  opacity: 0.7;
}
.msg-welcome-icon { font-size: 40px; }
.msg-welcome-text { font-size: 14px; color: var(--muted); text-align: center; }

/* ── Message rows ────────────────────────────────────────────────────────────── */
.msg-items { display: flex; flex-direction: column; gap: 16px; }

.msg-row { display: flex; }
.msg-row--user      { justify-content: flex-end; }
.msg-row--assistant { justify-content: flex-start; }

/* ── User bubble ──────────────────────────────────────────────────────────────── */
.msg-bubble--user {
  max-width: 78%;
  background: var(--accent-gradient, var(--accent));
  color: white;
  border-radius: 18px 18px 4px 18px;
  padding: 10px 16px 6px;
  box-shadow: 0 2px 8px var(--accent-glow);
}

.msg-bubble--user .msg-text {
  font-size: 14px;
  line-height: 1.5;
  margin: 0;
  word-break: break-word;
}

/* ── Assistant bubble ─────────────────────────────────────────────────────────── */
.msg-bubble--assistant {
  display: flex;
  gap: 10px;
  max-width: 92%;
}

.msg-avatar {
  font-size: 22px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--surface2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 1px solid var(--border-soft);
}

.msg-content {
  flex: 1;
  min-width: 0;
}

.msg-text-md {
  font-size: 14px;
  line-height: 1.65;
  color: var(--text);
  word-break: break-word;
}

/* Markdown elements inside assistant bubble */
.msg-text-md :deep(p)      { margin: 0 0 8px; }
.msg-text-md :deep(p:last-child) { margin-bottom: 0; }
.msg-text-md :deep(strong) { font-weight: 700; color: var(--text); }
.msg-text-md :deep(em)     { color: var(--muted); }

/* C29.6: extended markdown elements */
.msg-text-md :deep(.md-h)  { font-weight: 700; color: var(--text); margin: 12px 0 6px; line-height: 1.3; }
.msg-text-md :deep(h1.md-h) { font-size: 1.15em; }
.msg-text-md :deep(h2.md-h) { font-size: 1.05em; }
.msg-text-md :deep(h3.md-h) { font-size: 0.97em; }

.msg-text-md :deep(.md-ul),
.msg-text-md :deep(.md-ol)  { padding-left: 20px; margin: 6px 0 8px; }
.msg-text-md :deep(.md-ul li),
.msg-text-md :deep(.md-ol li) { margin-bottom: 3px; line-height: 1.5; }

.msg-text-md :deep(.md-hr) {
  border: none;
  border-top: 1px solid var(--border-soft);
  margin: 12px 0;
}

.msg-text-md :deep(.md-pre) {
  background: var(--surface2);
  border: 1px solid var(--border-soft);
  border-radius: 6px;
  padding: 10px 12px;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
  margin: 6px 0 8px;
}
.msg-text-md :deep(.md-pre code) {
  font-family: 'SF Mono', 'Fira Code', monospace;
  background: none;
  padding: 0;
  border-radius: 0;
}
.msg-text-md :deep(code) {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  background: var(--surface2);
  border: 1px solid var(--border-soft);
  border-radius: 3px;
  padding: 1px 4px;
}

.msg-text-md :deep(.md-table-wrap) {
  overflow-x: auto;
  margin: 8px 0;
}
.msg-text-md :deep(.md-table) {
  border-collapse: collapse;
  font-size: 13px;
  min-width: 100%;
}
.msg-text-md :deep(.md-table th),
.msg-text-md :deep(.md-table td) {
  border: 1px solid var(--border-soft);
  padding: 5px 10px;
  text-align: left;
  white-space: nowrap;
}
.msg-text-md :deep(.md-table th) {
  background: var(--surface2);
  font-weight: 600;
  font-size: 12px;
}
.msg-text-md :deep(.md-table tr:nth-child(even) td) {
  background: var(--surface2, rgba(0,0,0,0.02));
}

/* ── Typing animation ─────────────────────────────────────────────────────────── */
.msg-typing {
  display: flex;
  gap: 4px;
  padding: 10px 4px;
}
.msg-typing span {
  width: 6px;
  height: 6px;
  background: var(--muted);
  border-radius: 50%;
  animation: typing 1.2s ease-in-out infinite;
}
.msg-typing span:nth-child(2) { animation-delay: 0.2s; }
.msg-typing span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing { 0%,80%,100%{transform:scale(0.7);opacity:0.4} 40%{transform:scale(1);opacity:1} }

/* ── C29.4/C29.5: Message action bars ────────────────────────────────────────── */
.msg-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s ease;
  margin-top: 4px;
}
.msg-row:hover .msg-actions {
  opacity: 1;
}

.msg-actions--user  { justify-content: flex-end; }
.msg-actions--ai    { justify-content: flex-start; }

.msg-action-btn {
  background: none;
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 3px 7px;
  font-size: 13px;
  cursor: pointer;
  color: var(--muted);
  line-height: 1;
  transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}
.msg-action-btn:hover {
  background: var(--surface2);
  border-color: var(--border-soft);
  color: var(--text);
}

/* User bubble action bar: show in white since bg is accent color */
.msg-bubble--user .msg-action-btn {
  color: rgba(255,255,255,0.65);
}
.msg-bubble--user .msg-action-btn:hover {
  background: rgba(255,255,255,0.2);
  border-color: rgba(255,255,255,0.35);
  color: white;
}

/* ── Transition ────────────────────────────────────────────────────────────────── */
.msg-appear-enter-active { transition: all 0.25s ease; }
.msg-appear-enter-from   { opacity: 0; transform: translateY(8px); }
.msg-appear-enter-to     { opacity: 1; transform: translateY(0); }

/* ── Stream debug panel (DEV only, hidden in prod via SHOW_STREAM_DEBUG flag) ─── */
.stream-debug-panel {
  margin: 6px 0 8px;
  padding: 8px 10px;
  border: 1px dashed #888;
  border-radius: 6px;
  background: rgba(0,0,0,0.03);
  font-family: monospace;
  font-size: 11px;
  color: #555;
}
.sdp-title {
  font-weight: 700;
  color: #333;
  margin-bottom: 5px;
  font-size: 10px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}
.sdp-grid {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 1px 10px;
  row-gap: 2px;
}
.sdp-k  { color: #888; white-space: nowrap; }
.sdp-v  { color: #333; word-break: break-all; }
.sdp-mono  { font-family: monospace; }
.sdp-warn  { color: #b45309; font-weight: 700; }
.sdp-error { color: #dc2626; font-weight: 700; }
.sdp-no-events-alert {
  margin-top: 6px;
  padding: 5px 8px;
  background: #fee2e2;
  border: 1px solid #fca5a5;
  border-radius: 4px;
  color: #b91c1c;
  font-size: 11px;
  font-weight: 600;
}

/* ── Phase 2A: RAG citation sources ─────────────────────────────────────────────── */
.msg-sources {
  margin-top: 10px;
  padding: 8px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 6px;
  background: var(--surface2);
  font-size: 12px;
}
.msg-sources-label {
  font-weight: 600;
  color: var(--muted);
  margin-bottom: 6px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.msg-sources-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.msg-sources-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  flex-wrap: wrap;
}
.msg-sources-link {
  color: var(--accent, #4a90e2);
  text-decoration: none;
  font-weight: 500;
}
.msg-sources-link:hover { text-decoration: underline; }
.msg-sources-title  { color: var(--text); font-weight: 500; }
.msg-sources-meta   { color: var(--muted); font-size: 11px; }

/* C27: confidence badge on skill sources */
.msg-sources-confidence {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 8px;
  font-weight: 600;
}
.conf--high   { background: rgba(34,197,94,0.12); color: #16a34a; }
.conf--medium { background: rgba(245,158,11,0.12); color: #b45309; }
.conf--low    { background: rgba(239,68,68,0.12);  color: #dc2626; }
</style>
