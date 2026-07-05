<template>
  <!-- ── Outer wrapper holds both the sidebar and the resize handle ─────────── -->
  <div
    class="session-sidebar-wrap"
    :style="!isCollapsed ? { width: sidebarWidth + 'px' } : { width: '28px' }"
    :class="{ collapsed: isCollapsed, resizing: isResizing }"
  >
    <div class="session-sidebar">
      <!-- Toggle button -->
      <button
        class="sidebar-toggle"
        @click="isCollapsed = !isCollapsed"
        :title="isCollapsed ? t('chat_sidebar_expand') : t('chat_sidebar_collapse')"
      >
        <span>{{ isCollapsed ? '›' : '‹' }}</span>
      </button>

      <template v-if="!isCollapsed">
        <!-- ── Header ─────────────────────────────────────────────────────── -->
        <div class="sidebar-header">
          <span class="sidebar-title">{{ t('chat_sessions_title') }}</span>
          <div class="sidebar-header-actions">
            <!-- Calendar icon — only shown when sidebar is wide enough -->
            <button
              v-if="calendarVisible"
              ref="calendarBtnRef"
              class="btn-calendar"
              :class="{ active: dateStart !== null }"
              @click.stop="toggleDatePicker"
              :title="t('chat_calendar_btn')"
              aria-label="日期筛选"
            >📅</button>
            <button class="btn-new" @click="$emit('new-session')" :title="t('chat_sessions_new')">+</button>
          </div>
        </div>

        <!-- ── Date-picker popup ──────────────────────────────────────────── -->
        <div
          v-if="showDatePicker"
          ref="datePickerRef"
          class="date-picker-popup"
          @click.stop
        >
          <!-- Month / Year navigation -->
          <div class="dp-nav">
            <button class="dp-nav-btn" @click="prevYear" title="上一年">«</button>
            <button class="dp-nav-btn" @click="prevMonth" title="上一月">‹</button>
            <span class="dp-nav-label">{{ dpYear }}年 {{ dpMonthName }}</span>
            <button class="dp-nav-btn" @click="nextMonth" title="下一月">›</button>
            <button class="dp-nav-btn" @click="nextYear" title="下一年">»</button>
          </div>
          <!-- Weekday row -->
          <div class="dp-weekdays">
            <span v-for="w in weekdays" :key="w">{{ w }}</span>
          </div>
          <!-- Day grid -->
          <div class="dp-days">
            <button
              v-for="day in dpDays"
              :key="day.key"
              class="dp-day"
              :class="{
                'dp-other':   !day.inMonth,
                'dp-start':   isStartDate(day.date),
                'dp-end':     isEndDate(day.date),
                'dp-inrange': isInRange(day.date),
                'dp-today':   isToday(day.date),
              }"
              @click="selectDay(day.date)"
            >{{ day.d }}</button>
          </div>
          <!-- Footer: range summary + actions -->
          <div class="dp-footer">
            <div class="dp-range-label">
              <span v-if="!dateStart" class="dp-hint">{{ t('chat_date_select_hint') }}</span>
              <template v-else>
                <span class="dp-range-part">{{ t('chat_date_start_label') }} {{ fmtDate(dateStart) }}</span>
                <template v-if="dateEnd">
                  <span class="dp-range-sep">→</span>
                  <span class="dp-range-part">{{ t('chat_date_end_label') }} {{ fmtDate(dateEnd) }}</span>
                </template>
                <template v-else>
                  <span class="dp-range-sep">→</span>
                  <span class="dp-hint">{{ t('chat_date_end_label') }}?</span>
                </template>
              </template>
            </div>
            <div class="dp-actions">
              <button class="dp-btn dp-clear" @click="clearDateRange">{{ t('chat_filter_clear') }}</button>
              <button
                class="dp-btn dp-apply"
                :disabled="!dateStart"
                @click="applyDateRange"
              >{{ t('chat_apply_filter') }}</button>
            </div>
          </div>
        </div>

        <!-- ── C32.5: Search box ──────────────────────────────────────────── -->
        <div class="sidebar-search">
          <div class="search-input-wrap">
            <input
              ref="searchInputRef"
              v-model="searchQuery"
              class="search-input"
              type="text"
              :placeholder="t('chat_search_placeholder')"
              @input="onSearchInput"
            />
            <button
              v-if="searchQuery || activeRanges.length > 0 || dateStart"
              class="search-clear-btn"
              @click="clearSearch"
              :title="t('chat_search_clear')"
            >×</button>
          </div>

          <!-- C32.3.5: Time chips removed — use calendar icon (📅) in header instead -->
        </div>

        <!-- ── Session list ────────────────────────────────────────────────── -->
        <div class="session-list">
          <div v-if="isSearching" class="session-empty">
            {{ t('chat_search_loading') }}
          </div>
          <div
            v-else-if="isSearchMode && displayedSessions.length === 0"
            class="session-empty"
          >
            {{ t('chat_search_no_results') }}
          </div>
          <div
            v-else-if="!isSearchMode && sessions.length === 0"
            class="session-empty"
          >
            {{ t('chat_sessions_empty') }}
          </div>
          <div
            v-for="s in displayedSessions"
            :key="s.id || s.session_id"
            class="session-item"
            :class="{ active: (s.id || s.session_id) === activeSessionId }"
            @click="$emit('select-session', s.id || s.session_id)"
          >
            <div class="session-preview">{{ s.preview || t('chat_sessions_new') }}</div>
            <div v-if="isSearchMode && s.matched_snippet" class="session-snippet">
              {{ s.matched_snippet }}
            </div>
            <div class="session-meta">{{ formatDate(s.created_at || s.last_message_at) }}</div>
            <button
              class="session-delete"
              @click.stop="$emit('delete-session', s.id || s.session_id)"
              :title="t('chat_sessions_delete')"
            >×</button>
          </div>
        </div>
      </template>
    </div>

    <!-- ── Drag-resize handle (right edge) ─────────────────────────────────── -->
    <div
      v-if="!isCollapsed"
      class="resize-handle"
      @mousedown.prevent="startResize"
      title="拖拽调整宽度"
    ></div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onBeforeUnmount, nextTick } from 'vue'
import { useI18n } from '../../utils/i18n.js'

const { t } = useI18n()

const props = defineProps({
  sessions:        { type: Array,  default: () => [] },
  activeSessionId: { type: String, default: null },
})

const emit = defineEmits(['new-session', 'select-session', 'delete-session', 'search'])

// ── Constants ─────────────────────────────────────────────────────────────────

const SIDEBAR_MIN        = 160   // px — narrowest allowed
const SIDEBAR_MAX        = 440   // px — widest allowed
const SIDEBAR_DEFAULT    = 200   // px — default
const CALENDAR_THRESHOLD = 220   // px — show calendar icon above this width

// ── Sidebar width & collapse ──────────────────────────────────────────────────

const _storedWidth = parseInt(localStorage.getItem('chat-sidebar-width') || String(SIDEBAR_DEFAULT))
const sidebarWidth = ref(Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, _storedWidth)))
const isCollapsed  = ref(false)

// ── Drag-resize ───────────────────────────────────────────────────────────────

const isResizing    = ref(false)
let _resizeStartX   = 0
let _resizeStartW   = 0

function startResize(e) {
  isResizing.value = true
  _resizeStartX    = e.clientX
  _resizeStartW    = sidebarWidth.value
  document.addEventListener('mousemove', onResizeMove)
  document.addEventListener('mouseup',   stopResize)
}

function onResizeMove(e) {
  if (!isResizing.value) return
  const delta = e.clientX - _resizeStartX
  sidebarWidth.value = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, _resizeStartW + delta))
}

function stopResize() {
  isResizing.value = false
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup',   stopResize)
  localStorage.setItem('chat-sidebar-width', String(sidebarWidth.value))
}

// ── Calendar visibility ───────────────────────────────────────────────────────

const calendarVisible = computed(() => sidebarWidth.value >= CALENDAR_THRESHOLD)

// ── Date picker state ─────────────────────────────────────────────────────────

const showDatePicker = ref(false)
const calendarBtnRef = ref(null)
const datePickerRef  = ref(null)
const dateStart      = ref(null)   // Date | null — range start
const dateEnd        = ref(null)   // Date | null — range end
const dpYear         = ref(new Date().getFullYear())
const dpMonth        = ref(new Date().getMonth())   // 0-indexed

const weekdays = ['日', '一', '二', '三', '四', '五', '六']

const MONTH_NAMES = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月']
const dpMonthName = computed(() => MONTH_NAMES[dpMonth.value])

const dpDays = computed(() => {
  const year = dpYear.value
  const month = dpMonth.value
  const firstDay = new Date(year, month, 1)
  const lastDay  = new Date(year, month + 1, 0)
  const days = []

  // Fill days from previous month (leading blanks)
  const startDow = firstDay.getDay()  // 0 = Sunday
  for (let i = startDow - 1; i >= 0; i--) {
    const d = new Date(year, month, -i)   // day 0 = last day of prev month
    days.push({ date: d, d: d.getDate(), inMonth: false, key: `p${d.getTime()}` })
  }

  // Current month days
  for (let n = 1; n <= lastDay.getDate(); n++) {
    const d = new Date(year, month, n)
    days.push({ date: d, d: n, inMonth: true, key: `c${n}` })
  }

  // Fill trailing days from next month (to complete rows)
  let nd = 1
  while (days.length < 42) {
    const d = new Date(year, month + 1, nd++)
    days.push({ date: d, d: d.getDate(), inMonth: false, key: `n${d.getTime()}` })
  }

  return days
})

function prevMonth() {
  if (dpMonth.value === 0) { dpMonth.value = 11; dpYear.value-- }
  else dpMonth.value--
}
function nextMonth() {
  if (dpMonth.value === 11) { dpMonth.value = 0; dpYear.value++ }
  else dpMonth.value++
}
function prevYear() { dpYear.value-- }
function nextYear() { dpYear.value++ }

function selectDay(date) {
  // First click = start, second click = end; third click resets
  if (!dateStart.value || (dateStart.value && dateEnd.value)) {
    dateStart.value = date
    dateEnd.value   = null
  } else {
    if (date < dateStart.value) {
      dateEnd.value   = dateStart.value
      dateStart.value = date
    } else if (_isSameDay(date, dateStart.value)) {
      // Click same day = select single day range
      dateEnd.value = date
    } else {
      dateEnd.value = date
    }
  }
}

function _isSameDay(a, b) {
  return a.getFullYear() === b.getFullYear() &&
         a.getMonth()    === b.getMonth()    &&
         a.getDate()     === b.getDate()
}

function isStartDate(date) { return dateStart.value && _isSameDay(date, dateStart.value) }
function isEndDate(date)   { return dateEnd.value   && _isSameDay(date, dateEnd.value)   }
function isInRange(date) {
  if (!dateStart.value || !dateEnd.value) return false
  return date > dateStart.value && date < dateEnd.value
}
function isToday(date) { return _isSameDay(date, new Date()) }

function fmtDate(d) {
  if (!d) return ''
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function clearDateRange() {
  dateStart.value = null
  dateEnd.value   = null
}

function applyDateRange() {
  if (!dateStart.value) return
  const fmt = (d) => {
    const yy = d.getFullYear()
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const dd = String(d.getDate()).padStart(2, '0')
    return `${yy}-${mm}-${dd}`
  }
  const end = dateEnd.value || dateStart.value
  emit('search', {
    q:           searchQuery.value.trim() || null,
    date_ranges: activeRanges.value.length > 0 ? [...activeRanges.value] : null,
    date_from:   fmt(dateStart.value),
    date_to:     fmt(end),
  })
  showDatePicker.value = false
}

// ── Toggle date picker + click-outside handler ────────────────────────────────

function toggleDatePicker() {
  if (showDatePicker.value) {
    showDatePicker.value = false
    document.removeEventListener('mousedown', _onOutsideClick)
    return
  }
  showDatePicker.value = true
  nextTick(() => {
    document.addEventListener('mousedown', _onOutsideClick)
  })
}

function _onOutsideClick(e) {
  const picker = datePickerRef.value
  const btn    = calendarBtnRef.value
  if (!picker?.contains(e.target) && !btn?.contains(e.target)) {
    showDatePicker.value = false
    document.removeEventListener('mousedown', _onOutsideClick)
  }
}

// ── C32.5: Search ─────────────────────────────────────────────────────────────

const searchQuery   = ref('')
const activeRanges  = ref([])
const searchResults = ref([])
const isSearching   = ref(false)
const searchInputRef = ref(null)

const TIME_RANGES = [
  { value: 'today',     labelKey: 'chat_filter_today'     },
  { value: 'yesterday', labelKey: 'chat_filter_yesterday' },
  { value: '7days',     labelKey: 'chat_filter_7days'     },
  { value: '30days',    labelKey: 'chat_filter_30days'    },
  { value: 'month',     labelKey: 'chat_filter_month'     },
]

const isSearchMode = computed(() =>
  searchQuery.value.trim().length > 0 ||
  activeRanges.value.length > 0       ||
  dateStart.value !== null
)

const displayedSessions = computed(() =>
  isSearchMode.value ? searchResults.value : props.sessions
)

let _debounceTimer = null

function onSearchInput() {
  clearTimeout(_debounceTimer)
  _debounceTimer = setTimeout(() => triggerSearch(), 300)
}

function toggleRange(value) {
  const idx = activeRanges.value.indexOf(value)
  if (idx >= 0) activeRanges.value.splice(idx, 1)
  else          activeRanges.value.push(value)
  triggerSearch()
}

function triggerSearch() {
  emit('search', {
    q:           searchQuery.value.trim() || null,
    date_ranges: activeRanges.value.length > 0 ? [...activeRanges.value] : null,
    date_from:   null,
    date_to:     null,
  })
}

function clearSearch() {
  searchQuery.value   = ''
  activeRanges.value  = []
  searchResults.value = []
  isSearching.value   = false
  clearDateRange()
  clearTimeout(_debounceTimer)
  emit('search', null)
  searchInputRef.value?.focus()
}

function setSearchResults(items, loading = false) {
  searchResults.value = items
  isSearching.value   = loading
}

defineExpose({ setSearchResults, isSearchMode })

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(dateStr) {
  if (!dateStr) return ''
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}

// ── Cleanup ───────────────────────────────────────────────────────────────────

onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup',   stopResize)
  document.removeEventListener('mousedown', _onOutsideClick)
  clearTimeout(_debounceTimer)
})
</script>

<style scoped>
/* ── Outer wrapper — owns the width so the resize handle can sit at the edge ── */
.session-sidebar-wrap {
  position: relative;
  flex-shrink: 0;
  display: flex;
  align-items: stretch;
  transition: width 0.18s ease;
}
.session-sidebar-wrap.resizing {
  transition: none;   /* no lag while dragging */
  user-select: none;
}
.session-sidebar-wrap.collapsed {
  width: 28px !important;
}

/* ── Sidebar panel ─────────────────────────────────────────────────────────── */
.session-sidebar {
  flex: 1;
  min-width: 0;
  background: var(--surface-card, var(--surface));
  border-right: 1px solid var(--border-soft);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

/* ── Resize handle ─────────────────────────────────────────────────────────── */
.resize-handle {
  position: absolute;
  right: -2px;
  top: 0;
  bottom: 0;
  width: 5px;
  cursor: col-resize;
  z-index: 10;
  background: transparent;
  transition: background 0.15s;
}
.resize-handle:hover,
.session-sidebar-wrap.resizing .resize-handle {
  background: var(--accent, #3b82f6);
  opacity: 0.5;
}

/* ── Toggle button ─────────────────────────────────────────────────────────── */
.sidebar-toggle {
  position: absolute;
  top: 8px;
  right: 4px;
  width: 20px;
  height: 20px;
  border: none;
  background: none;
  cursor: pointer;
  color: var(--muted);
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  z-index: 1;
  padding: 0;
}
.sidebar-toggle:hover {
  background: var(--border-soft);
  color: var(--text);
}

/* ── Header ────────────────────────────────────────────────────────────────── */
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 30px 8px 10px;
  border-bottom: 1px solid var(--border-soft);
  flex-shrink: 0;
}
.sidebar-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sidebar-header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.btn-new {
  width: 20px;
  height: 20px;
  border: 1px solid var(--border-soft);
  background: none;
  border-radius: 4px;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 16px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}
.btn-new:hover {
  background: var(--status-info-bg);
  color: var(--accent);
  border-color: var(--accent);
}

/* ── Calendar button ───────────────────────────────────────────────────────── */
.btn-calendar {
  width: 20px;
  height: 20px;
  border: 1px solid var(--border-soft);
  background: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: background 0.12s, border-color 0.12s;
}
.btn-calendar:hover {
  background: var(--status-info-bg);
  border-color: var(--accent);
}
.btn-calendar.active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

/* ── Date-picker popup ─────────────────────────────────────────────────────── */
.date-picker-popup {
  position: absolute;
  top: 37px;         /* below header */
  left: 0;
  right: 0;
  z-index: 100;
  background: var(--surface-card, var(--surface));
  border: 1px solid var(--border-soft);
  border-top: none;
  box-shadow: 0 4px 12px rgba(0,0,0,0.12);
  padding: 8px;
  border-radius: 0 0 8px 8px;
}
.dp-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.dp-nav-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  flex: 1;
  text-align: center;
}
.dp-nav-btn {
  border: none;
  background: none;
  cursor: pointer;
  color: var(--muted);
  font-size: 13px;
  padding: 2px 4px;
  border-radius: 4px;
  line-height: 1;
}
.dp-nav-btn:hover {
  background: var(--surface2);
  color: var(--text);
}
.dp-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  margin-bottom: 2px;
}
.dp-weekdays span {
  text-align: center;
  font-size: 9px;
  color: var(--muted);
  padding: 2px 0;
  font-weight: 600;
}
.dp-days {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
}
.dp-day {
  aspect-ratio: 1;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 10px;
  border-radius: 4px;
  color: var(--text);
  transition: background 0.1s, color 0.1s;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.dp-day:hover {
  background: var(--surface2);
}
.dp-other {
  color: var(--muted);
  opacity: 0.5;
}
.dp-today {
  font-weight: 700;
  color: var(--accent);
}
.dp-start,
.dp-end {
  background: var(--accent) !important;
  color: #fff !important;
  border-radius: 50%;
}
.dp-inrange {
  background: var(--status-info-bg, #dbeafe);
  border-radius: 0;
}
/* ── Footer ── */
.dp-footer {
  margin-top: 6px;
  border-top: 1px solid var(--border-soft);
  padding-top: 6px;
}
.dp-range-label {
  font-size: 10px;
  color: var(--muted);
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  margin-bottom: 5px;
  min-height: 14px;
}
.dp-range-part {
  color: var(--text);
}
.dp-range-sep {
  color: var(--muted);
  padding: 0 2px;
}
.dp-hint {
  font-style: italic;
}
.dp-actions {
  display: flex;
  gap: 4px;
  justify-content: flex-end;
}
.dp-btn {
  padding: 3px 8px;
  font-size: 10px;
  border-radius: 5px;
  border: 1px solid var(--border-soft);
  cursor: pointer;
  transition: background 0.12s;
}
.dp-clear {
  background: none;
  color: var(--muted);
}
.dp-clear:hover { background: var(--surface2); color: var(--text); }
.dp-apply {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.dp-apply:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.dp-apply:not(:disabled):hover {
  filter: brightness(1.1);
}

/* ── C32.5: Search section ─────────────────────────────────────────────────── */
.sidebar-search {
  padding: 6px 8px 4px;
  border-bottom: 1px solid var(--border-soft);
  flex-shrink: 0;
}
.search-input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}
.search-input {
  width: 100%;
  padding: 4px 22px 4px 8px;
  font-size: 11px;
  background: var(--surface2);
  border: 1px solid var(--border-soft);
  border-radius: 6px;
  color: var(--text);
  outline: none;
  transition: border-color 0.15s;
}
.search-input:focus { border-color: var(--accent); }
.search-input::placeholder { color: var(--muted); }
.search-clear-btn {
  position: absolute;
  right: 4px;
  background: none;
  border: none;
  color: var(--muted);
  font-size: 14px;
  cursor: pointer;
  padding: 0 2px;
  line-height: 1;
}
.search-clear-btn:hover { color: var(--text); }
.filter-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  margin-top: 5px;
}
.filter-chip {
  padding: 2px 6px;
  font-size: 10px;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: none;
  color: var(--muted);
  cursor: pointer;
  transition: background 0.12s, color 0.12s, border-color 0.12s;
  white-space: nowrap;
}
.filter-chip:hover { background: var(--surface2); color: var(--text); }
.filter-chip.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.filter-chip--date { font-size: 9px; }

/* ── Session list ──────────────────────────────────────────────────────────── */
.session-list {
  flex: 1;
  overflow-y: auto;
  scrollbar-width: thin;
}
.session-empty {
  font-size: 12px;
  color: var(--muted);
  text-align: center;
  padding: 16px 8px;
}
.session-item {
  position: relative;
  padding: 8px 28px 8px 10px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-soft);
  transition: background 0.15s;
}
.session-item:hover { background: var(--surface); }
.session-item.active {
  background: var(--status-info-bg);
  border-left: 2px solid var(--accent);
}
.session-preview {
  font-size: 12px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.session-snippet {
  font-size: 10px;
  color: var(--accent);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 1px;
}
.session-meta {
  font-size: 10px;
  color: var(--muted);
  margin-top: 2px;
}
.session-delete {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  border: none;
  background: none;
  color: var(--muted);
  font-size: 14px;
  cursor: pointer;
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  opacity: 0;
  transition: opacity 0.15s;
}
.session-item:hover .session-delete { opacity: 1; }
.session-delete:hover {
  background: var(--status-down-bg, #fee2e2);
  color: var(--danger);
}

@media (max-width: 640px) {
  .session-sidebar-wrap { display: none; }
}
</style>
