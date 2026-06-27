<template>
  <!-- C29.1.1: Minimal thinking panel — visible in production (not debug) mode.
       Shows 3-5 high-level human-readable steps; no DQ cards, raw reasoning, or debug detail. -->
  <div v-if="shouldShow" class="think-mini" :class="{ 'think-mini--done': isDone, 'think-mini--expanded': isExpanded }">

    <!-- Done state: collapsible "已完成分析" badge -->
    <button v-if="isDone" class="think-mini-done" @click="isExpanded = !isExpanded">
      <span class="think-mini-done-icon">✓</span>
      <span class="think-mini-done-text">{{ t('chat_analysis_done') }}</span>
      <span class="think-mini-expand-arrow" :class="{ rotated: isExpanded }">›</span>
    </button>

    <!-- Step list: shown while streaming, or when expanded after done -->
    <div v-if="!isDone || isExpanded" class="think-mini-steps">
      <div
        v-for="(step, idx) in visibleSteps"
        :key="idx"
        class="think-mini-step"
        :class="{
          'think-mini-step--active': !isDone && idx === visibleSteps.length - 1,
          'think-mini-step--done':   isDone || idx < visibleSteps.length - 1,
        }"
      >
        <!-- Spinner on active step, check on done steps -->
        <span class="think-mini-dot">
          <span v-if="!isDone && idx === visibleSteps.length - 1" class="dot-spin"></span>
          <span v-else class="dot-done">✓</span>
        </span>
        <span class="think-mini-label">{{ step.label }}</span>
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
})

// Toggle expanded when done
const isExpanded = ref(false)

// ── Filtering ──────────────────────────────────────────────────────────────────

/** Items to exclude from the mini panel (internal/debug categories) */
const _EXCLUDE_SOURCES = new Set([
  'data_quality_review',
  'deepseek_reasoning',
])
/** Internal tool names that are not user-facing */
const _EXCLUDE_TOOLS = new Set([
  'general_financial_answer_skill',
  'report_explanation_skill',
  'financial_rag_search',  // show as "正在检索研究报告" via step instead
  'compute_data_quality',
])
/** Strings that indicate data-quality internal content */
const _DQ_KEYWORDS = ['数据质量', '数据完整', '数据有限', '数据不足', '数据部分完整', 'data_quality', 'DataQuality']

function _isDqContent(text) {
  return _DQ_KEYWORDS.some(kw => String(text ?? '').includes(kw))
}
function _isExcludedSource(item) {
  return _EXCLUDE_SOURCES.has(item.source) ||
         String(item.stage ?? '').includes('data_quality') ||
         _isDqContent(item.title) ||
         _isDqContent(item.content)
}
function _isExcludedTool(tool) {
  const name = (tool.key ?? '').replace(/^[^:]+:/, '') || tool.name || ''
  return _EXCLUDE_TOOLS.has(name) || _isDqContent(tool.title) || _isDqContent(tool.summary)
}

// ── Label mapping ──────────────────────────────────────────────────────────────

/** Tool name → human-readable label */
const _TOOL_LABELS = {
  get_stock_price:          '正在检索行情数据',
  get_stock_quote:          '正在检索行情数据',
  get_stock_market_data:    '正在检索行情数据',
  get_stock_news:           '正在检索新闻',
  search_realtime_news:     '正在检索实时新闻',
  get_industry_news:        '正在检索行业新闻',
  get_industry_hot:         '正在检索行业热度',
  get_industry_stocks:      '正在检索行业股票',
  financial_rag_search:     '正在检索研究报告',
  get_report_detail_tool:   '正在获取报告详情',
  get_financial_data:       '正在检索财务数据',
  get_fundamental_data:     '正在分析基本面数据',
  get_technical_indicators: '正在分析技术指标',
  universal_market_search:  '正在检索市场数据',
  get_watchlist_items:      '正在读取自选股',
  list_reports:             '正在读取历史报告',
}

/** Reasoning step title → human-readable label (fallback: use title directly if already Chinese) */
const _STEP_LABELS = {
  '理解问题':   '正在理解问题',
  '分析意图':   '正在理解问题',
  '规划分析':   '正在规划分析步骤',
  '选择分析方式': '正在选择分析方式',
  '路由':       '正在规划分析步骤',
  '基本面分析': '正在分析基本面',
  '技术面分析': '正在分析技术面',
  '新闻分析':   '正在分析新闻',
  '同行对比':   '正在进行同行对比',
  '综合分析':   '正在整理分析结果',
  '合成报告':   '正在整理分析结果',
  '风险评估':   '正在评估风险',
  '风险审核':   '正在评估风险',
  '生成回答':   '正在生成回答',
  '检索数据':   '正在检索数据',
  '数据检索':   '正在检索数据',
}

function _labelForStep(title) {
  if (!title) return null
  // Direct match
  if (_STEP_LABELS[title]) return _STEP_LABELS[title]
  // Fuzzy match: if title contains a key
  for (const [k, v] of Object.entries(_STEP_LABELS)) {
    if (title.includes(k)) return v
  }
  // If looks like snake_case internal name, skip it
  if (/^[a-z_]+$/.test(title)) return null
  // Otherwise use as-is (already Chinese)
  return title
}

function _labelForTool(tool) {
  const name = (tool.key ?? '').replace(/^[^:]+:/, '') || tool.name || ''
  if (_TOOL_LABELS[name]) return _TOOL_LABELS[name]
  // Fuzzy: tool.title if it's human-readable (contains Chinese)
  if (tool.title && /[\u4e00-\u9fff]/.test(tool.title) && !_isDqContent(tool.title)) return tool.title
  return null
}

// ── Computed steps ────────────────────────────────────────────────────────────

const isDone = computed(() =>
  props.status === 'done' || (!props.isStreaming && props.status !== 'connecting' && props.status !== 'streaming')
)

const shouldShow = computed(() => {
  // Show when streaming, or when done with steps to display
  if (props.isStreaming) return true
  if (isDone.value && visibleSteps.value.length > 0) return true
  return false
})

const visibleSteps = computed(() => {
  const seen   = new Set()
  const steps  = []

  const push = (label) => {
    if (!label || seen.has(label)) return
    seen.add(label)
    steps.push({ label })
  }

  // 1. thinkingItems (agent_step / tool_planning, non-DQ)
  for (const item of props.thinkingItems) {
    if (_isExcludedSource(item)) continue
    const label = _labelForStep(item.title)
    push(label)
  }

  // 2. reasoningSteps (non-DQ)
  for (const step of props.reasoningSteps) {
    if (_isDqContent(step.title) || _isDqContent(step.summary)) continue
    const label = _labelForStep(step.title)
    push(label)
  }

  // 3. toolTrace (non-excluded, mapped)
  for (const tool of props.toolTrace) {
    if (_isExcludedTool(tool)) continue
    const label = _labelForTool(tool)
    push(label)
  }

  // Default: always at least one step when streaming
  if (steps.length === 0) {
    steps.push({ label: t('chat_analyzing') })
  }

  // Cap at 5 most recent
  return steps.slice(-5)
})
</script>

<style scoped>
/* ── Container ─────────────────────────────────────────────────────────────── */
.think-mini {
  margin-bottom: 8px;
  font-size: 13px;
}

/* ── Done badge (collapsible) ──────────────────────────────────────────────── */
.think-mini-done {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: none;
  background: var(--status-up-bg, rgba(34, 197, 94, 0.08));
  border-radius: 20px;
  padding: 3px 10px 3px 8px;
  font-size: 12px;
  color: var(--success, #16a34a);
  cursor: pointer;
  margin-bottom: 2px;
  transition: background 0.15s;
}
.think-mini-done:hover {
  background: var(--status-up-bg, rgba(34, 197, 94, 0.14));
}
.think-mini-done-icon {
  font-size: 11px;
  font-weight: 700;
}
.think-mini-done-text {
  font-weight: 600;
}
.think-mini-expand-arrow {
  font-size: 12px;
  transition: transform 0.2s ease;
  display: inline-block;
}
.think-mini-expand-arrow.rotated {
  transform: rotate(90deg);
}

/* ── Step list ─────────────────────────────────────────────────────────────── */
.think-mini-steps {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 2px 0;
}

.think-mini-step {
  display: flex;
  align-items: center;
  gap: 7px;
  line-height: 1.4;
}

.think-mini-dot {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Animated spinner dot (active step) */
.dot-spin {
  width: 10px;
  height: 10px;
  border: 2px solid var(--border-soft);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: think-spin 0.8s linear infinite;
  display: inline-block;
}
@keyframes think-spin { to { transform: rotate(360deg); } }

/* Check mark (done steps) */
.dot-done {
  font-size: 10px;
  color: var(--success, #16a34a);
  font-weight: 700;
  line-height: 1;
}

/* Active step label — accent color + slightly bold */
.think-mini-step--active .think-mini-label {
  color: var(--text);
  font-weight: 500;
}

/* Done / past step labels — muted */
.think-mini-step--done .think-mini-label {
  color: var(--muted);
  font-size: 12px;
}

.think-mini-label {
  color: var(--muted);
  font-size: 13px;
}
</style>
