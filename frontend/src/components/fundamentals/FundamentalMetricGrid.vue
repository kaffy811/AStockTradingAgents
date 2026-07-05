<template>
  <div class="fmg-grid" v-if="metrics.length > 0">
    <div v-for="m in metrics" :key="m.field || m.label" class="fmg-card" :class="valueClass(m)">
      <div class="fmg-label">{{ m.label }}</div>
      <div class="fmg-value">{{ m.value }}</div>
    </div>
  </div>
</template>

<script setup>
defineProps({ metrics: { type: Array, default: () => [] } })

function valueClass(m) {
  if (m.raw == null || !Number.isFinite(Number(m.raw))) return ''
  const f = m.field || ''
  const isChange = /yoy|pct|change|growth|margin|ratio_pct/.test(f)
  if (!isChange) return ''
  return Number(m.raw) > 0 ? 'up' : Number(m.raw) < 0 ? 'dn' : ''
}
</script>

<style scoped>
.fmg-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.fmg-card { background: var(--surface2); border-radius: 8px; padding: 10px 12px; }
.fmg-label { font-size: 11px; color: var(--muted); margin-bottom: 4px; }
.fmg-value { font-size: 15px; font-weight: 600; color: var(--text); }
.fmg-card.up .fmg-value { color: var(--status-up, #e04040); }
.fmg-card.dn .fmg-value { color: var(--status-down, #00a870); }
@media (max-width: 540px) { .fmg-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
