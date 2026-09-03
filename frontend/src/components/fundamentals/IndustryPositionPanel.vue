<template>
  <div class="ipp-root">
    <!-- Header: industry name + level -->
    <div v-if="industryName" class="ipp-industry-header">
      <span class="ipp-industry-name">{{ industryName }}</span>
      <span v-if="industryLevel" class="ipp-industry-level">{{ industryLevel }}</span>
    </div>

    <!-- Unavailable -->
    <div v-if="isUnavailable" class="ipp-unavailable">
      <span class="ipp-unavail-icon">🏭</span>
      <p class="ipp-unavail-text">{{ unavailableMsg }}</p>
    </div>

    <!-- Rank cards grid -->
    <div v-else-if="ranks.length" class="ipp-grid">
      <div v-for="rank in ranks" :key="rank.display_name" class="ipp-card">
        <div class="ipp-card-name">{{ rank.display_name }}</div>
        <div class="ipp-card-value">
          {{ fmtValue(rank.value, rank.unit) }}
          <span class="ipp-card-unit">{{ rank.unit || '' }}</span>
        </div>
        <div class="ipp-card-rank">
          <span class="ipp-rank-num">{{ rank.rank_in_industry }}/{{ rank.peer_count }}</span>
          <span :class="['ipp-arrow', dirClass(rank.direction, rank.rank_in_industry, rank.peer_count)]">
            {{ dirArrow(rank.direction, rank.rank_in_industry, rank.peer_count) }}
          </span>
        </div>
      </div>
    </div>

    <div v-else class="ipp-unavailable">
      <p class="ipp-unavail-text">暂无行业排名数据</p>
    </div>

    <div v-if="reasons.length" class="ipp-reasons">
      <span v-for="r in reasons" :key="r" class="ipp-reason">{{ r }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  envelope: { type: Object, default: null },
  loading:  { type: Boolean, default: false },
})

const industryName  = computed(() => props.envelope?.data?.industry_name  || '')
const industryLevel = computed(() => props.envelope?.data?.industry_level || '')
const ranks         = computed(() => props.envelope?.data?.ranks          || [])
const reasons       = computed(() => {
  const r = props.envelope?.data?.reasons
  const pr = props.envelope?.data?.partial_reason
  if (Array.isArray(r) && r.length) return r
  if (pr) return [pr]
  return props.envelope?.errors || []
})

const isUnavailable = computed(() => {
  if (!props.envelope) return true
  if (!ranks.value.length && reasons.value.length) return true
  return false
})

const unavailableMsg = computed(() => {
  if (reasons.value.length) return reasons.value[0]
  return '行业数据暂不可用，请配置 ETL'
})

function fmtValue(v, unit) {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  if (!unit && Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + '亿'
  return n.toFixed(2)
}

function dirArrow(direction, rank, total) {
  // For "higher_better": low rank number = good
  if (!rank || !total) return ''
  const ratio = rank / total
  if (direction === 'higher_better') {
    return ratio <= 0.33 ? '↑' : ratio <= 0.67 ? '→' : '↓'
  }
  if (direction === 'lower_better') {
    return ratio <= 0.33 ? '↓' : ratio <= 0.67 ? '→' : '↑'
  }
  return ''
}

function dirClass(direction, rank, total) {
  if (!rank || !total) return ''
  const ratio = rank / total
  let good = false
  if (direction === 'higher_better') good = ratio <= 0.33
  else if (direction === 'lower_better') good = ratio <= 0.33
  else return ''
  const mid = ratio > 0.33 && ratio <= 0.67
  if (mid) return 'ipp-arrow--neutral'
  return good ? 'ipp-arrow--good' : 'ipp-arrow--bad'
}
</script>

<style scoped>
.ipp-root { display: flex; flex-direction: column; gap: 12px; }

.ipp-industry-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.ipp-industry-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #1a2540);
}

.ipp-industry-level {
  font-size: 11px;
  background: #e8f0fe;
  color: #1a73e8;
  border-radius: 4px;
  padding: 2px 7px;
}

.ipp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px;
}

.ipp-card {
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ipp-card-name {
  font-size: 11px;
  color: var(--color-text-secondary, #888);
  line-height: 1.3;
}

.ipp-card-value {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-primary, #1a2540);
}

.ipp-card-unit {
  font-size: 11px;
  font-weight: 400;
  color: #888;
  margin-left: 2px;
}

.ipp-card-rank {
  display: flex;
  align-items: center;
  gap: 5px;
}

.ipp-rank-num {
  font-size: 12px;
  color: var(--color-text-secondary, #555);
}

.ipp-arrow {
  font-size: 14px;
  font-weight: 700;
}

.ipp-arrow--good    { color: #16a34a; }
.ipp-arrow--bad     { color: #dc2626; }
.ipp-arrow--neutral { color: #9ca3af; }

.ipp-unavailable {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 20px 0;
  text-align: center;
}

.ipp-unavail-icon { font-size: 28px; }
.ipp-unavail-text { font-size: 13px; color: var(--color-text-secondary, #888); margin: 0; }

.ipp-reasons { display: flex; flex-direction: column; gap: 4px; }
.ipp-reason { font-size: 12px; color: #92400e; background: #fffbeb; border-radius: 4px; padding: 4px 8px; }
</style>
