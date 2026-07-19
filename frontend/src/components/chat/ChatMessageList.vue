<template>
  <div ref="listRef" class="message-list">

    <!-- Welcome state -->
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
        :class="[`msg-row--${msg.role}`, { 'msg-row--highlighted': msg.id === highlightedId }]"
        :data-message-id="msg.id"
      >

        <!-- ── User message ─────────────────────────────────────────────────── -->
        <template v-if="msg.role === 'user'">
          <div class="msg-bubble msg-bubble--user">
            <p class="msg-text">{{ msg.content }}</p>
          </div>
          <!-- C29.2.1: action bar — copy always visible; edit only for latest user msg -->
          <div class="msg-action-bar msg-action-bar--user">
            <button
              class="msg-action-btn"
              @click="onCopy(msg.id, msg.content)"
              :title="t('chat_copy')"
            >
              <span v-if="copiedId === msg.id">{{ t('chat_copied') }}</span>
              <span v-else>{{ t('chat_copy') }}</span>
            </button>
            <!-- C29.3.4: edit enabled even during streaming — clicking aborts current generation -->
            <button
              v-if="msg.id === latestUserMsgId"
              class="msg-action-btn"
              @click="$emit('edit-user', msg.id, msg.content)"
              :title="t('chat_edit')"
            >{{ t('chat_edit') }}</button>
          </div>
        </template>

        <!-- ── Assistant message ───────────────────────────────────────────── -->
        <template v-else>
          <div class="msg-bubble msg-bubble--assistant">
            <div class="msg-avatar">🤖</div>
            <div class="msg-content">

              <!-- C29.1.1: Mini thinking panel (production mode — always visible) -->
              <ChatThinkingMiniPanel
                v-if="SHOW_THINKING_MINI"
                :isStreaming="msg.isStreaming ?? false"
                :status="msg.status ?? (msg.isStreaming ? 'streaming' : 'done')"
                :thinkingEvents="msg.thinkingEvents ?? []"
                :thinkingItems="msg.thinkingItems ?? []"
                :reasoningSteps="msg.reasoningSteps ?? []"
                :toolTrace="msg.toolTrace ?? []"
                :query="msg._query ?? ''"
                :thinkingContent="msg.thinkingContent ?? ''"
              />

              <!-- C29.1.1: Full reasoning panel (debug mode only) -->
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

              <!-- C29.1.1: Stream debug panel (debug mode only) -->
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
                  <span class="sdp-k">elapsed</span>
                  <span class="sdp-v">
                    {{ _fmtMs(msg.streamDebug?.requestStartedAt ? nowTick - msg.streamDebug.requestStartedAt : null) }}
                  </span>
                  <span class="sdp-k">answerLength</span>
                  <span class="sdp-v">{{ msg.answerContent?.length ?? 0 }}</span>
                  <span class="sdp-k">hasFinalAnswer</span>
                  <span class="sdp-v">{{ !!msg.finalAnswer }}</span>
                  <span class="sdp-k">reasoningSteps</span>
                  <span class="sdp-v">{{ msg.reasoningSteps?.length ?? 0 }}</span>
                  <span class="sdp-k">toolTrace</span>
                  <span class="sdp-v">{{ msg.toolTrace?.length ?? 0 }}</span>
                </div>
                <div
                  v-if="msg.isStreaming && !msg.streamDebug?.eventsReceived && msg.streamDebug?.requestStartedAt && (nowTick - msg.streamDebug.requestStartedAt) > 5000"
                  class="sdp-no-events-alert"
                >
                  ⚠ No SSE events received yet — check Network EventStream or proxy buffering
                </div>
              </div>

              <!-- Text content (markdown rendered) -->
              <div v-if="msg.content" class="msg-text-md" v-html="renderMarkdown(stripStandardDisclaimer(msg.content))"></div>

              <!-- Typing indicator when no content yet -->
              <div v-else-if="msg.isStreaming && !SHOW_THINKING_MINI" class="msg-typing">
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

              <!-- P1.6.8: entity clarification candidates -->
              <ChatClarificationCard
                v-if="msg.clarification?.candidates?.length && !msg.isStreaming"
                :clarification="msg.clarification"
                :disabled="isSending"
                @select="(cand) => $emit('select-candidate', msg.id, cand)"
              />

              <!-- C29.1.6: Data quality card — debug only -->
              <DataQualityCard
                v-if="SHOW_DATA_QUALITY && (msg.dataQuality || msg.finalAnswer?.data_quality)"
                :dq="msg.dataQuality ?? msg.finalAnswer?.data_quality"
              />

              <!-- C29.1.6: Source list — debug only -->
              <ChatSourceList
                v-if="SHOW_SOURCES"
                :sources="msg.finalAnswer?.sources?.length
                  ? msg.finalAnswer.sources
                  : (msg.skillSources ?? [])"
              />

            </div>
          </div>

          <!-- C29.2.1: action bar — copy always; retry only for latest assistant msg -->
          <div v-if="!msg.isStreaming && msg.content" class="msg-action-bar msg-action-bar--ai">
            <button
              class="msg-action-btn"
              @click="onCopy(msg.id, msg.content)"
              :title="t('chat_copy')"
            >
              <span v-if="copiedId === msg.id">{{ t('chat_copied') }}</span>
              <span v-else>{{ t('chat_copy') }}</span>
            </button>
            <button
              v-if="msg.id === latestAssistantMsgId"
              class="msg-action-btn"
              :disabled="isSending"
              @click="$emit('retry-ai', msg.id)"
              :title="t('chat_retry')"
            >{{ t('chat_retry') }}</button>
          </div>
        </template>

      </div>
    </TransitionGroup>

  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import { useI18n } from '../../utils/i18n.js'
import ChatThinkingMiniPanel from './ChatThinkingMiniPanel.vue'
import ChatReasoningPanel    from './ChatReasoningPanel.vue'
import ChatResultCard        from './ChatResultCard.vue'
import ChatClarificationCard from './ChatClarificationCard.vue'
import ChatConfirmationCard  from './ChatConfirmationCard.vue'
import DataQualityCard       from './DataQualityCard.vue'
import ChatSourceList        from './ChatSourceList.vue'

// C29.1 display flags
import {
  SHOW_THINKING_MINI,
  SHOW_DATA_QUALITY,
  SHOW_SOURCES,
  SHOW_REASONING_PANEL,
  SHOW_STREAM_DEBUG,
} from '../../config/chatUiFlags.js'

const props = defineProps({
  messages:     { type: Array,   default: () => [] },
  isSending:    { type: Boolean, default: false },
  // C32.3: id of the message currently being highlighted by ConversationMarkers
  highlightedId: { type: String, default: null },
})

const emit = defineEmits(['confirm', 'cancel', 'action', 'edit-user', 'retry-ai', 'select-candidate'])

const { t } = useI18n()
const listRef = ref(null)

// C29.2.1: latest message ids — controls edit/retry visibility
const latestUserMsgId = computed(() => {
  const users = props.messages.filter(m => m.role === 'user')
  return users.length ? users[users.length - 1].id : null
})
const latestAssistantMsgId = computed(() => {
  const ais = props.messages.filter(m => m.role === 'assistant')
  return ais.length ? ais[ais.length - 1].id : null
})

// C29.1.2: copy feedback — shows "已复制" briefly
const copiedId = ref(null)
let _copyTimer = null

async function onCopy(msgId, text) {
  try {
    await navigator.clipboard.writeText(text ?? '')
    copiedId.value = msgId
    clearTimeout(_copyTimer)
    _copyTimer = setTimeout(() => { copiedId.value = null }, 1800)
  } catch {
    /* non-fatal */
  }
}

// Stream debug tick (only active in debug mode)
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
onBeforeUnmount(() => {
  if (_tickTimer) clearInterval(_tickTimer)
  clearTimeout(_copyTimer)
})

function _fmtMs(ms) {
  if (ms == null || isNaN(ms)) return '–'
  return (ms / 1000).toFixed(1) + 's'
}
function _fmtTs(ts) {
  if (!ts) return '–'
  return new Date(ts).toLocaleTimeString()
}

function stripStandardDisclaimer(text) {
  return String(text ?? '')
    .replace(/\n*\s*_?仅供研究参考，不构成投资建议。?_?\s*/g, '\n')
    .trim()
}

// Auto-scroll to bottom on new messages or toolTrace changes
watch(() => props.messages.length, () => scrollToBottom(), { flush: 'post' })
watch(() => props.messages.map(m => m.toolTrace?.length), () => scrollToBottom(), { flush: 'post' })

function scrollToBottom() {
  nextTick(() => {
    const el = listRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

// C29.1.3 + C32.3: Expose scrollToBottom and listRef for parent use.
// C32.3-fix: expose the DOM element directly (via getter) instead of the raw Ref<HTMLElement>.
// When defineExpose exposes a ref, the parent receives the Ref object — NOT the unwrapped
// DOM element — so chatListRef?.listRef in the parent template would be a Ref, not an HTMLElement.
// Using a getter ensures chatListRef.value.listRef returns the actual DOM node.
defineExpose({
  scrollToBottom,
  get listRef() { return listRef.value },
})

// ── C29.6: Markdown renderer ────────────────────────────────────────────────
function _inlineMd(text) {
  return text
    .replace(/`([^`\n]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+?)\*/g, '<em>$1</em>')
    .replace(/_([^_\n]+?)_/g, '<em>$1</em>')
}

function renderMarkdown(text) {
  if (!text) return ''

  const esc = s => s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  const lines = text.split('\n')
  const out   = []
  let i       = 0
  let inPara  = false

  const flushPara = () => { if (inPara) { out.push('</p>'); inPara = false } }
  const openPara  = () => { if (!inPara) { out.push('<p>'); inPara = true } }

  while (i < lines.length) {
    const raw  = lines[i]
    const line = raw.trim()

    // Fenced code block
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

    // Headings
    const hMatch = line.match(/^(#{1,3})\s+(.+)$/)
    if (hMatch) {
      flushPara()
      const lvl = hMatch[1].length
      out.push(`<h${lvl} class="md-h">${_inlineMd(esc(hMatch[2]))}</h${lvl}>`)
      i++
      continue
    }

    // Unordered list
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

    // Ordered list
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

    // Table
    if (line.startsWith('|') && line.endsWith('|')) {
      flushPara()
      const tableRows = []
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        tableRows.push(lines[i].trim())
        i++
      }
      const hasHeader = tableRows.length >= 2 && /^\|[\s|:-]+\|$/.test(tableRows[1])
      out.push('<div class="md-table-wrap"><table class="md-table">')
      tableRows.forEach((row, ri) => {
        if (hasHeader && ri === 1) return
        const isHead = hasHeader && ri === 0
        const parts  = row.split('|')
        const cells  = parts.slice(1, parts.length - 1).map(c => c.trim())
        const tag    = isHead ? 'th' : 'td'
        out.push('<tr>' + cells.map(c => `<${tag}>${_inlineMd(esc(c))}</${tag}>`).join('') + '</tr>')
      })
      out.push('</table></div>')
      continue
    }

    // Horizontal rule
    if (/^---+$/.test(line) || /^\*\*\*+$/.test(line)) {
      flushPara()
      out.push('<hr class="md-hr">')
      i++
      continue
    }

    // Blank line
    if (line === '') {
      flushPara()
      i++
      continue
    }

    // Normal line
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
/* ── Scroll container ───────────────────────────────────────────────────────── */
.message-list {
  flex: 1;
  overflow-y: auto;
  /* C29.1.3: bottom padding so last message isn't hidden behind input bar */
  padding: 16px 0 16px;
  display: flex;
  flex-direction: column;
  gap: 0;
  scroll-behavior: smooth;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

/* ── Welcome ──────────────────────────────────────────────────────────────── */
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

/* ── Message rows ─────────────────────────────────────────────────────────── */
.msg-items {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-bottom: 8px;
}

/* C29.1.2: rows are flex-column so bubble + action-bar stack vertically */
.msg-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.msg-row--user      { align-items: flex-end; }
.msg-row--assistant { align-items: flex-start; }

/* C32.3: scroll-target highlight */
@keyframes msg-highlight-pulse {
  0%   { box-shadow: 0 0 0 3px var(--accent-glow); }
  70%  { box-shadow: 0 0 0 6px transparent; }
  100% { box-shadow: none; }
}
.msg-row--highlighted {
  animation: msg-highlight-pulse 1.4s ease-out forwards;
  border-radius: 8px;
}

/* ── User bubble ──────────────────────────────────────────────────────────── */
.msg-bubble--user {
  max-width: 78%;
  background: var(--accent-gradient, var(--accent));
  color: white;
  border-radius: 18px 18px 4px 18px;
  padding: 10px 16px;
  box-shadow: 0 2px 8px var(--accent-glow);
}
.msg-bubble--user .msg-text {
  font-size: 14px;
  line-height: 1.5;
  margin: 0;
  word-break: break-word;
}

/* ── Assistant bubble ─────────────────────────────────────────────────────── */
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

/* ── Markdown output ──────────────────────────────────────────────────────── */
.msg-text-md {
  font-size: 14px;
  line-height: 1.65;
  color: var(--text);
  word-break: break-word;
}
.msg-text-md :deep(p)           { margin: 0 0 8px; }
.msg-text-md :deep(p:last-child){ margin-bottom: 0; }
.msg-text-md :deep(strong)      { font-weight: 700; color: var(--text); }
.msg-text-md :deep(em)          { color: var(--muted); }
.msg-text-md :deep(.md-h)       { font-weight: 700; color: var(--text); margin: 12px 0 6px; line-height: 1.3; }
.msg-text-md :deep(h1.md-h)     { font-size: 1.15em; }
.msg-text-md :deep(h2.md-h)     { font-size: 1.05em; }
.msg-text-md :deep(h3.md-h)     { font-size: 0.97em; }
.msg-text-md :deep(.md-ul),
.msg-text-md :deep(.md-ol)      { padding-left: 20px; margin: 6px 0 8px; }
.msg-text-md :deep(.md-ul li),
.msg-text-md :deep(.md-ol li)   { margin-bottom: 3px; line-height: 1.5; }
.msg-text-md :deep(.md-hr)      { border: none; border-top: 1px solid var(--border-soft); margin: 12px 0; }
.msg-text-md :deep(.md-pre)     { background: var(--surface2); border: 1px solid var(--border-soft); border-radius: 6px; padding: 10px 12px; overflow-x: auto; font-size: 12px; line-height: 1.5; margin: 6px 0 8px; }
.msg-text-md :deep(.md-pre code){ font-family: 'SF Mono', 'Fira Code', monospace; background: none; padding: 0; }
.msg-text-md :deep(code)        { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; background: var(--surface2); border: 1px solid var(--border-soft); border-radius: 3px; padding: 1px 4px; }
.msg-text-md :deep(.md-table-wrap){ overflow-x: auto; margin: 8px 0; }
.msg-text-md :deep(.md-table)   { border-collapse: collapse; font-size: 13px; min-width: 100%; }
.msg-text-md :deep(.md-table th),
.msg-text-md :deep(.md-table td){ border: 1px solid var(--border-soft); padding: 5px 10px; text-align: left; white-space: nowrap; }
.msg-text-md :deep(.md-table th){ background: var(--surface2); font-weight: 600; font-size: 12px; }
.msg-text-md :deep(.md-table tr:nth-child(even) td){ background: var(--surface2, rgba(0,0,0,0.02)); }

/* ── Typing animation ─────────────────────────────────────────────────────── */
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

/* ── C29.2.2: Action bars BELOW bubbles — always visible ─────────────────── */
.msg-action-bar {
  display: flex;
  gap: 4px;
  opacity: 1;
  min-height: 22px;
}
/* User bar: right-aligned (row already aligns to flex-end) */
.msg-action-bar--user {
  justify-content: flex-end;
  padding-right: 2px;
}
/* AI bar: left-aligned but indented past avatar (36px avatar + 10px gap) */
.msg-action-bar--ai {
  padding-left: 46px;
}
.msg-action-btn {
  background: none;
  border: 1px solid transparent;
  border-radius: 5px;
  padding: 2px 8px;
  font-size: 12px;
  color: var(--muted);
  cursor: pointer;
  line-height: 1.5;
  white-space: nowrap;
  transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}
.msg-action-btn:hover:not(:disabled) {
  background: var(--surface2);
  border-color: var(--border-soft);
  color: var(--text);
}
.msg-action-btn:disabled {
  opacity: 0.38;
  cursor: not-allowed;
}

/* Mobile: buttons already always visible (opacity: 1 globally above) */

/* ── Transition ───────────────────────────────────────────────────────────── */
.msg-appear-enter-active { transition: all 0.25s ease; }
.msg-appear-enter-from   { opacity: 0; transform: translateY(8px); }
.msg-appear-enter-to     { opacity: 1; transform: translateY(0); }

/* ── Stream debug panel ───────────────────────────────────────────────────── */
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
.sdp-title  { font-weight: 700; color: #333; margin-bottom: 5px; font-size: 10px; letter-spacing: 0.05em; text-transform: uppercase; }
.sdp-grid   { display: grid; grid-template-columns: max-content 1fr; gap: 1px 10px; row-gap: 2px; }
.sdp-k      { color: #888; white-space: nowrap; }
.sdp-v      { color: #333; word-break: break-all; }
.sdp-warn   { color: #b45309; font-weight: 700; }
.sdp-error  { color: #dc2626; font-weight: 700; }
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

/* ── Phase 2A: source styles (kept for structural compat) ─────────────────── */
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
