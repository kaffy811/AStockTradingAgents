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
        </div>

        <!-- Assistant bubble -->
        <div v-else class="msg-bubble msg-bubble--assistant">
          <!-- Avatar -->
          <div class="msg-avatar">🤖</div>

          <!-- Bubble content -->
          <div class="msg-content">
            <!-- Phase 2E-3: Unified reasoning panel (replaces thinking + agentTrace + toolTrace) -->
            <ChatReasoningPanel
              :isStreaming="msg.isStreaming"
              :status="msg.status ?? (msg.isStreaming ? 'streaming' : 'done')"
              :reasoningSteps="msg.reasoningSteps ?? []"
              :toolTrace="msg.toolTrace ?? []"
              :agentTrace="msg.agentTrace ?? []"
              :thinkingContent="msg.thinkingContent ?? ''"
              :thinkingItems="msg.thinkingItems ?? []"
            />

            <!-- Section I: DEV-only stream debug panel -->
            <div
              v-if="isDev && (msg.isStreaming || msg.streamDebug?.eventsReceived > 0)"
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

            <!-- Streaming indicator -->
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

            <!-- C27: Data quality card (skill path uses msg.dataQuality;
                  financial_agent path uses msg.finalAnswer.data_quality) -->
            <DataQualityCard
              v-if="msg.dataQuality || msg.finalAnswer?.data_quality"
              :dq="msg.dataQuality ?? msg.finalAnswer?.data_quality"
            />

            <!-- C27: Unified source list (agent path: finalAnswer.sources; skill path: skillSources) -->
            <ChatSourceList
              :sources="msg.finalAnswer?.sources?.length
                ? msg.finalAnswer.sources
                : (msg.skillSources ?? [])"
            />
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

const props = defineProps({
  messages: { type: Array, default: () => [] },
})

const emit = defineEmits(['confirm', 'cancel', 'action'])

const { t } = useI18n()
const listRef = ref(null)

// Section I: stream debug panel — only visible when CHAT_STREAM_DEBUG=1 in localStorage.
// Toggle on:  localStorage.setItem('CHAT_STREAM_DEBUG', '1'); location.reload()
// Toggle off: localStorage.removeItem('CHAT_STREAM_DEBUG'); location.reload()
const isDev   = import.meta.env.DEV && localStorage.getItem('CHAT_STREAM_DEBUG') === '1'
const nowTick = ref(Date.now())
let _tickTimer = null
watch(
  () => props.messages.some(m => m.isStreaming),
  (hasStreaming) => {
    if (hasStreaming && !_tickTimer) {
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

// Very basic markdown renderer (bold + newlines only — no external dep)
function renderMarkdown(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/_(.+?)_/g, '<em>$1</em>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/^(.+)$/, '<p>$1</p>')
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
  padding: 10px 16px;
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

/* ── Thinking panel (Phase 1) ─────────────────────────────────────────────────── */
.msg-thinking {
  margin: 6px 0 8px;
  border: 1px solid var(--border-soft);
  border-radius: 6px;
  background: var(--surface2);
  font-size: 12px;
  overflow: hidden;
}
.msg-thinking-label {
  padding: 5px 10px;
  cursor: pointer;
  user-select: none;
  color: var(--muted);
  font-weight: 600;
  list-style: none;
}
.msg-thinking-label::-webkit-details-marker { display: none; }
.msg-thinking-body {
  padding: 6px 10px 8px;
  color: var(--muted);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  border-top: 1px solid var(--border-soft);
  max-height: 200px;
  overflow-y: auto;
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

/* ── Transition ────────────────────────────────────────────────────────────────── */
.msg-appear-enter-active { transition: all 0.25s ease; }
.msg-appear-enter-from   { opacity: 0; transform: translateY(8px); }
.msg-appear-enter-to     { opacity: 1; transform: translateY(0); }

/* ── Section I: Stream debug panel (DEV only, hidden in prod) ────────────────────── */
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
.sdp-k {
  color: #888;
  white-space: nowrap;
}
.sdp-v {
  color: #333;
  word-break: break-all;
}
.sdp-mono { font-family: monospace; }
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
.msg-sources-title {
  color: var(--text);
  font-weight: 500;
}
.msg-sources-meta {
  color: var(--muted);
  font-size: 11px;
}

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
