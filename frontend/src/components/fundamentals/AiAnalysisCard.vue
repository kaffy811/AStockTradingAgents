<template>
  <div class="aac-root">
    <!-- Header -->
    <div class="aac-header">
      <span class="aac-title">AI 财报分析</span>
      <span class="aac-badge">AI 生成</span>
      <span v-if="isStale" class="aac-stale-badge">数据来自缓存</span>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="aac-loading">
      <span class="spinner"></span>
      <span>AI 分析生成中，请稍候…</span>
    </div>

    <!-- Error / unavailable state -->
    <div v-else-if="isUnavailable" class="aac-placeholder">
      <span class="aac-placeholder-icon">🤖</span>
      <p class="aac-placeholder-text">{{ placeholderMsg }}</p>
      <p class="aac-disclaimer">{{ disclaimer }}</p>
    </div>

    <!-- Main content -->
    <template v-else-if="analysis">
      <!-- Summary & score -->
      <div class="aac-summary-row">
        <div class="aac-summary-text">{{ analysis.summary }}</div>
        <div v-if="analysis.overall_score != null" class="aac-score-badge" :class="scoreLevelClass">
          {{ analysis.overall_score }}
        </div>
      </div>

      <!-- Review status -->
      <AiReviewNotes
        :status="reviewStatus"
        :notes="reviewNotes"
      />

      <!-- Radar chart -->
      <div v-if="dimensions.length" class="aac-radar-section">
        <div class="aac-section-title">五维基本面评分</div>
        <AiScoreRadar :dimensions="dimensions" :height="240" />
        <!-- Dimension detail list -->
        <div class="aac-dim-list">
          <div v-for="dim in dimensions" :key="dim.name" class="aac-dim-row">
            <span class="aac-dim-name">{{ dim.name }}</span>
            <span :class="['aac-dim-level', dim.level]">{{ levelLabel(dim.level) }}</span>
            <div class="aac-dim-bar-bg">
              <div class="aac-dim-bar" :class="dim.level" :style="{ width: (dim.score ?? 0) + '%' }"></div>
            </div>
            <span class="aac-dim-score">{{ dim.score }}</span>
          </div>
        </div>
      </div>

      <!-- Highlights -->
      <div v-if="highlights.length" class="aac-section">
        <div class="aac-section-title">✨ 核心亮点</div>
        <div v-for="(h, i) in highlights" :key="i" class="aac-card aac-card--highlight">
          <div class="aac-card-title">{{ h.title }}</div>
          <div class="aac-card-detail">{{ h.detail }}</div>
          <div v-if="h.source_modules?.length" class="aac-sources">
            来源：{{ h.source_modules.join('、') }}
          </div>
        </div>
      </div>

      <!-- Risks -->
      <div v-if="risks.length" class="aac-section">
        <div class="aac-section-title">⚠️ 主要风险</div>
        <div v-for="(r, i) in risks" :key="i" :class="['aac-card', 'aac-card--risk', 'aac-card--' + (r.severity || 'low')]">
          <div class="aac-card-title">{{ r.title }}</div>
          <div class="aac-card-detail">{{ r.detail }}</div>
          <span :class="['aac-severity', r.severity]">{{ severityLabel(r.severity) }}</span>
        </div>
      </div>

      <!-- Watch items -->
      <div v-if="watchItems.length" class="aac-section">
        <div class="aac-section-title">👁 关注事项</div>
        <div v-for="(w, i) in watchItems" :key="i" class="aac-card aac-card--watch">
          <div class="aac-card-title">{{ w.title }}</div>
          <div class="aac-card-detail">{{ w.reason }}</div>
        </div>
      </div>

      <!-- Data limitations -->
      <div v-if="dataLimitations.length" class="aac-section">
        <div class="aac-section-title aac-section-title--muted">📋 数据说明</div>
        <ul class="aac-limitations">
          <li v-for="(l, i) in dataLimitations" :key="i">{{ l }}</li>
        </ul>
      </div>

      <!-- Source chunks (RAG chunk-level citations) -->
      <div v-if="effectiveSourceChunks.length" class="aac-section">
        <div class="aac-section-title">
          🔍 引用财报片段
          <span v-if="effectiveChunksMeta.fallback_used" class="aac-fallback-badge">关键词检索</span>
          <span v-if="effectiveChunksMeta.provider === 'mock'" class="aac-mock-badge">测试向量</span>
          <span v-else-if="effectiveChunksMeta.provider === 'local'" class="aac-local-badge">本地语义向量</span>
          <span v-if="reviewAudit && reviewAudit.source_chunks_checked" class="aac-verified-badge">✓ 引用已通过系统校验</span>
        </div>
        <div v-for="(chunk, i) in effectiveSourceChunks" :key="chunk.chunk_id || i" class="aac-chunk-item">
          <div class="aac-chunk-header">
            <span class="aac-report-type-badge" :class="reportTypeClass(chunk.report_type)">
              {{ reportTypeLabel(chunk.report_type) }}
            </span>
            <span class="aac-chunk-section">{{ chunk.section_title || chunk.title || '报告片段' }}</span>
            <span class="aac-chunk-period">{{ chunk.period || '' }}</span>
            <span v-if="chunk.score != null" class="aac-chunk-score" :title="`相关度 ${(chunk.score * 100).toFixed(0)}%`">
              {{ (chunk.score * 100).toFixed(0) }}%
            </span>
            <a
              v-if="chunk.pdf_url"
              :href="chunk.pdf_url"
              target="_blank"
              rel="noopener noreferrer"
              class="aac-report-link"
            >PDF</a>
          </div>
          <div v-if="chunk.content && expandedChunks[i]" class="aac-chunk-content">{{ chunk.content }}</div>
          <button
            v-if="chunk.content"
            class="aac-chunk-toggle"
            @click="toggleChunk(i)"
          >{{ expandedChunks[i] ? '收起' : '展开片段' }}</button>
        </div>
      </div>

      <!-- Source reports (cited PDFs, fallback when no chunks) -->
      <div v-else-if="sourceReports.length" class="aac-section">
        <div class="aac-section-title">📄 引用财报</div>
        <div v-for="r in sourceReports" :key="r.id || r.report_id" class="aac-report-item">
          <span class="aac-report-type-badge" :class="reportTypeClass(r.report_type)">
            {{ reportTypeLabel(r.report_type) }}
          </span>
          <span class="aac-report-title" :title="r.title">{{ r.title || '年度报告' }}</span>
          <span class="aac-report-period">{{ r.period_end || '' }}</span>
          <a
            v-if="r.pdf_url || r.id"
            :href="r.pdf_proxy_url || r.pdf_url || '#'"
            target="_blank"
            rel="noopener noreferrer"
            class="aac-report-link"
          >PDF</a>
        </div>
      </div>

      <!-- Disclaimer (always visible) -->
      <div class="aac-disclaimer">
        ⚠️ {{ disclaimer }}
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import AiScoreRadar from './AiScoreRadar.vue'
import AiReviewNotes from './AiReviewNotes.vue'

const props = defineProps({
  envelope:      { type: Object, default: null },   // DataEnvelope
  loading:       { type: Boolean, default: false },
  sourceReports: { type: Array,  default: () => [] }, // parsed report docs for citation
  sourceChunks:  { type: Array,  default: () => [] }, // RAG chunks for chunk-level citation
  chunksMeta:    { type: Object, default: () => ({}) }, // { fallback_used, provider, search_mode }
})

// Chunk expand/collapse state
const expandedChunks = ref({})
function toggleChunk(index) {
  expandedChunks.value = { ...expandedChunks.value, [index]: !expandedChunks.value[index] }
}

const analysis = computed(() => {
  return props.envelope?.data?.ai_analysis || null
})

// Derive sourceChunks from envelope when not passed as prop
const effectiveSourceChunks = computed(() => {
  if (props.sourceChunks.length > 0) return props.sourceChunks
  return analysis.value?.source_chunks || []
})

// Derive chunksMeta from envelope when not passed as prop
const effectiveChunksMeta = computed(() => {
  if (Object.keys(props.chunksMeta).length > 0) return props.chunksMeta
  const chunks = analysis.value?.source_chunks || []
  if (!chunks.length) return {}
  const first = chunks[0]
  return {
    provider: first.provider || 'mock',
    fallback_used: chunks.some(c => c.fallback_used),
    search_mode: chunks.some(c => c.fallback_used) ? 'keyword' : 'vector',
  }
})

const isStale = computed(() => props.envelope?.stale === true)
const isPartial = computed(() => props.envelope?.partial === true)

const isUnavailable = computed(() => {
  if (!analysis.value) return true
  if (analysis.value.overall_score === null && !analysis.value.summary) return true
  const rv = analysis.value?.review
  if (rv?.review_status === 'rejected') return true
  return false
})

// Phase 6N-8B: classify AI unavailable reason for precise user guidance.
const _AI_UNAVAIL_REASONS = {
  AUTH_REQUIRED:      '请登录后查看 AI 分析。',
  DATA_PACK_EMPTY:    '当前结构化财务数据不足，暂无法生成 AI 分析。请先完成财务数据刷新或接入年报 PDF。',
  REPORT_NOT_INGESTED:'尚未接入可检索的年报 PDF，请先在年报文件中查找/上传 PDF 并生成索引。',
  AI_KEY_MISSING:     'AI 服务未配置，暂不可用。',
  SOURCE_CHUNKS_EMPTY:'未检索到可引用的年报片段，暂无法生成基于年报的 AI 分析。',
}

function _classifyAiUnavailMsg(envelope) {
  if (!envelope) return 'AI 分析暂不可用，当前展示确定性财务数据模块。'
  const errCode = envelope.error_code || ''
  if (_AI_UNAVAIL_REASONS[errCode]) return _AI_UNAVAIL_REASONS[errCode]
  // Scan error messages for known patterns
  const errs = (envelope.errors || []).join(' ')
  if (/登录已过期|AUTH_REQUIRED|请重新登录/.test(errs)) return _AI_UNAVAIL_REASONS.AUTH_REQUIRED
  if (/AI.*key|API.*key|KEY_MISSING|未配置.*AI|AI.*未配置/i.test(errs)) return _AI_UNAVAIL_REASONS.AI_KEY_MISSING
  if (/source_chunks|SOURCE_CHUNKS_EMPTY|未检索到.*片段/i.test(errs)) return _AI_UNAVAIL_REASONS.SOURCE_CHUNKS_EMPTY
  if (/REPORT_NOT_INGESTED|未接入.*年报|年报.*未接入/i.test(errs)) return _AI_UNAVAIL_REASONS.REPORT_NOT_INGESTED
  if (/DATA_PACK_EMPTY|财务数据不足|数据不足/i.test(errs)) return _AI_UNAVAIL_REASONS.DATA_PACK_EMPTY
  if (errs.length) return errs.split('\n')[0].slice(0, 120)
  return 'AI 分析暂不可用，当前展示确定性财务数据模块。'
}

const placeholderMsg = computed(() => {
  if (!analysis.value) {
    return _classifyAiUnavailMsg(props.envelope)
  }
  return analysis.value?.summary || 'AI 分析暂不可用。'
})

const disclaimer = computed(() => {
  return analysis.value?.disclaimer ||
    '本内容由 AI 基于公开财务数据生成，仅供参考，不构成投资建议。'
})

const dimensions = computed(() => analysis.value?.dimensions || [])
const highlights  = computed(() => analysis.value?.highlights || [])
const risks       = computed(() => analysis.value?.risks || [])
const watchItems  = computed(() => analysis.value?.watch_items || [])
const dataLimitations = computed(() => analysis.value?.data_limitations || [])

const reviewStatus = computed(() => analysis.value?.review?.review_status || 'approved')
const reviewNotes  = computed(() => analysis.value?.review?.review_notes || [])

// review_audit: provided by Review Agent (Phase 6I)
const reviewAudit  = computed(() => analysis.value?.review_audit || null)

const overallScore = computed(() => analysis.value?.overall_score)
const scoreLevelClass = computed(() => {
  const s = overallScore.value
  if (s == null) return ''
  if (s >= 70) return 'score--strong'
  if (s >= 40) return 'score--neutral'
  return 'score--weak'
})

function levelLabel(level) {
  return { strong: '优秀', neutral: '中性', weak: '偏弱' }[level] || level
}
function severityLabel(sev) {
  return { low: '低风险', medium: '中风险', high: '高风险' }[sev] || sev
}
function reportTypeLabel(type) {
  return { annual: '年报', semi: '半年报', q1: '一季报', q3: '三季报' }[type] || type || '报告'
}
function reportTypeClass(type) {
  return { annual: 'rtype--annual', semi: 'rtype--semi', q1: 'rtype--q', q3: 'rtype--q' }[type] || ''
}
</script>

<style scoped>
.aac-root {
  background: white; border-radius: 14px;
  padding: 16px 18px;
  box-shadow: 0 1px 5px rgba(0,0,0,.07);
  display: flex; flex-direction: column; gap: 14px;
}
.aac-header { display: flex; align-items: center; gap: 8px; }
.aac-title { font-size: 14px; font-weight: 600; color: var(--text); }
.aac-badge {
  font-size: 10px; font-weight: 600; padding: 1px 7px; border-radius: 20px;
  background: linear-gradient(135deg, #667eea, #764ba2); color: white;
}
.aac-stale-badge {
  font-size: 10px; padding: 1px 6px; border-radius: 4px;
  background: #fff8e1; color: #856404; border: 1px solid #ffc107;
}

/* Loading */
.aac-loading { display: flex; align-items: center; gap: 10px; color: var(--muted); font-size: 13px; padding: 24px 0; }

/* Placeholder */
.aac-placeholder { text-align: center; padding: 24px 0; }
.aac-placeholder-icon { font-size: 32px; }
.aac-placeholder-text { color: var(--muted); font-size: 13px; margin: 8px 0 4px; }

/* Summary row */
.aac-summary-row { display: flex; align-items: flex-start; gap: 12px; }
.aac-summary-text { flex: 1; font-size: 14px; color: var(--text); line-height: 1.6; }
.aac-score-badge {
  flex-shrink: 0; width: 44px; height: 44px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; font-weight: 700; border: 2px solid;
}
.aac-score-badge.score--strong { color: #52c41a; border-color: #52c41a; background: #f6ffed; }
.aac-score-badge.score--neutral { color: #1677ff; border-color: #1677ff; background: #e6f4ff; }
.aac-score-badge.score--weak { color: #ff4d4f; border-color: #ff4d4f; background: #fff2f0; }

/* Sections */
.aac-section { display: flex; flex-direction: column; gap: 8px; }
.aac-section-title { font-size: 12px; font-weight: 600; color: var(--text); padding-bottom: 4px; border-bottom: 1px solid var(--border); }
.aac-section-title--muted { color: var(--muted); }

/* Cards */
.aac-card {
  border-radius: 8px; padding: 10px 12px;
  border-left: 3px solid var(--border);
  background: var(--surface2, #f8f9fa);
}
.aac-card--highlight { border-left-color: #52c41a; }
.aac-card--risk { border-left-color: #ff4d4f; }
.aac-card--watch { border-left-color: #faad14; }
.aac-card--medium { border-left-color: #fa8c16; }
.aac-card--high { border-left-color: #ff4d4f; }
.aac-card-title { font-size: 12px; font-weight: 600; color: var(--text); margin-bottom: 4px; }
.aac-card-detail { font-size: 12px; color: var(--muted); line-height: 1.5; }
.aac-sources { font-size: 10px; color: var(--muted); margin-top: 4px; }
.aac-severity {
  font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 4px; margin-top: 4px; display: inline-block;
}
.aac-severity.low { background: #f6ffed; color: #52c41a; }
.aac-severity.medium { background: #fff7e6; color: #fa8c16; }
.aac-severity.high { background: #fff2f0; color: #ff4d4f; }

/* Radar section */
.aac-radar-section { display: flex; flex-direction: column; gap: 10px; }
.aac-dim-list { display: flex; flex-direction: column; gap: 6px; }
.aac-dim-row { display: flex; align-items: center; gap: 8px; font-size: 11px; }
.aac-dim-name { width: 56px; flex-shrink: 0; color: var(--text); font-weight: 500; }
.aac-dim-level { width: 28px; flex-shrink: 0; font-size: 10px; font-weight: 600; }
.aac-dim-level.strong { color: #52c41a; }
.aac-dim-level.neutral { color: #1677ff; }
.aac-dim-level.weak { color: #ff4d4f; }
.aac-dim-bar-bg { flex: 1; height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
.aac-dim-bar { height: 100%; border-radius: 3px; transition: width 0.3s; }
.aac-dim-bar.strong { background: #52c41a; }
.aac-dim-bar.neutral { background: #1677ff; }
.aac-dim-bar.weak { background: #ff4d4f; }
.aac-dim-score { width: 24px; text-align: right; color: var(--muted); }

/* Limitations */
.aac-limitations { margin: 0; padding: 0 0 0 16px; list-style: disc; }
.aac-limitations li { font-size: 11px; color: var(--muted); line-height: 1.6; }

/* RAG metadata badges */
.aac-fallback-badge {
  font-size: 9px; font-weight: 600; padding: 1px 5px; border-radius: 4px; margin-left: 6px;
  background: #fff7e6; color: #fa8c16; border: 1px solid #ffd591;
}
.aac-mock-badge {
  font-size: 9px; padding: 1px 5px; border-radius: 4px; margin-left: 4px;
  background: #f5f5f5; color: #8c8c8c; font-style: italic;
}
.aac-local-badge {
  font-size: 9px; padding: 1px 5px; border-radius: 4px; margin-left: 4px;
  background: #f0f9eb; color: #389e0d; border: 1px solid #b7eb8f;
}
.aac-verified-badge {
  font-size: 9px; padding: 1px 6px; border-radius: 4px; margin-left: 4px;
  background: #e6fffb; color: #08979c; border: 1px solid #87e8de;
  font-weight: 600;
}
.aac-chunk-score {
  flex-shrink: 0; font-size: 10px; color: var(--muted); font-weight: 500;
}

/* Source chunks (RAG) */
.aac-chunk-item {
  border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px;
  margin-bottom: 6px;
}
.aac-chunk-header { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.aac-chunk-section {
  flex: 1; font-size: 11px; font-weight: 500; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px;
}
.aac-chunk-period { font-size: 10px; color: var(--muted); }
.aac-chunk-content {
  font-size: 11px; color: var(--muted); line-height: 1.6;
  margin-top: 6px; white-space: pre-wrap; word-break: break-all;
  background: var(--surface2, #f8f9fa); border-radius: 4px; padding: 6px 8px;
  max-height: 200px; overflow-y: auto;
}
.aac-chunk-toggle {
  font-size: 10px; color: var(--accent, #1677ff); background: none; border: none;
  cursor: pointer; padding: 2px 0; margin-top: 4px;
}
.aac-chunk-toggle:hover { text-decoration: underline; }

/* Source reports */
.aac-report-item {
  display: flex; align-items: center; gap: 6px; font-size: 11px;
  padding: 5px 0; border-bottom: 1px solid var(--border);
}
.aac-report-item:last-child { border-bottom: none; }
.aac-report-type-badge {
  flex-shrink: 0; font-size: 10px; font-weight: 600;
  padding: 1px 5px; border-radius: 4px;
  background: var(--border); color: var(--text);
}
.rtype--annual { background: #e6f4ff; color: #1677ff; }
.rtype--semi   { background: #f6ffed; color: #52c41a; }
.rtype--q      { background: #fff7e6; color: #fa8c16; }
.aac-report-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); }
.aac-report-period { flex-shrink: 0; color: var(--muted); }
.aac-report-link {
  flex-shrink: 0; font-size: 10px; color: var(--accent, #1677ff);
  text-decoration: none; padding: 1px 5px; border: 1px solid currentColor;
  border-radius: 4px;
}
.aac-report-link:hover { background: #e6f4ff; }

/* Disclaimer */
.aac-disclaimer {
  font-size: 11px; color: #856404;
  background: #fff8e1; border-radius: 6px; padding: 8px 12px; line-height: 1.5;
}

@media (max-width: 540px) {
  .aac-root { padding: 12px; }
  .aac-summary-row { flex-direction: column; }
}
</style>
