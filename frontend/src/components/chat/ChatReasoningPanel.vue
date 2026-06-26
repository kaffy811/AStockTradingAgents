<template>
  <!-- Show when streaming or when there's anything to display -->
  <div v-if="shouldShow" class="rp-panel">

    <!-- ── Header ─────────────────────────────────────────────────────────────── -->
    <button class="rp-header" @click="collapsed = !collapsed" type="button" :aria-expanded="!collapsed">
      <span v-if="isActivelyRunning" class="rp-spinner" aria-hidden="true"></span>
      <span v-else class="rp-status-icon" aria-hidden="true">{{ overallStatusIcon }}</span>
      <span class="rp-title">{{ panelTitle }}</span>
      <span v-if="totalCount > 0" class="rp-count">{{ totalCount }} 步</span>
      <span class="rp-chevron" :class="{ 'rp-chevron--open': !collapsed }" aria-hidden="true">▶</span>
    </button>

    <!-- ── Expandable body ─────────────────────────────────────────────────────── -->
    <Transition name="rp-expand">
      <div v-if="!collapsed" class="rp-body">

        <!-- Connecting state: before agent_started received -->
        <div v-if="showConnecting" class="rp-connecting">
          <span class="rp-connecting-dot"></span>
          正在连接 AI 助理…
        </div>

        <!-- Waiting state: agent_started received but no step events yet -->
        <div v-else-if="showWaiting" class="rp-waiting">
          <span class="rp-waiting-dot"></span>
          AI 正在分析中，请稍候…
        </div>

        <!-- Unified step list (reasoningSteps + toolTrace, ordered by startedAt) -->
        <div
          v-for="(item, idx) in unifiedSteps"
          :key="`${item.key ?? item.name}-${idx}`"
          class="rp-step"
          :class="`rp-step--${item.status}`"
        >
          <!-- Running spinner — suppressed when outer status is done (defense-in-depth) -->
          <span v-if="item.status === 'running' && !isDone" class="rp-step-spinner" aria-hidden="true"></span>
          <!-- Done/error: icon — treat any still-running item as success when outer is done -->
          <span v-else class="rp-step-icon" aria-hidden="true">{{ stepIcon(isDone && item.status === 'running' ? 'success' : item.status) }}</span>

          <div class="rp-step-body">
            <span class="rp-step-title">{{ item.title ?? item.name }}</span>
            <span
              v-if="item.summary"
              class="rp-step-summary"
              :class="{ 'rp-step-summary--clamped': !expandedSummaries[idx] }"
              @click="toggleSummary(idx)"
            >{{ item.summary }}</span>
            <!-- Risk flag badges (from subagent / risk_review steps) -->
            <div v-if="item.riskFlags?.length" class="rp-risk-flags">
              <span
                v-for="flag in item.riskFlags.slice(0, 3)"
                :key="flag"
                class="rp-risk-badge"
              >{{ flag }}</span>
            </div>
          </div>
        </div>

        <!-- Thinking panel (collapsible, auto-open while streaming) -->
        <details v-if="thinkingContent" class="rp-thinking" :open="isStreaming">
          <summary class="rp-thinking-label">💭 思考过程</summary>
          <div class="rp-thinking-body">{{ thinkingContent }}</div>
        </details>

      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'

const props = defineProps({
  /** true while SSE stream is open */
  isStreaming:     { type: Boolean, default: false },
  /** 'connecting' | 'streaming' | 'done' | 'error' */
  status:          { type: String,  default: 'idle' },
  /** Orchestrator / agent steps (from reducer reasoningSteps) */
  reasoningSteps:  { type: Array,   default: () => [] },
  /** Tool call trace (from reducer toolTrace) */
  toolTrace:       { type: Array,   default: () => [] },
  /** Phase 2E-2 agentTrace (backward compat, shown when reasoningSteps empty) */
  agentTrace:      { type: Array,   default: () => [] },
  /** DeepSeek thinking content */
  thinkingContent: { type: String,  default: '' },
})

// ── Collapse control: open while streaming, no forced close on done ───────────
const collapsed = ref(false)

// Track which step summaries the user has expanded (click-to-expand)
const expandedSummaries = reactive({})
function toggleSummary(idx) {
  expandedSummaries[idx] = !expandedSummaries[idx]
}

// ── Skill name → Chinese display title ────────────────────────────────────────
const SKILL_TITLE_MAP = {
  'report_explanation_skill':       '报告解读',
  'general_financial_answer_skill': '智能问答',
  'stock_quote_skill':              '实时行情查询',
  'watchlist_skill':                '自选股管理',
  'analysis_run_skill':             '生成分析报告',
  'comparison_skill':               '多股对比',
}

function _skillDisplayTitle(title, key) {
  // key like "tool:skill:report_explanation_skill"
  const skillName = key?.split(':')[2]
  if (skillName && SKILL_TITLE_MAP[skillName]) {
    return `技能：${SKILL_TITLE_MAP[skillName]}`
  }
  return title ?? '技能路由'
}

// ── Unified step list: merge reasoningSteps + toolTrace by startedAt ──────────
const unifiedSteps = computed(() => {
  // If reasoningSteps populated (new normalizer path), use those + toolTrace
  // If only agentTrace (Phase 2E-2 direct path, e.g. no normalizer), fall back to agentTrace
  const rs = (props.reasoningSteps ?? []).map(s => ({ ...s, _isStep: true }))
  const tt = (props.toolTrace ?? []).map(t => {
    const key = t.key ?? t.name
    // Apply Chinese title for skill steps
    const title = key?.startsWith('tool:skill:')
      ? _skillDisplayTitle(t.title ?? t.name, key)
      : (t.title ?? t.name)
    return {
      key,
      title,
      status:    t.status,
      summary:   t.summary ?? t.detail ?? '',
      riskFlags: t.riskFlags ?? [],
      startedAt: t.startedAt ?? Date.now(),
      _isTool:   true,
    }
  })

  // When reasoningSteps is empty but agentTrace has items (pure 2E-2 path),
  // show agentTrace as fallback
  const at = (rs.length === 0 && tt.length === 0)
    ? (props.agentTrace ?? []).map(a => ({
        key:       a.name,
        title:     a.displayName ?? a.name,
        status:    a.status,
        summary:   a.summary ?? '',
        riskFlags: a.riskFlags ?? [],
        startedAt: 0,
      }))
    : []

  const all = [...rs, ...tt, ...at]
  // Sort by startedAt; reasoningSteps (agent_started) always pin to front
  all.sort((a, b) => {
    if (a._isStep && !b._isStep) return -1
    if (!a._isStep && b._isStep) return 1
    return (a.startedAt ?? 0) - (b.startedAt ?? 0)
  })
  return all
})

// ── Derived state ─────────────────────────────────────────────────────────────

/** True when the overall stream is finished — used as a spinner kill-switch. */
const isDone = computed(() => props.status === 'done' || props.status === 'error')

const hasSteps = computed(() =>
  unifiedSteps.value.length > 0 || !!props.thinkingContent
)

const isActivelyRunning = computed(() =>
  props.isStreaming && (
    unifiedSteps.value.some(s => s.status === 'running') ||
    props.status === 'streaming' ||
    props.status === 'connecting'
  )
)

/** Show "正在连接 AI 助理…" ONLY before agent_started (status='connecting') */
const showConnecting = computed(() =>
  props.isStreaming &&
  !hasSteps.value &&
  props.status === 'connecting'
)

/** Show "AI 正在分析中…" after agent_started but before any step events arrive */
const showWaiting = computed(() =>
  props.isStreaming &&
  !hasSteps.value &&
  props.status === 'streaming'
)

/** Show the panel when streaming or when there's something to display */
const shouldShow = computed(() => props.isStreaming || hasSteps.value)

const totalCount = computed(() => unifiedSteps.value.length)

const panelTitle = computed(() => {
  if (props.status === 'connecting') return '正在连接…'
  if (props.status === 'error')      return '出错'
  if (props.status === 'done')       return '已完成'
  if (isActivelyRunning.value)       return '研究中…'
  return hasSteps.value ? '研究过程' : '准备中…'
})

const overallStatusIcon = computed(() => {
  if (props.status === 'done')  return '✓'
  if (props.status === 'error') return '✕'
  return '●'
})

function stepIcon(status) {
  const MAP = {
    success: '✓',
    done:    '✓',
    error:   '✕',
    failed:  '✕',
    partial: '◑',
    warning: '⚠',
    skipped: '—',
    stopped: '□',
  }
  return MAP[status] ?? '○'
}
</script>

<style scoped>
/* ── Panel container ──────────────────────────────────────────────────────────── */
.rp-panel {
  margin: 6px 0 10px;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  overflow: hidden;
  background: var(--surface2);
  font-size: 13px;
}

/* ── Header ───────────────────────────────────────────────────────────────────── */
.rp-header {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 8px 12px;
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  color: var(--text);
  font-size: 12px;
  font-weight: 600;
  transition: background 0.15s;
  min-height: 38px;   /* large enough tap target on mobile */
}
.rp-header:hover { background: var(--surface3, rgba(0,0,0,0.04)); }

/* Header spinner */
.rp-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid var(--border-soft);
  border-top-color: var(--accent, #4a90e2);
  border-radius: 50%;
  animation: rp-spin 0.8s linear infinite;
  flex-shrink: 0;
}
@keyframes rp-spin { to { transform: rotate(360deg); } }

.rp-status-icon { font-size: 11px; width: 14px; text-align: center; flex-shrink: 0; }
.rp-title       { flex: 1; color: var(--muted); }

.rp-count {
  font-size: 11px;
  color: var(--muted);
  background: var(--surface3, rgba(0,0,0,0.06));
  border-radius: 10px;
  padding: 1px 7px;
  flex-shrink: 0;
}

.rp-chevron {
  color: var(--muted);
  font-size: 10px;
  transition: transform 0.2s;
  display: inline-block;
  flex-shrink: 0;
}
.rp-chevron--open { transform: rotate(90deg); }

/* ── Body ─────────────────────────────────────────────────────────────────────── */
.rp-body {
  border-top: 1px solid var(--border-soft);
  padding: 4px 0;
}

/* ── Connecting placeholder ───────────────────────────────────────────────────── */
.rp-connecting {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 14px;
  font-size: 12px;
  color: var(--muted);
}
.rp-connecting-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent, #4a90e2);
  animation: rp-pulse 1.4s ease-in-out infinite;
  flex-shrink: 0;
}
@keyframes rp-pulse {
  0%, 100% { opacity: 0.35; transform: scale(0.8); }
  50%       { opacity: 1;    transform: scale(1.15); }
}

/* ── Waiting placeholder (after agent_started, before steps) ─────────────────── */
.rp-waiting {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 14px;
  font-size: 12px;
  color: var(--muted);
}
.rp-waiting-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--status-up, #16a34a);
  animation: rp-pulse 1.4s ease-in-out infinite;
  flex-shrink: 0;
}

/* ── Step rows ────────────────────────────────────────────────────────────────── */
.rp-step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 5px 14px;
  transition: background 0.1s;
}
.rp-step:hover { background: var(--surface3, rgba(0,0,0,0.03)); }

/* Per-step spinner (running) */
.rp-step-spinner {
  width: 11px;
  height: 11px;
  border: 2px solid var(--border-soft);
  border-top-color: var(--accent, #4a90e2);
  border-radius: 50%;
  animation: rp-spin 0.8s linear infinite;
  flex-shrink: 0;
  margin-top: 2px;
}

.rp-step-icon {
  font-size: 11px;
  width: 14px;
  text-align: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.rp-step--success .rp-step-icon,
.rp-step--done    .rp-step-icon { color: var(--status-up, #16a34a); }
.rp-step--error   .rp-step-icon,
.rp-step--failed  .rp-step-icon { color: var(--danger, #dc2626); }
.rp-step--partial .rp-step-icon,
.rp-step--warning .rp-step-icon { color: var(--warning, #d97706); }
.rp-step--skipped .rp-step-icon { color: var(--muted); opacity: 0.5; }

.rp-step-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.rp-step-title {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary, var(--text));
  line-height: 1.4;
}

.rp-step-summary {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.4;
  word-break: break-word;
  cursor: pointer;
}
.rp-step-summary--clamped {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Risk flag badges */
.rp-risk-flags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 3px;
}
.rp-risk-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--status-warn-bg, rgba(234,179,8,0.12));
  color: var(--status-warn, #b45309);
  border: 1px solid var(--status-warn-ring, rgba(234,179,8,0.25));
}

/* ── Thinking panel ───────────────────────────────────────────────────────────── */
.rp-thinking {
  margin: 5px 10px;
  border: 1px solid var(--border-soft);
  border-radius: 6px;
  font-size: 12px;
  overflow: hidden;
}
.rp-thinking-label {
  padding: 5px 10px;
  cursor: pointer;
  user-select: none;
  color: var(--muted);
  font-weight: 600;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 4px;
}
.rp-thinking-label::-webkit-details-marker { display: none; }
.rp-thinking-body {
  padding: 6px 10px 8px;
  color: var(--muted);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  border-top: 1px solid var(--border-soft);
  max-height: 200px;
  overflow-y: auto;
}

/* ── Expand / collapse transition ─────────────────────────────────────────────── */
.rp-expand-enter-active,
.rp-expand-leave-active {
  transition: max-height 0.22s ease, opacity 0.18s ease;
  overflow: hidden;
}
.rp-expand-enter-from,
.rp-expand-leave-to   { max-height: 0;    opacity: 0; }
.rp-expand-enter-to,
.rp-expand-leave-from { max-height: 900px; opacity: 1; }

/* ── Mobile (≤ 640 px) ────────────────────────────────────────────────────────── */
@media (max-width: 640px) {
  .rp-panel   { border-radius: 8px; }
  .rp-header  { padding: 8px 10px; min-height: 42px; }
  .rp-step    { padding: 5px 10px; }
  .rp-connecting { padding: 9px 10px; }
  .rp-step-summary--clamped { -webkit-line-clamp: 3; }
}
</style>
