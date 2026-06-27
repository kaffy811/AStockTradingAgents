<template>
  <div v-if="dq && dq.level" class="dqc" :class="`dqc--${dq.level}`">
    <!-- Header row -->
    <div class="dqc-header">
      <span class="dqc-icon">{{ _icon }}</span>
      <span class="dqc-label">数据质量</span>
      <span class="dqc-badge">{{ _levelLabel }}</span>
    </div>

    <!-- Reason -->
    <p v-if="dq.reason" class="dqc-reason">{{ dq.reason }}</p>

    <!-- Verified / missing columns -->
    <div v-if="dq.verified_data?.length || dq.missing_data?.length" class="dqc-grid">
      <div v-if="dq.verified_data?.length" class="dqc-col dqc-col--ok">
        <div class="dqc-col-title">已获取</div>
        <ul>
          <li v-for="item in dq.verified_data" :key="item">{{ item }}</li>
        </ul>
      </div>
      <div v-if="dq.missing_data?.length" class="dqc-col dqc-col--miss">
        <div class="dqc-col-title">缺失</div>
        <ul>
          <li v-for="item in dq.missing_data" :key="item">{{ item }}</li>
        </ul>
      </div>
    </div>

    <!-- Warning flags -->
    <div v-if="dq.warning_flags?.length" class="dqc-flags">
      <span v-for="flag in dq.warning_flags" :key="flag" class="dqc-flag">{{ flag }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  dq: { type: Object, default: null },
})

const _LEVEL_LABELS = {
  high:         '高',
  medium:       '中',
  low:          '低',
  insufficient: '不足',
}
const _LEVEL_ICONS = {
  high:         '✓',
  medium:       '◑',
  low:          '⚠',
  insufficient: '✕',
}

const _levelLabel = computed(() => _LEVEL_LABELS[props.dq?.level] ?? props.dq?.level ?? '')
const _icon       = computed(() => _LEVEL_ICONS[props.dq?.level] ?? '?')
</script>

<style scoped>
.dqc {
  margin-top: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--border-soft);
  background: var(--surface2);
  font-size: 12px;
}

/* Level color accents */
.dqc--high         { border-left: 3px solid var(--status-up, #22c55e); }
.dqc--medium       { border-left: 3px solid #f59e0b; }
.dqc--low          { border-left: 3px solid #f97316; }
.dqc--insufficient { border-left: 3px solid var(--status-down, #ef4444); }

.dqc-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.dqc-icon   { font-size: 13px; font-weight: 700; }
.dqc-label  { font-weight: 600; color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
.dqc-badge  {
  margin-left: auto;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 10px;
  background: var(--surface3, rgba(0,0,0,0.06));
  color: var(--text);
}

.dqc--high         .dqc-icon { color: var(--status-up, #22c55e); }
.dqc--medium       .dqc-icon { color: #f59e0b; }
.dqc--low          .dqc-icon { color: #f97316; }
.dqc--insufficient .dqc-icon { color: var(--status-down, #ef4444); }

.dqc-reason {
  margin: 4px 0 6px;
  color: var(--muted);
  line-height: 1.4;
}

.dqc-grid {
  display: flex;
  gap: 12px;
  margin-top: 4px;
}
.dqc-col { flex: 1; }
.dqc-col-title {
  font-weight: 600;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 3px;
}
.dqc-col--ok   .dqc-col-title { color: var(--status-up, #22c55e); }
.dqc-col--miss .dqc-col-title { color: var(--status-down, #ef4444); }

.dqc-col ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.dqc-col ul li {
  font-size: 11px;
  color: var(--text);
}
.dqc-col--ok   ul li::before { content: '✓ '; color: var(--status-up, #22c55e); }
.dqc-col--miss ul li::before { content: '✕ '; color: var(--status-down, #ef4444); }

.dqc-flags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}
.dqc-flag {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 10px;
  background: rgba(249, 115, 22, 0.12);
  color: #c2410c;
  border: 1px solid rgba(249, 115, 22, 0.25);
}
</style>
