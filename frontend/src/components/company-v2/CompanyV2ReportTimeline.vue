<template>
  <div class="cv2-report-timeline" data-testid="report-timeline">
    <!-- 过滤 tabs -->
    <div class="cv2-rt-filter-tabs">
      <button
        v-for="tab in filterTabs"
        :key="tab.value"
        :class="['cv2-rt-tab', activeFilter === tab.value && 'active']"
        @click="activeFilter = tab.value"
      >
        {{ tab.label }}
        <span v-if="tab.count" class="cv2-rt-tab-count">{{ tab.count }}</span>
      </button>
    </div>

    <!-- 报告时间线 -->
    <div v-if="filteredReports.length" class="cv2-rt-list">
      <div
        v-for="item in displayedReports"
        :key="`${item.report_year}-${item.report_type}-${item.pdf_url || 'none'}`"
        :class="['cv2-rt-item', reportTypeClass(item.report_type)]"
        :data-testid="`report-item-${item.report_year}-${item.report_type}`"
      >
        <!-- 年份标签 -->
        <div class="cv2-rt-year-badge">
          <span class="cv2-rt-year">{{ item.report_year }}</span>
          <span :class="['cv2-rt-type-badge', typeColorClass(item.report_type)]">
            {{ reportTypeLabel(item.report_type) }}
          </span>
        </div>

        <!-- 内容卡片 -->
        <div :class="['cv2-rt-card', item.pdf_url ? 'has-pdf' : 'no-pdf']">
          <template v-if="item.pdf_url">
            <span :class="['cv2-rt-icon', iconClass(item.report_type)]">
              {{ reportTypeIcon(item.report_type) }}
            </span>
            <div class="cv2-rt-card-body">
              <p class="cv2-rt-title">{{ item.title || defaultTitle(item) }}</p>
              <div class="cv2-rt-meta">
                <span v-if="item.announcement_date" class="cv2-rt-date">
                  {{ item.announcement_date }}
                </span>
                <span v-if="item.is_correction" class="cv2-rt-correction-badge">更正版</span>
                <span class="cv2-rt-source">{{ item.source || 'CNINFO' }}</span>
                <!-- RAG 状态 badge -->
                <span
                  v-if="item.rag_status === 'rag_ready'"
                  class="cv2-rt-rag-badge ready"
                  title="RAG 已就绪"
                >RAG✓</span>
                <span
                  v-else-if="item.rag_status === 'downloaded'"
                  class="cv2-rt-rag-badge downloaded"
                  title="已下载"
                >下载✓</span>
                <span :class="['cv2-rt-pdf-status', pdfStatusClass(item)]">{{ pdfStatusLabel(item) }}</span>
                <span
                  v-if="item.official_verification?.status"
                  :class="['cv2-rt-verification-badge', verificationClass(item.official_verification.status)]"
                >{{ verificationLabel(item.official_verification, item) }}</span>
                <span
                  v-if="item.ai_verification?.ai_verification_status"
                  :class="['cv2-rt-ai-badge', aiVerificationClass(item.ai_verification.ai_verification_status)]"
                >{{ aiVerificationLabel(item.ai_verification) }}</span>
              </div>
              <div v-if="item.ai_verification?.human_review_queue?.length" class="cv2-rt-ai-review">
                以下字段建议人工抽检：
                <span
                  v-for="entry in item.ai_verification.human_review_queue.slice(0, 4)"
                  :key="entry.field"
                  :class="['cv2-rt-ai-review-item', aiFieldStatusClass(entry.status)]"
                >
                  {{ entry.field }}·{{ aiFieldReviewLabel(entry) }}<template v-if="entry.evidence_page">（第{{ entry.evidence_page }}页）</template>
                  <em v-if="entry.evidence_excerpt">：{{ shortEvidence(entry.evidence_excerpt) }}</em>
                </span>
              </div>
              <div v-if="item.ai_verification?.non_blocking_findings?.length" class="cv2-rt-ai-findings">
                非阻断发现：
                <span
                  v-for="entry in item.ai_verification.non_blocking_findings.slice(0, 4)"
                  :key="`${entry.field}-${entry.status}`"
                  :class="['cv2-rt-ai-finding-item', aiFieldStatusClass(entry.status)]"
                >
                  {{ entry.field }}·{{ aiFieldReviewLabel(entry) }}
                </span>
              </div>
              <div class="cv2-rt-actions">
                <a
                  :href="item.pdf_url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="cv2-rt-btn primary"
                  data-testid="open-pdf-btn"
                >
                  打开 PDF
                </a>
                <button class="cv2-rt-btn" @click="copyUrl(item.pdf_url)">
                  {{ copiedUrl === item.pdf_url ? '已复制 ✓' : '复制链接' }}
                </button>
                <button class="cv2-rt-btn" data-testid="parse-report-btn" @click="$emit('download-parse', item)">
                  下载/解析
                </button>
                <button class="cv2-rt-btn" data-testid="verify-report-btn" @click="$emit('verify', item)">
                  查看核验结果
                </button>
                <button class="cv2-rt-btn" data-testid="ai-verify-report-btn" @click="$emit('ai-verify', item)">
                  AI 校对
                </button>
                <button class="cv2-rt-btn" data-testid="report-qa-toggle-btn" @click="toggleQa(item)">
                  Report QA
                </button>
              </div>
              <CompanyV2ReportQaPanel
                v-if="qaOpenId === reportId(item)"
                :market="market"
                :symbol="symbol"
                :report="item"
                :reports="reports"
              />
            </div>
          </template>
          <template v-else>
            <span class="cv2-rt-icon muted">📭</span>
            <div class="cv2-rt-card-body">
              <p class="cv2-rt-title muted">{{ defaultTitle(item) }} — 未发现 PDF</p>
              <p class="cv2-rt-meta-hint">可尝试重新发现或手动录入</p>
            </div>
          </template>
        </div>
      </div>

      <!-- 展开/收起 -->
      <div v-if="filteredReports.length > defaultShow" class="cv2-rt-expand">
        <button class="cv2-rt-expand-btn" @click="expanded = !expanded">
          {{ expanded ? '收起' : `查看全部 ${filteredReports.length} 份报告` }}
        </button>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else class="cv2-rt-empty" data-testid="report-empty">
      <p>暂未发现报告文件。</p>
      <p class="cv2-rt-hint">可点击"发现报告"按钮从 CNINFO 查询，或手动录入 PDF URL。</p>
    </div>

    <!-- 操作栏 -->
    <div class="cv2-rt-toolbar">
      <button
        class="cv2-rt-action-btn"
        :disabled="discovering"
        @click="$emit('discover', false)"
      >
        {{ discovering ? '发现中...' : '发现报告' }}
      </button>
      <button
        class="cv2-rt-action-btn secondary"
        :disabled="discovering"
        @click="$emit('discover', true)"
      >
        强制刷新
      </button>
      <button class="cv2-rt-action-btn secondary" @click="$emit('manual')">
        手动录入 URL
      </button>
    </div>

    <!-- 数据免责提示 -->
    <p class="cv2-rt-disclaimer">
      报告文件来源：巨潮资讯（CNINFO）官方公告。PDF URL 仅供参考，以 CNINFO 实际披露为准。本页面不构成投资建议。
    </p>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import CompanyV2ReportQaPanel from './reports/CompanyV2ReportQaPanel.vue'

const props = defineProps({
  reports: { type: Array, default: () => [] },
  discovering: { type: Boolean, default: false },
  defaultShow: { type: Number, default: 20 },
  market: { type: String, default: 'CN' },
  symbol: { type: String, default: '' },
})

defineEmits(['discover', 'manual', 'download-parse', 'verify', 'ai-verify'])

const expanded = ref(false)
const activeFilter = ref('all')
const copiedUrl = ref('')
const qaOpenId = ref(null)

const REPORT_TYPE_LABELS = {
  annual: '年报',
  semi_annual: '半年报',
  q1: '一季报',
  q3: '三季报',
}
const REPORT_TYPE_ICONS = {
  annual: '📄',
  semi_annual: '📋',
  q1: '📊',
  q3: '📊',
}

// 过滤 tabs
const filterTabs = computed(() => {
  const counts = { all: props.reports.length }
  for (const r of props.reports) {
    const t = r.report_type || 'annual'
    counts[t] = (counts[t] || 0) + 1
  }
  const tabs = [{ value: 'all', label: '全部', count: counts.all }]
  for (const [type, label] of Object.entries(REPORT_TYPE_LABELS)) {
    if (counts[type]) {
      tabs.push({ value: type, label, count: counts[type] })
    }
  }
  return tabs
})

// 过滤后的报告
const filteredReports = computed(() => {
  if (activeFilter.value === 'all') return props.reports
  return props.reports.filter(r => r.report_type === activeFilter.value)
})

// 展示的报告（含展开/收起）
const displayedReports = computed(() => {
  if (expanded.value) return filteredReports.value
  return filteredReports.value.slice(0, props.defaultShow)
})

function reportTypeLabel(type) {
  return REPORT_TYPE_LABELS[type] || type || '年报'
}

function reportTypeIcon(type) {
  return REPORT_TYPE_ICONS[type] || '📄'
}

function defaultTitle(item) {
  const yearStr = item.report_year || ''
  const typeLabel = reportTypeLabel(item.report_type)
  return `${yearStr}年${typeLabel}`
}

function reportId(item) {
  return item.id || item.report_id || `${item.report_year}-${item.report_type}`
}

function toggleQa(item) {
  const id = reportId(item)
  qaOpenId.value = qaOpenId.value === id ? null : id
}

function reportTypeClass(type) {
  const map = { annual: 'type-annual', semi_annual: 'type-semi', q1: 'type-q1', q3: 'type-q3' }
  return map[type] || 'type-annual'
}

function typeColorClass(type) {
  const map = { annual: 'red', semi_annual: 'blue', q1: 'gray', q3: 'gray' }
  return `badge-${map[type] || 'red'}`
}

function iconClass(type) {
  const map = { annual: 'icon-annual', semi_annual: 'icon-semi', q1: 'icon-quarterly', q3: 'icon-quarterly' }
  return map[type] || 'icon-annual'
}

function pdfStatusLabel(item) {
  const status = item.pdf_status || item.download_status || (item.pdf_url ? 'discovered' : 'failed')
  return {
    discovered: 'PDF discovered',
    downloading: 'PDF downloading',
    downloaded: 'PDF downloaded',
    parsed: 'PDF parsed',
    verified: 'PDF verified',
    failed: 'PDF failed',
    download_failed: 'PDF failed',
    parse_failed: 'PDF failed',
  }[status] || status
}

function pdfStatusClass(item) {
  const status = item.pdf_status || item.download_status || (item.pdf_url ? 'discovered' : 'failed')
  if (['verified', 'parsed', 'downloaded'].includes(status)) return 'ok'
  if (status === 'failed' || status.endsWith?.('_failed')) return 'fail'
  return 'pending'
}

function verificationLabel(verification, item = {}) {
  const status = verification?.status || verification
  if (verification?.period_mismatch_count > 0) {
    return '当前年报年份与结构化数据期间不一致，已跳过强核验'
  }
  return {
    verified: `已按 ${item.report_year || ''} 年年度报告核验部分字段。`,
    partial: '部分字段已核验，其余字段缺少可靠抽取结果。',
    conflict: '结构化数据与年报字段存在差异',
    unverified: 'Unverified',
  }[status] || status
}

function aiVerificationLabel(result) {
  const status = result?.ai_verification_status || result?.verification_status
  if (result?.human_review_queue?.length) return 'AI 校对：以下字段建议人工抽检'
  return {
    verified: 'AI 校对通过，无需人工复核。',
    partial: 'AI 校对部分通过。',
    conflict: '同期同口径数据存在差异。',
    needs_human_review: 'AI 校对建议人工抽检。',
    insufficient_evidence: 'AI 校对证据不足。',
  }[status] || `AI 校对：${status || '未执行'}`
}

function aiVerificationClass(status) {
  if (status === 'verified' || status === 'partial') return 'verified'
  if (status === 'conflict') return 'conflict'
  if (status === 'needs_human_review') return 'warning'
  return 'unverified'
}

function aiFieldStatusLabel(status) {
  return {
    verified: '已核验',
    likely_match: '基本一致',
    conflict: '同期同口径数据存在差异',
    structured_field_missing: '结构化数据缺少该字段',
    official_field_not_found: '报告中未找到可靠字段',
    insufficient_evidence: '报告证据不足',
    definition_mismatch: '字段口径不同',
    period_basis_mismatch: '数据期间或时点不同',
    unit_scale_suspected: '疑似单位换算差异',
    needs_human_review: '建议人工抽检',
    skipped: '已跳过',
  }[status] || status || '未分类'
}

function aiFieldReviewLabel(entry) {
  if (entry?.status === 'definition_mismatch') {
    return {
      revenue: '营业收入字段口径不同',
      net_profit_parent: '净利润与归母净利润口径不同',
      roe_weighted: 'ROE 与加权平均 ROE 口径不同',
    }[entry.field] || aiFieldStatusLabel(entry.status)
  }
  return aiFieldStatusLabel(entry?.status)
}

function aiFieldStatusClass(status) {
  if (status === 'conflict') return 'conflict'
  if (['definition_mismatch', 'period_basis_mismatch', 'unit_scale_suspected', 'needs_human_review'].includes(status)) return 'warning'
  if (['structured_field_missing', 'official_field_not_found', 'insufficient_evidence', 'skipped'].includes(status)) return 'neutral'
  return 'verified'
}

function shortEvidence(text) {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim()
  return normalized.length > 80 ? `${normalized.slice(0, 80)}...` : normalized
}

function verificationClass(status) {
  if (status === 'verified' || status === 'partial') return 'verified'
  if (status === 'conflict') return 'conflict'
  return 'unverified'
}

async function copyUrl(url) {
  try {
    await navigator.clipboard.writeText(url)
    copiedUrl.value = url
    setTimeout(() => { copiedUrl.value = '' }, 2000)
  } catch {
    // fallback
    const el = document.createElement('textarea')
    el.value = url
    document.body.appendChild(el)
    el.select()
    document.execCommand('copy')
    document.body.removeChild(el)
    copiedUrl.value = url
    setTimeout(() => { copiedUrl.value = '' }, 2000)
  }
}
</script>

<style scoped>
.cv2-report-timeline { font-size: 13px; }

/* Filter tabs */
.cv2-rt-filter-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.cv2-rt-tab {
  padding: 4px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 20px;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
  color: #6b7280;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all 0.15s;
}
.cv2-rt-tab:hover { background: #f3f4f6; }
.cv2-rt-tab.active { background: #1d4ed8; color: #fff; border-color: #1d4ed8; }
.cv2-rt-tab-count {
  background: rgba(255,255,255,0.25);
  border-radius: 10px;
  padding: 0 5px;
  font-size: 10px;
}
.cv2-rt-tab.active .cv2-rt-tab-count { background: rgba(255,255,255,0.3); }

/* Timeline list */
.cv2-rt-list { display: flex; flex-direction: column; gap: 12px; }
.cv2-rt-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.cv2-rt-year-badge {
  min-width: 70px;
  text-align: right;
  padding-top: 10px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}
.cv2-rt-year { font-size: 14px; font-weight: 700; color: #374151; }
.cv2-rt-type-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 10px;
  font-weight: 500;
}
.badge-red { background: #fef2f2; color: #ef4444; border: 1px solid #fecaca; }
.badge-blue { background: #eff6ff; color: #3b82f6; border: 1px solid #bfdbfe; }
.badge-gray { background: #f9fafb; color: #6b7280; border: 1px solid #e5e7eb; }

/* Card */
.cv2-rt-card {
  flex: 1;
  display: flex;
  gap: 10px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px 14px;
  background: #fff;
}
.cv2-rt-card.has-pdf { border-left: 3px solid #10b981; }
.cv2-rt-card.no-pdf { border-left: 3px solid #d1d5db; background: #f9fafb; }
.cv2-rt-icon { font-size: 20px; padding-top: 2px; min-width: 24px; }
.cv2-rt-icon.icon-annual { filter: none; }
.cv2-rt-icon.icon-quarterly { filter: grayscale(0.3); }
.cv2-rt-icon.muted { opacity: 0.35; }
.cv2-rt-card-body { flex: 1; }
.cv2-rt-title { margin: 0 0 4px; font-size: 13px; font-weight: 500; color: #111827; }
.cv2-rt-title.muted { color: #9ca3af; }
.cv2-rt-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.cv2-rt-date { font-size: 11px; color: #6b7280; }
.cv2-rt-source { font-size: 10px; color: #9ca3af; }
.cv2-rt-correction-badge {
  font-size: 10px;
  background: #fef3c7;
  color: #f59e0b;
  padding: 1px 5px;
  border-radius: 3px;
}
.cv2-rt-rag-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
}
.cv2-rt-rag-badge.ready { background: #f0fdf4; color: #16a34a; }
.cv2-rt-rag-badge.downloaded { background: #eff6ff; color: #3b82f6; }
.cv2-rt-pdf-status,
.cv2-rt-verification-badge,
.cv2-rt-ai-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
}
.cv2-rt-pdf-status.ok,
.cv2-rt-verification-badge.verified,
.cv2-rt-ai-badge.verified { background: #dcfce7; color: #166534; }
.cv2-rt-pdf-status.pending,
.cv2-rt-verification-badge.unverified,
.cv2-rt-ai-badge.unverified { background: #f3f4f6; color: #6b7280; }
.cv2-rt-pdf-status.fail,
.cv2-rt-verification-badge.conflict,
.cv2-rt-ai-badge.warning { background: #fef3c7; color: #92400e; }
.cv2-rt-verification-badge.conflict,
.cv2-rt-ai-badge.conflict { background: #fee2e2; color: #991b1b; }
.cv2-rt-ai-review {
  margin: 4px 0 6px;
  font-size: 11px;
  color: #92400e;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.cv2-rt-ai-findings {
  margin: 2px 0 6px;
  font-size: 11px;
  color: #6b7280;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.cv2-rt-ai-review-item,
.cv2-rt-ai-finding-item {
  border-radius: 3px;
  padding: 1px 4px;
}
.cv2-rt-ai-review-item.conflict,
.cv2-rt-ai-finding-item.conflict { background: #fee2e2; color: #991b1b; }
.cv2-rt-ai-review-item.warning,
.cv2-rt-ai-finding-item.warning { background: #fef3c7; color: #92400e; }
.cv2-rt-ai-review-item.neutral,
.cv2-rt-ai-finding-item.neutral { background: #f3f4f6; color: #6b7280; }
.cv2-rt-ai-review-item.verified,
.cv2-rt-ai-finding-item.verified { background: #dcfce7; color: #166534; }
.cv2-rt-meta-hint { font-size: 11px; color: #9ca3af; margin: 0; }

/* Actions */
.cv2-rt-actions { display: flex; gap: 6px; }
.cv2-rt-btn {
  padding: 4px 10px;
  border-radius: 5px;
  border: 1px solid #e5e7eb;
  background: #fff;
  font-size: 12px;
  cursor: pointer;
  text-decoration: none;
  color: #374151;
  transition: background 0.1s;
}
.cv2-rt-btn:hover { background: #f3f4f6; }
.cv2-rt-btn.primary {
  background: #1d4ed8;
  border-color: #1d4ed8;
  color: #fff;
}
.cv2-rt-btn.primary:hover { background: #1e40af; }

/* Expand */
.cv2-rt-expand { text-align: center; padding: 8px 0; }
.cv2-rt-expand-btn {
  background: none;
  border: none;
  color: #3b82f6;
  cursor: pointer;
  font-size: 12px;
}
.cv2-rt-expand-btn:hover { text-decoration: underline; }

/* Empty */
.cv2-rt-empty { padding: 20px; text-align: center; color: #9ca3af; }
.cv2-rt-hint { font-size: 12px; color: #9ca3af; margin: 4px 0 0; }

/* Toolbar */
.cv2-rt-toolbar {
  display: flex;
  gap: 8px;
  margin-top: 16px;
  flex-wrap: wrap;
}
.cv2-rt-action-btn {
  padding: 6px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
  color: #374151;
}
.cv2-rt-action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.cv2-rt-action-btn.secondary { color: #6b7280; }

/* Disclaimer */
.cv2-rt-disclaimer {
  margin-top: 12px;
  font-size: 10px;
  color: #9ca3af;
  line-height: 1.5;
}
</style>
