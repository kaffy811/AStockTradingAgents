<template>
  <div class="cv2-stock-card">
    <div class="cv2-stock-items">
      <div v-for="item in items" :key="item.key" class="cv2-stock-item">
        <span class="cv2-stock-label">{{ item.label }}</span>
        <span :class="['cv2-stock-value', item.colorClass]">{{ item.display }}</span>
        <span v-if="item.unit" class="cv2-stock-unit">{{ item.unit }}</span>
      </div>
    </div>
    <p v-if="showDisclaimer" class="cv2-stock-disclaimer">
      行情可能存在延迟。最终以交易所公告为准。本页面不构成投资建议。
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  quoteRow: { type: Object, default: () => ({}) },
  stockBasic: { type: Object, default: () => ({}) },
  showDisclaimer: { type: Boolean, default: false },
})

function _fmt(v, type = 'number') {
  if (v == null || v === '') return '—'
  const n = Number(v)
  if (isNaN(n)) return String(v)
  if (type === 'percent') return (n * 100).toFixed(2) + '%'
  if (type === 'pct_direct') return n.toFixed(2) + '%'
  if (type === 'ratio') return n.toFixed(2) + 'x'
  if (type === 'currency_b') {
    if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + '亿'
    if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(2) + '万'
    return n.toFixed(2)
  }
  return n.toFixed(4)
}

function _colorClass(v, type) {
  if (v == null) return ''
  const n = Number(v)
  if (isNaN(n)) return ''
  if (type === 'change') return n > 0 ? 'cv2-positive' : n < 0 ? 'cv2-negative' : ''
  return ''
}

const items = computed(() => {
  const q = props.quoteRow || {}
  const result = []

  // 价格
  const price = q.latest_price ?? q.recent_close
  if (price != null) {
    result.push({
      key: 'price',
      label: '最新价',
      display: Number(price).toFixed(2),
      unit: '元',
      colorClass: '',
    })
  }

  // 涨跌幅
  const chg = q.pct_chg ?? q.change_pct
  if (chg != null) {
    result.push({
      key: 'pct_chg',
      label: '涨跌幅',
      display: _fmt(chg, 'pct_direct'),
      unit: '',
      colorClass: _colorClass(chg, 'change'),
    })
  }

  if (q.turnover != null) {
    result.push({
      key: 'turnover',
      label: '换手率',
      display: _fmt(q.turnover, 'pct_direct'),
      unit: '',
      colorClass: '',
    })
  }

  // 市值
  const mcap = q.market_cap
  if (mcap != null) {
    result.push({
      key: 'market_cap',
      label: '总市值',
      display: _fmt(mcap, 'currency_b'),
      unit: '',
      colorClass: '',
    })
  }

  return result
})
</script>

<style scoped>
.cv2-stock-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 12px 20px;
  margin-bottom: 16px;
}
.cv2-stock-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 24px;
}
.cv2-stock-item {
  display: flex;
  align-items: baseline;
  gap: 4px;
  min-width: 120px;
}
.cv2-stock-label {
  font-size: 11px;
  color: #9ca3af;
  white-space: nowrap;
}
.cv2-stock-value {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}
.cv2-stock-unit {
  font-size: 11px;
  color: #9ca3af;
}
.cv2-positive { color: #ef4444; }  /* A股：红涨绿跌 */
.cv2-negative { color: #10b981; }
.cv2-stock-disclaimer {
  margin-top: 10px;
  font-size: 10px;
  color: #9ca3af;
  border-top: 1px solid #f3f4f6;
  padding-top: 8px;
}
</style>
