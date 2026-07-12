<template>
  <div class="rcp-root">
    <!-- Conversation history -->
    <div v-if="history.length" class="rcp-history">
      <div
        v-for="(turn, i) in history"
        :key="i"
        class="rcp-history-turn"
      >
        <div class="rcp-history-q">
          <span class="rcp-history-label">Q</span>
          <span class="rcp-history-text">{{ turn.question }}</span>
        </div>
        <div class="rcp-history-a">
          <span class="rcp-history-label rcp-history-label--a">A</span>
          <span class="rcp-history-text rcp-history-a-text">{{ turn.answer }}</span>
        </div>
        <div v-if="turn.cacheHit" class="rcp-history-cache-badge">{{ t('rcp_cache_hit') }}</div>
      </div>
    </div>

    <!-- Input area -->
    <div class="rcp-input-row">
      <textarea
        v-model="question"
        class="rcp-textarea"
        :placeholder="t('rcp_placeholder')"
        :disabled="loading"
        maxlength="500"
        rows="2"
        @keydown.enter.exact.prevent="submit"
        @compositionstart="composing = true"
        @compositionend="composing = false"
      ></textarea>
      <button
        class="rcp-send-btn"
        :disabled="loading || !question.trim()"
        @click="submit"
      >
        <span v-if="loading" class="rcp-spinner"></span>
        <span v-else>{{ t('rcp_send') }}</span>
      </button>
    </div>

    <!-- Input controls row: force refresh + clear history -->
    <div class="rcp-controls-row">
      <label class="rcp-toggle-label">
        <input type="checkbox" v-model="forceRefresh" class="rcp-toggle-cb" />
        <span>{{ t('rcp_force_refresh') }}</span>
      </label>
      <button
        v-if="history.length"
        class="rcp-clear-btn"
        @click="clearHistory"
      >{{ t('rcp_clear_history') }}</button>
    </div>

    <!-- Suggestions -->
    <div v-if="!result && !loading" class="rcp-suggestions">
      <span class="rcp-sugg-label">{{ t('rcp_try') }}</span>
      <button
        v-for="(s, i) in suggestions"
        :key="i"
        class="rcp-sugg-chip"
        @click="useSuggestion(s)"
      >{{ s }}</button>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading" class="rcp-loading">
      <span class="rcp-spinner"></span>
      <span>{{ t('rcp_loading') }}</span>
    </div>

    <!-- Rate limit notice -->
    <div v-else-if="rateLimitHit" class="rcp-notice rcp-notice--warn">
      <span class="rcp-notice-icon">⏳</span>
      {{ t('rcp_rate_limit') }}
      <span v-if="retryAfter"> ({{ retryAfter }}s)</span>
    </div>

    <!-- Error / no-index notice -->
    <div v-else-if="result && result.partial && !result.answer" class="rcp-notice rcp-notice--warn">
      {{ result.errors?.[0] || t('rcp_unavailable') }}
    </div>

    <!-- Result -->
    <div v-else-if="result" class="rcp-result">

      <!-- Rejection notice (investment advice / injection blocked) -->
      <div v-if="isRejected" class="rcp-notice rcp-notice--reject">
        <span class="rcp-notice-icon">🚫</span>
        {{ result.answer }}
      </div>

      <!-- Normal answer -->
      <template v-else>
        <!-- Answer text -->
        <div class="rcp-answer">{{ result.answer }}</div>

        <!-- Confidence + RAG status + cache + memory badges -->
        <div class="rcp-meta-row">
          <span v-if="result.confidence" :class="['rcp-confidence', 'rcp-confidence--' + result.confidence]">
            {{ confidenceLabel(result.confidence) }}
          </span>
          <span v-if="result.rag_status" :class="['rcp-rag-badge', 'rcp-rag-badge--' + result.rag_status]">
            {{ ragStatusLabel(result.rag_status) }}
          </span>
          <span v-if="result.review_audit?.source_chunks_checked" class="rcp-verified-badge">
            ✓ {{ t('rcp_verified') }}
          </span>
          <span v-if="result.cache_meta?.hit" class="rcp-cache-badge">
            ⚡ {{ t('rcp_cache_hit') }}
          </span>
          <span v-if="memoryTurnsLoaded > 0" class="rcp-memory-badge">
            💬 {{ t('rcp_memory_active') }} ({{ memoryTurnsLoaded }})
          </span>
          <span v-if="result.partial" class="rcp-partial-badge">{{ t('rcp_partial') }}</span>
        </div>

        <!-- Data limitations -->
        <div v-if="result.data_limitations?.length" class="rcp-limitations">
          <span v-for="(l, i) in result.data_limitations" :key="i" class="rcp-limit-item">{{ l }}</span>
        </div>

        <!-- Source chunks -->
        <div v-if="result.source_chunks?.length" class="rcp-chunks">
          <div class="rcp-chunks-title">🔍 {{ t('rcp_source_chunks') }}</div>
          <div
            v-for="(chunk, i) in result.source_chunks"
            :key="chunk.chunk_id || i"
            class="rcp-chunk-item"
          >
            <div class="rcp-chunk-header">
              <span class="rcp-chunk-type-badge" :class="reportTypeClass(chunk.report_type)">
                {{ reportTypeLabel(chunk.report_type) }}
              </span>
              <span class="rcp-chunk-section">{{ chunk.section_title || t('rcp_chunk_default') }}</span>
              <span class="rcp-chunk-period">{{ chunk.period || '' }}</span>
              <span v-if="chunk.score != null" class="rcp-chunk-score">
                {{ (chunk.score * 100).toFixed(0) }}%
              </span>
              <a
                v-if="chunk.pdf_url"
                :href="chunk.pdf_url"
                target="_blank"
                rel="noopener noreferrer"
                class="rcp-pdf-link"
              >PDF</a>
            </div>

            <!-- Citation -->
            <div v-if="chunk.citation" class="rcp-chunk-citation">
              "{{ chunk.citation }}"
            </div>

            <!-- Expandable content -->
            <div v-if="chunk.content && expandedChunks[i]" class="rcp-chunk-content">
              {{ chunk.content }}
            </div>
            <button
              v-if="chunk.content"
              class="rcp-chunk-toggle"
              @click="toggleChunk(i)"
            >{{ expandedChunks[i] ? t('rcp_collapse') : t('rcp_expand') }}</button>
          </div>
        </div>

        <!-- No index / REPORT_RAG_NOT_READY notice with action suggestions -->
        <div v-else-if="result.rag_status === 'unavailable'" class="rcp-notice rcp-notice--info">
          <p>{{ result.answer || t('rcp_no_index') }}</p>
          <div v-if="result.action_suggestions && result.action_suggestions.length > 0" class="rcp-actions">
            <span class="rcp-actions-label">下一步操作：</span>
            <div class="rcp-action-btns">
              <button
                v-for="sug in result.action_suggestions"
                :key="sug.action"
                class="rcp-action-btn"
                @click="$emit('action', sug.action)"
              >{{ sug.label }}</button>
            </div>
          </div>
        </div>
      </template>

      <!-- Disclaimer -->
      <div class="rcp-disclaimer">⚠️ {{ result.disclaimer || t('rcp_disclaimer') }}</div>
    </div>

    <!-- Empty state (no query yet) — shows RAG index status from diagnostics -->
    <div v-else class="rcp-empty">
      <template v-if="ragIndexStatus === 'ready'">
        <span class="rcp-empty-icon">💬</span>
        <p class="rcp-empty-text">{{ t('rcp_empty_state') }}</p>
      </template>
      <template v-else-if="ragIndexStatus === 'not_indexed'">
        <span class="rcp-empty-icon">📑</span>
        <p class="rcp-empty-text">{{ t('rcp_rag_not_indexed') }}</p>
      </template>
      <template v-else-if="ragIndexStatus === 'empty'">
        <span class="rcp-empty-icon">📭</span>
        <p class="rcp-empty-text">{{ t('rcp_rag_empty') }}</p>
      </template>
      <template v-else>
        <!-- unknown / loading -->
        <span class="rcp-empty-icon">📄</span>
        <p class="rcp-empty-text">{{ t('rcp_rag_unknown') }}</p>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from '../../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  market:         { type: String, required: true },
  stockCode:      { type: String, required: true },
  /** RAG index status from diagnostics: ready | not_indexed | empty | unknown */
  ragIndexStatus: { type: String, default: 'unknown' },
})

const emit = defineEmits(['action'])

// ── State ─────────────────────────────────────────────────────────────────────

const question       = ref('')
const loading        = ref(false)
const result         = ref(null)
const expandedChunks = ref({})
const forceRefresh   = ref(false)
const composing      = ref(false)
const rateLimitHit   = ref(false)
const retryAfter     = ref(null)

// Conversation history for display (not the server-side Redis memory)
const history = ref([])

// Stable session ID persisted in localStorage per stock
const sessionId = computed(() => {
  if (!props.stockCode) return null
  const storageKey = `rcp_session_${props.stockCode}`
  let id = localStorage.getItem(storageKey)
  if (!id) {
    // Generate a simple UUID-like ID
    id = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
    localStorage.setItem(storageKey, id)
  }
  return id
})

const suggestions = computed(() => [
  t('rcp_sugg1'),
  t('rcp_sugg2'),
  t('rcp_sugg3'),
  t('rcp_sugg4'),
  t('rcp_sugg5'),
])

// ── Computed ──────────────────────────────────────────────────────────────────

const isRejected = computed(() => {
  if (!result.value) return false
  const audit = result.value.review_audit || {}
  return audit.investment_advice_blocked === true
})

const memoryTurnsLoaded = computed(() => {
  return result.value?.memory_meta?.turns_loaded ?? 0
})

// ── Methods ───────────────────────────────────────────────────────────────────

function useSuggestion(s) {
  question.value = s
  submit()
}

function toggleChunk(i) {
  expandedChunks.value = { ...expandedChunks.value, [i]: !expandedChunks.value[i] }
}

function clearHistory() {
  history.value = []
  result.value = null
  // Reset session ID so server memory also resets next time
  if (props.stockCode) {
    const storageKey = `rcp_session_${props.stockCode}`
    localStorage.removeItem(storageKey)
  }
}

async function submit() {
  const q = question.value.trim()
  if (!q || loading.value || composing.value) return

  loading.value  = true
  result.value   = null
  rateLimitHit.value = false
  retryAfter.value   = null
  expandedChunks.value = {}

  try {
    const code = props.stockCode
    const url = `/api/v1/stock/${encodeURIComponent(code)}/report-chat`
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question:      q,
        top_k:         6,
        force_refresh: forceRefresh.value,
        session_id:    sessionId.value,
        use_memory:    true,
      }),
    })

    if (resp.status === 429) {
      rateLimitHit.value = true
      const ra = resp.headers.get('Retry-After')
      retryAfter.value = ra ? parseInt(ra, 10) : null
      return
    }

    if (!resp.ok) {
      const txt = await resp.text()
      result.value = {
        answer: `请求失败（${resp.status}）：${txt.slice(0, 200)}`,
        source_chunks: [],
        review_audit: {},
        rag_status: 'unavailable',
        confidence: 'low',
        data_limitations: [],
        errors: [`HTTP ${resp.status}`],
        partial: true,
        disclaimer: t('rcp_disclaimer'),
      }
      return
    }

    const data = await resp.json()
    result.value = data

    // Append to local conversation display history (only non-rejected answers)
    const audit = data.review_audit || {}
    if (!audit.investment_advice_blocked && data.answer) {
      history.value.push({
        question: q,
        answer: data.answer.slice(0, 120) + (data.answer.length > 120 ? '…' : ''),
        cacheHit: !!data.cache_meta?.hit,
      })
      // Keep at most 5 visible history turns
      if (history.value.length > 5) {
        history.value = history.value.slice(-5)
      }
    }

    // Reset force_refresh after use
    forceRefresh.value = false
    question.value = ''

  } catch (err) {
    result.value = {
      answer: `网络错误：${err.message}`,
      source_chunks: [],
      review_audit: {},
      rag_status: 'unavailable',
      confidence: 'low',
      data_limitations: [],
      errors: [err.message],
      partial: true,
      disclaimer: t('rcp_disclaimer'),
    }
  } finally {
    loading.value = false
  }
}

// ── Label helpers ─────────────────────────────────────────────────────────────

function confidenceLabel(c) {
  return { high: t('rcp_conf_high'), medium: t('rcp_conf_medium'), low: t('rcp_conf_low') }[c] || c
}

function ragStatusLabel(s) {
  return {
    local:        t('rcp_rag_local'),
    mock:         t('rcp_rag_mock'),
    keyword_only: t('rcp_rag_keyword'),
    unavailable:  t('rcp_rag_unavailable'),
  }[s] || s
}

function reportTypeLabel(type) {
  return { annual: t('rcp_rt_annual'), semi: t('rcp_rt_semi'), q1: t('rcp_rt_q1'), q3: t('rcp_rt_q3') }[type] || type || t('rcp_rt_report')
}

function reportTypeClass(type) {
  return { annual: 'rtype--annual', semi: 'rtype--semi', q1: 'rtype--q', q3: 'rtype--q' }[type] || ''
}
</script>

<style scoped>
.rcp-root {
  display: flex; flex-direction: column; gap: 12px;
  background: var(--surface, white);
  border-radius: 12px;
  padding: 14px 16px;
}

/* Conversation history */
.rcp-history { display: flex; flex-direction: column; gap: 10px; }
.rcp-history-turn {
  padding: 10px 12px; border-radius: 8px;
  background: var(--surface2, #f8f9fa);
  border: 1px solid var(--border);
  display: flex; flex-direction: column; gap: 4px; font-size: 12px;
}
.rcp-history-q, .rcp-history-a { display: flex; gap: 6px; align-items: flex-start; }
.rcp-history-label {
  font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 4px;
  background: var(--accent, #1677ff); color: white; flex-shrink: 0; margin-top: 1px;
}
.rcp-history-label--a {
  background: #389e0d;
}
.rcp-history-text { color: var(--text); line-height: 1.5; flex: 1; }
.rcp-history-a-text { color: var(--muted); }
.rcp-history-cache-badge {
  font-size: 9px; color: #d46b08; align-self: flex-end;
}

/* Input */
.rcp-input-row {
  display: flex; gap: 8px; align-items: flex-end;
}
.rcp-textarea {
  flex: 1;
  resize: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text);
  background: var(--surface2, #f8f9fa);
  outline: none;
  transition: border-color 0.15s;
  font-family: inherit;
}
.rcp-textarea:focus { border-color: var(--accent, #1677ff); background: white; }
.rcp-textarea:disabled { opacity: 0.5; }
.rcp-send-btn {
  flex-shrink: 0;
  min-width: 64px; height: 38px;
  background: var(--accent, #1677ff); color: white;
  border: none; border-radius: 8px;
  font-size: 13px; font-weight: 600; cursor: pointer;
  display: flex; align-items: center; justify-content: center; gap: 4px;
  transition: opacity 0.15s;
}
.rcp-send-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.rcp-send-btn:not(:disabled):hover { opacity: 0.85; }

/* Controls row */
.rcp-controls-row {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
}
.rcp-toggle-label {
  display: flex; align-items: center; gap: 5px;
  font-size: 11px; color: var(--muted); cursor: pointer; user-select: none;
}
.rcp-toggle-cb { width: 12px; height: 12px; cursor: pointer; }
.rcp-clear-btn {
  font-size: 11px; color: var(--muted); background: none; border: none;
  cursor: pointer; text-decoration: underline; padding: 0;
}
.rcp-clear-btn:hover { color: var(--accent, #1677ff); }

/* Suggestions */
.rcp-suggestions {
  display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
}
.rcp-sugg-label { font-size: 11px; color: var(--muted); }
.rcp-sugg-chip {
  font-size: 11px; padding: 3px 9px; border-radius: 20px;
  border: 1px solid var(--border);
  background: var(--surface2, #f8f9fa); color: var(--text);
  cursor: pointer; transition: background 0.1s;
}
.rcp-sugg-chip:hover { background: #e6f4ff; border-color: var(--accent, #1677ff); color: var(--accent, #1677ff); }

/* Loading */
.rcp-loading {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; color: var(--muted); padding: 8px 0;
}

/* Spinner */
.rcp-spinner {
  display: inline-block; width: 14px; height: 14px;
  border: 2px solid rgba(255,255,255,.35);
  border-top-color: white;
  border-radius: 50%;
  animation: rcp-spin 0.7s linear infinite;
}
.rcp-loading .rcp-spinner {
  border-color: var(--border); border-top-color: var(--accent, #1677ff);
}
@keyframes rcp-spin { to { transform: rotate(360deg); } }

/* Notices */
.rcp-notice {
  border-radius: 8px; padding: 10px 12px;
  font-size: 12px; line-height: 1.5; display: flex; flex-direction: column; gap: 6px; align-items: flex-start;
}
.rcp-notice--warn { background: #fff8e1; color: #856404; border: 1px solid #ffc107; }
.rcp-notice--info { background: #e6f4ff; color: #0958d9; border: 1px solid #91caff; }
.rcp-notice--reject { background: #fff2f0; color: #cf1322; border: 1px solid #ffccc7; }
.rcp-notice-icon { flex-shrink: 0; font-size: 14px; }

.rcp-actions { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.rcp-actions-label { font-size: 11px; color: #666; font-weight: 600; }
.rcp-action-btns { display: flex; flex-wrap: wrap; gap: 8px; }
.rcp-action-btn {
  font-size: 12px; padding: 5px 14px; border-radius: 6px;
  background: #1d39c4; color: #fff; border: none; cursor: pointer;
  transition: background 0.15s;
}
.rcp-action-btn:hover { background: #122b9f; }

/* Result */
.rcp-result { display: flex; flex-direction: column; gap: 10px; }

.rcp-answer {
  font-size: 13px; color: var(--text); line-height: 1.7;
  white-space: pre-wrap; word-break: break-word;
}

/* Meta row */
.rcp-meta-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }

.rcp-confidence {
  font-size: 10px; font-weight: 600; padding: 1px 7px; border-radius: 20px;
}
.rcp-confidence--high   { background: #f6ffed; color: #389e0d; border: 1px solid #b7eb8f; }
.rcp-confidence--medium { background: #e6f4ff; color: #0958d9; border: 1px solid #91caff; }
.rcp-confidence--low    { background: #fff7e6; color: #d46b08; border: 1px solid #ffd591; }

.rcp-rag-badge {
  font-size: 9px; font-weight: 600; padding: 1px 6px; border-radius: 4px;
}
.rcp-rag-badge--local        { background: #f0f9eb; color: #389e0d; border: 1px solid #b7eb8f; }
.rcp-rag-badge--mock         { background: #f5f5f5; color: #8c8c8c; font-style: italic; }
.rcp-rag-badge--keyword_only { background: #fff7e6; color: #d46b08; border: 1px solid #ffd591; }
.rcp-rag-badge--unavailable  { background: #f5f5f5; color: #8c8c8c; }

.rcp-verified-badge {
  font-size: 9px; font-weight: 600; padding: 1px 6px; border-radius: 4px;
  background: #e6fffb; color: #08979c; border: 1px solid #87e8de;
}
.rcp-cache-badge {
  font-size: 9px; font-weight: 600; padding: 1px 6px; border-radius: 4px;
  background: #fff7e6; color: #d46b08; border: 1px solid #ffd591;
}
.rcp-memory-badge {
  font-size: 9px; font-weight: 600; padding: 1px 6px; border-radius: 4px;
  background: #f9f0ff; color: #531dab; border: 1px solid #d3adf7;
}
.rcp-partial-badge {
  font-size: 9px; padding: 1px 5px; border-radius: 4px;
  background: #fff8e1; color: #856404;
}

/* Data limitations */
.rcp-limitations {
  display: flex; flex-direction: column; gap: 2px;
}
.rcp-limit-item {
  font-size: 11px; color: var(--muted); padding-left: 12px;
  position: relative;
}
.rcp-limit-item::before {
  content: '·'; position: absolute; left: 3px;
}

/* Source chunks */
.rcp-chunks { display: flex; flex-direction: column; gap: 6px; }
.rcp-chunks-title {
  font-size: 11px; font-weight: 600; color: var(--text);
  padding-bottom: 4px; border-bottom: 1px solid var(--border);
}
.rcp-chunk-item {
  border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px;
}
.rcp-chunk-header { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.rcp-chunk-type-badge {
  font-size: 10px; font-weight: 600; padding: 1px 5px; border-radius: 4px;
  background: var(--border); color: var(--text); flex-shrink: 0;
}
.rtype--annual { background: #e6f4ff; color: #1677ff; }
.rtype--semi   { background: #f6ffed; color: #52c41a; }
.rtype--q      { background: #fff7e6; color: #fa8c16; }
.rcp-chunk-section {
  flex: 1; font-size: 11px; font-weight: 500; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 180px;
}
.rcp-chunk-period { font-size: 10px; color: var(--muted); flex-shrink: 0; }
.rcp-chunk-score  { font-size: 10px; color: var(--muted); flex-shrink: 0; }
.rcp-pdf-link {
  font-size: 10px; color: var(--accent, #1677ff);
  text-decoration: none; padding: 1px 5px;
  border: 1px solid currentColor; border-radius: 4px; flex-shrink: 0;
}
.rcp-pdf-link:hover { background: #e6f4ff; }

.rcp-chunk-citation {
  font-size: 11px; color: var(--muted); font-style: italic;
  margin-top: 4px; padding-left: 8px;
  border-left: 2px solid var(--border);
}
.rcp-chunk-content {
  font-size: 11px; color: var(--muted); line-height: 1.6;
  margin-top: 6px; white-space: pre-wrap; word-break: break-all;
  background: var(--surface2, #f8f9fa); border-radius: 4px; padding: 6px 8px;
  max-height: 220px; overflow-y: auto;
}
.rcp-chunk-toggle {
  font-size: 10px; color: var(--accent, #1677ff); background: none; border: none;
  cursor: pointer; padding: 2px 0; margin-top: 4px; display: block;
}
.rcp-chunk-toggle:hover { text-decoration: underline; }

/* Disclaimer */
.rcp-disclaimer {
  font-size: 11px; color: #856404;
  background: #fff8e1; border-radius: 6px; padding: 8px 12px; line-height: 1.5;
}

/* Empty state */
.rcp-empty { text-align: center; padding: 16px 0; }
.rcp-empty-icon { font-size: 28px; }
.rcp-empty-text { font-size: 12px; color: var(--muted); margin: 6px 0 0; line-height: 1.5; }

@media (max-width: 480px) {
  .rcp-root { padding: 10px 12px; }
  .rcp-input-row { flex-direction: column; }
  .rcp-send-btn { width: 100%; }
}
</style>
