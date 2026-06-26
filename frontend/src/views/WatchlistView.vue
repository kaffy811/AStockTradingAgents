<template>
  <div class="app-shell">
    <AppHeader />

    <!-- ── Page title ─────────────────────────────────────────────────────────── -->
    <div class="wv-title-bar">
      <div>
        <h1 class="wv-title">{{ t('wl_title') }}</h1>
        <p class="wv-subtitle">{{ t('wl_subtitle') }}</p>
      </div>
    </div>

    <!-- ── Add form ───────────────────────────────────────────────────────────── -->
    <div class="card">
      <div class="form-row">
        <div class="form-group">
          <label>{{ t('input_market_label') }}</label>
          <select v-model="form.market" :disabled="adding">
            <option value="CN">{{ t('input_market_cn') }}</option>
            <option value="HK">{{ t('input_market_hk') }}</option>
          </select>
        </div>
        <div class="form-group wv-ssb-group">
          <label>{{ t('input_symbol_label') }}</label>
          <StockSearchBox
            v-model:symbol="form.symbol"
            :market="form.market"
            :disabled="adding"
            @select="onSearchSelect"
            @keydown.enter="handleAdd"
          />
        </div>
        <div class="form-group wv-submit-group">
          <button
            class="btn btn-primary"
            :disabled="adding || !form.symbol.trim()"
            @click="handleAdd"
          >
            <span v-if="adding"><span class="spinner"></span>{{ t('wl_add_loading') }}</span>
            <span v-else>{{ t('wl_add_btn') }}</span>
          </button>
        </div>
      </div>
      <ErrorBox :message="addError" />
    </div>

    <!-- ── Loading ──────────────────────────────────────────────────────────── -->
    <div v-if="loading" class="wv-empty">
      <span class="spinner"></span> {{ t('wl_loading') }}
    </div>

    <!-- ── List error ─────────────────────────────────────────────────────────── -->
    <ErrorBox :message="listError" />

    <!-- ── Stats (shown when items exist) ────────────────────────────────────── -->
    <WatchlistStats v-if="items.length > 0" :items="items" :loading="loading" />

    <!-- ── Toolbar (shown when items exist) ──────────────────────────────────── -->
    <WatchlistToolbar
      v-if="items.length > 0"
      v-model:filters="filters"
      v-model:sortKey="sortKey"
      :bulk-mode="bulkMode"
      :selected-count="selectedIds.size"
      :industries="allIndustries"
      :loading="loading"
      @toggle-bulk="toggleBulk"
      @clear-selection="selectedIds.clear()"
      @batch-delete="openBatchConfirm"
      @compare="handleCompare"
      @refresh="loadItems"
    />

    <!-- ── Batch status message ───────────────────────────────────────────────── -->
    <div v-if="batchStatus" class="wv-batch-status">{{ batchStatus }}</div>

    <!-- ── Empty state ──────────────────────────────────────────────────────── -->
    <div v-if="!loading && !listError && items.length === 0" class="wv-empty">
      <div class="wv-empty-icon">⭐</div>
      <p>{{ t('wl_empty') }}</p>
    </div>

    <div
      v-else-if="!loading && items.length > 0 && filteredItems.length === 0"
      class="wv-empty"
    >
      {{ t('wl_no_results') }}
      <button class="wv-link-btn" @click="resetFilters">{{ t('wl_clear_filter') }}</button>
    </div>

    <!-- ── Stock cards ────────────────────────────────────────────────────────── -->
    <template v-if="!loading && filteredItems.length > 0">
      <WatchlistStockCard
        v-for="item in filteredItems"
        :key="item.id"
        :item="item"
        :selected="selectedIds.has(item.id)"
        :bulk-mode="bulkMode"
        :is-editing-note="editingNoteId === item.id"
        :edit-note-value="editNoteValue"
        :is-saving-note="savingNoteId === item.id"
        :note-error="editingNoteId === item.id ? noteError : ''"
        @toggle-select="toggleSelect(item.id)"
        @detail="goDetail(item)"
        @analyze="goAnalyze(item)"
        @history="goHistory(item)"
        @delete="handleDelete(item)"
        @edit-note="startEditNote(item)"
        @update:editNoteValue="editNoteValue = $event"
        @save-note="saveNote(item)"
        @cancel-note="cancelEditNote"
      />
    </template>

  </div>

  <!-- ── Single delete confirm ──────────────────────────────────────────────── -->
  <ConfirmDialog
    v-model="confirmOpen"
    :title="t('wl_del_title')"
    :message="t('wl_del_msg')"
    :confirm-text="t('wl_del_btn')"
    :cancel-text="t('wl_del_cancel')"
    :danger="true"
    :loading="deleteLoading"
    @confirm="doDelete"
    @cancel="cancelDelete"
  />

  <!-- ── Batch delete confirm ───────────────────────────────────────────────── -->
  <ConfirmDialog
    v-model="batchConfirmOpen"
    :title="t('wl_batch_del_title')"
    :message="t('wl_batch_del_msg', { n: selectedIds.size })"
    :confirm-text="t('wl_del_btn')"
    :cancel-text="t('wl_del_cancel')"
    :danger="true"
    :loading="batchDeleting"
    @confirm="doBatchDelete"
    @cancel="batchConfirmOpen = false"
  />
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from '../utils/i18n.js'

const { t } = useI18n()
import {
  listWatchlist,
  addWatchlist,
  deleteWatchlist,
  patchWatchlist,
  getWatchlistEnriched,
} from '../api/watchlist.js'
import { formatTime } from '../utils/warningMap.js'
import AppHeader         from '../components/AppHeader.vue'
import ErrorBox          from '../components/ErrorBox.vue'
import ConfirmDialog     from '../components/ConfirmDialog.vue'
import StockSearchBox    from '../components/StockSearchBox.vue'
import WatchlistStats    from '../components/WatchlistStats.vue'
import WatchlistToolbar  from '../components/WatchlistToolbar.vue'
import WatchlistStockCard from '../components/WatchlistStockCard.vue'

const router = useRouter()
const route  = useRoute()

// ── List state ────────────────────────────────────────────────────────────────
const loading   = ref(false)
const listError = ref('')
const items     = ref([])
const enriched  = ref(false)

// ── Filter & sort state ───────────────────────────────────────────────────────
const filters = ref({
  market:       '',
  direction:    '',
  industry:     '',
  reportFilter: '',
})
const sortKey = ref('default')

// ── Bulk mode state ───────────────────────────────────────────────────────────
const bulkMode        = ref(false)
const selectedIds     = reactive(new Set())
const batchConfirmOpen = ref(false)
const batchDeleting   = ref(false)
const batchStatus     = ref('')

// ── Add form state ────────────────────────────────────────────────────────────
const adding   = ref(false)
const addError = ref('')
const form     = reactive({ market: 'CN', symbol: '', name: '' })

// ── Single delete state ───────────────────────────────────────────────────────
const deletingId         = ref(null)
const confirmOpen        = ref(false)
const deleteLoading      = ref(false)
const pendingDeleteItem  = ref(null)

// ── Note editing state ────────────────────────────────────────────────────────
const editingNoteId = ref(null)
const editNoteValue = ref('')
const savingNoteId  = ref(null)
const noteError     = ref('')

// ── Computed: all industries from items ──────────────────────────────────────
const allIndustries = computed(() => {
  const names = items.value.map(i => i.industry_name).filter(Boolean)
  return [...new Set(names)].sort()
})

// ── Computed: filtered + sorted items ────────────────────────────────────────
const filteredItems = computed(() => {
  const f = filters.value
  let list = items.value.filter(item => {
    // Market
    if (f.market && item.market !== f.market) return false
    // Direction
    if (f.direction === 'up'     && !(item.change_pct != null && item.change_pct > 0 && item.quote_status !== 'failed')) return false
    if (f.direction === 'down'   && !(item.change_pct != null && item.change_pct < 0 && item.quote_status !== 'failed')) return false
    if (f.direction === 'unavail' && item.quote_status !== 'failed') return false
    // Industry
    if (f.industry) {
      const iname = item.industry_name || ''
      if (iname !== f.industry) return false
    }
    // Report filter
    if (f.reportFilter === 'has'  && !item.latest_report) return false
    if (f.reportFilter === 'none' &&  item.latest_report) return false
    return true
  })

  // Sort
  const key = sortKey.value
  if (key === 'default') return list

  return [...list].sort((a, b) => {
    if (key === 'change_desc') {
      const av = a.change_pct ?? -Infinity
      const bv = b.change_pct ?? -Infinity
      return bv - av
    }
    if (key === 'change_asc') {
      const av = a.change_pct ?? Infinity
      const bv = b.change_pct ?? Infinity
      return av - bv
    }
    if (key === 'symbol') {
      const as = `${a.market}/${a.symbol}`
      const bs = `${b.market}/${b.symbol}`
      return as < bs ? -1 : as > bs ? 1 : 0
    }
    if (key === 'name') {
      const an = (a.name || a.symbol).toLowerCase()
      const bn = (b.name || b.symbol).toLowerCase()
      return an < bn ? -1 : an > bn ? 1 : 0
    }
    return 0
  })
})

// ── Load (enriched with fallback) ─────────────────────────────────────────────
async function loadItems() {
  loading.value   = true
  listError.value = ''
  enriched.value  = false
  try {
    const data = await getWatchlistEnriched()
    items.value    = data.items
    enriched.value = true
  } catch {
    try {
      const data = await listWatchlist()
      items.value = data.items
    } catch (e) {
      listError.value = e.message || t('wl_load_fail')
    }
  } finally {
    loading.value = false
  }
}

// ── Add ───────────────────────────────────────────────────────────────────────
function onSearchSelect(item) {
  form.symbol = item.symbol
  form.name   = item.name || ''
}

async function handleAdd() {
  const sym = form.symbol.trim()
  if (!sym || adding.value) return
  adding.value  = true
  addError.value = ''
  try {
    const body = { market: form.market, symbol: sym }
    if (form.name.trim()) body.name = form.name.trim()
    await addWatchlist(body)
    form.symbol = ''
    form.name   = ''
    await loadItems()
  } catch (e) {
    addError.value = e.status === 409 ? t('wl_add_dup') : (e.message || t('wl_add_fail'))
  } finally {
    adding.value = false
  }
}

// ── Single delete ─────────────────────────────────────────────────────────────
function handleDelete(item) {
  pendingDeleteItem.value = item
  confirmOpen.value = true
}

function cancelDelete() {
  pendingDeleteItem.value = null
  confirmOpen.value = false
}

async function doDelete() {
  const item = pendingDeleteItem.value
  if (!item) return
  deleteLoading.value = true
  deletingId.value    = item.id
  try {
    await deleteWatchlist(item.id)
    confirmOpen.value       = false
    pendingDeleteItem.value = null
    await loadItems()
  } catch (e) {
    listError.value   = e.message || t('wl_del_fail')
    confirmOpen.value = false
  } finally {
    deleteLoading.value = false
    deletingId.value    = null
  }
}

// ── Bulk mode ─────────────────────────────────────────────────────────────────
function toggleBulk() {
  bulkMode.value = !bulkMode.value
  if (!bulkMode.value) {
    selectedIds.clear()
    batchStatus.value = ''
  }
}

function toggleSelect(id) {
  if (selectedIds.has(id)) selectedIds.delete(id)
  else selectedIds.add(id)
}

function openBatchConfirm() {
  if (selectedIds.size === 0) return
  batchConfirmOpen.value = true
}

function handleCompare() {
  const count = selectedIds.size
  if (count < 2) return
  if (count > 4) return
  const selectedItems = items.value.filter(item => selectedIds.has(item.id))
  const stocksParam = selectedItems
    .map(item => `${item.market}:${item.symbol}`)
    .join(',')
  router.push({ path: '/compare', query: { stocks: stocksParam } })
}

async function doBatchDelete() {
  batchDeleting.value = true
  batchStatus.value   = ''
  const ids = [...selectedIds]
  try {
    const results = await Promise.allSettled(ids.map(id => deleteWatchlist(id)))
    const succeeded = results.filter(r => r.status === 'fulfilled').length
    const failed    = results.filter(r => r.status === 'rejected').length

    // Remove successfully deleted items locally
    const failedIds = new Set(
      results
        .map((r, i) => r.status === 'rejected' ? ids[i] : null)
        .filter(Boolean)
    )
    items.value = items.value.filter(item => !ids.includes(item.id) || failedIds.has(item.id))

    selectedIds.clear()
    batchConfirmOpen.value = false
    batchStatus.value = t('wl_batch_result', { success: succeeded, fail: failed })

    if (failed > 0) {
      // Full reload to sync state
      await loadItems()
    }
  } catch {
    batchStatus.value = t('wl_batch_fail')
  } finally {
    batchDeleting.value = false
    bulkMode.value      = false
  }
}

// ── Note editing (logic unchanged from original WatchlistView) ────────────────
async function startEditNote(item) {
  if (savingNoteId.value) return
  if (editingNoteId.value === item.id) return
  if (editingNoteId.value !== null) {
    const prev = items.value.find(i => i.id === editingNoteId.value)
    if (prev) {
      await saveNote(prev)
      if (noteError.value) return
    }
  }
  noteError.value     = ''
  editingNoteId.value = item.id
  editNoteValue.value = item.note ?? ''
}

async function saveNote(item) {
  if (savingNoteId.value === item.id) return
  const newNote = editNoteValue.value.trim()
  const oldNote = item.note ?? ''
  if (newNote === oldNote) {
    editingNoteId.value = null
    noteError.value     = ''
    return
  }
  savingNoteId.value = item.id
  noteError.value    = ''
  try {
    const updated = await patchWatchlist(item.id, { note: newNote })
    item.note           = updated.note
    editingNoteId.value = null
  } catch (e) {
    noteError.value = e.message || '保存失败'
    await nextTick()
    // focus is handled by WatchlistStockCard's watch on isEditingNote
  } finally {
    savingNoteId.value = null
  }
}

function cancelEditNote() {
  editingNoteId.value = null
  noteError.value     = ''
}

function resetFilters() {
  filters.value = { market: '', direction: '', industry: '', reportFilter: '' }
  sortKey.value = 'default'
}

// ── Navigation ────────────────────────────────────────────────────────────────
function goDetail(item) {
  router.push(`/stocks/${item.market}/${item.symbol}`)
}

function goAnalyze(item) {
  router.push({ path: '/', query: { market: item.market, symbol: item.symbol } })
}

function goHistory(item) {
  router.push({ path: '/history', query: { market: item.market, symbol: item.symbol } })
}

onMounted(async () => {
  await loadItems()
  // Auto-enter bulk mode when navigating from HomeDashboardPanel "批量对比" button
  if (route.query.mode === 'compare') {
    bulkMode.value = true
  }
})
</script>

<style scoped>
/* ── Title bar ── */
.wv-title-bar {
  margin-bottom: 16px;
}

.wv-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 4px;
}

.wv-subtitle {
  font-size: 13px;
  color: var(--muted);
  margin: 0;
}

/* ── Add form ── */
.form-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: flex-end;
  margin-top: 4px;
}

.wv-ssb-group {
  min-width: 200px;
  flex: 1;
}

.wv-submit-group { justify-content: flex-end; }

/* ── Empty / loading ── */
.wv-empty {
  text-align: center;
  color: var(--muted);
  padding: 40px 0;
  font-size: 14px;
}

.wv-empty-icon {
  font-size: 36px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.wv-link-btn {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  text-decoration: underline;
  font-size: 14px;
  padding: 0;
}

/* ── Batch status ── */
.wv-batch-status {
  font-size: 13px;
  color: var(--success);
  padding: 8px 0 4px;
  text-align: center;
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .wv-title { font-size: 18px; }
  .wv-subtitle { font-size: 12px; }

  .wv-ssb-group { width: 100%; }
  .wv-submit-group { justify-content: stretch; }
  .wv-submit-group .btn { width: 100%; }
}
</style>
