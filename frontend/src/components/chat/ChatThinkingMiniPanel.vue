<template>
  <!-- C29.3.1: Rich "深度思考" card — business-level 5-step thinking summary (not raw chain-of-thought) -->
  <div v-if="shouldShow" class="think-mini">

    <!-- ── Status header ─────────────────────────────────────────────────────── -->
    <div
      class="think-mini-header"
      :class="{ 'think-mini-header--clickable': isDone }"
      @click="isDone && (isExpanded = !isExpanded)"
    >
      <span class="think-mini-icon">
        <span v-if="!isDone" class="dot-spin"></span>
        <span v-else class="think-done-check">✓</span>
      </span>
      <span class="think-mini-title">{{ isDone ? t('chat_analysis_done') : thinkingTitle }}</span>
      <span v-if="isDone" class="think-mini-toggle" :class="{ rotated: isExpanded }">›</span>
    </div>

    <!-- ── Step list: streaming (progressive) or done + expanded ─────────────── -->
    <div v-if="!isDone || isExpanded" class="think-steps-list">
      <div
        v-for="(step, idx) in visibleSteps"
        :key="step.title"
        class="think-step"
        :class="{
          'think-step--active': !isDone && idx === visibleSteps.length - 1,
          'think-step--done':   isDone || idx < visibleSteps.length - 1,
        }"
      >
        <div class="think-step-indicator">
          <span v-if="!isDone && idx === visibleSteps.length - 1" class="dot-spin-sm"></span>
          <span v-else class="dot-check">✓</span>
        </div>
        <div class="think-step-body">
          <div class="think-step-title">{{ step.title }}</div>
          <div class="think-step-content">{{ step.content }}</div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from '../../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  isStreaming:    { type: Boolean, default: false },
  status:         { type: String,  default: '' },
  thinkingItems:  { type: Array,   default: () => [] },
  reasoningSteps: { type: Array,   default: () => [] },
  toolTrace:      { type: Array,   default: () => [] },
  query:          { type: String,  default: '' },
})

const isExpanded = ref(false)

// ── Noise filtering (same as C29.1/C29.2) ────────────────────────────────────

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

// ── C29.3.1: Intent detection ─────────────────────────────────────────────────

function _detectIntent(query) {
  if (!query) return 'general'
  // p3_agent checked before report_explain (both contain "报告")
  if (/分析.*保存|创建.*报告|综合分析.*保存|深度分析.*保存|保存.*报告/.test(query)) return 'p3_agent'
  if (/财报|年报|季报|营收|利润|营业额|每股|EPS|ROE|市盈率|PE/.test(query))        return 'financial_report'
  if (/热门|热股|涨停|龙头|板块热|行业热|市场热点/.test(query))                    return 'hot_stocks'
  if (/报告|解读|分析报告|历史报告|查看报告/.test(query))                          return 'report_explain'
  if (/新闻|公告|消息|最新.*消息/.test(query))                                     return 'news'
  if (/技术|MACD|RSI|K线|均线|支撑|压力|形态|布林/.test(query))                    return 'technical'
  if (/对比|比较|vs|versus/.test(query))                                           return 'compare'
  return 'general'
}

// ── C29.3.1: 5-step thinking templates per intent (business-level summaries) ─

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

// ── Computed ──────────────────────────────────────────────────────────────────

const isDone = computed(() =>
  props.status === 'done' || (!props.isStreaming && props.status !== 'connecting' && props.status !== 'streaming')
)

const shouldShow = computed(() => props.isStreaming || isDone.value)

/** 5-step template for the detected intent */
const thinkingSteps = computed(() => {
  const intent = _detectIntent(props.query)
  return _THINKING_TEMPLATES[intent] ?? _THINKING_TEMPLATES.general
})

/** Count non-noise real events to determine step progression */
const _filteredEventCount = computed(() => {
  const fromThinking = (props.thinkingItems ?? []).filter(item => !_isExcludedSource(item))
  const fromTools    = (props.toolTrace    ?? []).filter(tool => !_isExcludedTool(tool))
  return fromThinking.length + fromTools.length
})

/** Which step (0-4) we're currently on — based on event count heuristic */
const currentStepIdx = computed(() => {
  if (isDone.value) return thinkingSteps.value.length - 1
  const n = _filteredEventCount.value
  if (n === 0) return 0   // 问题分析
  if (n <= 2)  return 1   // 关键数据检索
  if (n <= 5)  return 2   // 深度思考
  if (n <= 7)  return 3   // 风险审查
  return 4                 // 回答生成
})

/** Steps to render: progressive reveal during streaming; all when done (toggle hides via v-if) */
const visibleSteps = computed(() =>
  thinkingSteps.value.slice(0, isDone.value ? undefined : currentStepIdx.value + 1)
)

/** Header title during streaming: "正在 · <current step title>" */
const thinkingTitle = computed(() => {
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

.think-step-body { flex: 1; min-width: 0; }

.think-step-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.4;
  margin-bottom: 2px;
}
.think-step-content {
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
}

/* Active step: accent color + spinner */
.think-step--active .think-step-title  { color: var(--accent); }

/* Done / past steps: muted */
.think-step--done .think-step-title   { color: var(--muted); font-weight: 500; }
.think-step--done .think-step-content { opacity: 0.7; }

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
