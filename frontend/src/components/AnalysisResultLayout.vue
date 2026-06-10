<template>
  <div class="result-layout">

    <!-- ── Sticky action bar ───────────────────────────────────────────────── -->
    <div class="result-action-bar">
      <!-- Anchor nav -->
      <div class="result-anchors">
        <button class="anchor-btn" @click="scrollTo('rl-chart')">
          <span class="anchor-full">技术图表</span>
          <span class="anchor-short">图表</span>
        </button>
        <button class="anchor-btn" @click="scrollTo('rl-industry')">
          <span class="anchor-full">行业热股</span>
          <span class="anchor-short">行业</span>
        </button>
        <button class="anchor-btn" @click="scrollTo('rl-report')">
          <span class="anchor-full">{{ reportAnchorLabel.full }}</span>
          <span class="anchor-short">{{ reportAnchorLabel.short }}</span>
        </button>
        <button class="anchor-btn" @click="scrollTo('rl-sections')">
          <span class="anchor-full">分项分析</span>
          <span class="anchor-short">分项</span>
        </button>
      </div>
      <!-- Per-view action buttons injected via slot -->
      <div class="result-actions">
        <button class="anchor-btn new-analysis-btn" @click="emit('new-analysis')">
          <span class="anchor-full">+ 新建分析</span>
          <span class="anchor-short">+ 新建</span>
        </button>
        <slot name="actions" />
      </div>
    </div>

    <!-- ── 技术走势 ────────────────────────────────────────────────────────── -->
    <div id="rl-chart" class="result-section">
      <div class="section-label">
        技术图表
        <span v-if="result.market || result.symbol" class="section-label-sub">
          {{ result.market }}/{{ result.symbol }}<template v-if="result.stock_name"> · {{ result.stock_name }}</template> · 可查看价格走势与均线指标
        </span>
      </div>
      <TechnicalChartPanel
        :market="result.market"
        :symbol="result.symbol"
        :visible="true"
        :height="340"
      />
    </div>

    <!-- ── 行业热度与动态同行 ──────────────────────────────────────────────── -->
    <div id="rl-industry" class="result-section">
      <div class="section-label">行业热度与动态同行</div>
      <IndustryHotStocksPanel
        :market="result.market"
        :symbol="result.symbol"
        :stock-name="result.stock_name || ''"
        :visible="true"
      />
    </div>

    <!-- ── 综合结论 ────────────────────────────────────────────────────────── -->
    <div id="rl-report" class="result-section">
      <div class="section-label">综合结论</div>
      <div class="card">
        <AgentStatusBar
          :metadata="result.metadata"
          :market="result.market"
          :symbol="result.symbol"
        />
        <WarningPanel :warnings="result.metadata?.warnings || []" />
        <hr class="divider" />
        <div class="report-identity-bar">
          <span class="rib-label">当前报告对象：</span>
          <span class="rib-id">
            <template v-if="result.stock_name">{{ result.stock_name }}（{{ result.market }}/{{ result.symbol }}）</template>
            <template v-else>{{ result.market }}/{{ result.symbol }}</template>
          </span>
          <div class="rib-badges">
            <span v-for="badge in activeBadges" :key="badge" class="rib-badge">{{ badge }}</span>
          </div>
        </div>
        <DataQualitySummary :result="result" />
        <ResearchActionPanel
          :result="result"
          :saved="saved"
          :saving="saving"
          @save="emit('save')"
          @reanalyze="emit('reanalyze')"
        />
        <MarkdownReport :content="result.report" />
      </div>
    </div>

    <!-- ── 分项分析 ────────────────────────────────────────────────────────── -->
    <div id="rl-sections" class="result-section result-section--last">
      <div class="section-label">分项分析</div>
      <SectionAccordion
        :sections="result.sections"
        :agents="result.metadata?.agents || {}"
      />
    </div>

  </div>
</template>

<script setup>
import { computed } from 'vue'
import TechnicalChartPanel    from './TechnicalChartPanel.vue'
import IndustryHotStocksPanel from './IndustryHotStocksPanel.vue'
import AgentStatusBar         from './AgentStatusBar.vue'
import WarningPanel           from './WarningPanel.vue'
import MarkdownReport         from './MarkdownReport.vue'
import SectionAccordion       from './SectionAccordion.vue'
import DataQualitySummary     from './DataQualitySummary.vue'
import ResearchActionPanel    from './ResearchActionPanel.vue'

const props = defineProps({
  result: { type: Object, required: true },
  saved:  { type: Boolean, default: false },
  saving: { type: Boolean, default: false },
})

const emit = defineEmits(['save', 'reanalyze', 'new-analysis'])

function scrollTo(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// ── Scope helpers ─────────────────────────────────────────────────────────────
const _SCOPE_ANCHOR = {
  comprehensive:         { full: '综合报告',       short: '综合' },
  technical_only:        { full: '技术面报告',     short: '技术' },
  fundamental_only:      { full: '基本面报告',     short: '基本面' },
  peer_only:             { full: '同行对比报告',   short: '同行' },
  news_only:             { full: '新闻面报告',     short: '新闻' },
  technical_fundamental: { full: '技术+基本面报告', short: '双维' },
}

const analysisScope = computed(
  () => props.result?.metadata?.analysis_scope
     || props.result?.analysis_scope
     || 'comprehensive'
)

const reportAnchorLabel = computed(
  () => _SCOPE_ANCHOR[analysisScope.value] || _SCOPE_ANCHOR.comprehensive
)

// Dynamic rib-badges: only show sections that actually exist
const _SECTION_BADGE_MAP = {
  technical:       { label: '技术图表',   hkLabel: null },
  fundamental:     { label: '基本面',     hkLabel: null },
  peer_comparison: { label: '同行对比',   hkLabel: '港股同行对比' },
  news:            { label: '新闻信息',   hkLabel: null },
}

const activeBadges = computed(() => {
  const sections = props.result?.sections || {}
  const agents   = props.result?.metadata?.agents || {}
  const isHK     = props.result?.market === 'HK'
  return Object.keys(_SECTION_BADGE_MAP)
    .filter(key => {
      const content = sections[key]
      const status  = agents[key]?.status
      return content && status !== 'skipped'
    })
    .map(key => {
      const def = _SECTION_BADGE_MAP[key]
      return (isHK && def.hkLabel) ? def.hkLabel : def.label
    })
})
</script>

<style scoped>
.result-layout {
  display: flex;
  flex-direction: column;
}

/* ── Sticky action bar ── */
.result-action-bar {
  position: sticky;
  top: 0;
  z-index: 50;
  /* Match page background so the bar is invisible before sticking;
     box-shadow appears once content scrolls underneath. */
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 0;
  margin-bottom: 20px;
}

.result-anchors {
  display: flex;
  gap: 4px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  white-space: nowrap;
  /* hide scrollbar but allow scroll on mobile */
  scrollbar-width: none;
}
.result-anchors::-webkit-scrollbar { display: none; }

.anchor-btn {
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 500;
  color: var(--muted);
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 20px;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
  flex-shrink: 0;
}

.anchor-btn:hover {
  color: var(--accent);
  background: var(--status-info-bg);
  border-color: var(--border-glow);
}

.result-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* ── Report identity bar ── */
.report-identity-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 16px;
  background: var(--surface-hover);
  border: 1px solid var(--status-info-ring);
  border-radius: 6px;
  font-size: 12px;
}

.rib-label {
  color: var(--muted);
  white-space: nowrap;
  flex-shrink: 0;
}

.rib-id {
  font-weight: 600;
  color: var(--text);
  font-family: monospace;
  word-break: break-all;
}

.rib-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-left: auto;
}

.rib-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 7px;
  background: var(--status-info-bg);
  border: 1px solid var(--status-info-ring);
  border-radius: 4px;
  color: var(--accent);
  white-space: nowrap;
}

@media (max-width: 540px) {
  .rib-badges {
    margin-left: 0;
    width: 100%;
  }
}

/* ── Sections ── */
.result-section {
  margin-bottom: 24px;
  /* leave room above for the sticky bar (~48px bar + 8px gap) */
  scroll-margin-top: 60px;
}

.result-section--last {
  margin-bottom: 32px;
}

.section-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 10px;
  padding-left: 2px;
}

.section-label-sub {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
  color: var(--muted);
  opacity: 0.75;
}

/* ── New analysis button ── */
.new-analysis-btn {
  color: var(--accent);
  border-color: var(--border-glow);
  background: var(--surface-hover);
}

.new-analysis-btn:hover {
  background: var(--status-info-bg);
}

/* ── Anchor full/short text ── */
.anchor-short { display: none; }

/* ── Mobile ── */
@media (max-width: 480px) {
  .anchor-full  { display: none; }
  .anchor-short { display: inline; }
}

@media (max-width: 540px) {
  .result-action-bar {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }

  .result-actions {
    width: 100%;
    justify-content: flex-start;
  }

  /* Sticky bar is ~85px tall on mobile (two rows + padding).
     Override the desktop 60px so anchor-scroll sections are not
     hidden underneath the taller bar. */
  .result-section {
    scroll-margin-top: 92px;
  }
}
</style>
