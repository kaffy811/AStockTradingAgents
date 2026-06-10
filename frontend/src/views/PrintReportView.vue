<template>
  <div class="print-shell">

    <!-- Toolbar: visible on screen, hidden when printing -->
    <div class="print-toolbar no-print">
      <button class="btn btn-secondary btn-sm" @click="router.back()">
        ← 返回
      </button>
      <span class="print-toolbar-hint">
        在下方预览报告内容。点击右侧按钮或使用浏览器 <kbd>Ctrl+P</kbd> / <kbd>⌘P</kbd> 打印 / 导出 PDF。
      </span>
      <button class="btn btn-secondary btn-sm" @click="doPrint">
        打印 / 导出 PDF
      </button>
    </div>

    <!-- Empty state (result was cleared or page refreshed) -->
    <div v-if="!result" class="print-empty no-print">
      <p>暂无可打印报告，请先生成或打开一份报告。</p>
      <RouterLink to="/" class="btn btn-secondary btn-sm">返回综合分析</RouterLink>
    </div>

    <!-- Report body -->
    <div v-else class="print-body">

      <!-- Document header -->
      <h1 class="print-doc-title">{{ printTitle }}</h1>
      <p class="print-doc-meta">生成时间：{{ displayTime }}</p>
      <hr class="print-divider" />

      <!-- Agent status -->
      <h2 class="print-agents-title">{{ _plbl(reportLang, 'agent_status') }}</h2>
      <table class="print-agents-table">
        <thead>
          <tr>
            <th>{{ _plbl(reportLang, 'col_module') }}</th>
            <th>{{ _plbl(reportLang, 'col_status') }}</th>
            <th>{{ _plbl(reportLang, 'col_note') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="{ key } in SECTION_DEFS" :key="key">
            <td>{{ AGENT_LABELS[key] ?? key }}</td>
            <td>{{ agents[key]?.status ?? '—' }}</td>
            <td>{{ agents[key]?.error  ?? '-' }}</td>
          </tr>
        </tbody>
      </table>
      <hr class="print-divider" />

      <!-- Data quality warnings -->
      <h2 class="print-warnings-title">{{ _plbl(reportLang, 'data_quality') }}</h2>
      <p v-if="!warnings.length" class="print-no-warnings">{{ _plbl(reportLang, 'no_warnings') }}</p>
      <ul v-else class="print-warnings-list">
        <li v-for="(w, i) in warnings" :key="i">{{ translateWarning(w) }}</li>
      </ul>
      <hr class="print-divider" />

      <!-- Main report -->
      <div class="print-section">
        <h2 class="print-section-title">{{ scopeTitle }}</h2>
        <MarkdownReport :content="result.report" />
      </div>

      <!-- Sub-reports (all expanded, fixed order) -->
      <div
        v-for="{ key } in SECTION_DEFS"
        :key="key"
        class="print-section"
      >
        <template v-if="result.sections?.[key]">
          <h2 class="print-section-title">{{ _plbl(reportLang, _SECTION_KEY_MAP[key] ?? key) }}</h2>
          <MarkdownReport :content="result.sections[key]" />
        </template>
      </div>

    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { usePrintStore } from '../stores/print.js'
import { AGENT_LABELS, SECTION_DEFS, translateWarning } from '../utils/warningMap.js'
import { buildReportIdentity } from '../utils/reportText.js'
import MarkdownReport from '../components/MarkdownReport.vue'

const router     = useRouter()
const printStore = usePrintStore()

const result = computed(() => printStore.result)

// ── Multilingual label tables ─────────────────────────────────────────────
const _PRINT_LABELS = {
  'zh-CN': {
    scope_comprehensive:         '综合分析报告',
    scope_technical_only:        '技术面分析报告',
    scope_fundamental_only:      '基本面分析报告',
    scope_peer_only:             '同行对比分析报告',
    scope_news_only:             '新闻面分析报告',
    scope_technical_fundamental: '技术面与基本面分析报告',
    section_technical:           '技术面分析',
    section_fundamental:         '基本面分析',
    section_peer_comparison:     '同行对比分析',
    section_news:                '新闻面分析',
    agent_status:                'Agent 执行状态',
    data_quality:                '数据质量提示',
    no_warnings:                 '暂无数据质量提示。',
    col_module:                  '模块',
    col_status:                  '状态',
    col_note:                    '说明',
  },
  'en-US': {
    scope_comprehensive:         'Comprehensive Analysis Report',
    scope_technical_only:        'Technical Analysis Report',
    scope_fundamental_only:      'Fundamental Analysis Report',
    scope_peer_only:             'Peer Comparison Report',
    scope_news_only:             'News Analysis Report',
    scope_technical_fundamental: 'Technical & Fundamental Report',
    section_technical:           'Technical Analysis',
    section_fundamental:         'Fundamental Analysis',
    section_peer_comparison:     'Peer Comparison',
    section_news:                'News Analysis',
    agent_status:                'Agent Execution Status',
    data_quality:                'Data Quality Notes',
    no_warnings:                 'No data quality issues.',
    col_module:                  'Module',
    col_status:                  'Status',
    col_note:                    'Note',
  },
  'zh-TW': {
    scope_comprehensive:         '綜合分析報告',
    scope_technical_only:        '技術面分析報告',
    scope_fundamental_only:      '基本面分析報告',
    scope_peer_only:             '同行對比分析報告',
    scope_news_only:             '新聞面分析報告',
    scope_technical_fundamental: '技術面與基本面分析報告',
    section_technical:           '技術面分析',
    section_fundamental:         '基本面分析',
    section_peer_comparison:     '同行對比分析',
    section_news:                '新聞面分析',
    agent_status:                'Agent 執行狀態',
    data_quality:                '數據質量提示',
    no_warnings:                 '暫無數據質量提示。',
    col_module:                  '模塊',
    col_status:                  '狀態',
    col_note:                    '說明',
  },
  'ja-JP': {
    scope_comprehensive:         '総合分析レポート',
    scope_technical_only:        'テクニカル分析レポート',
    scope_fundamental_only:      'ファンダメンタル分析レポート',
    scope_peer_only:             '同業比較レポート',
    scope_news_only:             'ニュース分析レポート',
    scope_technical_fundamental: 'テクニカル・ファンダメンタル分析レポート',
    section_technical:           'テクニカル分析',
    section_fundamental:         'ファンダメンタル分析',
    section_peer_comparison:     '同業比較',
    section_news:                'ニュース分析',
    agent_status:                'エージェント実行状況',
    data_quality:                'データ品質メモ',
    no_warnings:                 'データ品質の問題はありません。',
    col_module:                  'モジュール',
    col_status:                  'ステータス',
    col_note:                    '備考',
  },
  'ko-KR': {
    scope_comprehensive:         '종합 분석 보고서',
    scope_technical_only:        '기술 분석 보고서',
    scope_fundamental_only:      '기본 분석 보고서',
    scope_peer_only:             '동종 비교 보고서',
    scope_news_only:             '뉴스 분석 보고서',
    scope_technical_fundamental: '기술·기본 분석 보고서',
    section_technical:           '기술 분석',
    section_fundamental:         '기본 분석',
    section_peer_comparison:     '동종 비교',
    section_news:                '뉴스 분석',
    agent_status:                '에이전트 실행 상태',
    data_quality:                '데이터 품질 메모',
    no_warnings:                 '데이터 품질 문제 없음.',
    col_module:                  '모듈',
    col_status:                  '상태',
    col_note:                    '비고',
  },
  'es-ES': {
    scope_comprehensive:         'Informe de Análisis Integral',
    scope_technical_only:        'Informe de Análisis Técnico',
    scope_fundamental_only:      'Informe de Análisis Fundamental',
    scope_peer_only:             'Informe de Comparación entre Pares',
    scope_news_only:             'Informe de Análisis de Noticias',
    scope_technical_fundamental: 'Informe Técnico y Fundamental',
    section_technical:           'Análisis Técnico',
    section_fundamental:         'Análisis Fundamental',
    section_peer_comparison:     'Comparación entre Pares',
    section_news:                'Análisis de Noticias',
    agent_status:                'Estado de los Agentes',
    data_quality:                'Notas de Calidad de Datos',
    no_warnings:                 'Sin problemas de calidad de datos.',
    col_module:                  'Módulo',
    col_status:                  'Estado',
    col_note:                    'Nota',
  },
}

function _plbl(lang, key) {
  const tbl = _PRINT_LABELS[lang] ?? _PRINT_LABELS['zh-CN']
  return tbl[key] ?? (_PRINT_LABELS['zh-CN'][key] ?? key)
}

const _SECTION_KEY_MAP = {
  technical:       'section_technical',
  fundamental:     'section_fundamental',
  peer_comparison: 'section_peer_comparison',
  news:            'section_news',
}

const warnings   = computed(() => result.value?.metadata?.warnings ?? [])
const agents     = computed(() => result.value?.metadata?.agents   ?? {})

const analysisScope = computed(() =>
  result.value?.metadata?.analysis_scope || result.value?.analysis_scope || 'comprehensive'
)

const reportLang = computed(() =>
  result.value?.output_language || result.value?.metadata?.output_language || 'zh-CN'
)

const scopeTitle = computed(() => _plbl(reportLang.value, `scope_${analysisScope.value}`))

const printTitle = computed(() => {
  if (!result.value) return '综合分析报告'
  return `${buildReportIdentity(result.value)} ${scopeTitle.value}`
})

const displayTime = computed(() => {
  if (!result.value) return '—'
  const src = result.value.created_at ?? result.value.metadata?.generated_at
  if (!src) return '—'
  try {
    return new Date(src).toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: false,
    })
  } catch {
    return src
  }
})

function doPrint() {
  window.print()
}

const originalTitle = document.title

onMounted(async () => {
  if (!result.value) return
  const name = result.value.stock_name
  document.title = name
    ? `分析报告_${name}_${result.value.market}_${result.value.symbol}`
    : `分析报告_${result.value.market}_${result.value.symbol}`
  await nextTick()
  setTimeout(() => window.print(), 300)
})

onBeforeUnmount(() => {
  document.title = originalTitle
})
</script>

<style scoped>
/* Empty state — screen only */
.print-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 80px 24px;
  font-size: 14px;
  color: #6b7280;
}

kbd {
  font-family: monospace;
  font-size: 12px;
  background: #e5e7eb;
  border: 1px solid #d1d5db;
  border-radius: 3px;
  padding: 1px 5px;
  color: #374151;
}
</style>
