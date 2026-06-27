<template>
  <div v-if="visibleSources.length" class="csl">
    <div class="csl-header">
      <span class="csl-label">资料来源</span>
      <span class="csl-count">{{ sources.length }} 条</span>
    </div>

    <ul class="csl-list">
      <li
        v-for="(src, i) in visibleSources"
        :key="src.id || i"
        class="csl-item"
      >
        <!-- Title / link -->
        <a
          v-if="src.url"
          :href="src.url"
          target="_blank"
          rel="noopener noreferrer"
          class="csl-title csl-link"
        >{{ _safeTitle(src) }}</a>
        <span v-else class="csl-title">{{ _safeTitle(src) }}</span>

        <!-- Type badge -->
        <span class="csl-type-badge">{{ _typeLabel(src.source_type) }}</span>

        <!-- Confidence badge -->
        <span
          v-if="src.confidence"
          class="csl-conf"
          :class="`csl-conf--${src.confidence}`"
        >{{ _confLabel(src.confidence) }}</span>

        <!-- Low-confidence snippet (news title-only warning) -->
        <span
          v-if="src.confidence === 'low' && src.snippet"
          class="csl-warn"
        >{{ src.snippet }}</span>

        <!-- Meta: provider / date -->
        <span v-if="_meta(src)" class="csl-meta">{{ _meta(src) }}</span>
      </li>
    </ul>

    <!-- Expand / collapse -->
    <button
      v-if="sources.length > INITIAL_SHOW"
      class="csl-toggle"
      @click="expanded = !expanded"
    >
      {{ expanded ? '收起' : `展开全部 ${sources.length} 条` }}
    </button>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const INITIAL_SHOW = 3

const props = defineProps({
  sources: { type: Array, default: () => [] },
})

const expanded = ref(false)

const visibleSources = computed(() =>
  expanded.value ? props.sources : props.sources.slice(0, INITIAL_SHOW)
)

const _TYPE_LABELS = {
  official_report:  '官方报告',
  financial_report: '财报',
  rag:              '知识库',
  historical_report:'历史报告',
  market_quote:     '实时行情',
  news:             '新闻',
  tool_result:      '工具结果',
  manual:           '手动资料',
  document:         '文档',
  // C28.1: internal event names → friendly labels
  unknown:          '来源未标注',
}

// C28.1: friendly title overrides for internal/raw names that should never be shown as-is
const _TITLE_OVERRIDES = {
  'rag_retrieve':    '金融知识库资料',
  'rag_review':      '资料质量审查',
  'unknown':         '来源未标注',
  'tool_result':     '工具结果',
}

const _CONF_LABELS = {
  high:   '高可信',
  medium: '中可信',
  low:    '待核验',
}

function _typeLabel(type) {
  return _TYPE_LABELS[type] || '参考资料'
}

function _safeTitle(src) {
  // C28.1: never show raw snake_case names or internal event names
  const raw = src.title || ''
  if (!raw || _TITLE_OVERRIDES[raw] || /^[a-z][a-z0-9_]+$/.test(raw)) {
    // raw is empty or is a snake_case internal name
    return _TITLE_OVERRIDES[raw] || _typeLabel(src.source_type) || '参考资料'
  }
  return raw
}

function _confLabel(conf) {
  return _CONF_LABELS[conf] || conf
}

function _meta(src) {
  // support both old SourceRef (.source field) and new C27 (.provider field)
  return [(src.provider || src.source), src.published_at?.slice(0, 10)].filter(Boolean).join(' · ')
}
</script>

<style scoped>
.csl {
  margin-top: 10px;
  padding: 8px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 6px;
  background: var(--surface2);
  font-size: 12px;
}

.csl-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.csl-label {
  font-weight: 600;
  color: var(--muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.csl-count {
  font-size: 10px;
  color: var(--muted);
  margin-left: auto;
}

.csl-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.csl-item {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px;
  padding-bottom: 5px;
  border-bottom: 1px solid var(--border-soft);
  font-size: 12px;
}
.csl-item:last-child { border-bottom: none; }

.csl-title {
  font-weight: 500;
  color: var(--text);
  word-break: break-word;
}
.csl-link {
  color: var(--accent, #4a90e2);
  text-decoration: none;
}
.csl-link:hover { text-decoration: underline; }

.csl-type-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--surface3, rgba(0,0,0,0.06));
  color: var(--muted);
  white-space: nowrap;
}

.csl-conf {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
  white-space: nowrap;
}
.csl-conf--high   { background: rgba(34,197,94,0.12);  color: #15803d; }
.csl-conf--medium { background: rgba(245,158,11,0.12); color: #b45309; }
.csl-conf--low    { background: rgba(239,68,68,0.12);  color: #b91c1c; }

.csl-warn {
  font-size: 10px;
  color: #b91c1c;
  font-style: italic;
  width: 100%;
}

.csl-meta {
  font-size: 10px;
  color: var(--muted);
  width: 100%;
}

.csl-toggle {
  margin-top: 6px;
  background: none;
  border: none;
  color: var(--accent, #4a90e2);
  font-size: 11px;
  cursor: pointer;
  padding: 0;
  font-weight: 600;
}
.csl-toggle:hover { text-decoration: underline; }
</style>
