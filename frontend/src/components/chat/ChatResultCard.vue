<template>
  <div v-if="card" class="result-card" :class="`result-card--${card.type}`">

    <!-- ── stock_summary ──────────────────────────────────────────────────── -->
    <template v-if="card.type === 'stock_summary'">
      <div class="rc-header">
        <div class="rc-stock-title">
          <span class="rc-market-tag">{{ card.data.market }}</span>
          {{ card.data.name }}
          <span class="rc-symbol">{{ card.data.symbol }}</span>
        </div>
        <div class="rc-price" :class="priceClass(card.data.changeDir)">
          {{ card.data.price }}
          <span class="rc-change">{{ card.data.changePct }}</span>
        </div>
      </div>
      <p class="rc-summary">{{ card.data.summary }}</p>
      <div class="rc-actions">
        <template v-for="link in card.data.links" :key="link.label">
          <RouterLink v-if="link.path" :to="link.path" class="rc-btn rc-btn--secondary">
            {{ link.label }}
          </RouterLink>
          <button v-else-if="link.action" class="rc-btn rc-btn--primary" @click="$emit('action', link)">
            {{ link.label }}
          </button>
        </template>
      </div>
    </template>

    <!-- ── report_link ────────────────────────────────────────────────────── -->
    <template v-else-if="card.type === 'report_link'">
      <div class="rc-header">
        <span class="rc-tag rc-tag--report">报告已生成</span>
        <span class="rc-stock-name">{{ card.data.name }}（{{ card.data.market }}/{{ card.data.symbol }}）</span>
      </div>
      <div class="rc-report-meta">
        <span class="rc-badge">{{ card.data.scope }}</span>
        <span class="rc-verdict" :class="verdictClass(card.data.verdict)">{{ card.data.verdict }}</span>
      </div>
      <div class="rc-actions">
        <RouterLink v-for="link in card.data.links" :key="link.label" :to="link.path" class="rc-btn rc-btn--primary">
          {{ link.label }}
        </RouterLink>
      </div>
    </template>

    <!-- ── watchlist_success ──────────────────────────────────────────────── -->
    <template v-else-if="card.type === 'watchlist_success'">
      <div class="rc-header">
        <span class="rc-tag rc-tag--success">✓ 已加入自选股</span>
        <span class="rc-stock-name">{{ card.data.name }}（{{ card.data.market }}/{{ card.data.symbol }}）</span>
      </div>
      <div class="rc-actions">
        <RouterLink v-for="link in card.data.links" :key="link.label" :to="link.path" class="rc-btn rc-btn--secondary">
          {{ link.label }}
        </RouterLink>
      </div>
    </template>

    <!-- ── compare_link ───────────────────────────────────────────────────── -->
    <template v-else-if="card.type === 'compare_link'">
      <div class="rc-header">
        <span class="rc-tag rc-tag--compare">多股对比</span>
      </div>
      <div class="rc-stock-chips">
        <span v-for="s in card.data.stocks" :key="s.symbol" class="rc-stock-chip">
          {{ s.name }}
        </span>
      </div>
      <p class="rc-disclaimer-mini">研究维度对比，不代表投资价值判断。</p>
      <div class="rc-actions">
        <RouterLink v-for="link in card.data.links" :key="link.label" :to="link.path" class="rc-btn rc-btn--primary">
          {{ link.label }}
        </RouterLink>
      </div>
    </template>

    <!-- ── watchlist_list ───────────────────────────────────────────────── -->
    <template v-else-if="card.type === 'watchlist_list'">
      <div class="rc-header">
        <span class="rc-tag rc-tag--watchlist">自选股</span>
        <span class="rc-hint">共 {{ card.data.total }} 只，仅供研究线索参考</span>
      </div>
      <div class="rc-watchlist-list">
        <div v-for="item in card.data.items" :key="item.symbol" class="rc-watchlist-item">
          <span class="rc-market-tag">{{ item.market }}</span>
          <span class="rc-watchlist-symbol">{{ item.symbol }}</span>
          <span v-if="item.note" class="rc-watchlist-note">{{ item.note }}</span>
        </div>
        <div v-if="card.data.items.length === 0" class="rc-empty-hint">暂无自选股</div>
      </div>
      <div class="rc-actions">
        <RouterLink v-for="link in card.data.links" :key="link.label" :to="link.path" class="rc-btn rc-btn--secondary">
          {{ link.label }}
        </RouterLink>
      </div>
    </template>

    <!-- ── report_list ───────────────────────────────────────────────────── -->
    <template v-else-if="card.type === 'report_list'">
      <div class="rc-header">
        <span class="rc-tag rc-tag--report">历史报告</span>
        <span class="rc-hint">共 {{ card.data.items.length }} 份</span>
      </div>
      <div class="rc-report-list">
        <div v-for="item in card.data.items" :key="item.id" class="rc-report-item">
          <span class="rc-report-stock">{{ item.stock_name }}</span>
          <span class="rc-badge">{{ item.analysis_scope }}</span>
          <span class="rc-report-date">{{ item.created_at ? item.created_at.slice(0, 10) : '' }}</span>
        </div>
        <div v-if="card.data.items.length === 0" class="rc-empty-hint">暂无历史报告</div>
      </div>
      <div class="rc-actions">
        <RouterLink v-for="link in card.data.links" :key="link.label" :to="link.path" class="rc-btn rc-btn--secondary">
          {{ link.label }}
        </RouterLink>
      </div>
    </template>

    <!-- ── industry_hot ───────────────────────────────────────────────────── -->
    <template v-else-if="card.type === 'industry_hot'">
      <div class="rc-header">
        <span class="rc-tag rc-tag--industry">行业热度</span>
        <span class="rc-hint">研究线索，不代表投资价值</span>
      </div>
      <div class="rc-industry-list">
        <div v-for="ind in card.data.items" :key="ind.code" class="rc-industry-item">
          <span class="rc-industry-name">{{ ind.name }}</span>
          <span class="rc-industry-score">热度 {{ ind.hotScore }}</span>
          <span class="rc-industry-change" :class="ind.changePct.startsWith('+') ? 'is-up' : 'is-down'">
            {{ ind.changePct }}
          </span>
        </div>
      </div>
      <div class="rc-actions">
        <RouterLink v-for="link in card.data.links" :key="link.label" :to="link.path" class="rc-btn rc-btn--secondary">
          {{ link.label }}
        </RouterLink>
      </div>
    </template>

    <!-- ── watchlist_action (C5) ────────────────────────────────────────── -->
    <template v-else-if="card.type === 'watchlist_action'">
      <div class="rc-header">
        <span class="rc-tag" :class="card.data.already_exists ? 'rc-tag--warn' : 'rc-tag--success'">
          {{ card.data.already_exists ? '已在自选股' : '✓ 已加入自选股' }}
        </span>
        <span class="rc-stock-name">{{ card.data.name }}（{{ card.data.market }}/{{ card.data.symbol }}）</span>
      </div>
      <div class="rc-actions">
        <RouterLink v-for="link in card.data.links" :key="link.label" :to="link.path" class="rc-btn rc-btn--secondary">
          {{ link.label }}
        </RouterLink>
      </div>
    </template>

    <!-- ── analysis_run (C5) ───────────────────────────────────────────── -->
    <template v-else-if="card.type === 'analysis_run'">
      <div class="rc-header">
        <span class="rc-tag rc-tag--report">分析任务已提交</span>
        <span class="rc-stock-name">{{ card.data.name }}（{{ card.data.market }}/{{ card.data.symbol }}）</span>
      </div>
      <div class="rc-report-meta">
        <span class="rc-badge">{{ card.data.scope }}</span>
        <span class="rc-badge rc-badge--run">{{ card.data.status }}</span>
      </div>
      <p class="rc-run-hint">报告生成需约 30～60 秒，完成后可在报告中心查看。</p>
      <div class="rc-actions">
        <template v-for="link in card.data.links" :key="link.label">
          <RouterLink :to="link.path" class="rc-btn rc-btn--primary">
            {{ link.label }}
          </RouterLink>
        </template>
      </div>
    </template>

  </div>
</template>

<script setup>
import { RouterLink } from 'vue-router'

const props = defineProps({
  card: { type: Object, default: null },
})

const emit = defineEmits(['action'])

function priceClass(dir) {
  if (dir === 'up')   return 'is-up'
  if (dir === 'down') return 'is-down'
  return ''
}

function verdictClass(verdict) {
  if (!verdict) return ''
  if (/偏强|strong/i.test(verdict)) return 'is-up'
  if (/偏弱|weak/i.test(verdict))   return 'is-down'
  return 'is-neutral'
}
</script>

<style scoped>
.result-card {
  margin-top: 10px;
  background: var(--surface-card-strong, var(--surface));
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-card);
  padding: 14px 16px;
  box-shadow: var(--shadow-card);
}

.rc-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.rc-tag {
  font-size: 11px;
  font-weight: 700;
  border-radius: 6px;
  padding: 2px 8px;
}
.rc-tag--report   { background: var(--status-info-bg);  color: var(--accent); }
.rc-tag--success  { background: var(--status-down-bg);  color: var(--success); }
.rc-tag--compare  { background: var(--status-warn-bg);  color: var(--warn); }
.rc-tag--industry { background: var(--status-info-bg);  color: var(--accent); }

.rc-market-tag {
  font-size: 11px;
  background: var(--surface2);
  border-radius: 4px;
  padding: 1px 6px;
  font-weight: 700;
  color: var(--muted);
}

.rc-stock-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 700;
  font-size: 15px;
  color: var(--text);
}

.rc-symbol {
  font-size: 12px;
  color: var(--muted);
  font-weight: 400;
}

.rc-price {
  margin-left: auto;
  font-size: 18px;
  font-weight: 700;
}
.rc-price.is-up   { color: var(--up-color); }
.rc-price.is-down { color: var(--down-color); }

.rc-change {
  font-size: 13px;
  font-weight: 500;
  margin-left: 4px;
}

.rc-summary {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 12px;
  line-height: 1.5;
}

.rc-stock-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}

.rc-report-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.rc-badge {
  font-size: 11px;
  background: var(--surface2);
  border-radius: 5px;
  padding: 2px 8px;
  color: var(--muted);
  font-weight: 600;
}
.rc-verdict {
  font-size: 12px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 5px;
}
.rc-verdict.is-up      { background: var(--status-up-bg);   color: var(--up-color); }
.rc-verdict.is-down    { background: var(--status-down-bg); color: var(--down-color); }
.rc-verdict.is-neutral { background: var(--status-warn-bg); color: var(--warn); }

.rc-hint {
  font-size: 11px;
  color: var(--muted);
  margin-left: auto;
}

.rc-stock-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.rc-stock-chip {
  background: var(--surface2);
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}

.rc-disclaimer-mini {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 10px;
}

.rc-tag--watchlist { background: var(--status-warn-bg); color: var(--warn); }

.rc-watchlist-list { margin-bottom: 10px; }
.rc-watchlist-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid var(--border-soft);
  font-size: 13px;
}
.rc-watchlist-item:last-child { border-bottom: none; }
.rc-watchlist-symbol { font-weight: 600; color: var(--text); flex: 1; }
.rc-watchlist-note   { font-size: 11px; color: var(--muted); }

.rc-report-list { margin-bottom: 10px; }
.rc-report-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px solid var(--border-soft);
  font-size: 13px;
}
.rc-report-item:last-child { border-bottom: none; }
.rc-report-stock { font-weight: 600; color: var(--text); flex: 1; }
.rc-report-date  { font-size: 11px; color: var(--muted); }

.rc-empty-hint {
  font-size: 12px;
  color: var(--muted);
  padding: 6px 0;
}

.rc-industry-list { margin-bottom: 10px; }
.rc-industry-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px solid var(--border-soft);
  font-size: 13px;
}
.rc-industry-item:last-child { border-bottom: none; }
.rc-industry-name  { flex: 1; font-weight: 600; color: var(--text); }
.rc-industry-score { font-size: 12px; color: var(--muted); }
.rc-industry-change { font-size: 12px; font-weight: 600; min-width: 54px; text-align: right; }
.rc-industry-change.is-up   { color: var(--up-color); }
.rc-industry-change.is-down { color: var(--down-color); }

.rc-tag--warn { background: var(--status-warn-bg); color: var(--warn); }

.rc-badge--run {
  background: var(--status-info-bg);
  color: var(--accent);
}

.rc-run-hint {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 10px;
  line-height: 1.4;
}

.rc-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.rc-btn {
  display: inline-block;
  font-size: 13px;
  font-weight: 600;
  border-radius: var(--radius-control);
  padding: 7px 16px;
  text-decoration: none;
  cursor: pointer;
  border: none;
  transition: opacity 0.15s, transform 0.1s;
}
.rc-btn:active { transform: scale(0.98); }

.rc-btn--primary {
  background: var(--accent-gradient, var(--accent));
  color: white;
}
.rc-btn--primary:hover { opacity: 0.9; }

.rc-btn--secondary {
  background: var(--surface2);
  color: var(--text);
  border: 1px solid var(--border-soft);
}
.rc-btn--secondary:hover { background: var(--surface-hover); }
</style>
