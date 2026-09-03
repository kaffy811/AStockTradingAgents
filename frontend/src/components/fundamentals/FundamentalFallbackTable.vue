<template>
  <div v-if="visibleRows.length" class="fft-wrap">
    <div class="fft-label">{{ label }}</div>
    <div class="fft-scroll">
      <table class="fft-table">
        <thead>
          <tr>
            <th v-for="col in visibleCols" :key="col">
              {{ fieldLabels[col] || col }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in visibleRows" :key="i">
            <td v-for="col in visibleCols" :key="col" :class="tdClass(row[col], col)">
              {{ fmtCell(row[col], col) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** DataEnvelope.data — accepts rows / series / periods / records */
  data:        { type: Object, default: null },
  /** Override column list (optional) */
  columns:     { type: Array,  default: () => [] },
  /** Human-readable column labels */
  fieldLabels: { type: Object, default: () => ({}) },
  /** Max rows to display */
  limit:       { type: Number, default: 8 },
  /** Header label shown above the table */
  label:       { type: String, default: '数据预览' },
})

// ── Row extraction: supports all field conventions ────────────────────────────
const allRows = computed(() => {
  const d = props.data
  if (!d) return []
  return d.rows || d.series || d.periods || d.records || []
})

const visibleRows = computed(() => allRows.value.slice(0, props.limit))

// ── Column auto-detection ────────────────────────────────────────────────────
const EXCLUDE_COLS = new Set(['source', 'ts_code', 'symbol', 'curr_type', '_partial_errors', 'comment', 'reasons'])

const visibleCols = computed(() => {
  if (props.columns.length) return props.columns
  const rows = visibleRows.value
  if (!rows.length) return []
  // Gather all keys from all rows, preserve first-seen order
  const seen = new Set()
  const cols = []
  for (const row of rows) {
    for (const k of Object.keys(row)) {
      if (!seen.has(k) && !k.startsWith('_') && !EXCLUDE_COLS.has(k) && typeof row[k] !== 'object') {
        seen.add(k)
        cols.push(k)
      }
    }
  }
  return cols
})

// ── Formatting ────────────────────────────────────────────────────────────────
function fmtCell(v, col) {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'boolean') return v ? '是' : '否'
  if (typeof v === 'string') return v || '—'
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v)
  // Detect pct/ratio columns
  if (/pct$|_pct$|_ratio$|margin|yoy|percentile/.test(col)) return n.toFixed(2) + '%'
  // Large numbers → 亿
  if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + '亿'
  if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(2) + '万'
  return n.toFixed(2)
}

function tdClass(v, col) {
  const isChange = /yoy|change|pct|ratio_pct$|percentile/.test(col)
  if (!isChange || v == null || !Number.isFinite(Number(v))) return ''
  return Number(v) > 0 ? 'td-up' : Number(v) < 0 ? 'td-dn' : ''
}
</script>

<style scoped>
.fft-wrap { margin-top: 8px; }
.fft-label { font-size: 11px; color: var(--muted); margin-bottom: 4px; font-weight: 500; }
.fft-scroll { overflow-x: auto; border-radius: 6px; border: 1px solid var(--border); }
.fft-table {
  width: 100%; border-collapse: collapse; font-size: 12px;
  min-width: 300px; white-space: nowrap;
}
.fft-table th {
  background: var(--surface2); color: var(--muted); font-weight: 600;
  padding: 6px 10px; text-align: right; border-bottom: 1px solid var(--border);
  position: sticky; top: 0;
}
.fft-table th:first-child { text-align: left; }
.fft-table td {
  padding: 5px 10px; border-bottom: 1px solid var(--border);
  color: var(--text); text-align: right;
}
.fft-table td:first-child { text-align: left; color: var(--muted); }
.fft-table tr:last-child td { border-bottom: none; }
.fft-table tr:hover td { background: var(--surface2); }
.td-up { color: var(--status-up, #e04040); font-weight: 600; }
.td-dn { color: var(--status-down, #00a870); font-weight: 600; }
</style>
