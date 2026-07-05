<template>
  <div class="ft-wrap" v-if="rows.length > 0">
    <div class="ft-scroll">
      <table class="ft-table">
        <thead>
          <tr>
            <th v-for="col in columns" :key="col">
              {{ fieldLabels[col] || col }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="i">
            <td v-for="col in columns" :key="col" :class="tdClass(row[col], col)">
              {{ formatCell(row[col], col) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
  <div v-else class="ft-empty">暂无数据</div>
</template>

<script setup>
import { fmtVal } from '../../utils/fundamentalAdapters.js'

const props = defineProps({
  rows:        { type: Array,  default: () => [] },
  columns:     { type: Array,  default: () => [] },
  fieldLabels: { type: Object, default: () => ({}) },
  unitHints:   { type: Object, default: () => ({}) },
})

function formatCell(v, col) {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'string') return v || '—'
  if (typeof v === 'boolean') return v ? '是' : '否'
  return fmtVal(v, col, props.unitHints)
}

function tdClass(v, col) {
  // Color yoy / change columns
  const isChange = /yoy|change|pct|ratio_pct|percentile/.test(col)
  if (!isChange || v == null || !Number.isFinite(Number(v))) return ''
  return Number(v) > 0 ? 'td-up' : Number(v) < 0 ? 'td-dn' : ''
}
</script>

<style scoped>
.ft-wrap { overflow: hidden; border-radius: 8px; border: 1px solid var(--border); }
.ft-scroll { overflow-x: auto; }
.ft-table { width: 100%; border-collapse: collapse; font-size: 12px; min-width: 360px; white-space: nowrap; }
.ft-table th { background: var(--surface2); color: var(--muted); font-weight: 600; padding: 8px 10px; text-align: right; border-bottom: 1px solid var(--border); }
.ft-table th:first-child { text-align: left; }
.ft-table td { padding: 7px 10px; border-bottom: 1px solid var(--border); color: var(--text); text-align: right; }
.ft-table td:first-child { text-align: left; color: var(--muted); }
.ft-table tr:last-child td { border-bottom: none; }
.ft-table tr:hover td { background: var(--surface2); }
.td-up { color: var(--status-up, #e04040); font-weight: 600; }
.td-dn { color: var(--status-down, #00a870); font-weight: 600; }
.ft-empty { padding: 20px; text-align: center; color: var(--muted); font-size: 13px; }
</style>
