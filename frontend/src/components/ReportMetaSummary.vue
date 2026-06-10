<template>
  <div class="rms-card card">

    <div class="rms-grid">

      <!-- ── 报告类型 & 保存方式 ──────────────────────────────────────────────── -->
      <div class="rms-section">
        <span class="rms-section-label">报告类型</span>
        <div class="rms-row">
          <span :class="['rms-scope-badge', scopeBadgeClass]">{{ scopeText }}</span>
          <span class="rms-tag">{{ report?.auto_saved ? '自动保存' : '手动保存' }}</span>
        </div>
      </div>

      <!-- ── 覆盖维度 ──────────────────────────────────────────────────────────── -->
      <div class="rms-section">
        <span class="rms-section-label">覆盖维度</span>
        <div class="rms-row rms-row--wrap">
          <template v-if="coverageDims.length > 0">
            <span
              v-for="dim in coverageDims"
              :key="dim.key"
              class="rms-dim-badge"
            >{{ dim.label }}</span>
          </template>
          <span v-else class="rms-empty-text">数据不可用</span>
        </div>
      </div>

      <!-- ── Agent 状态 ─────────────────────────────────────────────────────────── -->
      <div v-if="agentList.length > 0" class="rms-section">
        <span class="rms-section-label">Agent 执行状态</span>
        <div class="rms-agent-list">
          <div
            v-for="agent in agentList"
            :key="agent.name"
            class="rms-agent-row"
          >
            <span class="rms-agent-name">{{ agent.label }}</span>
            <span :class="['rms-agent-status', `rms-agent-status--${agent.status}`]">
              {{ agentStatusLabel(agent.status) }}
            </span>
          </div>
        </div>
      </div>

      <!-- ── 数据边界 (warnings) ────────────────────────────────────────────────── -->
      <div v-if="warnings.length > 0" class="rms-section">
        <span class="rms-section-label">数据边界提示</span>
        <ul class="rms-warning-list">
          <li
            v-for="(w, i) in warnings"
            :key="i"
            class="rms-warning-item"
          >{{ w }}</li>
        </ul>
      </div>

    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  report: { type: Object, default: null },
})

// ── Scope ─────────────────────────────────────────────────────────────────────
const _SCOPE_LABELS = {
  comprehensive:         '综合分析',
  technical_only:        '仅技术面',
  fundamental_only:      '仅基本面',
  peer_only:             '仅同行对比',
  news_only:             '仅新闻面',
  technical_fundamental: '技术+基本面',
}

const scopeText = computed(() => {
  const s = props.report?.analysis_scope
  return _SCOPE_LABELS[s] || '综合分析'
})

const scopeBadgeClass = computed(() => {
  const s = props.report?.analysis_scope
  return (!s || s === 'comprehensive') ? 'rms-scope-badge--comprehensive' : 'rms-scope-badge--partial'
})

// ── Coverage dimensions from sections keys ────────────────────────────────────
const _DIM_LABELS = {
  technical:       '技术面',
  fundamental:     '基本面',
  peer_comparison: '同行对比',
  news:            '新闻',
}

const coverageDims = computed(() => {
  const sections = props.report?.sections
  if (!sections || typeof sections !== 'object') return []
  return Object.keys(sections)
    .filter(k => _DIM_LABELS[k] && sections[k])
    .map(k => ({ key: k, label: _DIM_LABELS[k] }))
})

// ── Agent list from metadata.agents ──────────────────────────────────────────
const _AGENT_LABELS = {
  technical_agent:    '技术面 Agent',
  fundamental_agent:  '基本面 Agent',
  peer_agent:         '同行 Agent',
  news_agent:         '新闻 Agent',
  synthesis_agent:    '综合分析 Agent',
}

const agentList = computed(() => {
  const agents = props.report?.metadata?.agents
  if (!agents || typeof agents !== 'object') return []
  return Object.entries(agents).map(([name, info]) => ({
    name,
    label:  _AGENT_LABELS[name] || name,
    status: (typeof info === 'string' ? info : info?.status) || 'unknown',
  }))
})

function agentStatusLabel(status) {
  const MAP = {
    success:  '成功',
    skipped:  '已跳过',
    failed:   '失败',
    timeout:  '超时',
    degraded: '降级',
    unknown:  '未知',
  }
  return MAP[status] || status
}

// ── Warnings (first 3) ────────────────────────────────────────────────────────
const warnings = computed(() => {
  const ws = props.report?.metadata?.warnings
  if (!Array.isArray(ws) || ws.length === 0) return []
  return ws.slice(0, 3)
})
</script>

<style scoped>
.rms-card {
  padding: 14px 20px;
}

.rms-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ── Section ── */
.rms-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rms-section-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}

/* ── Rows ── */
.rms-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.rms-row--wrap {
  flex-wrap: wrap;
}

/* ── Scope badge ── */
.rms-scope-badge {
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
  padding: 2px 8px;
  border: 1px solid transparent;
}

.rms-scope-badge--comprehensive {
  color: var(--accent);
  background: var(--status-info-bg);
  border-color: var(--status-info-ring);
}

.rms-scope-badge--partial {
  color: var(--muted);
  background: var(--surface2);
  border-color: var(--border);
}

/* ── Small tag ── */
.rms-tag {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 6px;
}

/* ── Dimension badges ── */
.rms-dim-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  background: var(--status-info-bg);
  border: 1px solid var(--status-info-ring);
  border-radius: 4px;
  padding: 2px 8px;
}

.rms-empty-text {
  font-size: 12px;
  color: var(--muted);
  font-style: italic;
}

/* ── Agent list ── */
.rms-agent-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rms-agent-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}

.rms-agent-name {
  color: var(--text);
  font-size: 12px;
}

.rms-agent-status {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 3px;
  white-space: nowrap;
}

.rms-agent-status--success  { background: var(--status-down-bg); color: var(--success); }
.rms-agent-status--skipped  { background: var(--surface2);           color: var(--muted);   }
.rms-agent-status--failed   { background: var(--status-up-bg);   color: var(--danger);  }
.rms-agent-status--timeout  { background: var(--status-warn-bg);  color: var(--warn);    }
.rms-agent-status--degraded { background: var(--status-warn-bg);  color: var(--warn);    }
.rms-agent-status--unknown  { background: var(--surface2);           color: var(--muted);   }

/* ── Warnings ── */
.rms-warning-list {
  margin: 0;
  padding: 0 0 0 16px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.rms-warning-item {
  font-size: 11px;
  color: var(--warn);
  line-height: 1.4;
}

/* ── Mobile ── */
@media (max-width: 375px) {
  .rms-card { padding: 12px 14px; }
}
</style>
