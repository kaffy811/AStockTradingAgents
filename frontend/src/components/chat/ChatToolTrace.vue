<template>
  <div v-if="items.length" class="tool-trace">
    <div class="tool-trace-header" @click="expanded = !expanded">
      <span class="tool-trace-icon">⚙</span>
      <span class="tool-trace-label">{{ t('chat_tool_calls') }}</span>
      <span class="tool-trace-count">{{ items.length }}</span>
      <span class="tool-trace-chevron" :class="{ 'is-open': expanded }">▾</span>
    </div>
    <transition name="trace-expand">
      <div v-if="expanded" class="tool-trace-list">
        <div
          v-for="(item, i) in items"
          :key="i"
          class="tool-trace-item"
          :class="`is-${item.status}`"
        >
          <span class="trace-status-icon">
            {{ item.status === 'success' ? '✓' : item.status === 'running' ? '⋯' : item.status === 'failed' ? '✗' : '○' }}
          </span>
          <span class="trace-name">{{ TOOL_LABELS[item.name] ?? item.name }}</span>
          <span v-if="item.detail" class="trace-detail">{{ item.detail }}</span>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from '../../utils/i18n.js'

const { t } = useI18n()

const TOOL_LABELS = {
  resolve_stock_tool:            '解析股票代码',
  get_quote_tool:                '获取实时行情',
  get_kline_summary_tool:        '分析 K 线走势',
  get_fundamentals_tool:         '读取基本面数据',
  get_latest_news_tool:          '搜索近期新闻',
  get_peer_comparison_tool:      '同行对比查询',
  get_industry_hot_tool:         '查询行业热门股',
  get_watchlist_tool:            '读取自选股列表',
  get_recent_reports_tool:       '查找历史报告',
  get_report_detail_tool:        '读取报告详情',
  create_analysis_run_tool:      '创建报告生成任务',
  add_to_watchlist_tool:         '添加到自选股',
  remove_from_watchlist_tool:    '从自选股移除',
  create_compare_selection_tool: '准备多股对比',
  // Phase 1: FinancialAgent real tools
  stock_quote:                   '获取实时报价',
  stock_kline:                   '分析近期走势',
  financial_news:                '搜索相关新闻',
  us_quote:                      '获取美股报价',
  us_news:                       '搜索美股新闻',
  // Phase 2A: financial knowledge-base RAG
  financial_rag_search:          '检索金融知识库',
  // Phase 2B: official report search + verify + ingest
  official_financial_report_search: '搜索官方财报',
  verify_financial_report:          '审核财报来源',
  financial_document_ingest:        '导入财报知识库',
}

const props = defineProps({
  items: { type: Array, default: () => [] },
})

const expanded = ref(true)
</script>

<style scoped>
.tool-trace {
  margin: 10px 0 6px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  overflow: hidden;
  background: var(--surface2);
  font-size: 12px;
}

.tool-trace-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  cursor: pointer;
  user-select: none;
  color: var(--muted);
  background: var(--surface2);
  transition: background var(--motion-fast);
}

.tool-trace-header:hover { background: var(--surface-hover); }

.tool-trace-icon  { font-size: 11px; }
.tool-trace-label { font-weight: 600; flex: 1; }
.tool-trace-count {
  background: var(--status-info-bg);
  color: var(--accent);
  border-radius: 10px;
  padding: 1px 7px;
  font-size: 11px;
  font-weight: 700;
}
.tool-trace-chevron {
  transition: transform var(--motion-fast);
  font-size: 14px;
}
.tool-trace-chevron.is-open { transform: rotate(180deg); }

.tool-trace-list {
  border-top: 1px solid var(--border-soft);
  padding: 6px 0;
}

.tool-trace-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px;
  color: var(--muted);
  transition: background var(--motion-fast);
}
.tool-trace-item:hover { background: var(--surface-hover); }

.trace-status-icon {
  font-size: 12px;
  width: 14px;
  text-align: center;
  flex-shrink: 0;
}
.is-success .trace-status-icon { color: var(--success); }
.is-running .trace-status-icon { color: var(--warn); animation: pulse 1s infinite; }
.is-failed  .trace-status-icon { color: var(--danger); }

.trace-name   { font-weight: 500; color: var(--text-secondary); }
.trace-detail { color: var(--muted); font-size: 11px; margin-left: 4px; }

/* expand transition */
.trace-expand-enter-active,
.trace-expand-leave-active { transition: all 0.2s ease; }
.trace-expand-enter-from,
.trace-expand-leave-to   { opacity: 0; max-height: 0; }
.trace-expand-enter-to,
.trace-expand-leave-from { opacity: 1; max-height: 400px; }

@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
</style>
