<template>
  <div class="card app-panel">
    <!-- Header -->
    <div class="app-header">
      <span class="app-title">{{ panelTitle }}</span>
      <span v-if="displayName" class="app-subject">{{ displayName }}</span>
    </div>

    <!-- Progress bar -->
    <div class="app-bar-track">
      <div class="app-bar-fill" :style="{ width: effectiveProgress + '%' }"></div>
    </div>

    <!-- Realtime mode: agent status grid -->
    <template v-if="mode === 'realtime'">
      <ul class="app-agents">
        <li
          v-for="agent in AGENT_LIST"
          :key="agent.key"
          class="app-agent"
          :class="agentClass(agent.key)"
        >
          <span class="app-agent-icon">
            <template v-if="agentStatus(agent.key) === 'success'">✓</template>
            <template v-else-if="agentStatus(agent.key) === 'failed'">✗</template>
            <template v-else-if="agentStatus(agent.key) === 'running'">
              <span class="spinner app-spinner"></span>
            </template>
            <template v-else-if="agentStatus(agent.key) === 'skipped'">—</template>
            <template v-else>·</template>
          </span>
          <span class="app-agent-label">{{ agent.label }}</span>
          <span v-if="agentStatus(agent.key) === 'failed'" class="app-agent-err">失败</span>
        </li>
      </ul>

      <div class="app-helper">
        <span class="app-current-step">{{ latestEventLabel }}</span>
        <span class="app-elapsed">已用时：{{ elapsedSeconds }} 秒</span>
      </div>
    </template>

    <!-- Time mode (fallback): step list -->
    <template v-else>
      <ol class="app-steps">
        <li
          v-for="(step, i) in STEPS"
          :key="step.label"
          class="app-step"
          :class="stepClass(i)"
        >
          <span class="app-step-icon">
            <template v-if="i < currentStepIndex">✓</template>
            <template v-else-if="i === currentStepIndex">
              <span class="spinner app-spinner"></span>
            </template>
            <template v-else>·</template>
          </span>
          <span class="app-step-label">{{ step.label }}</span>
        </li>
      </ol>

      <div class="app-helper">
        <span class="app-current-step">当前正在：{{ STEPS[currentStepIndex]?.label }}</span>
        <span class="app-elapsed">已用时：{{ elapsedSeconds }} 秒</span>
      </div>
    </template>

    <p v-if="showSseSlowHint" class="app-slow-hint">
      15 秒内未收到进度更新，可能是网络较慢或服务繁忙，系统仍在后台处理中。
    </p>
    <p v-else-if="elapsedSeconds >= 40" class="app-slow-hint">
      大模型正在整合多维度信息，可能需要较长时间，请保持页面打开。
    </p>
    <p v-else class="app-hint">
      不同数据源响应速度不同，请保持页面打开。
    </p>

    <!-- Cancel -->
    <div class="app-cancel-row">
      <button class="btn btn-secondary btn-sm" @click="$emit('cancel')">
        {{ mode === 'realtime' ? '停止等待' : '取消分析' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted, onMounted } from 'vue'

const props = defineProps({
  market:        { type: String,  default: 'CN' },
  symbol:        { type: String,  default: '' },
  stockName:     { type: String,  default: '' },
  startedAt:     { type: Number,  default: null },
  loading:       { type: Boolean, default: true },
  analysisScope: { type: String,  default: 'comprehensive' },
  // M25-a realtime mode props
  mode:          { type: String,  default: 'time' },   // 'time' | 'realtime'
  progress:      { type: Number,  default: null },      // 0-100 from SSE
  agentStatuses: { type: Object,  default: () => ({}) },// { name: 'pending'|'running'|'success'|'failed'|'skipped' }
  latestEvent:   { type: Object,  default: null },      // last SSE event object
})

defineEmits(['cancel'])

// ── Agent definitions for realtime grid ───────────────────────────────────────
const AGENT_LIST = [
  { key: 'technical',       label: '技术面分析' },
  { key: 'fundamental',     label: '基本面分析' },
  { key: 'peer_comparison', label: '同行对比' },
  { key: 'news',            label: '新闻面分析' },
  { key: 'synthesis',       label: '综合报告生成' },
]

// Agents in scope per analysis_scope
const SCOPE_AGENTS_MAP = {
  comprehensive:         ['technical', 'fundamental', 'peer_comparison', 'news'],
  technical_only:        ['technical'],
  fundamental_only:      ['fundamental'],
  peer_only:             ['peer_comparison'],
  news_only:             ['news'],
  technical_fundamental: ['technical', 'fundamental'],
}

function agentStatus(key) {
  const s = props.agentStatuses?.[key]
  if (s) return s
  // Derive 'skipped' from scope when no status event received yet
  if (props.mode === 'realtime' && props.analysisScope) {
    const inScope = (SCOPE_AGENTS_MAP[props.analysisScope] || SCOPE_AGENTS_MAP.comprehensive).includes(key)
    if (!inScope && key !== 'synthesis') return 'skipped'
  }
  return 'pending'
}

function agentClass(key) {
  const s = agentStatus(key)
  return {
    'app-agent--pending': s === 'pending',
    'app-agent--running': s === 'running',
    'app-agent--success': s === 'success',
    'app-agent--failed':  s === 'failed',
    'app-agent--skipped': s === 'skipped',
  }
}

// ── Steps definition by scope (time mode) ────────────────────────────────────
const STEPS_BY_SCOPE = {
  comprehensive: [
    { label: '确认分析对象',          minSec: 0  },
    { label: '获取行情与技术指标',     minSec: 3  },
    { label: '获取基本面数据',         minSec: 8  },
    { label: '匹配同行样本',           minSec: 15 },
    { label: '检索近期新闻',           minSec: 25 },
    { label: '生成综合报告',           minSec: 40 },
  ],
  technical_only: [
    { label: '确认分析对象',          minSec: 0  },
    { label: '获取行情与技术指标',     minSec: 3  },
    { label: '生成技术面报告',         minSec: 8  },
  ],
  fundamental_only: [
    { label: '确认分析对象',          minSec: 0  },
    { label: '获取基本面数据',         minSec: 3  },
    { label: '生成基本面报告',         minSec: 10 },
  ],
  peer_only: [
    { label: '确认分析对象',          minSec: 0  },
    { label: '匹配同行样本',           minSec: 3  },
    { label: '生成同行对比报告',       minSec: 10 },
  ],
  news_only: [
    { label: '确认分析对象',          minSec: 0  },
    { label: '检索近期新闻',           minSec: 3  },
    { label: '生成新闻面报告',         minSec: 8  },
  ],
  technical_fundamental: [
    { label: '确认分析对象',          minSec: 0  },
    { label: '获取行情与技术指标',     minSec: 3  },
    { label: '获取基本面数据',         minSec: 8  },
    { label: '生成技术面与基本面报告', minSec: 20 },
  ],
}

const STEPS = computed(
  () => STEPS_BY_SCOPE[props.analysisScope] || STEPS_BY_SCOPE.comprehensive
)

// ── Elapsed timer ──────────────────────────────────────────────────────────────
const elapsedSeconds    = ref(0)
const secondsSinceEvent = ref(0)  // seconds since last SSE event (realtime mode)
let timerId = null
let _lastEventAt = Date.now()

function startTimer() {
  stopTimer()
  const base = props.startedAt ?? Date.now()
  _lastEventAt = Date.now()
  elapsedSeconds.value    = Math.floor((Date.now() - base) / 1000)
  secondsSinceEvent.value = 0
  timerId = setInterval(() => {
    elapsedSeconds.value    = Math.floor((Date.now() - base) / 1000)
    secondsSinceEvent.value = Math.floor((Date.now() - _lastEventAt) / 1000)
  }, 1000)
}

function stopTimer() {
  if (timerId !== null) {
    clearInterval(timerId)
    timerId = null
  }
}

watch(
  () => props.loading,
  (val) => { val ? startTimer() : stopTimer() },
  { immediate: true },
)

watch(
  () => props.startedAt,
  () => { if (props.loading) startTimer() },
)

// Reset event timer whenever a new SSE event arrives
watch(
  () => props.latestEvent,
  () => { _lastEventAt = Date.now(); secondsSinceEvent.value = 0 },
)

onUnmounted(stopTimer)

// Show slow-connection hint when no SSE events received for 15s in realtime mode
const showSseSlowHint = computed(
  () => props.mode === 'realtime' && secondsSinceEvent.value >= 15
)

// ── Current step (time mode) ───────────────────────────────────────────────────
const currentStepIndex = computed(() => {
  const s     = elapsedSeconds.value
  const steps = STEPS.value
  let idx = 0
  for (let i = 0; i < steps.length; i++) {
    if (s >= steps[i].minSec) idx = i
  }
  return idx
})

// ── Progress ───────────────────────────────────────────────────────────────────
const timeProgress = computed(() => {
  const total = STEPS.value.length
  const pct = 5 + ((currentStepIndex.value / (total - 1)) * 90)
  return Math.min(pct, 95)
})

const effectiveProgress = computed(() => {
  if (props.mode === 'realtime' && props.progress !== null) {
    return Math.min(props.progress, 99)  // cap at 99 until report_ready
  }
  return timeProgress.value
})

// ── Panel title ────────────────────────────────────────────────────────────────
const SCOPE_PANEL_TITLE = {
  comprehensive:         '正在生成综合分析报告',
  technical_only:        '正在生成技术面分析报告',
  fundamental_only:      '正在生成基本面分析报告',
  peer_only:             '正在生成同行对比报告',
  news_only:             '正在生成新闻面分析报告',
  technical_fundamental: '正在生成技术面与基本面报告',
}
const panelTitle = computed(
  () => SCOPE_PANEL_TITLE[props.analysisScope] || '正在生成分析报告'
)

// ── Display name ───────────────────────────────────────────────────────────────
const displayName = computed(() => {
  const sym = props.symbol?.trim()
  if (!sym) return ''
  if (props.stockName) return `${props.stockName}（${props.market}/${sym}）`
  return `${props.market}/${sym}`
})

// ── Step CSS class (time mode) ────────────────────────────────────────────────
function stepClass(i) {
  if (i < currentStepIndex.value) return 'app-step--done'
  if (i === currentStepIndex.value) return 'app-step--active'
  return 'app-step--pending'
}

// ── Latest event label (realtime mode) ───────────────────────────────────────
const EVENT_LABELS = {
  analysis_started:    '任务已启动',
  identity_resolved:   '股票名称已解析',
  agent_started:       '正在运行分析模块',
  agent_completed:     '分析模块完成',
  agent_failed:        '分析模块异常（已降级）',
  synthesis_started:   '正在调用大模型整合报告',
  synthesis_completed: '报告整合完成',
  report_ready:        '报告已就绪',
  analysis_failed:     '分析出错',
  cancelled:           '已取消',
}

const latestEventLabel = computed(() => {
  if (!props.latestEvent) return '正在连接分析服务...'
  const evt = props.latestEvent
  // agent events: show agent name
  if (evt.event === 'agent_started' && evt.agent) {
    const agentLabel = AGENT_LIST.find(a => a.key === evt.agent)?.label || evt.agent
    return `正在运行：${agentLabel}`
  }
  if (evt.event === 'agent_completed' && evt.agent) {
    const agentLabel = AGENT_LIST.find(a => a.key === evt.agent)?.label || evt.agent
    return `${agentLabel} 完成`
  }
  return EVENT_LABELS[evt.event] || evt.event || '处理中...'
})
</script>

<style scoped>
.app-panel {
  padding: 20px 20px 16px;
}

/* ── Header ── */
.app-header {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.app-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  white-space: nowrap;
}

.app-subject {
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
  font-family: monospace;
  word-break: break-all;
}

/* ── Progress bar ── */
.app-bar-track {
  width: 100%;
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 18px;
}

.app-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--accent2, var(--accent)));
  border-radius: 2px;
  transition: width 0.8s ease;
}

/* ── Realtime agent grid ── */
.app-agents {
  list-style: none;
  padding: 0;
  margin: 0 0 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.app-agent {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.app-agent-icon {
  width: 18px;
  flex-shrink: 0;
  text-align: center;
  font-size: 13px;
  line-height: 1;
}

.app-agent-err {
  font-size: 11px;
  color: var(--error, #e53935);
  margin-left: auto;
}

.app-agent--pending .app-agent-icon  { color: var(--border); }
.app-agent--pending .app-agent-label { color: var(--muted); opacity: 0.6; }
.app-agent--running .app-agent-icon  { color: var(--accent); }
.app-agent--running .app-agent-label { color: var(--text); font-weight: 600; }
.app-agent--success .app-agent-icon  { color: var(--success, #4caf50); }
.app-agent--success .app-agent-label { color: var(--muted); }
.app-agent--failed  .app-agent-icon  { color: var(--error, #e53935); }
.app-agent--failed  .app-agent-label { color: var(--muted); }
.app-agent--skipped .app-agent-icon  { color: var(--border); }
.app-agent--skipped .app-agent-label { color: var(--muted); opacity: 0.4; }

/* ── Time-mode steps ── */
.app-steps {
  list-style: none;
  padding: 0;
  margin: 0 0 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.app-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.app-step-icon {
  width: 18px;
  flex-shrink: 0;
  text-align: center;
  font-size: 13px;
  line-height: 1;
}

.app-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-width: 1.5px;
  vertical-align: middle;
}

.app-step--done .app-step-icon   { color: var(--success, #4caf50); }
.app-step--done .app-step-label  { color: var(--muted); }
.app-step--active .app-step-icon { color: var(--accent); }
.app-step--active .app-step-label{ color: var(--text); font-weight: 600; }
.app-step--pending .app-step-icon{ color: var(--border); }
.app-step--pending .app-step-label{ color: var(--muted); opacity: 0.6; }

/* ── Helper text ── */
.app-helper {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 6px;
}

.app-current-step { font-weight: 500; }

/* ── Hints ── */
.app-hint,
.app-slow-hint {
  font-size: 12px;
  color: var(--muted);
  margin: 0 0 14px;
  line-height: 1.5;
}

.app-slow-hint {
  color: var(--warn, #f5a623);
}

/* ── Cancel ── */
.app-cancel-row {
  display: flex;
  justify-content: flex-end;
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .app-panel { padding: 16px 14px 14px; }

  .app-header { gap: 4px; }
  .app-title  { font-size: 13px; }
  .app-subject{ font-size: 12px; }

  .app-steps, .app-agents { gap: 10px; }
  .app-step, .app-agent  { font-size: 12px; }
}
</style>
