<template>
  <div class="app-shell">
    <AppHeader />

    <!-- ── Page title ────────────────────────────────────────────────────────── -->
    <div class="hv-title-bar">
      <div>
        <h1 class="hv-title">{{ t('rpt_title') }}</h1>
        <p class="hv-subtitle">{{ t('rpt_subtitle') }}</p>
      </div>
    </div>

    <!-- ── Stats ─────────────────────────────────────────────────────────────── -->
    <ReportCenterStats :reports="items" :total="total" :loading="loading" />

    <!-- ── Filter panel ───────────────────────────────────────────────────────── -->
    <ReportFilterPanel
      v-model:filters="filters"
      :loading="loading"
      @search="applyFilters"
      @reset="resetFilters"
    />

    <!-- ── Loading ──────────────────────────────────────────────────────────── -->
    <div v-if="loading" class="hv-empty">
      <span class="spinner"></span> {{ t('rpt_loading') }}
    </div>

    <!-- ── Error ─────────────────────────────────────────────────────────────── -->
    <ErrorBox :message="errorMsg" />

    <!-- ── Empty state ──────────────────────────────────────────────────────── -->
    <div v-if="!loading && !errorMsg && total === 0" class="hv-empty">
      <div class="hv-empty-icon">📋</div>
      <p>{{ t('rpt_empty_p1') }}<RouterLink to="/" class="hv-link">{{ t('rpt_empty_link') }}</RouterLink>{{ t('rpt_empty_p2') }}</p>
    </div>

    <!-- ── Report cards ──────────────────────────────────────────────────────── -->
    <template v-if="!loading && items.length">
      <ReportListCard
        v-for="item in items"
        :key="item.id"
        :report="item"
        :is-deleting="deletingId === item.id"
        @view="router.push(`/history/${item.id}`)"
        @go-stock="goStock(item)"
        @reanalyze="goReanalyze(item)"
        @delete="handleDelete(item.id)"
      />

      <!-- ── Pagination ─────────────────────────────────────────────────────── -->
      <div v-if="total > limit" class="hv-pagination">
        <button
          class="btn btn-secondary btn-sm"
          :disabled="offset === 0"
          @click="prevPage"
        >{{ t('rpt_prev_page') }}</button>
        <span class="hv-page-info">{{ pageNum }} / {{ totalPages }}</span>
        <button
          class="btn btn-secondary btn-sm"
          :disabled="offset + limit >= total"
          @click="nextPage"
        >{{ t('rpt_next_page') }}</button>
      </div>
    </template>

  </div>

  <ConfirmDialog
    v-model="confirmOpen"
    :title="t('rpt_confirm_del_title')"
    :message="t('rpt_confirm_del_msg')"
    :confirm-text="t('rpt_confirm_del_btn')"
    :cancel-text="t('rpt_cancel')"
    :danger="true"
    :loading="deleteLoading"
    @confirm="doDelete"
    @cancel="cancelDelete"
  />
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { listReports, deleteReport } from '../api/reports.js'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()
import AppHeader         from '../components/AppHeader.vue'
import ErrorBox          from '../components/ErrorBox.vue'
import ConfirmDialog     from '../components/ConfirmDialog.vue'
import ReportCenterStats from '../components/ReportCenterStats.vue'
import ReportFilterPanel from '../components/ReportFilterPanel.vue'
import ReportListCard    from '../components/ReportListCard.vue'

const route  = useRoute()
const router = useRouter()

// ── Filter state ──────────────────────────────────────────────────────────────
const filters = ref({
  market:    route.query.market         || '',
  symbol:    route.query.symbol         || '',
  scope:     route.query.analysis_scope || '',
  autoSaved: route.query.auto_saved     || '',
  dateRange: route.query.date_range     || '',
})

// ── List state ────────────────────────────────────────────────────────────────
const loading    = ref(false)
const errorMsg   = ref('')
const items      = ref([])
const total      = ref(0)
const limit      = 20
const offset     = ref(0)
const deletingId = ref(null)

const confirmOpen         = ref(false)
const pendingDeleteId     = ref(null)
const deleteLoading       = ref(false)

const pageNum    = computed(() => Math.floor(offset.value / limit) + 1)
const totalPages = computed(() => Math.ceil(total.value / limit))

// ── Date range → start/end dates ─────────────────────────────────────────────
function _dateRangeToDates(range) {
  if (!range) return {}
  const today = new Date()
  const daysMap = { '7d': 7, '30d': 30, '90d': 90 }
  const days = daysMap[range]
  if (!days) return {}
  const start = new Date(today)
  start.setDate(start.getDate() - days)
  const fmt = (d) => d.toISOString().slice(0, 10)
  return { start_date: fmt(start), end_date: fmt(today) }
}

// ── Load ──────────────────────────────────────────────────────────────────────
async function loadReports() {
  loading.value  = true
  errorMsg.value = ''
  try {
    const f = filters.value
    const params = { limit, offset: offset.value }
    if (f.market)    params.market         = f.market
    if (f.symbol)    params.symbol         = f.symbol.trim()
    if (f.scope)     params.analysis_scope = f.scope
    if (f.autoSaved) params.auto_saved     = f.autoSaved === 'true'
    const dates = _dateRangeToDates(f.dateRange)
    if (dates.start_date) params.start_date = dates.start_date
    if (dates.end_date)   params.end_date   = dates.end_date

    const data = await listReports(params)
    items.value = data.items
    total.value = data.total
  } catch (e) {
    errorMsg.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

// ── Apply filters (reset offset + update URL) ─────────────────────────────────
function applyFilters() {
  offset.value = 0
  _syncUrl()
  loadReports()
}

function _syncUrl() {
  const f = filters.value
  const q = {}
  if (f.market)    q.market         = f.market
  if (f.symbol)    q.symbol         = f.symbol
  if (f.scope)     q.analysis_scope = f.scope
  if (f.autoSaved) q.auto_saved     = f.autoSaved
  if (f.dateRange) q.date_range     = f.dateRange
  router.replace({ query: q })
}

// ── Reset ─────────────────────────────────────────────────────────────────────
function resetFilters() {
  filters.value = { market: '', symbol: '', scope: '', autoSaved: '', dateRange: '' }
  offset.value  = 0
  router.replace({ query: {} })
  loadReports()
}

// ── Navigation helpers ────────────────────────────────────────────────────────
function goStock(item) {
  if (!item.market || !item.symbol) return
  router.push(`/stocks/${item.market}/${item.symbol}`)
}

function goReanalyze(item) {
  if (!item.market || !item.symbol) return
  const q = { market: item.market, symbol: item.symbol }
  if (item.analysis_scope) q.scope = item.analysis_scope
  router.push({ path: '/', query: q })
}

// ── Delete ────────────────────────────────────────────────────────────────────
function handleDelete(id) {
  pendingDeleteId.value = id
  confirmOpen.value = true
}

function cancelDelete() {
  pendingDeleteId.value = null
  confirmOpen.value = false
}

async function doDelete() {
  const id = pendingDeleteId.value
  deleteLoading.value = true
  deletingId.value    = id
  try {
    await deleteReport(id)
    confirmOpen.value     = false
    pendingDeleteId.value = null
    await loadReports()
  } catch (e) {
    errorMsg.value    = e.message || '删除失败'
    confirmOpen.value = false
  } finally {
    deleteLoading.value = false
    deletingId.value    = null
  }
}

// ── Pagination ────────────────────────────────────────────────────────────────
function prevPage() {
  offset.value = Math.max(0, offset.value - limit)
  loadReports()
}

function nextPage() {
  offset.value = offset.value + limit
  loadReports()
}

onMounted(loadReports)
</script>

<style scoped>
/* ── Title bar ── */
.hv-title-bar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}

.hv-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 4px;
}

.hv-subtitle {
  font-size: 13px;
  color: var(--muted);
  margin: 0;
}

/* ── Empty / loading ── */
.hv-empty {
  text-align: center;
  color: var(--muted);
  padding: 48px 0 32px;
  font-size: 14px;
}

.hv-empty-icon {
  font-size: 36px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.hv-link {
  color: var(--accent);
  text-decoration: underline;
}

/* ── Pagination ── */
.hv-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 16px 0 8px;
}

.hv-page-info {
  font-size: 13px;
  color: var(--muted);
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .hv-title { font-size: 18px; }
  .hv-subtitle { font-size: 12px; }
}
</style>
