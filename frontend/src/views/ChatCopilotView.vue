<template>
  <div class="app-shell chat-shell">
    <AppHeader />

    <div class="chat-layout">
      <!-- ── Left: Session sidebar (collapsible) ──────────────────────────── -->
      <ChatSessionSidebar
        :sessions="sessions"
        :activeSessionId="sessionId"
        @new-session="onNewSession"
        @select-session="onSelectSession"
        @delete-session="onDeleteSession"
      />

      <!-- ── Center: Main chat column ─────────────────────────────────────── -->
      <div class="chat-column">
        <div class="chat-inner">

          <!-- Compact topbar: title + status dot -->
          <div class="chat-topbar">
            <span class="chat-topbar-icon">🤖</span>
            <span class="chat-topbar-title">{{ t('chat_title') }}</span>
            <span
              class="chat-api-dot"
              :class="fallbackMode ? 'dot-warn' : 'dot-ok'"
              :title="fallbackMode ? t('chat_demo_badge') : t('chat_api_mode')"
            ></span>
          </div>

          <!-- Status notices (compact) -->
          <div v-if="sessionError" class="chat-session-error">
            {{ t('chat_session_error') }}
          </div>
          <div v-if="softTimeout && isSending" class="chat-soft-timeout">
            {{ t('chat_timeout_soft') }}
            <button class="btn-stop" @click="onStop">{{ t('chat_stop') }}</button>
          </div>

          <!-- Session-switch skeleton: shown while loading session history -->
          <div v-if="isLoadingSession" class="chat-session-skeleton">
            <div class="skeleton-line wide"></div>
            <div class="skeleton-line medium"></div>
            <div class="skeleton-line narrow"></div>
          </div>

          <!-- Empty state: welcome hero + quick prompts -->
          <div v-else-if="messages.length === 0 && !sessionLoading" class="chat-welcome-area">
            <div class="welcome-hero">
              <div class="welcome-title">{{ t('chat_welcome_title') }}</div>
              <div class="welcome-sub">{{ t('chat_welcome_sub') }}</div>
            </div>
            <ChatQuickActions @fill="onQuickFill" />
          </div>

          <!-- Message list (scrollable) -->
          <div class="chat-messages-area">
            <ChatMessageList
              :messages="messages"
              :isSending="isSending"
              @confirm="onConfirm"
              @cancel="onCancel"
              @action="onCardAction"
              @edit-user="onEditUser"
              @retry-ai="onRetryAi"
            />
          </div>

          <!-- Disclaimer + input -->
          <div class="chat-footer">
            <div class="chat-disclaimer">{{ t('chat_disclaimer') }}</div>
            <div class="chat-input-area">
              <ChatInputBox
                ref="inputBoxRef"
                v-model="inputText"
                :isSending="isSending || sessionLoading"
                @send="onSend"
              />
            </div>
          </div>

        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader          from '../components/AppHeader.vue'
import ChatMessageList    from '../components/chat/ChatMessageList.vue'
import ChatQuickActions   from '../components/chat/ChatQuickActions.vue'
import ChatInputBox       from '../components/chat/ChatInputBox.vue'
import ChatSessionSidebar from '../components/chat/ChatSessionSidebar.vue'
import { useI18n }        from '../utils/i18n.js'
import { useAuthStore }   from '../stores/auth.js'
import { normalizeChatEvent } from '../utils/chatEventNormalizer.js'
import { applyChatUiEvent }   from '../utils/chatReducer.js'
import {
  getMockResponse,
  streamToolTrace,
  newMsgId,
} from '../mocks/chatMock.js'
import {
  createChatSession,
  listChatSessions,
  getChatSession,
  deleteChatSession,
  sendChatMessage,
  sendChatMessageStream,
  confirmChatAction,
} from '../api/chat.js'
import { getAnalysisRun } from '../api/analysis.js'

// Timeout constants (ms)
// DeepSeek can take 60-120 s for complex questions — give it room
const _SOFT_TIMEOUT_MS = 30_000
const _HARD_TIMEOUT_MS = 120_000

const { t }      = useI18n()
const router     = useRouter()
const authStore  = useAuthStore()

// ── State ─────────────────────────────────────────────────────────────────────
const inputText      = ref('')
const isSending      = ref(false)
const sessionLoading = ref(false)
const sessionError   = ref(false)
const fallbackMode   = ref(false)  // true = no backend session available
const sessionId      = ref(null)   // current backend session UUID
const messages       = ref([])
const inputBoxRef    = ref(null)
const sessions       = ref([])      // sidebar session list
const softTimeout    = ref(false)   // "thinking" notice shown after 15s

// AbortController for hard timeout — replaced per request
let _abortController = null
let _softTimerId = null
let _hardTimerId = null

// C29.1.5: analysis run polling intervals (msgId → intervalId)
const _runPolls = new Map()

const _SESSION_KEY        = 'ta_chat_session_id'
// C29.2.7: per-session click timestamps stored in localStorage
const _SESSION_ACCESS_KEY = 'ta_chat_access'

function _readAccessMap() {
  try { return JSON.parse(localStorage.getItem(_SESSION_ACCESS_KEY) ?? '{}') } catch { return {} }
}
function _writeAccessMap(map) {
  try { localStorage.setItem(_SESSION_ACCESS_KEY, JSON.stringify(map)) } catch {}
}
function _touchAccess(id) {
  const map = _readAccessMap()
  map[id] = Date.now()
  _writeAccessMap(map)
  return map
}
function _effectiveTime(s, accessMap) {
  const local = accessMap?.[s.id]
  if (local) return local  // number timestamp (ms)
  return new Date(s.last_accessed_at || s.updated_at || s.created_at || 0).getTime()
}
function _sortSessions(arr, accessMap) {
  return [...arr].sort((a, b) => _effectiveTime(b, accessMap) - _effectiveTime(a, accessMap))
}

// Problem 3 fix: creation lock prevents double-session on rapid clicks
const isCreatingChat   = ref(false)
// Problem 2 fix: separate loading flag for session switch (vs initial mount)
const isLoadingSession = ref(false)

// ── Optimistic placeholder steps shown immediately after send ─────────────────

function _makePlaceholderSteps() {
  return [
    { name: t('chat_step_analyze'),  status: 'running', detail: '' },
    { name: t('chat_step_rag'),      status: 'pending', detail: '' },
    { name: t('chat_step_review'),   status: 'pending', detail: '' },
    { name: t('chat_step_tool'),     status: 'pending', detail: '' },
    { name: t('chat_step_conclude'), status: 'pending', detail: '' },
  ]
}

// ── Reactivity helpers ────────────────────────────────────────────────────────

/**
 * commitAssistantMessage — the central Vue reactivity fix.
 *
 * Root cause: applyChatUiEvent mutates the original plain-JS assistantMsg object.
 * Vue 3 only fires reactive updates when mutations go through the Proxy returned by
 * messages.value[i]. Mutating the original (non-proxy) reference bypasses the setter
 * intercept, so Vue never schedules a re-render.
 *
 * The Debug panel's 500ms tick accidentally worked around this by updating nowTick,
 * forcing ChatMessageList to re-render and pick up the already-mutated values.
 * Removing the tick (CHAT_STREAM_DEBUG off) broke the UI.
 *
 * Fix: after every mutation, replace the array item with a new spread object AND
 * replace the array reference itself. Both operations go through Vue's Proxy,
 * guaranteeing a re-render on every SSE event — regardless of the debug panel.
 */
function commitAssistantMessage(msg) {
  const idx = messages.value.findIndex(m => m.id === msg.id)
  if (idx < 0) {
    console.error('[chat stream] commit failed: message not found', {
      msgId:      msg.id,
      messageIds: messages.value.map(m => m.id),
    })
    return
  }

  // Replace the item with a shallow-spread copy so Vue's Proxy setter fires
  messages.value[idx] = {
    ...msg,
    reasoningSteps: [...(msg.reasoningSteps ?? [])],
    toolTrace:      [...(msg.toolTrace      ?? [])],
    agentTrace:     [...(msg.agentTrace     ?? [])],
    streamDebug:    msg.streamDebug  ? { ...msg.streamDebug  } : msg.streamDebug,
    finalAnswer:    msg.finalAnswer  ? { ...msg.finalAnswer  } : msg.finalAnswer,
  }

  // Replace the array reference as well — belt-and-suspenders trigger
  messages.value = [...messages.value]
}

/**
 * getLiveAssistantMsg — always return the current item from the reactive array.
 *
 * After commitAssistantMessage the array item is a new spread object.
 * Any subsequent handler must call this again to get the fresh copy.
 */
function getLiveAssistantMsg(msgId) {
  return messages.value.find(m => m.id === msgId) ?? null
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function pushUserMsg(content, id = null) {
  messages.value.push({
    id:   id ?? newMsgId(),
    role: 'user',
    content,
  })
}

function pushAssistantMsg(overrides = {}) {
  const msg = {
    id:              newMsgId(),
    role:            'assistant',
    content:         '',
    // Phase 2E-3: normalizer / reducer fields
    status:          'connecting',   // 'connecting' | 'streaming' | 'done' | 'error'
    reasoningSteps:  [],
    answerContent:   '',
    // Legacy fields (still used by ChatReasoningPanel / ChatMessageList)
    toolTrace:       [],
    thinkingContent: '',
    finalAnswer:     null,
    agentTrace:      [],
    resultCard:      null,
    confirmation:    null,
    isStreaming:     true,
    error:           null,
    // Section IV: stream debug counters (dev / diagnostic use)
    streamDebug: {
      eventsReceived:   0,
      lastEventType:    null,
      lastEventAt:      null,
      droppedEvents:    0,
      handlerErrors:    0,
      requestStartedAt: null,  // set in _sendApiStream
      streamSessionId:  null,  // set in _sendApiStream
      currentSessionId: null,  // updated on each event
    },
    ...overrides,
  }
  messages.value.push(msg)
  return msg
}

// Build an assistant message object from an API response
function _apiRespToAssistantMsg(resp, assistantMsgId) {
  return {
    id:           assistantMsgId ?? String(resp.assistant_message_id),
    role:         'assistant',
    content:      resp.answer ?? '',
    toolTrace:    resp.tool_events ?? [],
    resultCard:   (resp.cards ?? [])[0] ?? null,
    confirmation: null,  // set below if needed
    isStreaming:  false,
  }
}

// Attach onConfirm callback to a confirmation object from the API
function _wrapConfirmation(conf) {
  if (!conf) return null
  return {
    ...conf,
    onConfirm: async () => {
      const result = await confirmChatAction(sessionId.value, conf.id, true)
      return {
        toolTrace:  result.tool_events ?? [],
        content:    result.answer ?? '',
        resultCard: (result.cards ?? [])[0] ?? null,
      }
    },
  }
}

// Restore messages array from session detail (on page load)
function _restoreMessages(sessionDetail) {
  const restored = []
  for (const m of sessionDetail.messages) {
    if (m.role === 'user') {
      restored.push({
        id:      String(m.message_id),
        role:    'user',
        content: m.content,
      })
    } else {
      const conf = m.confirmation ? { ...m.confirmation, resolved: true } : null
      restored.push({
        id:           String(m.message_id),
        role:         'assistant',
        content:      m.content,
        toolTrace:    m.tool_events ?? [],
        resultCard:   (m.cards ?? [])[0] ?? null,
        confirmation: conf,
        isStreaming:  false,
      })
    }
  }
  messages.value = restored

  // C29.2.5: resume / refresh polling for analysis run cards
  for (const m of restored) {
    if (m.role === 'assistant' && m.resultCard?.type === 'analysis_run') {
      const { run_id, status } = m.resultCard.data ?? {}
      if (run_id) _startRunPolling(m.id, run_id)  // handles both active + terminal (refresh once)
    }
  }
}

// Update the sidebar session preview with the first user message
// C29.3: also move the active session to the top (optimistic ordering)
function _updateSessionTitle(text) {
  const title = text.replace(/[<>\n\r]/g, '').slice(0, 25).trim()
  const s = sessions.value.find(s => s.id === sessionId.value)
  if (s) {
    if (!s.preview) s.preview = title
    // Move to top
    sessions.value = [s, ...sessions.value.filter(x => x.id !== s.id)]
  }
}

// ── Timeout helpers ────────────────────────────────────────────────────────────

function _startTimeouts(assistantMsg) {
  _clearTimeouts()
  _softTimerId = setTimeout(() => {
    softTimeout.value = true
  }, _SOFT_TIMEOUT_MS)

  _hardTimerId = setTimeout(() => {
    _clearTimeouts()
    if (_abortController) _abortController.abort()
    if (isSending.value) {
      // Show error card — do NOT auto-switch to demo/fallback mode
      Object.assign(assistantMsg, {
        content:     t('chat_timeout_hard'),
        toolTrace:   [],  // clear placeholder steps
        isStreaming: false,
        resultCard:  { type: 'error', title: t('chat_timeout_hard'), action: 'retry' },
      })
      isSending.value = false
    }
  }, _HARD_TIMEOUT_MS)
}

function _clearTimeouts() {
  clearTimeout(_softTimerId)
  clearTimeout(_hardTimerId)
  softTimeout.value = false
}

function onStop() {
  if (_abortController) _abortController.abort()
  _clearTimeouts()
  isSending.value = false
  const last = messages.value.at(-1)
  if (last && last.isStreaming) {
    // Finalize reasoningSteps
    ;(last.reasoningSteps ?? []).forEach(s => {
      if (s.status === 'running') s.status = 'stopped'
    })
    // Finalize toolTrace
    ;(last.toolTrace ?? []).forEach(step => {
      if (step.status === 'running') step.status = 'stopped'
      else if (step.status === 'pending') step.status = 'skipped'
    })
    // Finalize agentTrace
    ;(last.agentTrace ?? []).forEach(a => {
      if (a.status === 'running') a.status = 'stopped'
    })
    last.isStreaming = false
    last.status      = 'done'
    if (!last.content) last.content = t('chat_stopped')
  }
}

// ── Session list helpers ───────────────────────────────────────────────────────

async function _loadSessions() {
  try {
    const data = await listChatSessions(20, 0)
    const accessMap = _readAccessMap()
    const mapped = (data.items ?? data ?? []).map(s => ({
      id:               String(s.session_id ?? s.id),
      preview:          s.title ?? s.preview ?? '',
      last_accessed_at: s.last_accessed_at ?? null,
      updated_at:       s.updated_at ?? s.created_at ?? '',
      created_at:       s.created_at ?? '',
    }))
    // C29.2.7: sort by effective time (localStorage click time > backend times)
    sessions.value = _sortSessions(mapped, accessMap)
  } catch {
    // non-fatal
  }
}

async function onNewSession() {
  // Problem 3 fix: creation lock prevents duplicate sessions on rapid clicks
  if (isCreatingChat.value) return
  isCreatingChat.value = true
  try {
    const created = await createChatSession(null)
    const newId = String(created.session_id)
    // Guard: skip if session was already added (e.g. by concurrent call)
    if (sessions.value.some(s => s.id === newId)) {
      sessionId.value = newId
      localStorage.setItem(_SESSION_KEY, newId)
      messages.value = []
      return
    }
    sessionId.value = newId
    localStorage.setItem(_SESSION_KEY, newId)
    messages.value = []
    _touchAccess(newId)   // C29.2.7: new session → top of list
    await _loadSessions()
  } catch {
    messages.value = []
  } finally {
    isCreatingChat.value = false
  }
}

async function onSelectSession(id) {
  // Problem 2 fix: show loading state to prevent welcome-page flash during switch
  if (isSending.value) return   // don't switch while a stream is in-flight
  isLoadingSession.value = true
  messages.value = []           // clear early while loading flag suppresses welcome

  // C29.2.7: record access time + re-sort (stable optimistic move-to-top)
  const accessMap = _touchAccess(id)
  sessions.value = _sortSessions(sessions.value, accessMap)

  try {
    const detail = await getChatSession(id)
    // Guard: if user clicked another session while this was loading, bail out
    if (isLoadingSession.value === false) return
    sessionId.value = id
    localStorage.setItem(_SESSION_KEY, id)
    _restoreMessages(detail)
  } catch {
    // session gone — welcome screen will show (messages empty, loading done)
  } finally {
    isLoadingSession.value = false
  }
}

async function onDeleteSession(id) {
  try {
    await deleteChatSession(id)
    sessions.value = sessions.value.filter(s => s.id !== id)
    if (sessionId.value === id) {
      await onNewSession()
    }
  } catch {
    // non-fatal
  }
}

// ── Session init ──────────────────────────────────────────────────────────────

onMounted(async () => {
  if (!authStore.token) return

  sessionLoading.value = true
  sessionError.value   = false

  try {
    const savedId = localStorage.getItem(_SESSION_KEY)
    if (savedId) {
      try {
        const detail = await getChatSession(savedId)
        sessionId.value = savedId
        _restoreMessages(detail)
        sessionLoading.value = false
        _loadSessions()
        return
      } catch {
        localStorage.removeItem(_SESSION_KEY)
      }
    }

    // Create fresh session
    const created = await createChatSession(null)
    sessionId.value = String(created.session_id)
    localStorage.setItem(_SESSION_KEY, sessionId.value)
  } catch {
    // Backend unreachable — show empty state without demo mode banner
    fallbackMode.value = true
  } finally {
    sessionLoading.value = false
  }

  // Load session list for sidebar (non-blocking)
  _loadSessions()
})

// ── Session ensure (Problem A fix) ────────────────────────────────────────────
// Creates a session if none exists yet, synchronises sessionId + sidebar list.
// Returns the session id string; throws on backend failure.
async function ensureSession() {
  if (sessionId.value) return sessionId.value
  const created = await createChatSession(null)
  const newId   = String(created.session_id)
  sessionId.value = newId
  localStorage.setItem(_SESSION_KEY, newId)
  // Prepend to sidebar list if not already present
  if (!sessions.value.some(s => s.id === newId)) {
    sessions.value = [{ id: newId, preview: '', created_at: new Date().toISOString() }, ...sessions.value]
  }
  return newId
}

// ── Send flow ─────────────────────────────────────────────────────────────────

async function onSend(text) {
  if (!text.trim() || isSending.value) return

  isSending.value = true

  if (fallbackMode.value) {
    await _sendMock(text)
    return
  }

  // Problem A fix: if no active session (e.g. creation failed at mount),
  // create one now before entering the stream.
  if (!sessionId.value) {
    try {
      await ensureSession()
    } catch {
      sessionError.value = true
      isSending.value    = false
      return
    }
  }

  // Final guard — abort rather than letting the stream use a null session id.
  if (!sessionId.value) {
    console.error('[chat] missing active session before send — aborting')
    sessionError.value = true
    isSending.value    = false
    return
  }

  await _sendApi(text)
}

// ── API send path (C13-a: SSE-first with sync fallback) ──────────────────────

async function _sendApi(text) {
  // 1. User message
  pushUserMsg(text)

  // 2. Assistant message — toolTrace starts empty; real events populate it
  const assistantMsg = pushAssistantMsg({
    isStreaming: true,
    toolTrace:   [],
    agentTrace:  [],   // populated by orchestrator events (Phase 2E-2)
  })
  assistantMsg._query = text   // C29.2.6: passed to MiniPanel for intent detection

  // Update session title on first message
  if (messages.value.filter(m => m.role === 'user').length === 1) {
    _updateSessionTitle(text)
  }

  // C29.2.7: touch access so this session stays at top
  if (sessionId.value) _touchAccess(sessionId.value)

  // 3. Start timeout guards
  _abortController = new AbortController()
  _startTimeouts(assistantMsg)

  // 4. Try SSE stream first; fallback to sync POST on failure
  try {
    await _sendApiStream(text, assistantMsg)
  } catch (streamErr) {
    // Stream endpoint not available or failed at connection — fallback to sync
    if (streamErr?.name === 'AbortError') return  // user stopped / hard timeout
    if (isSending.value) {
      // Brief fallback notice then try sync
      Object.assign(assistantMsg, {
        content:     t('chat_stream_fallback'),
        toolTrace:   [],
        isStreaming: true,
      })
      await _sendApiSync(text, assistantMsg)
    }
  } finally {
    isSending.value = false
    nextTick(() => inputBoxRef.value?.focus())
  }
}

// ── SSE streaming send (C13-a + Phase 2E-3 normalizer/reducer) ──────────────

async function _sendApiStream(text, assistantMsg) {
  // Problem A assertion: session must be set before any streaming starts.
  if (!sessionId.value) {
    console.error('[chat stream] missing active session before stream — aborting')
    throw new Error('missing_active_session')
  }

  const outputLanguage = authStore.currentUser?.output_language ?? 'zh-CN'
  let streamStarted    = false  // set on agent_started (legacy compat)
  let anyEventReceived = false  // set on ANY event — used for fallback decision
  const streamSessionId    = sessionId.value  // session isolation guard
  const requestStartedAt   = Date.now()

  // Problem A fix: stamp currentSessionId immediately (not just on first event)
  // so the debug panel never shows '-' while connecting.
  if (assistantMsg.streamDebug) {
    assistantMsg.streamDebug.requestStartedAt = requestStartedAt
    assistantMsg.streamDebug.streamSessionId  = streamSessionId
    assistantMsg.streamDebug.currentSessionId = streamSessionId
  }

  if (import.meta.env.DEV) {
    console.debug('[chat stream] start', {
      sessionId:    streamSessionId,
      msgId:        assistantMsg.id,
      text:         text.slice(0, 80),
      outputLanguage,
    })
  }

  /**
   * Unified event handler — Vue reactivity fixed version.
   *
   * Core rule: NEVER mutate the local `assistantMsg` reference directly and
   * expect Vue to notice. After every push into messages.value, the item
   * becomes a new Proxy. We must:
   *   1. Get the live item from the array via getLiveAssistantMsg()
   *   2. Mutate that item
   *   3. Call commitAssistantMessage() to replace the array slot + array ref
   *
   * This guarantees re-renders regardless of the Debug panel tick state.
   */
  const _handleEvent = (eventType, payload) => {
    // ── 1. Get the live reactive item from the array ──────────────────────────
    const liveMsg = getLiveAssistantMsg(assistantMsg.id)
    if (!liveMsg) {
      console.error('[chat stream] assistant message disappeared from array — events lost', {
        msgId:     assistantMsg.id,
        eventType,
        msgIds:    messages.value.map(m => m.id),
      })
      return
    }

    if (import.meta.env.DEV) {
      console.debug('[chat stream] handleEvent', {
        eventType,
        streamSessionId,
        currentSessionId: sessionId.value,
        msgId:            liveMsg.id,
        eventsReceived:   liveMsg.streamDebug?.eventsReceived ?? '?',
      })
    }

    // ── 2. Stale session guard ────────────────────────────────────────────────
    if (sessionId.value !== streamSessionId) {
      if (import.meta.env.DEV) {
        console.warn('[chat stream] dropped stale event', {
          eventType,
          streamSessionId,
          currentSessionId: sessionId.value,
        })
      }
      if (liveMsg.streamDebug) {
        liveMsg.streamDebug.droppedEvents++
        commitAssistantMessage(liveMsg)
      }
      return
    }

    // ── 3. Mark stream as live ────────────────────────────────────────────────
    anyEventReceived = true
    if (liveMsg.status === 'connecting') {
      liveMsg.status = 'streaming'
    }

    // ── 4. Update debug counters ──────────────────────────────────────────────
    if (liveMsg.streamDebug) {
      liveMsg.streamDebug.eventsReceived++
      liveMsg.streamDebug.lastEventType    = eventType
      liveMsg.streamDebug.lastEventAt      = Date.now()
      liveMsg.streamDebug.currentSessionId = sessionId.value
    }

    // ── 5. Event-type dispatch ────────────────────────────────────────────────
    switch (eventType) {
      case 'session_title_updated': {
        // Updates sessions sidebar only — no assistantMsg commit needed
        const s = sessions.value.find(s => s.id === sessionId.value)
        if (s) s.preview = payload.title || s.preview
        // Still commit debug counter change
        commitAssistantMessage(liveMsg)
        return
      }

      case 'agent_started':
        streamStarted      = true
        liveMsg.status     = 'streaming'
        liveMsg.toolTrace  = []   // clear stale placeholders
        // fall through to normalizer → ui_step_start
        break

      case 'confirmation_required':
        liveMsg.confirmation = _wrapConfirmation(payload.confirmation)
        commitAssistantMessage(liveMsg)
        return

      case 'cards_delta':
        liveMsg.resultCard = (payload.cards ?? [])[0] ?? null
        commitAssistantMessage(liveMsg)
        return

      case 'agent_completed':
        _clearTimeouts()
        applyChatUiEvent(liveMsg, { type: 'ui_done' })
        commitAssistantMessage(liveMsg)
        return

      case 'agent_error':
        _clearTimeouts()
        applyChatUiEvent(liveMsg, {
          type:    'ui_error',
          message: payload.error ?? payload.message ?? t('chat_error'),
        })
        commitAssistantMessage(liveMsg)
        return
    }

    // ── 6. Visual events → normalizer → reducer → commit ─────────────────────
    const uiEvent = normalizeChatEvent(eventType, payload)
    if (uiEvent) {
      applyChatUiEvent(liveMsg, uiEvent)
      if (import.meta.env.DEV) {
        console.debug('[chat stream] message after apply', {
          eventType,
          uiEventType:   uiEvent.type,
          status:        liveMsg.status,
          isStreaming:   liveMsg.isStreaming,
          contentLength: liveMsg.content?.length ?? 0,
          answerLength:  liveMsg.answerContent?.length ?? 0,
          finalAnswer:   !!liveMsg.finalAnswer,
          steps:         liveMsg.reasoningSteps?.length ?? 0,
          tools:         liveMsg.toolTrace?.length ?? 0,
        })
      }
    }
    // Commit on every event — including unknown events that updated debug counters
    commitAssistantMessage(liveMsg)
  }

  // C25: use universal onEvent passthrough — all backend events flow through here.
  // No more per-event registration needed; normalizeChatEvent handles new types
  // automatically without any changes to this file or chat.js.
  const _handlers = {
    onEvent: (eventType, payload) => _handleEvent(eventType, payload),
  }

  try {
    await sendChatMessageStream(
      sessionId.value,
      text,
      outputLanguage,
      _handlers,
      _abortController?.signal,
    )
  } finally {
    // Get the final live reference — may differ from assistantMsg after commits
    const finalMsg = getLiveAssistantMsg(assistantMsg.id)

    if (import.meta.env.DEV) {
      console.debug('[chat stream] finally', {
        anyEventReceived,
        eventsReceived:  finalMsg?.streamDebug?.eventsReceived ?? 0,
        status:          finalMsg?.status,
        isStreaming:     finalMsg?.isStreaming,
        contentLength:   finalMsg?.content?.length ?? 0,
        hasFinalAnswer:  !!finalMsg?.finalAnswer,
        elapsedMs:       Date.now() - requestStartedAt,
      })
    }

    // Finalize: if stream ended but status is still pending, force ui_done + commit
    if (finalMsg && finalMsg.isStreaming &&
        (finalMsg.status === 'connecting' || finalMsg.status === 'streaming')) {
      applyChatUiEvent(finalMsg, { type: 'ui_done' })
      commitAssistantMessage(finalMsg)
    }
  }

  // Only trigger sync fallback if the stream returned with ZERO events —
  // meaning the SSE endpoint itself failed to connect (not just missing agent_started)
  if (!anyEventReceived) {
    throw new Error('stream_not_started')
  }
}

// ── Sync fallback send (existing behavior) ────────────────────────────────────

async function _sendApiSync(text, assistantMsg) {
  const outputLanguage = authStore.currentUser?.output_language ?? 'zh-CN'
  try {
    const resp = await sendChatMessage(sessionId.value, text, outputLanguage)

    _clearTimeouts()

    // Animate tool events
    assistantMsg.toolTrace = []
    if (resp.tool_events?.length) {
      await streamToolTrace(resp.tool_events, (item) => {
        const last = assistantMsg.toolTrace.at(-1)
        if (last && last.name === item.name && last.status === 'running') {
          Object.assign(last, item)
        } else {
          assistantMsg.toolTrace.push({ ...item })
        }
      })
    }

    Object.assign(assistantMsg, {
      content:      resp.answer ?? '',
      resultCard:   (resp.cards ?? [])[0] ?? null,
      confirmation: _wrapConfirmation(resp.confirmation),
      isStreaming:  false,
    })
  } catch (err) {
    _clearTimeouts()
    if (err?.name === 'AbortError') return
    Object.assign(assistantMsg, {
      content:     t('chat_error'),
      toolTrace:   [],
      isStreaming: false,
    })
  }
}

// ── Mock send path (when backend session unavailable) ─────────────────────────

async function _sendMock(text) {
  pushUserMsg(text)
  const assistantMsg = pushAssistantMsg({
    isStreaming: true,
    toolTrace:   _makePlaceholderSteps(),
  })

  try {
    const response = await getMockResponse(text)

    assistantMsg.toolTrace = []
    if (response.toolTrace?.length) {
      await streamToolTrace(response.toolTrace, (item) => {
        const last = assistantMsg.toolTrace.at(-1)
        if (last && last.name === item.name && last.status === 'running') {
          Object.assign(last, item)
        } else {
          assistantMsg.toolTrace.push({ ...item })
        }
      })
    }

    Object.assign(assistantMsg, {
      content:      response.content ?? '',
      resultCard:   response.resultCard ?? null,
      confirmation: response.confirmation ?? null,
      isStreaming:  false,
    })
  } catch {
    Object.assign(assistantMsg, {
      toolTrace:   [],
      content:     t('chat_error'),
      isStreaming: false,
    })
  } finally {
    isSending.value = false
    nextTick(() => inputBoxRef.value?.focus())
  }
}

// ── Quick prompt: fill input only (do NOT auto-send) ─────────────────────────

function onQuickFill(prompt) {
  inputText.value = prompt
  nextTick(() => inputBoxRef.value?.focus())
}

// ── Confirmation handling ─────────────────────────────────────────────────────

async function onConfirm(msgId, confirmation) {
  const origMsg = messages.value.find(m => m.id === msgId)
  if (!origMsg || !confirmation.onConfirm) return

  if (origMsg.confirmation) {
    origMsg.confirmation = { ...origMsg.confirmation, status: 'executing' }
  }

  isSending.value = true
  const followUp = pushAssistantMsg({
    isStreaming: true,
    toolTrace:   _makePlaceholderSteps(),
  })

  try {
    const result = await confirmation.onConfirm()

    if (origMsg.confirmation) {
      origMsg.confirmation = { ...origMsg.confirmation, status: 'executed' }
    }

    followUp.toolTrace = []
    if (result.toolTrace?.length) {
      await streamToolTrace(result.toolTrace, (item) => {
        const last = followUp.toolTrace.at(-1)
        if (last && last.name === item.name && last.status === 'running') {
          Object.assign(last, item)
        } else {
          followUp.toolTrace.push({ ...item })
        }
      })
    }

    let card = result.resultCard
    // C29.3.2: for analysis_run cards — sanitize initial state
    if (card?.type === 'analysis_run' && card.data) {
      // Initial status must be queued/running/submitted (never optimistic completed)
      const VALID_INITIAL = new Set(['queued', 'running', 'submitted', 'pending'])
      if (!VALID_INITIAL.has(card.data.status)) {
        card = { ...card, data: { ...card.data, status: 'queued', links: [] } }
      }
      // Never show fabricated progress — only use backend value
      card = { ...card, data: { ...card.data, progress: card.data.progress ?? null } }
    }
    // C29.2.3: override content with clean user message (remove run_id/technical text)
    const content = card?.type === 'analysis_run'
      ? '正在为您创建分析报告，请稍候…'
      : (result.content ?? '')

    Object.assign(followUp, {
      content,
      resultCard:  card ?? null,
      isStreaming: false,
    })

    // Commit to Vue's reactive system (Object.assign bypasses Proxy)
    commitAssistantMessage(getLiveAssistantMsg(followUp.id) ?? followUp)

    // Start polling if an analysis run was created
    if (card?.type === 'analysis_run' && card.data?.run_id) {
      _startRunPolling(followUp.id, card.data.run_id)
    }
  } catch {
    if (origMsg.confirmation) {
      origMsg.confirmation = { ...origMsg.confirmation, status: 'failed' }
    }
    Object.assign(followUp, {
      toolTrace:   [],
      content:     t('chat_error'),
      isStreaming: false,
    })
    // Commit error state
    commitAssistantMessage(getLiveAssistantMsg(followUp.id) ?? followUp)
  } finally {
    isSending.value = false
  }
}

function onCancel(msgId, _confirmation) {
  const origMsg = messages.value.find(m => m.id === msgId)
  if (origMsg?.confirmation) {
    origMsg.confirmation = { ...origMsg.confirmation, status: 'cancelled' }
  }

  messages.value.push({
    id:           newMsgId(),
    role:         'assistant',
    content:      t('chat_cancelled_msg'),
    toolTrace:    [],
    resultCard:   null,
    confirmation: null,
    isStreaming:  false,
  })
}

// ── Card action handling ──────────────────────────────────────────────────────

function onCardAction(_msgId, link) {
  if (link.action === 'generate_report') {
    const prompt = `帮我生成 ${link.name}（${link.market}/${link.symbol}）的综合分析报告`
    onSend(prompt)
  } else if (link.action === 'retry_analysis') {
    // C29.2.3: rebuild the analysis request for the same stock
    const prompt = link.name && link.market && link.symbol
      ? `帮我分析 ${link.name}（${link.market}/${link.symbol}）并保存到历史报告`
      : '请重新生成分析报告'
    onSend(prompt)
  } else if (link.path) {
    router.push(link.path)
  }
}

// C29.2: poll helpers — immediate first tick + interval; handles terminal links
const _TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])

async function _pollRunTick(msgId, runId, iid) {
  try {
    const snap = await getAnalysisRun(runId)
    const liveMsg = getLiveAssistantMsg(msgId)
    if (!liveMsg) {
      if (iid != null) { clearInterval(iid); _runPolls.delete(msgId) }
      return 'gone'
    }

    const isTerminal = _TERMINAL_STATUSES.has(snap.status)
    const cardData   = liveMsg.resultCard?.data ?? {}

    // Build updated links for terminal states
    let newLinks = cardData.links ?? []
    if (snap.status === 'completed') {
      // C29.2.4: prefer direct report link; fallback to history center
      const reportId = snap.report_id ?? snap.result?.report_id ?? snap.result?.id ?? null
      newLinks = reportId
        ? [{ label: '查看报告', path: { name: 'HistoryDetail', params: { id: String(reportId) }, query: { from: 'chat', session_id: sessionId.value ?? '' } } }]
        : [{ label: '查看报告中心', path: '/history' }]
    } else if (isTerminal) {
      // C29.2.3: failed/cancelled — offer retry action (no path link)
      newLinks = [{ label: '重试分析', action: 'retry_analysis', name: cardData.name, market: cardData.market, symbol: cardData.symbol, scope: cardData.scope }]
    }

    if (liveMsg.resultCard?.type === 'analysis_run') {
      // C29.2.5: backend status always wins — overwrite optimistic state
      liveMsg.resultCard = {
        ...liveMsg.resultCard,
        data: {
          ...cardData,
          status:   snap.status,
          // C29.3.2: only show progress if backend explicitly returns it
          progress: snap.progress !== undefined ? snap.progress : null,
          links:    isTerminal ? newLinks : cardData.links ?? [],
        },
      }
      // C29.2.3: update message content on terminal state
      if (snap.status === 'completed') {
        const reportId = snap.report_id ?? snap.result?.report_id ?? snap.result?.id ?? null
        liveMsg.content = reportId
          ? '分析报告已生成，点击下方按钮查看完整报告。'
          : '分析报告已生成，但暂未获取到报告链接，请前往报告中心查看。'
      } else if (isTerminal) {
        liveMsg.content = '本次分析未能完成，请稍后重试。'
      }
      commitAssistantMessage(liveMsg)
    }

    if (isTerminal && iid != null) { clearInterval(iid); _runPolls.delete(msgId) }
    return snap.status
  } catch {
    return 'error'
  }
}

function _startRunPolling(msgId, runId) {
  if (_runPolls.has(msgId)) return   // already polling this message

  // Sentinel so duplicate calls during the async first-tick are rejected
  _runPolls.set(msgId, null)

  ;(async () => {
    // Immediate first check (also refreshes stale state on session restore)
    const status = await _pollRunTick(msgId, runId, null)
    if (_TERMINAL_STATUSES.has(status) || status === 'gone') {
      _runPolls.delete(msgId)
      return
    }

    // Set up 4s interval for ongoing polls
    const iid = setInterval(() => _pollRunTick(msgId, runId, iid), 4000)
    _runPolls.set(msgId, iid)
  })()
}

// Clean up polling intervals on unmount
onBeforeUnmount(() => {
  _runPolls.forEach(iid => clearInterval(iid))
  _runPolls.clear()
})

// C29.3.4: edit latest user message — aborts any active stream, fills input
function onEditUser(_msgId, content) {
  // 1. Cancel any pending confirmation on the last assistant message
  const lastAssistant = [...messages.value].reverse().find(m => m.role === 'assistant')
  if (lastAssistant?.confirmation &&
      !['executed', 'cancelled'].includes(lastAssistant.confirmation.status)) {
    const liveMsg = getLiveAssistantMsg(lastAssistant.id)
    if (liveMsg) {
      liveMsg.confirmation = { ...liveMsg.confirmation, status: 'cancelled' }
      commitAssistantMessage(liveMsg)
    }
  }

  // 2. Abort stream + finalise the streaming assistant message
  if (isSending.value) {
    if (_abortController) _abortController.abort()
    _clearTimeouts()

    // Mark streaming assistant message as stopped (not error)
    const streamingMsg = messages.value.find(m => m.role === 'assistant' && m.isStreaming)
    if (streamingMsg) {
      const liveMsg = getLiveAssistantMsg(streamingMsg.id)
      if (liveMsg) {
        liveMsg.isStreaming = false
        liveMsg.status      = 'done'
        if (!liveMsg.content) liveMsg.content = t('chat_stopped')
        commitAssistantMessage(liveMsg)
      }
    }
    isSending.value = false
  }

  // 3. Refill input and focus
  inputText.value = content
  nextTick(() => inputBoxRef.value?.focus())
}

// C29.5: retry — find the user message before this AI message and resend
function onRetryAi(msgId) {
  if (isSending.value) return
  const idx = messages.value.findIndex(m => m.id === msgId)
  if (idx <= 0) return
  // Walk backwards to find the preceding user message
  const userMsg = messages.value.slice(0, idx).reverse().find(m => m.role === 'user')
  if (!userMsg) return
  // Remove messages from the user message onward and resend
  messages.value = messages.value.slice(0, messages.value.indexOf(userMsg))
  onSend(userMsg.content)
}
</script>

<style scoped>
/* ── C29.1.3: Full-screen fixed chat layout — override ALL global app-shell defaults ── */
.chat-shell {
  /* Reset global app-shell (max-width, margins, padding) */
  max-width: 100% !important;
  width: 100%;
  margin: 0 !important;
  padding: 0 !important;
  /* Fixed full-viewport column */
  display: flex;
  flex-direction: column;
  height: 100dvh;
  overflow: hidden;
}

/* Remove AppHeader's default margin-bottom in the chat context */
.chat-shell :deep(.app-header) {
  margin-bottom: 0 !important;
  flex-shrink: 0;
}

/* ── Two-column layout: sidebar + chat ───────────────────────────────────────── */
.chat-layout {
  display: flex;
  gap: 0;
  flex: 1;
  min-height: 0;
  /* No hardcoded height — parent is 100dvh, flex: 1 fills the rest */
}

/* ── Chat column (fills remaining space) ─────────────────────────────────────── */
.chat-column {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  display: flex;
  justify-content: center;
}

/* ── Inner container (max-width centered) ────────────────────────────────────── */
.chat-inner {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 860px;
  padding: 0 16px;
  min-height: 0;
  overflow: hidden;
}

/* ── Compact topbar ──────────────────────────────────────────────────────────── */
.chat-topbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 0 8px;
  border-bottom: 1px solid var(--border-soft);
  margin-bottom: 8px;
  flex-shrink: 0;
}

.chat-topbar-icon {
  font-size: 18px;
}

.chat-topbar-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  flex: 1;
}

.chat-api-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.chat-api-dot.dot-ok   { background: var(--status-up, #16a34a); }
.chat-api-dot.dot-warn { background: var(--warn, #d97706); }

/* ── Session error ───────────────────────────────────────────────────────────── */
.chat-session-error {
  font-size: 12px;
  color: var(--danger);
  background: var(--status-down-bg);
  border: 1px solid var(--status-down-ring, var(--danger));
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

/* ── Soft timeout notice ──────────────────────────────────────────────────────── */
.chat-soft-timeout {
  font-size: 12px;
  color: var(--accent);
  background: var(--status-info-bg);
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  padding: 6px 12px;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.btn-stop {
  font-size: 11px;
  font-weight: 700;
  border: 1px solid var(--accent);
  color: var(--accent);
  background: none;
  border-radius: 6px;
  padding: 2px 8px;
  cursor: pointer;
  white-space: nowrap;
}
.btn-stop:hover { background: var(--accent); color: white; }

/* ── Session-switch skeleton ─────────────────────────────────────────────────── */
.chat-session-skeleton {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 12px;
  padding: 40px 24px;
}

.skeleton-line {
  height: 14px;
  border-radius: 7px;
  background: linear-gradient(90deg, var(--border-soft) 25%, var(--surface) 50%, var(--border-soft) 75%);
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.2s infinite;
}

.skeleton-line.wide   { width: 80%; }
.skeleton-line.medium { width: 60%; }
.skeleton-line.narrow { width: 40%; }

@keyframes skeleton-shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ── Welcome area (empty state) ─────────────────────────────────────────────── */
.chat-welcome-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 0 20px;
  flex-shrink: 0;
}

.welcome-hero {
  text-align: center;
  margin-bottom: 32px;
}

.welcome-title {
  font-size: 26px;
  font-weight: 800;
  background: var(--accent-gradient, var(--accent));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1.2;
  margin-bottom: 8px;
}

.welcome-sub {
  font-size: 14px;
  color: var(--muted);
  line-height: 1.5;
  max-width: 400px;
}

/* ── Messages area — C29.2: pure flex container; inner .message-list scrolls ── */
.chat-messages-area {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Footer: disclaimer + input ──────────────────────────────────────────────── */
.chat-footer {
  flex-shrink: 0;
}

.chat-disclaimer {
  font-size: 11px;
  color: var(--muted);
  text-align: center;
  padding: 6px 0 2px;
  line-height: 1.4;
}

.chat-input-area {
  padding: 4px 0 12px;
}

/* ── Mobile ──────────────────────────────────────────────────────────────────── */
@media (max-width: 640px) {
  /* BottomTabBar is position:fixed at bottom, 56px tall — shrink chat-shell so
     the input area is not hidden beneath it */
  .chat-shell {
    height: calc(100dvh - 56px - env(safe-area-inset-bottom));
  }

  .chat-inner {
    padding: 0 10px;
  }

  .welcome-title {
    font-size: 20px;
  }

  .chat-input-area {
    padding-bottom: 8px;
  }
}
</style>
