<template>
  <div class="rdp-root">
    <!-- Auto-discover toolbar -->
    <div class="rdp-toolbar">
      <div class="rdp-toolbar-left">
        <span class="rdp-title-text">年报文件索引</span>
        <span v-if="rows.length" class="rdp-count-badge">{{ rows.length }}</span>
      </div>
      <div class="rdp-toolbar-right">
        <select v-model="discoverYear" class="rdp-year-select" :disabled="discovering">
          <option v-for="y in yearOptions" :key="y" :value="y">{{ y }} 年</option>
        </select>
        <button
          class="rdp-discover-btn"
          :class="{ 'rdp-discover-btn--loading': discovering }"
          :disabled="discovering || notEnabled"
          @click="discoverLatest"
          :title="notEnabled ? '需后端配置 ENABLE_REPORT_PDF=true' : '自动搜索最新年报/半年报/季报'"
        >
          <span v-if="discovering" class="rdp-spinner"></span>
          <span v-else>🔍</span>
          {{ discovering ? '搜索中…' : '自动查找财报' }}
        </button>
      </div>
    </div>

    <!-- Discover result notice -->
    <div v-if="discoverResult" class="rdp-discover-result" :class="discoverResult.type">
      <span>{{ discoverResult.message }}</span>
      <button class="rdp-dismiss" @click="discoverResult = null">✕</button>
    </div>

    <!-- Discovery attempts detail (shown when search returned nothing) -->
    <div v-if="discoverAttempts.length > 0 && !rows.length" class="rdp-attempts">
      <div class="rdp-attempts-title">已搜索以下来源：</div>
      <div class="rdp-attempts-list">
        <div
          v-for="(a, i) in discoverAttempts"
          :key="i"
          class="rdp-attempt-row"
          :class="'rdp-attempt--' + a.status"
        >
          <span class="rdp-attempt-year">{{ a.year }}年</span>
          <span class="rdp-attempt-status">
            {{ a.status === 'candidate_found' ? '✓ 找到 ' + a.candidate_count + ' 条' : '未找到' }}
          </span>
          <span v-if="a.providers && a.providers.length" class="rdp-attempt-providers">
            {{ a.providers.join(' / ') }}
          </span>
          <span v-if="a.errors && a.errors.length" class="rdp-attempt-error">
            {{ a.errors[0] }}
          </span>
        </div>
      </div>
    </div>

    <!-- Not enabled notice -->
    <div v-if="notEnabled" class="rdp-notice">
      <span class="rdp-notice-icon">📄</span>
      <div>
        <div class="rdp-notice-title">年报文件功能未开启</div>
        <div class="rdp-notice-desc">
          需后端配置 <code>ENABLE_REPORT_PDF=true</code>
          并完成 PDF 采集后，此处才会显示历年年报/半年报文件索引。
          点击「自动查找财报」可在线搜索公开披露平台。
        </div>
      </div>
    </div>

    <!-- Loading skeleton -->
    <div v-else-if="loading" class="rdp-skeleton">
      <div class="rdp-skel-row" v-for="i in 3" :key="i"></div>
    </div>

    <!-- Error / empty state -->
    <div v-else-if="isEmpty" class="rdp-empty">
      <div class="rdp-empty-icon">📂</div>
      <div class="rdp-empty-title">暂无年报文件</div>
      <div class="rdp-empty-desc">
        暂未接入该股票财报 PDF，可点击「自动查找财报」或手动上传。
      </div>
      <!-- Phase 6N-8B: show discovery_attempts if available -->
      <div v-if="discoverAttempts.length" class="rdp-discover-attempts">
        <div class="rdp-attempts-label">搜索记录：</div>
        <ul class="rdp-attempts-list">
          <li v-for="(a, i) in discoverAttempts" :key="i" class="rdp-attempt-item">
            <span class="rdp-attempt-provider">{{ a.provider || a.source }}</span>
            <span class="rdp-attempt-year">{{ a.year }}</span>
            <span :class="['rdp-attempt-status', a.found || a.total_found > 0 ? 'status-found' : 'status-empty']">
              {{ (a.found || a.total_found > 0) ? '找到' : '未找到' }}
            </span>
          </li>
        </ul>
        <div class="rdp-attempts-hint">
          已尝试 CNINFO/SSE/SZSE 的年报，暂未找到可确认 PDF。你可以手动上传 PDF 或手动录入 PDF URL。
        </div>
      </div>
    </div>

    <!-- Document list -->
    <div v-else class="rdp-list">
      <table class="rdp-table">
        <thead>
          <tr>
            <th>类型</th>
            <th>报告期</th>
            <th>标题</th>
            <th>披露日</th>
            <th>来源</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="doc in rows" :key="doc.id" class="rdp-row">
            <!-- Type badge -->
            <td>
              <span class="rdp-type-badge" :class="typeClass(doc.report_type)">
                {{ typeLabel(doc.report_type) }}
              </span>
            </td>
            <!-- Period -->
            <td class="rdp-date">{{ doc.period_end || doc.report_year || '—' }}</td>
            <!-- Title with PDF icon -->
            <td class="rdp-title-cell">
              <span
                v-if="doc.pdf_url"
                class="rdp-pdf-icon"
                title="点击查看 PDF"
                @click="openPdf(doc)"
              >📄</span>
              <span class="rdp-title-text-cell" :title="doc.title">{{ doc.title || '—' }}</span>
            </td>
            <!-- Disclosure date -->
            <td class="rdp-date">{{ doc.disclosure_date || '—' }}</td>
            <!-- Source badge -->
            <td>
              <span class="rdp-source-badge" :class="`rdp-source-${doc.source || 'manual'}`">
                {{ sourceLabel(doc.source) }}
              </span>
              <span v-if="doc.confidence" class="rdp-confidence" :title="`置信度 ${(doc.confidence * 100).toFixed(0)}%`">
                {{ (doc.confidence * 100).toFixed(0) }}%
              </span>
            </td>
            <!-- Parse + RAG status -->
            <td>
              <span class="rdp-status" :class="parseStatusClass(doc)">
                {{ parseStatusLabel(doc) }}
              </span>
              <span v-if="doc.rag_status && doc.rag_status !== 'pending'" class="rdp-rag-badge" :class="ragStatusClass(doc.rag_status)" :title="`RAG: ${doc.rag_status}${doc.rag_provider ? ' (' + doc.rag_provider + ')' : ''}`">
                {{ ragStatusLabel(doc.rag_status) }}
              </span>
              <span v-if="doc.chunk_count" class="rdp-chunk-count">{{ doc.chunk_count }} 片</span>
              <span v-if="doc.rag_provider === 'mock'" class="rdp-mock-hint" title="当前为测试向量，检索结果仅用于链路验证">测试向量</span>
              <span v-else-if="doc.rag_provider === 'local'" class="rdp-local-hint" title="本地语义向量（sentence-transformers）">本地语义向量</span>
              <span v-else-if="doc.rag_provider === 'disabled'" class="rdp-disabled-hint" title="向量检索已禁用，仅关键词回退">关键词检索</span>
            </td>
            <!-- Actions -->
            <td class="rdp-actions">
              <button
                v-if="doc.pdf_url"
                class="rdp-action-btn rdp-action-view"
                @click="openPdf(doc)"
                title="查看 PDF"
              >查看</button>
              <button
                v-if="doc.pdf_url && doc.download_status !== 'downloaded'"
                class="rdp-action-btn rdp-action-dl"
                :disabled="downloadingId === doc.id"
                @click="downloadPdf(doc)"
                title="下载到服务端缓存"
              >{{ downloadingId === doc.id ? '下载中…' : '下载' }}</button>
              <button
                v-if="doc.download_status === 'downloaded' && !doc.parsed"
                class="rdp-action-btn rdp-action-parse"
                :disabled="parsingId === doc.id"
                @click="parsePdf(doc)"
                title="提取文本摘录供 AI 引用"
              >{{ parsingId === doc.id ? '解析中…' : '解析' }}</button>
              <button
                v-if="doc.parsed"
                class="rdp-action-btn rdp-action-text"
                @click="viewText(doc)"
                title="查看提取的文本摘录"
              >查看摘录</button>
              <button
                v-if="doc.parsed && doc.rag_status !== 'embedded'"
                class="rdp-action-btn rdp-action-rag"
                :disabled="buildingRagId === doc.id"
                @click="buildRag(doc)"
                title="切分 + 向量化，生成 RAG 索引"
              >{{ buildingRagId === doc.id ? '建索引…' : '生成索引' }}</button>
              <span v-if="!doc.pdf_url" class="rdp-no-pdf">无 PDF</span>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Warnings for docs with low confidence -->
      <div v-if="docWarnings.length" class="rdp-warnings">
        <div class="rdp-warnings-title">⚠️ 注意事项</div>
        <ul class="rdp-warnings-list">
          <li v-for="(w, i) in docWarnings" :key="i">{{ w }}</li>
        </ul>
      </div>
    </div>

    <!-- Discover candidates (low confidence, pending user confirmation) -->
    <div v-if="pendingCandidates.length" class="rdp-pending">
      <div class="rdp-pending-title">
        以下候选置信度不足 75%，需人工确认后手动录入：
      </div>
      <div v-for="c in pendingCandidates" :key="c.pdf_url" class="rdp-pending-item">
        <span class="rdp-type-badge" :class="typeClass(c.report_type)">{{ typeLabel(c.report_type) }}</span>
        <span class="rdp-pending-title-text">{{ c.title }}</span>
        <span class="rdp-confidence rdp-confidence-low">{{ (c.confidence * 100).toFixed(0) }}%</span>
        <a v-if="c.pdf_url" :href="c.pdf_url" target="_blank" rel="noopener noreferrer" class="rdp-link">预览</a>
      </div>
    </div>

    <!-- Disclaimer -->
    <div class="rdp-disclaimer">
      年报文件信息来自公开披露平台（CNINFO/SSE/SZSE），仅供参考，不构成投资建议。
      数据以官方披露为准，本系统不对 PDF 内容准确性负责。
    </div>
  </div>

  <!-- Text excerpt modal -->
  <div v-if="textModal" class="rdp-modal-overlay" @click.self="textModal = null">
    <div class="rdp-modal">
      <div class="rdp-modal-header">
        <span class="rdp-modal-title">{{ textModal.title }}</span>
        <span v-if="textModal.chars" class="rdp-modal-meta">{{ textModal.chars }} 字符</span>
        <button class="rdp-modal-close" @click="textModal = null">✕</button>
      </div>
      <pre class="rdp-modal-text">{{ textModal.text }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  envelope:   { type: Object, default: null },
  loading:    { type: Boolean, default: false },
  market:     { type: String, default: 'CN' },
  stockCode:  { type: String, default: '' },
})

// ── Constants ─────────────────────────────────────────────────────────────────
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1'
const HIGH_CONFIDENCE = 0.75

// ── State ─────────────────────────────────────────────────────────────────────
const discovering       = ref(false)
const discoverResult    = ref(null)
const discoverAttempts  = ref([])   // discovery_attempts from last discover call
const pendingCandidates = ref([])
const localRows         = ref([])  // rows added by auto-discover in this session
const downloadingId   = ref(null)
const parsingId       = ref(null)
const buildingRagId   = ref(null)
const textModal       = ref(null)  // { title, text } or null

// ── Derived from envelope ─────────────────────────────────────────────────────
const data = computed(() => props.envelope?.data || null)

const notEnabled = computed(() => {
  if (!props.envelope) return false
  const reasons = data.value?.reasons || props.envelope?.errors || []
  return reasons.some(r => typeof r === 'string' && r.includes('ENABLE_REPORT_PDF'))
})

const envelopeRows = computed(() => data.value?.rows || [])
const rows = computed(() => [...envelopeRows.value, ...localRows.value])
const isEmpty = computed(() => !props.loading && !notEnabled.value && rows.value.length === 0)

const docWarnings = computed(() => {
  const out = []
  for (const doc of rows.value) {
    if (doc.warnings && Array.isArray(doc.warnings)) {
      out.push(...doc.warnings)
    }
  }
  return [...new Set(out)]
})

// ── Year picker ────────────────────────────────────────────────────────────────
const currentYear = new Date().getFullYear()
const discoverYear = ref(currentYear - 1)  // default: last year's annual report
const yearOptions = computed(() => {
  const opts = []
  for (let y = currentYear - 1; y >= currentYear - 6; y--) {
    opts.push(y)
  }
  return opts
})

// ── PDF URL helper ────────────────────────────────────────────────────────────
function pdfProxyUrl(doc) {
  if (!doc.id || !props.stockCode) return doc.pdf_url || '#'
  return `${API_BASE}/stocks/${props.market}/${props.stockCode}/reports/${doc.id}/pdf`
}

function openPdf(doc) {
  const url = pdfProxyUrl(doc)
  window.open(url, '_blank', 'noopener,noreferrer')
}

// ── Auto-discover ─────────────────────────────────────────────────────────────
async function discoverLatest() {
  if (!props.stockCode) {
    discoverResult.value = { type: 'error', message: '缺少股票代码，无法搜索' }
    return
  }

  discovering.value = true
  discoverResult.value = null
  pendingCandidates.value = []

  try {
    const url = (
      `${API_BASE}/stocks/${props.market}/${props.stockCode}/reports/discover/latest`
      + `?report_year=${discoverYear.value}`
    )
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
    const json = await res.json()

    const inserted = json.inserted || []
    const candidates = json.candidates || []
    const errors = json.errors || []
    discoverAttempts.value = json.discovery_attempts || []

    // Add inserted rows to local list (so they appear without a full reload)
    for (const c of inserted) {
      if (c.report_id && !localRows.value.find(r => r.id === c.report_id)) {
        localRows.value.push({
          id:              c.report_id,
          ts_code:         `${props.stockCode}.SH`,
          report_type:     c.report_type,
          report_year:     c.report_year,
          period_end:      c.period ? `${c.period.slice(0,4)}-${c.period.slice(4,6)}-${c.period.slice(6,8)}` : null,
          title:           c.title,
          source:          c.source,
          source_url:      c.source_url,
          pdf_url:         c.pdf_url,
          confidence:      c.confidence,
          disclosure_date: c.ann_date ? `${c.ann_date.slice(0,4)}-${c.ann_date.slice(4,6)}-${c.ann_date.slice(6,8)}` : null,
          parsed:          false,
          warnings:        c.warnings || [],
        })
      }
    }

    // Pending candidates (low confidence)
    pendingCandidates.value = candidates.filter(c => c.confidence < HIGH_CONFIDENCE && !inserted.find(i => i.pdf_url === c.pdf_url))

    if (inserted.length > 0) {
      discoverResult.value = {
        type: 'success',
        message: `已自动录入 ${inserted.length} 条报告。${pendingCandidates.value.length ? ` 另有 ${pendingCandidates.value.length} 条低置信度候选需人工确认。` : ''}`,
      }
    } else if (candidates.length > 0) {
      discoverResult.value = {
        type: 'warn',
        message: `找到 ${candidates.length} 条候选，置信度不足 75%，需人工确认后手动录入。`,
      }
    } else {
      const reason = errors.length ? errors[0] : '未找到相关报告，请尝试更换年份或手动查找。'
      // Build attempt summary for display
      const attemptSummary = discoverAttempts.value.length > 0
        ? '（已尝试：' + discoverAttempts.value.map(a => `${a.year}年`).join('、') + '）'
        : ''
      discoverResult.value = { type: 'error', message: reason + attemptSummary }
    }
  } catch (e) {
    discoverResult.value = { type: 'error', message: `搜索失败: ${e.message || e}` }
  } finally {
    discovering.value = false
  }
}

// ── Download PDF to server cache ──────────────────────────────────────────────
async function downloadPdf(doc) {
  if (!doc.id || !props.stockCode) return
  downloadingId.value = doc.id
  try {
    const url = `${API_BASE}/stocks/${props.market}/${props.stockCode}/reports/${doc.id}/download`
    const res = await fetch(url, { method: 'POST' })
    const json = await res.json()
    if (json.status === 'downloaded' || json.status === 'exists') {
      doc.download_status = 'downloaded'
      doc.file_size = json.file_size
      discoverResult.value = {
        type: 'success',
        message: json.status === 'exists'
          ? `已缓存，大小 ${_fmtSize(json.file_size || doc.file_size)}`
          : `下载成功，大小 ${_fmtSize(json.file_size)}`,
      }
    } else {
      discoverResult.value = { type: 'error', message: `下载失败: ${json.reason || '未知错误'}` }
    }
  } catch (e) {
    discoverResult.value = { type: 'error', message: `下载失败: ${e.message}` }
  } finally {
    downloadingId.value = null
  }
}

// ── Parse PDF text ─────────────────────────────────────────────────────────────
async function parsePdf(doc) {
  if (!doc.id || !props.stockCode) return
  parsingId.value = doc.id
  try {
    const url = `${API_BASE}/stocks/${props.market}/${props.stockCode}/reports/${doc.id}/parse`
    const res = await fetch(url, { method: 'POST' })
    const json = await res.json()
    if (json.status === 'parsed') {
      doc.parsed = true
      doc.parse_status = 'parsed'
      discoverResult.value = { type: 'success', message: `解析完成，提取 ${json.chars} 字符摘录` }
    } else {
      discoverResult.value = { type: 'error', message: `解析失败: ${json.reason || '未知错误'}` }
    }
  } catch (e) {
    discoverResult.value = { type: 'error', message: `解析失败: ${e.message}` }
  } finally {
    parsingId.value = null
  }
}

// ── View text excerpt ──────────────────────────────────────────────────────────
async function viewText(doc) {
  if (!doc.id || !props.stockCode) return
  try {
    const url = `${API_BASE}/stocks/${props.market}/${props.stockCode}/reports/${doc.id}/text`
    const res = await fetch(url)
    const json = await res.json()
    textModal.value = {
      title: doc.title || json.title || '文本摘录',
      text: json.text || '（无文本内容）',
      chars: json.chars || 0,
    }
  } catch (e) {
    discoverResult.value = { type: 'error', message: `获取摘录失败: ${e.message}` }
  }
}

// ── Build RAG index (chunk + embed) ──────────────────────────────────────────
async function buildRag(doc) {
  if (!doc.id || !props.stockCode) return
  buildingRagId.value = doc.id
  try {
    const url = `${API_BASE}/stocks/${props.market}/${props.stockCode}/reports/${doc.id}/rag/build`
    const res = await fetch(url, { method: 'POST' })
    const json = await res.json()
    if (json.status === 'embedded' || json.status === 'partial') {
      doc.rag_status = json.status
      const chunkResult = json.chunk_result || {}
      const embedResult = json.embed_result || {}
      doc.chunk_count = chunkResult.chunk_count || 0
      doc.rag_provider = embedResult.provider || 'mock'
      const isMock = doc.rag_provider === 'mock'
      discoverResult.value = {
        type: json.status === 'embedded' ? 'success' : 'warn',
        message: `索引完成：${doc.chunk_count} 个片段已向量化${isMock ? '（测试向量，仅验证链路）' : '（语义向量）'}。${embedResult.failed ? ` ${embedResult.failed} 个 embedding 失败。` : ''}`,
      }
    } else {
      discoverResult.value = { type: 'error', message: `建索引失败: ${json.reason || '未知错误'}` }
    }
  } catch (e) {
    discoverResult.value = { type: 'error', message: `建索引失败: ${e.message}` }
  } finally {
    buildingRagId.value = null
  }
}

function _fmtSize(bytes) {
  if (!bytes) return '未知'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

// ── Label helpers ─────────────────────────────────────────────────────────────
function typeLabel(type) {
  return { annual: '年报', semi: '半年报', q1: '一季报', q3: '三季报' }[type] || type || '—'
}

function typeClass(type) {
  return { annual: 'rdp-type-annual', semi: 'rdp-type-semi', q1: 'rdp-type-q', q3: 'rdp-type-q' }[type] || ''
}

function sourceLabel(source) {
  return { cninfo: 'CNINFO', sse: 'SSE', szse: 'SZSE', manual: '手动' }[source] || source || '—'
}

function parseStatusLabel(doc) {
  if (doc.parsed || doc.parse_status === 'parsed') return '已解析'
  if (doc.parse_status === 'failed') return '解析失败'
  if (doc.download_status === 'downloaded') return '待解析'
  if (doc.download_status === 'failed') return '下载失败'
  return '待下载'
}

function parseStatusClass(doc) {
  if (doc.parsed || doc.parse_status === 'parsed') return 'rdp-parsed-yes'
  if (doc.parse_status === 'failed' || doc.download_status === 'failed') return 'rdp-parsed-no'
  if (doc.download_status === 'downloaded') return 'rdp-parsed-pending'
  return 'rdp-parsed-none'
}

function ragStatusLabel(status) {
  return { pending: '', chunked: '已切分', embedded: '已向量化', partial: '部分', failed: 'RAG失败' }[status] || ''
}

function ragStatusClass(status) {
  return {
    embedded: 'rdp-rag-embedded',
    chunked:  'rdp-rag-chunked',
    partial:  'rdp-rag-partial',
    failed:   'rdp-rag-failed',
  }[status] || ''
}
</script>

<style scoped>
.rdp-root {
  font-size: 0.875rem;
  color: var(--text-primary);
}

/* ── Toolbar ── */
.rdp-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.rdp-toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rdp-title-text {
  font-weight: 600;
  color: var(--text-secondary);
}
.rdp-count-badge {
  background: var(--bg-secondary);
  color: var(--text-muted);
  font-size: 0.75rem;
  padding: 1px 7px;
  border-radius: 10px;
}
.rdp-toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rdp-year-select {
  font-size: 0.82rem;
  padding: 4px 8px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-primary);
  cursor: pointer;
}
.rdp-discover-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 0.82rem;
  border: 1px solid var(--accent-primary);
  border-radius: 6px;
  background: var(--accent-primary);
  color: #fff;
  cursor: pointer;
  transition: opacity 0.15s;
}
.rdp-discover-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.rdp-discover-btn--loading {
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border-color: var(--border-color);
}
.rdp-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Discover result notice ── */
.rdp-discover-result {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 0.82rem;
  margin-bottom: 10px;
}
.rdp-discover-result.success {
  background: var(--status-info-bg);
  color: var(--status-info);
  border: 1px solid var(--status-info);
}
.rdp-discover-result.warn {
  background: var(--status-warn-bg);
  color: var(--status-warn);
  border: 1px solid var(--status-warn);
}
.rdp-discover-result.error {
  background: var(--status-down-bg, #fff0f0);
  color: var(--status-down, #c0392b);
  border: 1px solid var(--status-down, #c0392b);
}
.rdp-dismiss {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.85rem;
  opacity: 0.6;
  color: inherit;
  flex-shrink: 0;
}

/* ── Discovery attempts detail ── */
.rdp-attempts {
  margin-top: 8px;
  padding: 10px 12px;
  background: var(--surface2, #f8f9fa);
  border: 1px solid var(--border, #dde3ef);
  border-radius: 8px;
  font-size: 12px;
}

.rdp-attempts-title {
  font-weight: 600;
  color: var(--color-text-secondary, #666);
  margin-bottom: 6px;
}

.rdp-attempts-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rdp-attempt-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
}

.rdp-attempt-year {
  font-weight: 600;
  min-width: 44px;
  color: var(--color-text-primary, #1a2540);
}

.rdp-attempt-status {
  min-width: 80px;
}

.rdp-attempt--candidate_found .rdp-attempt-status {
  color: var(--status-up, #16a34a);
}

.rdp-attempt--empty .rdp-attempt-status {
  color: var(--muted, #999);
}

.rdp-attempt-providers {
  color: var(--muted, #aaa);
  font-size: 11px;
}

.rdp-attempt-error {
  color: var(--status-down, #dc2626);
  font-size: 11px;
}

/* ── Not-enabled notice ── */
.rdp-notice {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 14px;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}
.rdp-notice-icon { font-size: 1.5rem; flex-shrink: 0; }
.rdp-notice-title { font-weight: 600; margin-bottom: 4px; color: var(--text-secondary); }
.rdp-notice-desc { color: var(--text-muted); line-height: 1.5; }
.rdp-notice-desc code {
  background: var(--bg-tertiary);
  padding: 1px 4px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 0.8rem;
}

/* ── Skeleton ── */
.rdp-skeleton { display: flex; flex-direction: column; gap: 8px; padding: 12px 0; }
.rdp-skel-row {
  height: 36px;
  border-radius: 6px;
  background: var(--bg-secondary);
  animation: pulse 1.4s ease-in-out infinite;
}
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

/* ── Empty ── */
.rdp-empty {
  text-align: center;
  padding: 32px 16px;
  color: var(--text-muted);
}
.rdp-empty-icon { font-size: 2.5rem; margin-bottom: 8px; }
.rdp-empty-title { font-weight: 600; margin-bottom: 4px; color: var(--text-secondary); }
.rdp-empty-desc { font-size: 0.82rem; line-height: 1.5; }

/* ── Table ── */
.rdp-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
.rdp-table th {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 2px solid var(--border-color);
  color: var(--text-muted);
  font-weight: 600;
  white-space: nowrap;
}
.rdp-row td { padding: 7px 8px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
.rdp-row:last-child td { border-bottom: none; }
.rdp-row:hover { background: var(--bg-secondary); }
.rdp-date { white-space: nowrap; color: var(--text-secondary); }

/* Title cell */
.rdp-title-cell { display: flex; align-items: center; gap: 6px; max-width: 200px; }
.rdp-pdf-icon {
  font-size: 1.1rem;
  cursor: pointer;
  flex-shrink: 0;
  transition: transform 0.15s;
}
.rdp-pdf-icon:hover { transform: scale(1.2); }
.rdp-title-text-cell {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

/* Type badge */
.rdp-type-badge {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 10px;
  font-size: 0.73rem;
  font-weight: 600;
  white-space: nowrap;
}
.rdp-type-annual { background: var(--status-info-bg); color: var(--status-info); }
.rdp-type-semi   { background: var(--status-warn-bg); color: var(--status-warn); }
.rdp-type-q      { background: var(--bg-secondary);   color: var(--text-secondary); }

/* Source badge */
.rdp-source-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 0.72rem;
  font-weight: 600;
  margin-right: 4px;
}
.rdp-source-cninfo { background: #e8f4fd; color: #1a6ca8; }
.rdp-source-sse    { background: #fef3e2; color: #b45309; }
.rdp-source-szse   { background: #f0fdf4; color: #15803d; }
.rdp-source-manual { background: var(--bg-secondary); color: var(--text-muted); }
.rdp-confidence {
  font-size: 0.7rem;
  color: var(--text-muted);
}
.rdp-confidence-low { color: var(--status-warn); }

/* Status */
.rdp-status { font-size: 0.73rem; padding: 2px 6px; border-radius: 8px; }
.rdp-parsed-yes     { background: var(--status-info-bg);  color: var(--status-info); }
.rdp-parsed-no      { background: var(--status-down-bg, #fff0f0); color: var(--status-down, #c0392b); }
.rdp-parsed-pending { background: var(--status-warn-bg);  color: var(--status-warn); }
.rdp-parsed-none    { background: var(--bg-secondary);    color: var(--text-muted); }

/* Actions */
.rdp-actions { display: flex; gap: 4px; white-space: nowrap; flex-wrap: wrap; }
.rdp-action-btn {
  padding: 3px 8px;
  font-size: 0.75rem;
  border-radius: 5px;
  cursor: pointer;
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  text-decoration: none;
  display: inline-block;
  transition: background 0.15s, color 0.15s;
}
.rdp-action-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.rdp-action-btn:not(:disabled):hover { background: var(--accent-primary); color: #fff; border-color: var(--accent-primary); }
.rdp-action-view  { color: var(--accent-primary); border-color: var(--accent-primary); }
.rdp-action-dl    { color: var(--text-secondary); }
.rdp-action-parse { color: var(--status-warn); border-color: var(--status-warn); }
.rdp-action-text  { color: var(--status-info);  border-color: var(--status-info); }
.rdp-action-rag   { color: #7c3aed; border-color: #7c3aed; }
.rdp-no-pdf { font-size: 0.73rem; color: var(--text-muted); }

/* RAG status badges */
.rdp-rag-badge {
  font-size: 0.68rem; padding: 1px 5px; border-radius: 8px; margin-left: 4px;
  display: inline-block;
}
.rdp-rag-embedded { background: #ede9fe; color: #7c3aed; }
.rdp-rag-chunked  { background: #f3f4f6; color: #6b7280; }
.rdp-rag-partial  { background: var(--status-warn-bg); color: var(--status-warn); }
.rdp-rag-failed   { background: var(--status-down-bg, #fff0f0); color: var(--status-down, #c0392b); }
.rdp-chunk-count  { font-size: 0.68rem; color: var(--text-muted); margin-left: 3px; }
.rdp-mock-hint     { font-size: 0.65rem; color: var(--text-muted); margin-left: 4px; font-style: italic; }
.rdp-local-hint    { font-size: 0.65rem; color: #389e0d; margin-left: 4px; font-weight: 500; }
.rdp-disabled-hint { font-size: 0.65rem; color: #fa8c16; margin-left: 4px; font-style: italic; }

/* ── Text excerpt modal ── */
.rdp-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.45);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.rdp-modal {
  background: var(--bg-primary);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.18);
  max-width: 720px;
  width: 100%;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.rdp-modal-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}
.rdp-modal-title { flex: 1; font-weight: 600; font-size: 0.9rem; color: var(--text-primary); }
.rdp-modal-meta  { font-size: 0.78rem; color: var(--text-muted); }
.rdp-modal-close {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1rem;
  color: var(--text-muted);
  padding: 2px 6px;
  border-radius: 4px;
}
.rdp-modal-close:hover { background: var(--bg-secondary); }
.rdp-modal-text {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  font-size: 0.82rem;
  line-height: 1.7;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-all;
  font-family: var(--font-mono, monospace);
  margin: 0;
}

/* Warnings */
.rdp-warnings {
  margin-top: 12px;
  padding: 10px 12px;
  background: var(--status-warn-bg);
  border-radius: 6px;
  border: 1px solid var(--status-warn);
}
.rdp-warnings-title { font-size: 0.8rem; font-weight: 600; color: var(--status-warn); margin-bottom: 4px; }
.rdp-warnings-list { margin: 0; padding-left: 18px; font-size: 0.78rem; color: var(--text-secondary); }
.rdp-warnings-list li { margin-bottom: 2px; }

/* Pending candidates */
.rdp-pending {
  margin-top: 12px;
  padding: 10px 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
  border: 1px dashed var(--border-color);
}
.rdp-pending-title { font-size: 0.8rem; color: var(--text-muted); margin-bottom: 8px; }
.rdp-pending-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px solid var(--border-color);
  font-size: 0.8rem;
}
.rdp-pending-item:last-child { border-bottom: none; }
.rdp-pending-title-text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rdp-link {
  color: var(--accent-primary);
  text-decoration: none;
  font-size: 0.78rem;
  flex-shrink: 0;
}
.rdp-link:hover { text-decoration: underline; }

/* Disclaimer */
.rdp-disclaimer {
  margin-top: 12px;
  font-size: 0.72rem;
  color: var(--text-muted);
  border-top: 1px solid var(--border-color);
  padding-top: 8px;
  line-height: 1.5;
}
</style>
