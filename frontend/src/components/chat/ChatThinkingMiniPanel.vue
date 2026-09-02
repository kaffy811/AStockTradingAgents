<template>
  <!-- C29.3.1 / C31.5: Rich "深度思考" card — event-driven when thinkingEvents present -->
  <div v-if="shouldShow" class="think-mini">

    <!-- ── Status header ─────────────────────────────────────────────────────── -->
    <div
      class="think-mini-header"
      :class="{ 'think-mini-header--clickable': isDone }"
      @click="isDone && (isExpanded = !isExpanded)"
    >
      <span class="think-mini-icon" :class="`think-mini-icon--${terminalTone}`">
        <span v-if="!isDone" class="dot-spin"></span>
        <span v-else-if="isFulfilled" class="think-done-check">✓</span>
        <span v-else class="think-terminal-mark">{{ terminalMark }}</span>
      </span>
      <span class="think-mini-title">{{ isDone ? terminalTitle : thinkingTitle }}</span>
      <span v-if="isDone" class="think-mini-toggle" :class="{ rotated: isExpanded }">›</span>
    </div>

    <!-- ── Step list: streaming (progressive) or done + expanded ─────────────── -->
    <div v-if="!isDone || isExpanded" class="think-steps-list">
      <div
        v-for="(step, idx) in visibleSteps"
        :key="step.phase || step.title"
        class="think-step"
        :class="{
          'think-step--active':  !isDone && idx === visibleSteps.length - 1,
          'think-step--running': step.status === 'running',
          'think-step--done':    isDone || idx < visibleSteps.length - 1 || step.status === 'completed',
          'think-step--failed':  step.status === 'failed',
        }"
      >
        <div class="think-step-indicator">
          <span v-if="step.status === 'running' || (!isDone && idx === visibleSteps.length - 1)" class="dot-spin-sm"></span>
          <span v-else-if="step.status === 'failed'" class="dot-fail">✗</span>
          <span v-else class="dot-check">✓</span>
        </div>
        <div class="think-step-body">
          <div class="think-step-title">
            {{ step.title }}
            <span v-if="step.agent" class="think-step-agent">· {{ step.agent }}</span>
          </div>
          <div v-if="step.content" class="think-step-content">{{ step.content }}</div>
        </div>
      </div>
    </div>

    <!-- ── C32: Raw reasoning chain drawer — always visible when content exists ── -->
    <!-- Placed OUTSIDE the step-list collapse so it persists after panel collapses -->
    <div v-if="hasRawChain" class="think-chain-drawer">
      <button
        class="think-chain-header"
        @click="isChainExpanded = !isChainExpanded"
      >
        <span class="think-chain-icon">
          <span v-if="!isDone" class="dot-spin-sm"></span>
          <span v-else class="dot-check">✓</span>
        </span>
        <span class="think-chain-label">深度思考</span>
        <span class="think-chain-chars">{{ thinkingContent.length }} 字</span>
        <span class="think-chain-toggle" :class="{ rotated: isChainExpanded }">›</span>
      </button>
      <div v-if="isChainExpanded" class="think-chain-body">
        <div class="think-chain-scroll">
          <p
            v-for="(para, i) in chainParagraphs"
            :key="i"
            class="think-chain-para"
          >{{ para }}</p>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from '../../utils/i18n.js'
import { researchFulfillmentView } from '../../utils/researchFulfillment.js'

const { t } = useI18n()

const props = defineProps({
  isStreaming:    { type: Boolean, default: false },
  status:         { type: String,  default: '' },
  fulfillment:    { type: String,  default: '' },
  // C31.5: new event-driven prop — prioritized over heuristic template
  thinkingEvents: { type: Array,   default: () => [] },
  // C28.x legacy props — used as fallback when thinkingEvents is empty
  thinkingItems:  { type: Array,   default: () => [] },
  reasoningSteps: { type: Array,   default: () => [] },
  toolTrace:      { type: Array,   default: () => [] },
  query:          { type: String,  default: '' },
  // C32: raw DeepSeek reasoning_content accumulated from ui_thinking_delta events
  thinkingContent: { type: String, default: '' },
})

const isExpanded    = ref(false)
// C32: raw chain drawer — open by default during streaming, closed when done
const isChainExpanded = ref(true)

// ── C31.5: Phase labels (canonical mapping) ───────────────────────────────────

const PHASE_LABELS = {
  problem_analysis:   '问题分析',
  intent_decision:    '意图识别',
  planning:           '自主规划',
  task_decomposition: '任务拆解',
  agent_dispatch:     'Agent 调度',
  agent_observation:  '数据观测',
  deep_reasoning:     '深度思考',
  risk_review:        '风险审查',
  synthesis:          '回答生成',
}

// ── C29.3.1 legacy: Noise filtering ──────────────────────────────────────────

const _EXCLUDE_SOURCES = new Set(['data_quality_review', 'deepseek_reasoning'])
const _EXCLUDE_TOOLS   = new Set([
  'general_financial_answer_skill',
  'report_explanation_skill',
  'financial_rag_search',
  'compute_data_quality',
])
const _DQ_KEYWORDS = ['数据质量', '数据完整', '数据有限', '数据不足', '数据部分完整', 'data_quality', 'DataQuality']

function _isDqContent(text) { return _DQ_KEYWORDS.some(kw => String(text ?? '').includes(kw)) }
function _isExcludedSource(item) {
  return _EXCLUDE_SOURCES.has(item.source) ||
         String(item.stage ?? '').includes('data_quality') ||
         _isDqContent(item.title) || _isDqContent(item.content)
}
function _isExcludedTool(tool) {
  const name = (tool.key ?? '').replace(/^[^:]+:/, '') || tool.name || ''
  return _EXCLUDE_TOOLS.has(name) || _isDqContent(tool.title) || _isDqContent(tool.summary)
}

// ── C29.3.1 legacy: Intent detection + 5-step templates ──────────────────────

function _detectIntent(query) {
  if (!query) return 'general'
  if (/分析.*保存|创建.*报告|综合分析.*保存|深度分析.*保存|保存.*报告/.test(query)) return 'p3_agent'
  if (/财报|年报|季报|营收|利润|营业额|每股|EPS|ROE|市盈率|PE/.test(query))        return 'financial_report'
  if (/热门|热股|涨停|龙头|板块热|行业热|市场热点/.test(query))                    return 'hot_stocks'
  if (/报告|解读|分析报告|历史报告|查看报告/.test(query))                          return 'report_explain'
  if (/新闻|公告|消息|最新.*消息/.test(query))                                     return 'news'
  if (/技术|MACD|RSI|K线|均线|支撑|压力|形态|布林/.test(query))                    return 'technical'
  if (/对比|比较|vs|versus/.test(query))                                           return 'compare'
  return 'general'
}

const _THINKING_TEMPLATES = {
  financial_report: [
    { title: '问题分析',     content: '我正在理解你的问题，判断这是财报分析类请求，需要检索官方财务数据和公告信息。' },
    { title: '关键数据检索', content: '我会优先检索官方财报、行情数据、相关新闻和知识库资料，确保数据来源可靠。' },
    { title: '深度思考',     content: '我会比较已获取数据和缺失数据，避免编造未验证的财务指标或业绩预测。' },
    { title: '风险审查',     content: '我会检查是否存在直接买卖建议、无来源估值数字或过度推断。' },
    { title: '回答生成',     content: '我会基于已验证信息生成最终回答，并说明无法确认的部分。' },
  ],
  hot_stocks: [
    { title: '问题分析',     content: '我正在理解你的问题，判断这是市场热点类请求，需要检索行业热度和相关股票表现。' },
    { title: '关键数据检索', content: '我会检索市场热点、行业线索、相关股票的涨幅和成交量数据。' },
    { title: '深度思考',     content: '我会区分短期市场热度和真实产业链关联，避免把热门股直接等同于主题股。' },
    { title: '风险审查',     content: '我会检查是否存在直接买卖建议、无来源估值数字或过度推断。' },
    { title: '回答生成',     content: '我会基于已验证信息生成最终回答，并说明无法确认的部分。' },
  ],
  report_explain: [
    { title: '问题分析',     content: '我正在理解你的问题，判断这是历史报告解读请求，需要查找对应的报告内容。' },
    { title: '关键数据检索', content: '我会查找历史报告并读取报告详情，提取其中的关键结论和数据。' },
    { title: '深度思考',     content: '我会把报告里的技术面、基本面和风险提示转成更容易理解的语言。' },
    { title: '风险审查',     content: '我会检查是否存在直接买卖建议、无来源估值数字或过度推断。' },
    { title: '回答生成',     content: '我会基于已验证信息生成最终回答，并说明无法确认的部分。' },
  ],
  p3_agent: [
    { title: '问题分析',     content: '我正在理解你的问题，判断这是分析任务创建请求，需要提交后台报告生成任务。' },
    { title: '关键数据检索', content: '我会创建分析任务，配置分析范围和参数，确认目标股票信息。' },
    { title: '深度思考',     content: '我会根据任务状态判断报告是否真正生成完成，不会在无报告时显示成功。' },
    { title: '风险审查',     content: '我会验证任务提交状态，确保不误报已完成的任务。' },
    { title: '回答生成',     content: '我会持续跟踪报告生成状态，完成后提供直接查看链接。' },
  ],
  news: [
    { title: '问题分析',     content: '我正在理解你的问题，判断这是新闻资讯类请求，需要检索最新市场新闻。' },
    { title: '关键数据检索', content: '我会检索最新新闻、公告和市场事件，按时间和相关性排序。' },
    { title: '深度思考',     content: '我会区分市场传言和官方公告，避免把未经证实的消息作为事实引用。' },
    { title: '风险审查',     content: '我会检查是否存在直接买卖建议、无来源估值数字或过度推断。' },
    { title: '回答生成',     content: '我会基于已验证信息生成最终回答，并说明无法确认的部分。' },
  ],
  technical: [
    { title: '问题分析',     content: '我正在理解你的问题，判断这是技术分析类请求，需要获取行情和技术指标数据。' },
    { title: '关键数据检索', content: '我会获取行情数据、计算技术指标，包括均线、MACD、RSI 等关键信号。' },
    { title: '深度思考',     content: '我会综合技术信号判断当前趋势，但不会给出确定性的涨跌结论。' },
    { title: '风险审查',     content: '我会检查是否存在直接买卖建议、无来源估值数字或过度推断。' },
    { title: '回答生成',     content: '我会基于已验证信息生成最终回答，并说明无法确认的部分。' },
  ],
  compare: [
    { title: '问题分析',     content: '我正在理解你的问题，判断这是股票对比类请求，需要获取多支股票的数据。' },
    { title: '关键数据检索', content: '我会获取各股票的行情、财务数据进行横向对比，确保数据口径一致。' },
    { title: '深度思考',     content: '我会分析各股票的异同，避免仅用涨跌幅做简单排名。' },
    { title: '风险审查',     content: '我会检查是否存在直接买卖建议、无来源估值数字或过度推断。' },
    { title: '回答生成',     content: '我会基于已验证信息生成最终回答，并说明无法确认的部分。' },
  ],
  general: [
    { title: '问题分析',     content: '我正在理解你的问题，判断需要哪类信息来提供准确回答。' },
    { title: '关键数据检索', content: '我会检索相关数据，优先使用官方来源和已验证的市场信息。' },
    { title: '深度思考',     content: '我会综合已获取的信息，区分已验证的事实和需要进一步确认的内容。' },
    { title: '风险审查',     content: '我会检查是否存在直接买卖建议、无来源估值数字或过度推断。' },
    { title: '回答生成',     content: '我会基于已验证信息生成最终回答，并说明无法确认的部分。' },
  ],
}

// ── C31.5: Event-driven steps (from thinkingEvents) ──────────────────────────

/**
 * Filter thinkingEvents: remove empty-content events and internal noise.
 * Never show: raw tool args, internal skill names, data quality items.
 */
const filteredThinkingEvents = computed(() => {
  return (props.thinkingEvents ?? []).filter(ev => {
    if (!ev || !ev.phase) return false
    if (!ev.content && !ev.title) return false
    // Don't show intent_decision phase to users (too technical)
    if (ev.phase === 'intent_decision') return false
    // Skip internal-only phases with no content
    if (!ev.content) return false
    const text = `${ev.title ?? ''} ${ev.content ?? ''} ${ev.agent ?? ''}`
    if (/ReportChatCopilotAgent|MultiCompanyFinancialComparisonAgent|report_explanation_skill|report_comparison_skill/.test(text)) return false
    return true
  }).map(ev => ({
    ...ev,
    agent: '',
    content: sanitizeTraceContent(ev.content),
  }))
})

function sanitizeTraceContent(text) {
  return String(text ?? '')
    .replace(/ReportChatCopilotAgent|MultiCompanyFinancialComparisonAgent/g, '财报分析流程')
    .replace(/report_explanation_skill|report_comparison_skill/g, '财报分析流程')
    .replace(/Agent 调度/g, '执行过程')
}

/** True when we have backend-supplied thinking events */
const hasThinkingEvents = computed(() => filteredThinkingEvents.value.length > 0)

// ── C29.3.1 legacy: fallback template system ──────────────────────────────────

const isDone = computed(() =>
  props.status === 'done' || (!props.isStreaming && props.status !== 'connecting' && props.status !== 'streaming')
)

const fulfillmentView = computed(() => researchFulfillmentView(props.fulfillment))
const isFulfilled = computed(() => !fulfillmentView.value || fulfillmentView.value.completed)
const terminalTitle = computed(() => fulfillmentView.value?.title ?? t('chat_analysis_done'))
const terminalTone = computed(() => fulfillmentView.value?.tone ?? 'success')
const terminalMark = computed(() => props.fulfillment === 'failed' ? '!' : '–')

const shouldShow = computed(() => props.isStreaming || isDone.value)

/** 5-step template for the detected intent (legacy fallback) */
const thinkingSteps = computed(() => {
  const intent = _detectIntent(props.query)
  return _THINKING_TEMPLATES[intent] ?? _THINKING_TEMPLATES.general
})

/** Count non-noise real events for step progression (legacy) */
const _filteredEventCount = computed(() => {
  const fromThinking = (props.thinkingItems ?? []).filter(item => !_isExcludedSource(item))
  const fromTools    = (props.toolTrace    ?? []).filter(tool => !_isExcludedTool(tool))
  return fromThinking.length + fromTools.length
})

/** Step index for legacy heuristic */
const currentStepIdx = computed(() => {
  if (isDone.value) return thinkingSteps.value.length - 1
  const n = _filteredEventCount.value
  if (n === 0) return 0
  if (n <= 2)  return 1
  if (n <= 5)  return 2
  if (n <= 7)  return 3
  return 4
})

// ── C31.5: Unified visibleSteps ───────────────────────────────────────────────

/**
 * Primary: use backend thinking_event phases when available.
 * Fallback: use the legacy count-heuristic + intent template.
 */
const visibleSteps = computed(() => {
  if (hasThinkingEvents.value) {
    // C31.5: Event-driven mode
    // During streaming: show all received events (they arrive progressively)
    // When done: show all (toggle hides via v-if on parent)
    return filteredThinkingEvents.value.map(ev => ({
      phase:   ev.phase,
      title:   PHASE_LABELS[ev.phase] || ev.title || ev.phase,
      content: ev.content,
      agent:   '',
      status:  ev.status || 'completed',
    }))
  }
  // Fallback: legacy template sliced to current step
  return thinkingSteps.value.slice(0, isDone.value ? undefined : currentStepIdx.value + 1)
})

// ── C32: Raw reasoning chain ──────────────────────────────────────────────────

/** True when we have actual DeepSeek reasoning_content to display */
const hasRawChain = computed(() => props.thinkingContent.trim().length > 0)

/** Split raw thinking into display paragraphs (skip blank lines) */
const chainParagraphs = computed(() => {
  return props.thinkingContent
    .split(/\n{2,}/)
    .map(p => p.replace(/\n/g, ' ').trim())
    .filter(p => p.length > 0)
})

// Auto-collapse the chain drawer when streaming finishes
watch(isDone, (done) => {
  if (done) isChainExpanded.value = false
})

/** Header title during streaming */
const thinkingTitle = computed(() => {
  if (hasThinkingEvents.value) {
    const last = filteredThinkingEvents.value[filteredThinkingEvents.value.length - 1]
    if (last) {
      const label = PHASE_LABELS[last.phase] || last.title || ''
      return label ? `正在 · ${label}` : t('chat_analyzing')
    }
    return t('chat_analyzing')
  }
  // Legacy path
  const step = thinkingSteps.value[currentStepIdx.value]
  return step ? `正在 · ${step.title}` : t('chat_analyzing')
})
</script>

<style scoped>
/* ── Container ─────────────────────────────────────────────────────────────── */
.think-mini {
  margin-bottom: 10px;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: var(--surface2, rgba(0,0,0,0.02));
  overflow: hidden;
  font-size: 13px;
}

/* ── Header ────────────────────────────────────────────────────────────────── */
.think-mini-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  user-select: none;
}
.think-mini-header--clickable {
  cursor: pointer;
  transition: background 0.12s;
}
.think-mini-header--clickable:hover {
  background: var(--surface-hover, rgba(0,0,0,0.04));
}

.think-mini-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.think-done-check {
  color: var(--up-color, #16a34a);
  font-weight: 700;
  font-size: 12px;
}

.think-mini-title {
  flex: 1;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.think-mini-toggle {
  color: var(--muted);
  font-size: 14px;
  transition: transform 0.2s ease;
  display: inline-block;
}
.think-mini-toggle.rotated { transform: rotate(90deg); }

/* ── Step list ─────────────────────────────────────────────────────────────── */
.think-steps-list {
  border-top: 1px solid var(--border-soft);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.think-step {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.think-step-indicator {
  width: 16px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
}

.dot-check {
  color: var(--up-color, #16a34a);
  font-weight: 700;
  font-size: 11px;
  line-height: 1;
}
.dot-fail {
  color: var(--down-color, #dc2626);
  font-weight: 700;
  font-size: 11px;
  line-height: 1;
}

.think-step-body { flex: 1; min-width: 0; }

.think-step-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.4;
  margin-bottom: 2px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.think-step-agent {
  font-size: 11px;
  font-weight: 400;
  color: var(--muted);
}
.think-step-content {
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
}

/* Active step: accent color + spinner */
.think-step--active .think-step-title,
.think-step--running .think-step-title  { color: var(--accent); }

/* Done / past steps: muted */
.think-step--done .think-step-title   { color: var(--muted); font-weight: 500; }
.think-step--done .think-step-content { opacity: 0.7; }

/* Failed step */
.think-step--failed .think-step-title { color: var(--down-color, #dc2626); }

/* ── C32: Raw reasoning chain drawer ──────────────────────────────────────── */
/* Drawer sits directly inside .think-mini (outside the step-list collapse block) */
.think-chain-drawer {
  border-top: 1px dashed var(--border-soft);
  padding: 6px 12px 10px;
}

.think-chain-header {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  background: none;
  border: none;
  padding: 4px 0;
  cursor: pointer;
  text-align: left;
  color: var(--text);
}
.think-chain-header:hover { opacity: 0.8; }

.think-chain-icon {
  width: 14px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.think-chain-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  flex: 1;
}

.think-chain-chars {
  font-size: 11px;
  color: var(--muted);
  opacity: 0.7;
}

.think-chain-toggle {
  font-size: 12px;
  color: var(--muted);
  transition: transform 0.2s ease;
  display: inline-block;
}
.think-chain-toggle.rotated { transform: rotate(90deg); }

.think-chain-body {
  margin-top: 6px;
}

.think-chain-scroll {
  max-height: 240px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
  padding-right: 4px;
}

.think-chain-para {
  font-size: 11.5px;
  line-height: 1.65;
  color: var(--muted);
  margin: 0 0 8px;
  word-break: break-word;
}
.think-chain-para:last-child { margin-bottom: 0; }

/* ── Spinners ──────────────────────────────────────────────────────────────── */
.dot-spin {
  width: 12px;
  height: 12px;
  border: 2px solid var(--border-soft);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: think-spin 0.8s linear infinite;
  display: inline-block;
}
.dot-spin-sm {
  width: 10px;
  height: 10px;
  border: 1.5px solid var(--border-soft);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: think-spin 0.8s linear infinite;
  display: inline-block;
}
@keyframes think-spin { to { transform: rotate(360deg); } }
</style>
